# /// script
# requires-python = ">=3.11"
# dependencies = ["pymupdf>=1.24", "numpy>=1.26", "pillow>=10", "shapely>=2.0"]
# ///
"""Extract outlines from a vector dimensional drawing (PDF) as millimetre polylines.

CAD drawings exported to PDF are a soup of short line segments. For each configured view this
script collects the segments inside the view's clip rectangle, chains them into polylines, finds
the closed loops, and converts them to phone-local millimetres using a dimensioned reference
(the product's overall width x height, which the largest closed loop in the view must match).

    uv run tools/measure/pdf_vectors.py <drawing.pdf> --config <views.json> --out <loops.json> [--debug-dir DIR]

Config (JSON):
    {"views": [{"name": "back", "page": 2, "clip_pt": [x0, y0, x1, y1],
                "body_mm": [71.85, 150.01], "mirror_x": true, "min_size_mm": 0.8,
                "faces": [{"id": "backGlass", "seed_mm": [0, -20]}]}]}

`faces` names regions of the drawing: the line work is polygonised and the face containing
`seed_mm` is returned (its outer boundary), which copes with T-junctions that break plain loops.
The special seed "union" returns the outer boundary of everything (the silhouette).

`clip_pt` is in PDF points (top-left origin). `mirror_x` flips x so that a back view is expressed
in the front-view coordinate system (+x right, +y up when looking at the screen, origin at centre).
Output: per view, the scale check and every closed loop (bbox, perimeter, circle fit, points).
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

SNAP = 0.02  # pt; endpoints closer than this are the same node


def segments_in(page: pymupdf.Page, clip: pymupdf.Rect) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segs = []
    for d in page.get_drawings():
        if d.get("dashes") not in (None, "", "[] 0"):
            continue  # centre lines / hidden lines
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if clip.contains(a) and clip.contains(b):
                    segs.append(((a.x, a.y), (b.x, b.y)))
            elif it[0] == "c":  # bezier: flatten
                p = [np.array([q.x, q.y]) for q in it[1:5]]
                if not all(clip.contains(pymupdf.Point(*q)) for q in p):
                    continue
                prev = p[0]
                for t in np.linspace(0, 1, 17)[1:]:
                    q = (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t**2 * p[2] + t**3 * p[3]
                    segs.append((tuple(prev), tuple(q)))
                    prev = q
    return segs


def chain(segs):
    """Chain segments into polylines; returns list of (points Nx2, closed)."""
    key = lambda p: (round(p[0] / SNAP), round(p[1] / SNAP))
    adj: dict = defaultdict(list)
    pts: dict = {}
    seen_edges = set()
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka == kb or (ka, kb) in seen_edges or (kb, ka) in seen_edges:
            continue
        seen_edges.add((ka, kb))
        pts[ka], pts[kb] = a, b
        adj[ka].append(kb)
        adj[kb].append(ka)
    used = set()
    out = []

    def walk(start, nxt):
        path = [start, nxt]
        used.add(frozenset((start, nxt)))
        while True:
            cur = path[-1]
            if len(adj[cur]) != 2:
                return path, False
            a, b = adj[cur]
            n = b if a == path[-2] else a
            e = frozenset((cur, n))
            if e in used:
                return path, n == path[0]
            used.add(e)
            path.append(n)
            if n == path[0]:
                return path, True

    # open chains start at junctions / ends; then remaining are pure loops
    for k in list(adj):
        if len(adj[k]) != 2:
            for n in adj[k]:
                if frozenset((k, n)) not in used:
                    path, closed = walk(k, n)
                    out.append((np.array([pts[q] for q in path]), closed))
    for k in list(adj):
        for n in adj[k]:
            if frozenset((k, n)) not in used:
                path, closed = walk(k, n)
                out.append((np.array([pts[q] for q in path]), closed))
    return out


def circle_fit(p: np.ndarray):
    x, y = p[:, 0], p[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(p))]
    sol, *_ = np.linalg.lstsq(A, x**2 + y**2, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(max(sol[2] + cx**2 + cy**2, 0))
    rms = float(np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2)))
    return float(cx), float(cy), float(r), rms


def process_view(doc, view, debug_dir: Path | None):
    page = doc[view["page"] - 1]
    clip = pymupdf.Rect(*view["clip_pt"])
    polys = chain(segments_in(page, clip))
    loops = [p for p, closed in polys if closed and len(p) >= 8]
    opens = [p for p, closed in polys if not closed and len(p) >= 2]
    wmm, hmm = view["body_mm"]
    if "body_bbox_pt" in view:
        bx0, by0, bx1, by1 = view["body_bbox_pt"]
    else:
        # The body's flat sides are the longest axis-aligned runs in the view.
        segs = np.array(segments_in(page, clip)).reshape(-1, 4)
        dx, dy = np.abs(segs[:, 2] - segs[:, 0]), np.abs(segs[:, 3] - segs[:, 1])
        est = (clip.height - 4) / hmm  # rough pt/mm from the clip, used only for length thresholds
        def sides(coord, length, need):
            tot: dict = defaultdict(float)
            for c, l in zip(coord, length):
                tot[round(c / 0.05)] += l
            ok = [k * 0.05 for k, v in tot.items() if v > need]
            if len(ok) < 2:
                raise SystemExit(f"view {view['name']}: could not find the body's flat sides; set body_bbox_pt")
            return min(ok), max(ok)

        v, h = dx < 0.01, dy < 0.01
        bx0, bx1 = sides(segs[v, 0], dy[v], 0.4 * hmm * est)
        by0, by1 = sides(segs[h, 1], dx[h], 0.3 * wmm * est)
    sx, sy = (bx1 - bx0) / wmm, (by1 - by0) / hmm  # pt per mm
    scale = (sx + sy) / 2
    if abs(sx - sy) / scale > 0.005:
        raise SystemExit(f"view {view['name']}: x/y scale disagree ({sx:.4f} vs {sy:.4f} pt/mm); check clip or set body_bbox_pt")
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    sign = -1.0 if view.get("mirror_x") else 1.0

    def to_mm(p):
        return np.c_[sign * (p[:, 0] - cx) / scale, -(p[:, 1] - cy) / scale]

    min_size = view.get("min_size_mm", 0.8)
    res = []
    for p in loops:
        m = to_mm(p)
        x0, y0, x1, y1 = m[:, 0].min(), m[:, 1].min(), m[:, 0].max(), m[:, 1].max()
        if max(x1 - x0, y1 - y0) < min_size:
            continue
        per = float(np.sum(np.hypot(*np.diff(np.r_[m, m[:1]], axis=0).T)))
        ccx, ccy, r, rms = circle_fit(m)
        res.append(
            {
                "bbox_mm": [round(float(v), 3) for v in (x0, y0, x1, y1)],
                "size_mm": [round(float(x1 - x0), 3), round(float(y1 - y0), 3)],
                "perimeter_mm": round(per, 3),
                "circle": {"cx": round(ccx, 3), "cy": round(ccy, 3), "r": round(r, 3), "rms": round(rms, 4)},
                "n": len(m),
                "points_mm": [[round(float(a), 3), round(float(b), 3)] for a, b in m],
            }
        )
    res.sort(key=lambda l: -l["size_mm"][0] * l["size_mm"][1])
    paths = []
    for p in opens:
        m = to_mm(p)
        length = float(np.sum(np.hypot(*np.diff(m, axis=0).T)))
        if length >= view.get("min_path_mm", 3.0):
            paths.append({"length_mm": round(length, 3), "points_mm": [[round(float(a), 3), round(float(b), 3)] for a, b in m]})
    paths.sort(key=lambda q: -q["length_mm"])
    named = {}
    if view.get("faces"):
        segs_mm = [to_mm(np.array(sg)) for sg in segments_in(page, clip)]
        polys_mm = list(polygonize(unary_union([LineString(sg) for sg in segs_mm if np.hypot(*(sg[1] - sg[0])) > 1e-6])))
        for f in view["faces"]:
            if f["seed_mm"] == "union":
                g = unary_union(polys_mm)
                g = max(g.geoms, key=lambda q: q.area) if g.geom_type == "MultiPolygon" else g
            else:
                hits = [q for q in polys_mm if q.contains(Point(*f["seed_mm"]))]
                if not hits:
                    raise SystemExit(f"view {view['name']}: no face contains seed for {f['id']}")
                g = min(hits, key=lambda q: q.area)
            ext = Polygon(g.exterior)
            x0, y0, x1, y1 = ext.bounds
            named[f["id"]] = {
                "bbox_mm": [round(v, 3) for v in (x0, y0, x1, y1)],
                "size_mm": [round(x1 - x0, 3), round(y1 - y0, 3)],
                "area_mm2": round(ext.area, 2),
                "points_mm": [[round(a, 3), round(b, 3)] for a, b in list(ext.exterior.coords)[:-1]],
            }
    info = {
        "name": view["name"],
        "page": view["page"],
        "pt_per_mm": {"x": round(sx, 5), "y": round(sy, 5), "used": round(scale, 5)},
        "scale_anisotropy_pct": round(abs(sx - sy) / scale * 100, 3),
        "mm_per_pt": round(1 / scale, 5),
        "body_bbox_pt": [round(v, 3) for v in (bx0, by0, bx1, by1)],
        "faces": named,
        "loops": res,
        "paths": paths,
    }
    if debug_dir:
        z = 6.0
        pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip)
        im = Image.frombytes("RGB", (pm.width, pm.height), pm.samples).convert("L").convert("RGB")
        im = Image.blend(im, Image.new("RGB", im.size, "white"), 0.6)
        dr = ImageDraw.Draw(im)
        palette = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#008080", "#9a6324", "#800000", "#000075"]
        for i, l in enumerate(res):
            m = np.array(l["points_mm"])
            px = (sign * m[:, 0] * scale + cx - clip.x0) * z
            py = (-m[:, 1] * scale + cy - clip.y0) * z
            xy = list(zip(px, py))
            dr.line(xy + xy[:1], fill=palette[i % len(palette)], width=2)
            dr.text((float(px.min()) + 3, float(py.min()) + 3), str(i), fill=palette[i % len(palette)])
        for name, f in named.items():
            m = np.array(f["points_mm"])
            px = (sign * m[:, 0] * scale + cx - clip.x0) * z
            py = (-m[:, 1] * scale + cy - clip.y0) * z
            xy = list(zip(px, py))
            dr.line(xy + xy[:1], fill="#ff00aa", width=3)
            dr.text((float(px.mean()) - 20, float(py.min()) + 8), name, fill="#ff00aa")
        debug_dir.mkdir(parents=True, exist_ok=True)
        im.save(debug_dir / f"pdf_{view['name']}.png")
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug-dir")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    doc = pymupdf.open(a.pdf)
    views = [process_view(doc, v, Path(a.debug_dir) if a.debug_dir else None) for v in cfg["views"]]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"source": Path(a.pdf).name, "views": views}, indent=1))
    for v in views:
        print(f"[{v['name']}] {v['mm_per_pt']} mm/pt, anisotropy {v['scale_anisotropy_pct']}%, {len(v['loops'])} loops")
        for k, f in v["faces"].items():
            print(f"  face {k:<14} size {f['size_mm'][0]:7.2f} x {f['size_mm'][1]:7.2f}  bbox {f['bbox_mm']} area {f['area_mm2']}")
        for i, l in enumerate(v["loops"][:40] if not v["faces"] else []):
            c = l["circle"]
            circ = f" circle c=({c['cx']},{c['cy']}) d={2 * c['r']:.3f} rms={c['rms']}" if c["rms"] < 0.03 else ""
            print(f"  #{i:<2} size {l['size_mm'][0]:7.2f} x {l['size_mm'][1]:7.2f}  bbox {l['bbox_mm']}{circ}")


if __name__ == "__main__":
    main()
