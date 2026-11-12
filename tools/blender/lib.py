"""Small procedural-modelling kit for headless Blender (bpy + bmesh), used by tools/blender/build.py.

Conventions: 1 Blender unit = 1 mm, phone-local axes (+x right / +y up looking at the screen,
+z towards the screen). Every mesh belongs to a part (an empty named after the part id).
Plain colours are baked into a vertex-colour attribute and share three material classes
(v.metal / v.matte / v.glass) so the viewer needs few draw calls; anything that needs its own
shader or texture gets a named "special" material that the web side maps to a real material.
"""
from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from mathutils.geometry import tessellate_polygon


# ---------------------------------------------------------------- 2D helpers
def srgb_to_linear(hex_color: str):
    c = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def area2(p):
    p = np.asarray(p, float)
    return float(np.dot(p[:, 0], np.roll(p[:, 1], -1)) - np.dot(p[:, 1], np.roll(p[:, 0], -1)))


def ccw(p):
    p = np.asarray(p, float)
    return p if area2(p) > 0 else p[::-1]


def round_poly(pts, r, seg=5):
    """Fillet every corner of a polygon with radius r (clamped to the adjacent edge lengths)."""
    p = ccw(pts)
    if r <= 0:
        return p
    n = len(p)
    out = []
    for i in range(n):
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        u, v = a - b, c - b
        lu, lv = np.linalg.norm(u), np.linalg.norm(v)
        u, v = u / lu, v / lv
        cosang = float(np.clip(u @ v, -1, 1))
        ang = math.acos(cosang)
        if ang > math.pi - 0.05 or ang < 0.05:
            out.append(b)
            continue
        t = min(r / math.tan(ang / 2), lu * 0.48, lv * 0.48)
        rr = t * math.tan(ang / 2)
        p1, p2 = b + u * t, b + v * t
        bis = (u + v) / np.linalg.norm(u + v)
        centre = b + bis * (rr / math.sin(ang / 2))
        a1 = math.atan2(*(p1 - centre)[::-1])
        a2 = math.atan2(*(p2 - centre)[::-1])
        d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        k = max(2, int(seg * abs(d) / (math.pi / 2) + 0.5))
        for s in range(k + 1):
            th = a1 + d * s / k
            out.append(centre + rr * np.array([math.cos(th), math.sin(th)]))
    return np.array(out)


def rect(x0, y0, x1, y1, r=0.0, seg=5):
    return round_poly([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], r, seg)


def circle(cx, cy, r, seg=48):
    th = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    return np.c_[cx + r * np.cos(th), cy + r * np.sin(th)]


def stadium(cx, cy, length, width, seg=10, vertical=True):
    """Pill shape; `length` along y when vertical."""
    r = width / 2
    h = max(length / 2 - r, 0)
    th = np.linspace(0, math.pi, seg + 1)
    top = np.c_[r * np.cos(th), h + r * np.sin(th)]
    bot = np.c_[-r * np.cos(th), -h - r * np.sin(th)]
    p = np.vstack([top, bot])
    if not vertical:
        p = np.c_[p[:, 1], -p[:, 0]]
    return ccw(p + [cx, cy])


def inset(pts, d):
    """Offset a CCW polygon inward by d using vertex bisectors (fine for d << feature size)."""
    p = ccw(pts)
    e1 = p - np.roll(p, 1, axis=0)
    e2 = np.roll(p, -1, axis=0) - p
    n1 = np.c_[-e1[:, 1], e1[:, 0]]
    n2 = np.c_[-e2[:, 1], e2[:, 0]]
    n1 /= np.maximum(np.linalg.norm(n1, axis=1), 1e-9)[:, None]
    n2 /= np.maximum(np.linalg.norm(n2, axis=1), 1e-9)[:, None]
    b = n1 + n2
    ln = np.maximum(np.linalg.norm(b, axis=1), 1e-9)
    b /= ln[:, None]
    cosh = np.clip(ln / 2, 0.35, 1.0)  # limit the miter length on sharp corners
    return p + b * (d / cosh)[:, None]


class Lcg:
    """Deterministic pseudo-random numbers (same generator as the old three.js smdField)."""

    def __init__(self, seed=1):
        self.s = seed

    def __call__(self):
        self.s = (self.s * 16807) % 2147483647
        return self.s / 2147483647


# ---------------------------------------------------------------- builder
class Builder:
    def __init__(self, colors: dict, classes: dict, specials: set):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.colors, self.classes, self.specials = colors, classes, specials
        self.mats: dict = {}
        self.part = None
        self.parts: dict = {}
        self.count = 0

    # materials -------------------------------------------------
    def _mat(self, name):
        if name not in self.mats:
            m = bpy.data.materials.new(name)
            # Material names are the contract with the web side, which builds the real materials.
            # Give each a distinct base colour so optimisers that merge identical materials
            # (gltf-transform dedup) can never fold two keys into one.
            k = len(self.mats) + 1
            m.diffuse_color = (((k * 37) % 101) / 100, ((k * 59) % 103) / 102, ((k * 83) % 107) / 106, 1.0)
            self.mats[name] = m
        return self.mats[name]

    def resolve(self, key):
        """material key -> (glTF material name, linear rgb or None)"""
        if key in self.specials or key.startswith("chip.") or key.startswith("overlay."):
            return key, None
        return "v." + self.classes[key], srgb_to_linear(self.colors[key])

    # parts -----------------------------------------------------
    def begin(self, part_id):
        e = bpy.data.objects.new(part_id, None)
        bpy.context.scene.collection.objects.link(e)
        e["partId"] = part_id
        self.part = e
        self.parts[part_id] = e
        return e

    def mesh(self, name, verts, faces, key, uvs=None, extra=None, overlay=False, sharp=40.0, part=None):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(f) for f in faces])
        me.validate()
        mat_name, rgb = self.resolve(key)
        me.materials.append(self._mat(mat_name))
        if rgb is not None:  # plain colour classes carry their colour per vertex; specials do not need it
            col = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
            col.data.foreach_set("color", np.tile(rgb + [1.0], len(me.loops)).astype(np.float32))
        if uvs is not None:  # only textured (special) materials need UVs; they must stay inside [0, 1]
            uvl = me.uv_layers.new(name="UVMap")
            co = np.zeros(len(me.vertices) * 3, np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            li = np.zeros(len(me.loops), np.int32)
            me.loops.foreach_get("vertex_index", li)
            x0, y0, x1, y1 = uvs
            uv = np.c_[(co[li][:, 0] - x0) / (x1 - x0), (co[li][:, 1] - y0) / (y1 - y0)]
            uvl.data.foreach_set("uv", np.clip(uv, 0, 1).astype(np.float32).ravel())
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(sharp))
        self.count += 1
        ob = bpy.data.objects.new(f"{(part or self.part).name}/{name}.{self.count}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = part or self.part
        ob["mat"] = mat_name
        if extra:
            ob["extra"] = extra
        if overlay:
            ob["overlay"] = True
        return ob

    # primitives ------------------------------------------------
    def prism(self, name, outline, z0, z1, key, holes=(), bevel=0.0, bevel_bottom=None, uvs=None, cap_top=True, cap_bottom=True, **kw):
        """Extrude a 2D outline (with optional holes) from z0 to z1; `bevel` chamfers the top rim,
        `bevel_bottom` the bottom rim (defaults to the same value)."""
        if z1 < z0:
            z0, z1 = z1, z0
        bb = bevel if bevel_bottom is None else bevel_bottom
        bevel = min(bevel, (z1 - z0) * 0.45)
        bb = min(bb, (z1 - z0) * 0.45)
        loops = [ccw(outline)] + [ccw(h)[::-1] for h in holes]  # holes clockwise
        verts, faces = [], []

        def ring(pts, z):
            i0 = len(verts)
            verts.extend([(x, y, z) for x, y in pts])
            return list(range(i0, i0 + len(pts)))

        def bridge(a, b, flip):
            n = len(a)
            for i in range(n):
                j = (i + 1) % n
                faces.append((a[i], a[j], b[j], b[i]) if not flip else (a[i], b[i], b[j], a[j]))

        def cap(rings, pts_loops, up):
            flat = [[(float(x), float(y), 0.0) for x, y in l] for l in pts_loops]
            idx = [i for r in rings for i in r]
            for t in tessellate_polygon(flat):
                tri = (idx[t[0]], idx[t[1]], idx[t[2]])
                a, b, c = (np.array(verts[i][:2]) for i in tri)
                nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                faces.append(tri if (nz > 0) == up else tri[::-1])

        bot_rings, top_rings, bot_pts, top_pts = [], [], [], []
        for li, lp in enumerate(loops):
            hole = li > 0
            sgn = -1 if hole else 1  # inset direction: holes grow, outline shrinks
            stack = []
            if bb > 0:
                pb = inset(lp if not hole else lp[::-1], sgn * bb)
                pb = pb if not hole else pb[::-1]
                stack.append((pb, z0))
                stack.append((lp, z0 + bb))
            else:
                stack.append((lp, z0))
            if bevel > 0:
                pt = inset(lp if not hole else lp[::-1], sgn * bevel)
                pt = pt if not hole else pt[::-1]
                stack.append((lp, z1 - bevel))
                stack.append((pt, z1))
            else:
                stack.append((lp, z1))
            rings = [ring(p, z) for p, z in stack]
            for a, b in zip(rings[:-1], rings[1:]):
                bridge(a, b, False)
            bot_rings.append(rings[0]), top_rings.append(rings[-1])
            bot_pts.append(stack[0][0]), top_pts.append(stack[-1][0])
        if cap_top:
            cap(top_rings, top_pts, True)
        if cap_bottom:
            cap(bot_rings, bot_pts, False)
        return self.mesh(name, verts, faces, key, uvs=uvs, **kw)

    def box(self, name, x0, x1, y0, y1, z0, z1, key, r=0.0, bevel=0.0, **kw):
        return self.prism(name, rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), r), z0, z1, key, bevel=bevel, **kw)

    def cyl(self, name, x, y, r, z0, z1, key, seg=40, bevel=0.0, **kw):
        return self.prism(name, circle(x, y, r, seg), z0, z1, key, bevel=bevel, **kw)

    def ring(self, name, x, y, ro, ri, z0, z1, key, seg=48, bevel=0.0, **kw):
        return self.prism(name, circle(x, y, ro, seg), z0, z1, key, holes=[circle(x, y, ri, seg)], bevel=bevel, **kw)

    def loft(self, name, rings, key, cap_first=None, cap_last=None, closed=False, **kw):
        """Skin a sequence of (Nx2 outline, z) rings with equal vertex counts.
        cap_first / cap_last: 'up' or 'down' facing n-gon caps."""
        verts, faces = [], []
        idx = []
        for pts, z in rings:
            i0 = len(verts)
            verts.extend([(x, y, z) for x, y in pts])
            idx.append(list(range(i0, i0 + len(pts))))
        pairs = list(zip(idx[:-1], idx[1:])) + ([(idx[-1], idx[0])] if closed else [])
        for a, b in pairs:
            n = len(a)
            for i in range(n):
                j = (i + 1) % n
                faces.append((a[i], a[j], b[j], b[i]))

        def cap(ring_idx, pts, up):
            flat = [[(float(x), float(y), 0.0) for x, y in pts]]
            for t in tessellate_polygon(flat):
                tri = (ring_idx[t[0]], ring_idx[t[1]], ring_idx[t[2]])
                a, b, c = (np.array(verts[i][:2]) for i in tri)
                nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                faces.append(tri if (nz > 0) == up else tri[::-1])

        if cap_first:
            cap(idx[0], rings[0][0], cap_first == "up")
        if cap_last:
            cap(idx[-1], rings[-1][0], cap_last == "up")
        ob = self.mesh(name, verts, faces, key, **kw)
        # make normals consistent (ring order decides the winding; let Blender fix it)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.set_sharp_from_angle(angle=math.radians(kw.get("sharp", 40.0)))
        return ob

    def side_pill(self, name, side, y, length, width, z, x_in, x_out, key, seg=8, **kw):
        """A pill-shaped button on the left (-1) or right (+1) edge, extruded along x."""
        prof = stadium(0, 0, length, width, seg)  # (u along phone y, v along z) -> stadium is vertical in (v,u)
        # stadium() returns points with the long axis on its y; map: u = y_long -> phone y, x_short -> phone z
        a, b = sorted((x_in, x_out))
        verts, faces = [], []
        n = len(prof)
        for xx in (a, b):
            verts.extend([(xx, y + q[1], z + q[0]) for q in prof])
        for i in range(n):
            j = (i + 1) % n
            faces.append((i, j, n + j, n + i))
        faces.append(tuple(range(n - 1, -1, -1)))
        faces.append(tuple(range(n, 2 * n)))
        ob = self.mesh(name, verts, faces, key, **kw)
        self.fix_normals(ob)
        return ob

    def end_pill(self, name, x, z, width, height, y_in, y_out, key, seg=8, **kw):
        """A pill-shaped feature on the bottom/top edge (long axis along x), extruded along y."""
        prof = stadium(0, 0, width, height, seg, vertical=False)
        a, b = sorted((y_in, y_out))
        verts, faces = [], []
        n = len(prof)
        for yy in (a, b):
            verts.extend([(x + q[0], yy, z + q[1]) for q in prof])
        for i in range(n):
            j = (i + 1) % n
            faces.append((i, j, n + j, n + i))
        faces.append(tuple(range(n - 1, -1, -1)))
        faces.append(tuple(range(n, 2 * n)))
        ob = self.mesh(name, verts, faces, key, **kw)
        self.fix_normals(ob)
        return ob

    def smd_field(self, name, x0, x1, y0, y1, z, count, key, avoid=(), seed=1, down=False, **kw):
        """Scatter small SMD-like boxes on a board (one merged mesh)."""
        rnd = Lcg(seed)
        verts, faces = [], []
        i = guard = 0
        while i < count and guard < count * 20:
            guard += 1
            x, y = x0 + rnd() * (x1 - x0), y0 + rnd() * (y1 - y0)
            if any(a0 - 0.6 < x < a1 + 0.6 and b0 - 0.6 < y < b1 + 0.6 for a0, a1, b0, b1 in avoid):
                continue
            w, h, d = 0.5 + rnd() * 0.7, 0.3 + rnd() * 0.35, 0.25 + rnd() * 0.25
            if rnd() < 0.5:
                w, h = h, w
            za, zb = (z - d, z) if down else (z, z + d)
            b0 = len(verts)
            for zz in (za, zb):
                verts.extend([(x - w / 2, y - h / 2, zz), (x + w / 2, y - h / 2, zz), (x + w / 2, y + h / 2, zz), (x - w / 2, y + h / 2, zz)])
            q = lambda *f: faces.append(tuple(b0 + k for k in f))
            q(0, 3, 2, 1), q(4, 5, 6, 7), q(0, 1, 5, 4), q(1, 2, 6, 5), q(2, 3, 7, 6), q(3, 0, 4, 7)
            i += 1
        return self.mesh(name, verts, faces, key, sharp=30, **kw)

    # mesh operations -------------------------------------------
    def fix_normals(self, ob):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.set_sharp_from_angle(angle=math.radians(40))

    def cut(self, target, cutter, keep_cutter=False):
        """Boolean difference target - cutter (exact solver)."""
        mod = target.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        bpy.context.view_layer.objects.active = target
        with bpy.context.temp_override(object=target, active_object=target, selected_objects=[target]):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        if not keep_cutter:
            bpy.data.objects.remove(cutter, do_unlink=True)
        target.data.set_sharp_from_angle(angle=math.radians(40))
        return target

    def recolor(self, ob, key, predicate):
        """Repaint the faces for which predicate(centre xyz, normal xyz) is true (same material class)."""
        _, rgb = self.resolve(key)
        me = ob.data
        col = me.color_attributes["Col"]
        data = np.zeros(len(me.loops) * 4, np.float32)
        col.data.foreach_get("color", data)
        data = data.reshape(-1, 4)
        for poly in me.polygons:
            if predicate(poly.center, poly.normal):
                data[poly.loop_start : poly.loop_start + poly.loop_total] = rgb + [1.0]
        col.data.foreach_set("color", data.ravel())

    def tag(self, ob, extra=None, overlay=False):
        if extra:
            ob["extra"] = extra
        if overlay:
            ob["overlay"] = True
        return ob

    # export ----------------------------------------------------
    def stats(self):
        out = {}
        for pid, e in self.parts.items():
            tris = 0
            for c in e.children:
                if c.type == "MESH":
                    c.data.calc_loop_triangles()
                    tris += len(c.data.loop_triangles)
            out[pid] = {"objects": len([c for c in e.children if c.type == "MESH"]), "triangles": tris}
        return out

    def merge(self):
        """Join each part's meshes that share (material, extra, overlay): one draw call each."""
        for pid, e in self.parts.items():
            groups: dict = {}
            for c in list(e.children):
                if c.type != "MESH":
                    continue
                groups.setdefault((c["mat"], c.get("extra", ""), bool(c.get("overlay", False))), []).append(c)
            for (mat, extra, overlay), obs in groups.items():
                keep = obs[0]
                if len(obs) > 1:
                    with bpy.context.temp_override(active_object=keep, object=keep, selected_objects=obs, selected_editable_objects=obs):
                        bpy.ops.object.join()
                keep.name = f"{pid}/{mat}" + (f"/{extra}" if extra else "") + ("/overlay" if overlay else "")
                keep.data.name = keep.name

    def export(self, path):
        bpy.ops.export_scene.gltf(
            filepath=str(path),
            export_format="GLB",
            export_yup=False,  # keep phone-local axes exactly as authored
            export_apply=True,
            export_extras=True,
            export_normals=True,
            export_tangents=False,
            export_vertex_color="ACTIVE",
            export_all_vertex_colors=False,
            export_materials="EXPORT",
            export_animations=False,
            export_cameras=False,
            export_lights=False,
        )
