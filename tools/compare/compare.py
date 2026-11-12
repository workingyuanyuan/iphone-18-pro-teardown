# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26", "shapely>=2.0", "trimesh>=4.4", "opencv-python-headless>=4.9", "networkx>=3", "rtree>=1.2", "scipy>=1.11"]
# ///
"""Score a phone model against the measurements and draw overlay images on the reference photos.

    uv run tools/compare/compare.py --model <model.dev.glb | legacy-parts.json> --label after \\
        --measurements tools/measure/models/iphone-18-pro/measurements.json \\
        --config tools/compare/iphone-18-pro.json --rectified-dir refs/out --out refs/out/compare/after

What is measured (all in mm, model geometry projected straight down the z axis, no per-part
re-alignment before scoring):

  exterior   Named features of the model (overall size, silhouette, edge profile, lens rings,
             flash, plateau, back glass, buttons, ports) against Apple's dimensioned values.
             Gate: <= 0.5 mm.
  internal   Each part's XY silhouette against the outline traced on a registered image.
             contour = max of the two directional 95th-percentile nearest-boundary distances
             (model->reference, reference->model); also Hausdorff, centroid offset and the worst
             bounding-box edge. Gate: contour + reference uncertainty <= 1 mm.
  edge fit   Reference-free check: the fraction of the model's contour that lies within 0.5 mm of
             a strong image edge on each orthoimage that shows the part (includes images of a
             different unit that were NOT used to build the model).

Overlays: the model silhouettes are drawn semi-transparent on every orthoimage, and warped back
through the image's own px<->mm mapping onto the original photo/frame (same viewpoint and lens as
the reference; planar approximation at the registration plane).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import struct
from pathlib import Path

import cv2
import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union


# ------------------------------------------------------------------ model loading
class Model:
    """parts[id] -> list of {name, tris (Nx3x3), extra, overlay}"""

    def __init__(self, path: Path):
        self.parts: dict[str, list[dict]] = {}
        self.named = path.suffix == ".glb"
        if self.named:
            self._load_glb(path)
        else:
            for pid, meshes in json.loads(path.read_text()).items():
                self.parts[pid] = [
                    {"name": m["name"], "tris": np.array(m["tris"], float).reshape(-1, 3, 3), "extra": m.get("extra"), "overlay": bool(m.get("overlay"))} for m in meshes
                ]

    def _load_glb(self, path: Path):
        raw = path.read_bytes()
        jlen = struct.unpack_from("<I", raw, 12)[0]
        gltf = json.loads(raw[20 : 20 + jlen])
        extras = {n.get("name"): n.get("extras", {}) for n in gltf["nodes"]}
        scene = trimesh.load(path, process=False)
        for node in scene.graph.nodes_geometry:
            T, gname = scene.graph[node]
            g = scene.geometry[gname]
            v = trimesh.transformations.transform_points(g.vertices, T)
            name = node
            if "/" not in name:
                continue
            pid, sub = name.split("/", 1)
            ex = extras.get(name, {})
            self.parts.setdefault(pid, []).append({"name": sub.rsplit(".", 1)[0], "tris": v[g.faces], "extra": ex.get("extra"), "overlay": bool(ex.get("overlay"))})

    def meshes(self, pid, patterns=None, include_extra=False):
        out = []
        for m in self.parts.get(pid, []):
            if m["overlay"] or (m["extra"] == "show" and not include_extra):
                continue
            if patterns and self.named and not any(fnmatch.fnmatch(m["name"], p) for p in patterns):
                continue
            out.append(m)
        return out

    def tris(self, pid, patterns=None):
        ms = self.meshes(pid, patterns)
        return np.concatenate([m["tris"] for m in ms]) if ms else np.zeros((0, 3, 3))


def silhouette(tris, axis=2):
    """Union of the triangles projected along an axis -> shapely geometry."""
    keep = [i for i in range(3) if i != axis]
    p = tris[:, :, keep]
    a = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0]))
    polys = [Polygon(t) for t in p[a > 1e-7]]
    if not polys:
        return Polygon()
    return unary_union(polys).buffer(0)


def main_body(geom, open_mm=0.6):
    """Largest component after a small morphological opening (drops flex tails, screws)."""
    g = geom.buffer(-open_mm).buffer(open_mm)
    if g.is_empty:
        g = geom
    if isinstance(g, MultiPolygon):
        big = max(q.area for q in g.geoms)
        g = unary_union([q for q in g.geoms if q.area >= 0.15 * big])
    return g


def boundary_points(geom, step=0.1):
    pts = []
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        for ring in [poly.exterior, *poly.interiors]:  # holes are part of the outline
            n = max(int(ring.length / step), 8)
            pts += [ring.interpolate(i / n, normalized=True).coords[0] for i in range(n)]
    return np.array(pts)


def outer(geom):
    """Outer outline only (fills holes): for silhouettes whose reference has no holes."""
    if isinstance(geom, MultiPolygon):
        return unary_union([Polygon(q.exterior) for q in geom.geoms])
    return Polygon(geom.exterior) if not geom.is_empty else geom


def contour_metrics(model_geom, ref_geom):
    if model_geom.is_empty:
        return None
    mp, rp = boundary_points(model_geom), boundary_points(ref_geom)
    mb, rb = model_geom.boundary, ref_geom.boundary
    d_mr = np.array([rb.distance(Point(p)) for p in mp])
    d_rm = np.array([mb.distance(Point(p)) for p in rp])
    mx0, my0, mx1, my1 = model_geom.bounds
    rx0, ry0, rx1, ry1 = ref_geom.bounds
    return {
        "contour_p95": round(float(max(np.percentile(d_mr, 95), np.percentile(d_rm, 95))), 2),
        "mean": round(float((d_mr.mean() + d_rm.mean()) / 2), 2),
        "hausdorff": round(float(max(d_mr.max(), d_rm.max())), 2),
        "centroid_offset": round(float(model_geom.centroid.distance(ref_geom.centroid)), 2),
        "bbox_edge_max": round(float(max(abs(mx0 - rx0), abs(my0 - ry0), abs(mx1 - rx1), abs(my1 - ry1))), 2),
        "model_size": [round(mx1 - mx0, 2), round(my1 - my0, 2)],
        "ref_size": [round(rx1 - rx0, 2), round(ry1 - ry0, 2)],
    }


def circle_fit(p):
    A = np.c_[2 * p, np.ones(len(p))]
    sol, *_ = np.linalg.lstsq(A, (p**2).sum(1), rcond=None)
    c = sol[:2]
    return float(c[0]), float(c[1]), float(np.sqrt(sol[2] + c @ c))


# ------------------------------------------------------------------ orthoimages
class Ortho:
    def __init__(self, d: Path, name: str):
        self.name, self.dir = name, d
        self.meta = json.loads((d / f"{name}.rectify.json").read_text())
        o = self.meta["ortho"]
        self.ppm = o["px_per_mm"]
        self.x0, self.y0, self.x1, self.y1 = o["extent_mm"]
        self.img = cv2.imread(str(d / o["file"]))
        g = cv2.GaussianBlur(cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY), (0, 0), 1.2)
        mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
        self.edge_dist = cv2.distanceTransform(1 - (mag > np.percentile(mag, 88)).astype(np.uint8), cv2.DIST_L2, 3)

    def px(self, pts):
        p = np.asarray(pts, float)
        return np.c_[(p[:, 0] - self.x0) * self.ppm, (self.y1 - p[:, 1]) * self.ppm]

    def edge_fit(self, geom, tol=0.5):
        p = boundary_points(geom, 0.15)
        if len(p) == 0:
            return None
        q = self.px(p)
        h, w = self.edge_dist.shape
        inside = (q[:, 0] >= 0) & (q[:, 0] < w) & (q[:, 1] >= 0) & (q[:, 1] < h)
        if inside.mean() < 0.9:
            return None
        q = q[inside].round().astype(int)
        return round(float(np.mean(self.edge_dist[q[:, 1], q[:, 0]] <= tol * self.ppm)), 2)


def draw_geom(layer, o: Ortho, geom, color, fill=True):
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        ext = o.px(np.array(poly.exterior.coords)).astype(np.int32)
        if fill:
            cv2.fillPoly(layer, [ext], color)
        else:
            cv2.polylines(layer, [ext], True, color, 2, cv2.LINE_AA)


PALETTE = [(60, 180, 255), (80, 220, 120), (255, 160, 60), (220, 100, 255), (60, 220, 220), (255, 110, 150), (160, 200, 60), (120, 140, 255), (255, 210, 90), (100, 255, 200)]


# ------------------------------------------------------------------ exterior features
def exterior(model: Model, m: dict, cfg: dict, legacy_feats: dict | None):
    rows = []

    def row(name, model_v, ref_v, src, kind="value"):
        if model_v is None:
            rows.append({"feature": name, "model": None, "reference": ref_v, "error": None, "source": src})
            return
        if kind == "point":
            err = float(np.hypot(model_v[0] - ref_v[0], model_v[1] - ref_v[1]))
            model_v = [round(float(v), 3) for v in model_v]
        else:
            err = abs(float(model_v) - float(ref_v))
            model_v = round(float(model_v), 3)
        rows.append({"feature": name, "model": model_v, "reference": ref_v, "error": round(err, 3), "source": src})

    W, H, T = (m["body"][k]["value"] for k in ("width", "height", "thickness"))
    rear, sides, D = m["rear"], m["sides"], m["derived"]
    A1 = "Apple p.2"
    shell = model.tris("frame", cfg["frame"]["shell"])
    if len(shell):
        lo, hi = shell.reshape(-1, 3).min(0), shell.reshape(-1, 3).max(0)
        row("機身寬", hi[0] - lo[0], W, A1)
        row("機身高", hi[1] - lo[1], H, A1)
        zs = shell.reshape(-1, 3)
        if model.named:
            glass_top = model.tris("display", cfg["display"]["glass"]).reshape(-1, 3)[:, 2].max()
            back = shell.reshape(-1, 3)[:, 2]
            back = back[back > -T / 2 - 0.5].min()  # the shell's back face, not the camera plateau
            row("機身厚（背板到螢幕玻璃頂）", glass_top - back, T, A1)
        else:
            row("機身厚（背板到螢幕玻璃頂）", model.tris("display").reshape(-1, 3)[:, 2].max() - (-legacy_feats["D"] / 2), T, A1)
        sil = outer(main_body(silhouette(shell), 0.2))
        cm = contour_metrics(sil, Polygon(D["bodyOutline"]))
        rows.append({"feature": "機身正面輪廓（含四角）", "model": cm["model_size"], "reference": cm["ref_size"], "error": cm["contour_p95"], "hausdorff": cm["hausdorff"], "source": "Apple p.2 DETAIL A"})
        # edge profile: section at y = 0, right-hand side
        # the profile's last front point lies on the cover glass, so section frame shell + glass together
        prof_tris = np.concatenate([shell, model.tris("display", cfg["display"]["glass"])]) if model.named else np.concatenate([shell, model.tris("display")])
        mesh = trimesh.Trimesh(prof_tris.reshape(-1, 3), np.arange(len(prof_tris) * 3).reshape(-1, 3), process=False)
        sec = mesh.section(plane_origin=[0, 0.01, 0], plane_normal=[0, 1, 0])
        if sec is not None:
            from shapely.geometry import LineString, MultiLineString

            lines = MultiLineString([LineString(np.asarray(sec.vertices)[e.points][:, [0, 2]]) for e in sec.entities if len(e.points) > 1])
            prof = m["body"]["edgeProfile"]["value"]
            errs = [float(lines.distance(Point(W / 2 - ins, z))) for ins, z in prof["front"] + prof["back"]]
            if errs:
                rows.append({"feature": "側邊截面（10 個標註點到模型表面）", "model": f"max {max(errs):.2f}", "reference": "DETAIL B", "error": round(max(errs), 3), "source": "Apple p.2 DETAIL B"})
    # lens rings etc.
    names = {"ultraWide": "超廣角", "main": "主鏡頭", "tele": "長焦"}
    for k, zh in names.items():
        ref = rear["lenses"][k]["value"]
        if model.named:
            t = model.tris("frame", [f"lensRing.{k}"])
            if len(t):
                b = boundary_points(outer(silhouette(t)))
                cx, cy, r = circle_fit(b)
                row(f"{zh}鏡頭中心", (cx, cy), ref, "Apple p.2 DETAIL D", "point")
                row(f"{zh}鏡環外徑", 2 * r, rear["lensRingDiameter"]["value"], "Apple p.2 DETAIL D")
        else:
            lf = legacy_feats["lenses"][k]
            row(f"{zh}鏡頭中心", lf["c"], ref, "Apple p.2 DETAIL D", "point")
            row(f"{zh}鏡環外徑", lf["d"], rear["lensRingDiameter"]["value"], "Apple p.2 DETAIL D")
    for key, obj, zh in (("flash", "flashLens", "閃光燈"), ("rearSensor", "sensorWindow", "LiDAR 視窗"), ("rearMic", "rearMic", "後置麥克風")):
        ref = rear[key]["value"]
        if model.named:
            t = model.tris("frame", [obj])
            if len(t):
                cx, cy, r = circle_fit(boundary_points(outer(silhouette(t))))
                row(f"{zh}中心", (cx, cy), ref["centre"], "Apple p.2 DETAIL D", "point")
                row(f"{zh}直徑", 2 * r, ref["diameter"], "Apple p.2 DETAIL D")
        else:
            lf = legacy_feats[key]
            row(f"{zh}中心", lf["c"], ref["centre"], "Apple p.2 DETAIL D", "point")
            row(f"{zh}直徑", lf["d"], ref["diameter"], "Apple p.2 DETAIL D")
    # plateau: height, island outline; lens glass height
    zb = -T / 2
    if model.named:
        pl = model.tris("frame", ["plateau"])
        if len(pl):
            ztop = pl.reshape(-1, 3)[:, 2].min()
            row("鏡頭凸台高度", zb - ztop, rear["plateauHeight"]["value"], "Apple p.2 右視圖")
            top = pl[np.all(np.abs(pl[:, :, 2] - ztop) < 1e-3, axis=1)]
            cm = contour_metrics(outer(silhouette(top)), Polygon(rear["outlines"]["cameraIsland"]["polygon"]))
            rows.append({"feature": "鏡頭島輪廓", "model": cm["model_size"], "reference": cm["ref_size"], "error": cm["contour_p95"], "hausdorff": cm["hausdorff"], "source": "Apple p.2 線稿 (B)"})
        lc = model.tris("frame", ["lensCover.*"])
        if len(lc):
            row("鏡頭玻璃高出凸台", (zb - rear["plateauHeight"]["value"]) - lc.reshape(-1, 3)[:, 2].min(), rear["lensGlassAbovePlateau"]["value"], "Apple p.2 右視圖")
    else:
        row("鏡頭凸台高度", legacy_feats["plateauHeight"], rear["plateauHeight"]["value"], "Apple p.2 右視圖")
        isl = legacy_feats["island"]
        cm = contour_metrics(Polygon([(isl[0], isl[1]), (isl[2], isl[1]), (isl[2], isl[3]), (isl[0], isl[3])]), Polygon(rear["outlines"]["cameraIsland"]["polygon"]))
        rows.append({"feature": "鏡頭島輪廓", "model": cm["model_size"], "reference": cm["ref_size"], "error": cm["contour_p95"], "hausdorff": cm["hausdorff"], "source": "Apple p.2 線稿 (B)"})
        row("鏡頭玻璃高出凸台", legacy_feats["lensAbovePlateau"], rear["lensGlassAbovePlateau"]["value"], "Apple p.2 右視圖")
    # back glass, cover glass, active area
    bg = model.tris("backGlass", cfg["parts"]["backGlass"]["body"])
    if len(bg):
        g = main_body(silhouette(bg), 0.3) if not model.named else silhouette(bg)
        cm = contour_metrics(g, Polygon(rear["outlines"]["backGlass"]["polygon"]))
        rows.append({"feature": "背蓋玻璃輪廓", "model": cm["model_size"], "reference": cm["ref_size"], "error": cm["contour_p95"], "hausdorff": cm["hausdorff"], "source": "Apple p.2 線稿 (B)"})
    dg = model.tris("display", cfg["display"]["glass"])
    if len(dg):
        g = silhouette(dg) if model.named else main_body(silhouette(model.tris("display")), 0.2)
        cm = contour_metrics(g, Polygon(D["glassOutline"]))
        rows.append({"feature": "螢幕玻璃輪廓", "model": cm["model_size"], "reference": [69.45, 147.61], "error": cm["contour_p95"], "hausdorff": cm["hausdorff"], "source": "Apple p.2"})
    if model.named:
        sc = model.tris("display", ["screen"])
        if len(sc):
            lo, hi = sc.reshape(-1, 3).min(0), sc.reshape(-1, 3).max(0)
            aw, ah = m["front"]["activeArea"]["value"]["size"]
            row("顯示區寬", hi[0] - lo[0], aw, A1)
            row("顯示區高", hi[1] - lo[1], ah, A1)
    else:
        aw, ah = m["front"]["activeArea"]["value"]["size"]
        row("顯示區寬", legacy_feats["active"][0], aw, A1)
        row("顯示區高", legacy_feats["active"][1], ah, A1)
    # buttons + SIM tray
    zh_btn = {"actionButton": "操作按鈕", "volumeUp": "音量＋", "volumeDown": "音量－", "sideButton": "側邊按鈕", "cameraControl": "相機控制"}
    for side in ("left", "right"):
        for k, v in sides[side].items():
            v = v["value"]
            if k == "simTray":
                t = model.tris("simTray", ["cap"]) if model.named else None
                lf = None if model.named else legacy_feats["buttons"]["simTray"]
            else:
                t = model.tris("frame", [k]) if model.named else None
                lf = None if model.named else legacy_feats["buttons"][k]
            if t is not None and len(t):
                p = t.reshape(-1, 3)
                yc, ln, wd = (p[:, 1].max() + p[:, 1].min()) / 2, p[:, 1].max() - p[:, 1].min(), p[:, 2].max() - p[:, 2].min()
                proud = (p[:, 0].max() - W / 2) if side == "right" else (-W / 2 - p[:, 0].min())
            elif lf:
                yc, ln, wd, proud = lf["y"], lf["len"], lf["width"], lf["proud"]
            else:
                continue
            zh = zh_btn.get(k, "SIM 卡托")
            row(f"{zh}：中心 y", yc, v["y"], A1)
            row(f"{zh}：長度", ln, v["len"], A1)
            row(f"{zh}：寬度", wd, v["width"], A1)
            row(f"{zh}：凸出量", max(proud, 0) if abs(proud) > 0.04 else 0.0, v["proud"], A1)
    # bottom edge: USB-C opening and ports from the section of the shell just inside the bottom face
    bot = sides["bottom"]
    if model.named and len(shell):
        mesh = trimesh.Trimesh(shell.reshape(-1, 3), np.arange(len(shell) * 3).reshape(-1, 3), process=False)
        mesh.merge_vertices()
        sec = mesh.section(plane_origin=[0, -H / 2 + 0.45, 0], plane_normal=[0, 1, 0])
        holes = []
        if sec is not None:
            for e in sec.entities:
                pts = np.asarray(sec.vertices)[e.points][:, [0, 2]]
                if len(pts) > 5 and np.hypot(*(pts[0] - pts[-1])) < 1e-3:
                    holes.append(pts)
        holes = [h for h in holes if np.ptp(h[:, 0]) < 12]
        usb = min(holes, key=lambda h: abs(h[:, 0].mean()), default=None)
        if usb is not None and np.ptp(usb[:, 0]) > 5:
            row("USB-C 開口中心 x", (usb[:, 0].max() + usb[:, 0].min()) / 2, bot["usbC"]["value"]["x"], "Apple p.2 DETAIL C")
            row("USB-C 開口寬", np.ptp(usb[:, 0]), bot["usbC"]["value"]["width"], "Apple p.2 DETAIL C")
            row("USB-C 開口高", np.ptp(usb[:, 1]), bot["usbC"]["value"]["height"], "Apple p.2 DETAIL C")
        ports = sorted([h for h in holes if np.ptp(h[:, 0]) < 2.5], key=lambda h: h[:, 0].mean())
        ref_x = sorted(bot["portsLeft"]["value"]["x"] + bot["portsRight"]["value"]["x"])
        if len(ports) == len(ref_x):
            errs = [abs((h[:, 0].max() + h[:, 0].min()) / 2 - x) for h, x in zip(ports, ref_x)]
            dia = [np.ptp(h[:, 0]) for h in ports]
            rows.append({"feature": "底部 10 孔位置（最大偏差）", "model": f"{len(ports)} 孔", "reference": "10 孔", "error": round(max(errs), 3), "source": A1})
            row("底部孔直徑（平均）", float(np.mean(dia)), bot["portsLeft"]["value"]["diameter"], A1)
        else:
            rows.append({"feature": "底部 10 孔位置", "model": f"找到 {len(ports)} 孔", "reference": "10 孔", "error": None, "source": A1})
        sc = model.meshes("frame", ["screw"])
        if sc:
            xs = sorted(float((s["tris"][:, :, 0].max() + s["tris"][:, :, 0].min()) / 2) for s in sc)
            errs = [abs(a - b) for a, b in zip(xs, sorted(bot["screws"]["value"]["x"]))]
            rows.append({"feature": "底部螺絲位置（最大偏差）", "model": [round(x, 3) for x in xs], "reference": bot["screws"]["value"]["x"], "error": round(max(errs), 3), "source": A1})
    elif not model.named:
        lf = legacy_feats["bottom"]
        row("USB-C 開口寬", lf["usbWidth"], bot["usbC"]["value"]["width"], "Apple p.2 DETAIL C")
        row("USB-C 開口高", lf["usbHeight"], bot["usbC"]["value"]["height"], "Apple p.2 DETAIL C")
        ref_x = sorted(bot["portsLeft"]["value"]["x"] + bot["portsRight"]["value"]["x"])
        errs = [min(abs(x - r) for x in lf["ports"]) for r in ref_x]
        rows.append({"feature": "底部 10 孔位置（最大偏差）", "model": f"{len(lf['ports'])} 孔", "reference": "10 孔", "error": round(max(errs), 3), "source": A1})
        errs = [abs(a - b) for a, b in zip(sorted(lf["screws"]), sorted(bot["screws"]["value"]["x"]))]
        rows.append({"feature": "底部螺絲位置（最大偏差）", "model": lf["screws"], "reference": bot["screws"]["value"]["x"], "error": round(max(errs), 3), "source": A1})
    return rows


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--measurements", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--rectified-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.measurements).read_text())
    cfg = json.loads(Path(a.config).read_text())
    model = Model(Path(a.model))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rdir = Path(a.rectified_dir)
    orthos = {n: Ortho(rdir, n) for n in cfg["orthos"] if (rdir / f"{n}.rectify.json").exists()}

    ext = exterior(model, m, cfg, cfg.get("legacy_features"))

    internal = []
    sil_cache = {}
    for pid, pc in cfg["parts"].items():
        tris = model.tris(pid, pc.get("body"))
        if not len(tris):
            internal.append({"part": pid, "status": "no geometry"})
            continue
        geom = silhouette(tris)
        if not model.named:
            geom = main_body(geom)
        sil_cache[pid] = geom
        refs = [m["internal"][r] for r in pc.get("refs", []) if r in m.get("internal", {})]
        official = pc.get("official")
        rec = {"part": pid, "verified": pc.get("verified", "xy"), "note": pc.get("note", "")}
        if official:
            ref_geom = Polygon(m["rear"]["outlines"][official]["polygon"])
            rec.update({"reference": f"Apple 線稿 {official}", "uncertainty": 0.05})
        elif refs:
            polys = []
            for r in refs:
                poly = Polygon(r["polygon_mm"], [h for h in r.get("holes_mm", [])])
                polys.append(poly.buffer(0))
            ref_geom = unary_union(polys)
            rec.update({"reference": "; ".join(sorted({r["source"] for r in refs})), "uncertainty": pc.get("uncertainty", 0.5)})
        else:
            rec.update({"status": "no reference", "reason": pc.get("reason", "")})
            internal.append(rec)
            continue
        cm = contour_metrics(geom, ref_geom)
        rec.update(cm)
        rec["with_uncertainty"] = round(cm["contour_p95"] + rec["uncertainty"], 2)
        rec["gate"] = pc.get("gate", 1.0)
        rec["pass"] = bool(rec["with_uncertainty"] <= rec["gate"]) if rec["verified"] != "none" else None
        rec["edge_fit"] = {n: orthos[n].edge_fit(geom) for n in pc.get("show_on", []) if n in orthos}
        # independent cross-checks on another unit / source
        for r in pc.get("cross", []):
            if r in m.get("internal", {}):
                x = m["internal"][r]
                cg = Polygon(x["polygon_mm"]).buffer(0)
                rec.setdefault("cross_check", {})[r] = {"contour_p95": contour_metrics(geom, cg)["contour_p95"], "centroid_offset": round(float(geom.centroid.distance(cg.centroid)), 2), "source": x["source"]}
        internal.append(rec)

    # overlays -----------------------------------------------------------
    for n, o in orthos.items():
        layer = np.zeros_like(o.img)
        lines = np.zeros_like(o.img)
        shown = [pid for pid, pc in cfg["parts"].items() if n in pc.get("show_on", []) and pid in sil_cache]
        for i, pid in enumerate(shown):
            col = PALETTE[i % len(PALETTE)]
            draw_geom(layer, o, sil_cache[pid], col, fill=True)
            draw_geom(lines, o, sil_cache[pid], col, fill=False)
        if n in cfg.get("exterior_on", []):
            for k, pat in cfg["exterior_draw"].items():
                t = model.tris("frame", pat) if model.named else np.zeros((0, 3, 3))
                if len(t):
                    draw_geom(lines, o, silhouette(t), (0, 255, 255), fill=False)
        refl = np.zeros_like(o.img)
        for pid in shown:
            for r in cfg["parts"][pid].get("refs", []):
                if r in m.get("internal", {}) and m["internal"][r].get("ortho") == n:
                    cv2.polylines(refl, [o.px(m["internal"][r]["polygon_mm"]).astype(np.int32)], True, (255, 255, 255), 1, cv2.LINE_AA)
        mask = layer.any(axis=2)
        comp = o.img.copy()
        comp[mask] = (0.58 * o.img[mask] + 0.42 * layer[mask]).astype(np.uint8)
        for extra_layer in (lines, refl):
            mk = extra_layer.any(axis=2)
            comp[mk] = extra_layer[mk]
        for i, pid in enumerate(shown):
            c = sil_cache[pid].representative_point()
            q = o.px([[c.x, c.y]])[0].astype(int)
            cv2.putText(comp, pid, (q[0] - 30, q[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(comp, pid, (q[0] - 30, q[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.55, PALETTE[i % len(PALETTE)], 1, cv2.LINE_AA)
        cv2.imwrite(str(out / f"overlay_ortho_{n}.jpg"), comp, [cv2.IMWRITE_JPEG_QUALITY, 88])
        # same viewpoint as the source image: warp the overlay back through the registration
        src_name = o.meta.get("image") or o.meta.get("photo")
        H = np.array(o.meta["matrix_px_to_mm"])
        Mx = np.array([[o.ppm, 0, -o.x0 * o.ppm], [0, -o.ppm, o.y1 * o.ppm], [0, 0, 1]]) @ H  # source px -> ortho px
        cand = [Path(a.config).parent / "../measure/models" / cfg["model"] / "jobs" / src_name, rdir / src_name] + list(Path("refs").rglob(Path(src_name).name))
        src_path = next((p for p in cand if p.is_file()), None)
        if src_path is not None:
            src = cv2.imread(str(src_path))
            inv = np.linalg.inv(Mx)
            wl = cv2.warpPerspective(layer, inv, (src.shape[1], src.shape[0]))
            wlines = cv2.warpPerspective(np.maximum(lines, refl), inv, (src.shape[1], src.shape[0]))
            mk = wl.any(axis=2)
            comp2 = src.copy()
            comp2[mk] = (0.58 * src[mk] + 0.42 * wl[mk]).astype(np.uint8)
            mk = wlines.any(axis=2)
            comp2[mk] = wlines[mk]
            corners = cv2.perspectiveTransform(np.float32([[[0, 0], [o.img.shape[1], 0], [o.img.shape[1], o.img.shape[0]], [0, o.img.shape[0]]]]), inv)[0]
            x0, y0 = np.maximum(corners.min(0).astype(int) - 60, 0)
            x1, y1 = np.minimum(corners.max(0).astype(int) + 60, [src.shape[1], src.shape[0]])
            cv2.imwrite(str(out / f"overlay_source_{n}.jpg"), comp2[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 88])

    (out / "metrics.json").write_text(json.dumps({"label": a.label, "model": a.model, "exterior": ext, "internal": internal}, indent=1, ensure_ascii=False))
    worst = max((r["error"] for r in ext if r.get("error") is not None), default=None)
    print(f"[{a.label}] exterior features: {len(ext)}, worst error {worst} mm")
    for r in ext:
        if r.get("error") is None or r["error"] > 0.5:
            print("   EXT >0.5:", r["feature"], r.get("model"), "vs", r.get("reference"), "->", r.get("error"))
    for r in internal:
        if "contour_p95" in r:
            print(f"   {r['part']:<14} p95 {r['contour_p95']:5.2f}  haus {r['hausdorff']:5.2f}  centroid {r['centroid_offset']:5.2f}  +u {r['with_uncertainty']:5.2f}  pass={r['pass']}  edge_fit={r['edge_fit']}")
        else:
            print(f"   {r['part']:<14} {r.get('status')}")


if __name__ == "__main__":
    main()
