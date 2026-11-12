# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless>=4.9", "numpy>=1.26"]
# ///
"""Trace part outlines on rectified orthoimages and write them as millimetre polygons.

    uv run tools/measure/contours.py <parts.json> --rectified-dir DIR --out <outlines.json> [--debug-dir DIR]

parts.json:
  {"parts": [
     {"id": "battery", "ortho": "weki-1019", "roi_mm": [x0, y0, x1, y1], "method": "threshold",
      "polarity": "bright", "simplify_mm": 0.15, "source": "...", "note": "..."},
     {"id": "taptic", "ortho": "ifixit-photo-NoBattery", "roi_mm": [...], "method": "canny"},
     {"id": "magnetRing", "ortho": "ifixit-ct07", "roi_mm": [...], "method": "circle", "r_mm": [20, 30]},
     {"id": "apBoard", "ortho": "weki-1019", "method": "manual", "polygon_mm": [[x, y], ...]}
  ]}

`ortho` names a <name>.ortho.png + <name>.rectify.json pair written by rectify.py / register_pair.py.
Methods:
  threshold  Otsu inside the ROI; the largest blob of the given polarity ("bright" | "dark").
  canny      Canny edges, closed and filled; the largest closed region inside the ROI.
  grabcut    GrabCut initialised with the ROI inset by 6 %.
  circle     Sub-pixel circle fit (Hough + radial edge refinement); r_mm = [lo, hi].
  manual     A hand-traced polygon given in mm (for low-contrast black-on-black parts).

Every outline, including manual ones, gets `edge_support`: the fraction of its perimeter that lies
within 0.3 mm of a strong image edge. It is the objective check that a trace follows something
real; outlines with low support are reported so they can be down-graded or redone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


class Ortho:
    def __init__(self, d: Path, name: str):
        self.name = name
        self.meta = json.loads((d / f"{name}.rectify.json").read_text())
        o = self.meta["ortho"]
        self.ppm = o["px_per_mm"]
        self.x0, self.y0, self.x1, self.y1 = o["extent_mm"]
        self.img = cv2.imread(str(d / o["file"]))
        if self.img is None:
            raise SystemExit(f"missing orthoimage for {name}")
        self.gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(self.gray, (0, 0), 1.2)
        mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
        strong = (mag > np.percentile(mag, 88)).astype(np.uint8)
        # distance (px) from every pixel to the nearest strong edge
        self.edge_dist = cv2.distanceTransform(1 - strong, cv2.DIST_L2, 3)
        self.debug = self.img.copy()

    def to_px(self, pts):
        p = np.asarray(pts, np.float64)
        return np.c_[(p[:, 0] - self.x0) * self.ppm, (self.y1 - p[:, 1]) * self.ppm]

    def to_mm(self, px):
        p = np.asarray(px, np.float64)
        return np.c_[p[:, 0] / self.ppm + self.x0, self.y1 - p[:, 1] / self.ppm]

    def roi(self, roi_mm):
        (ax, ay), (bx, by) = self.to_px([[roi_mm[0], roi_mm[3]], [roi_mm[2], roi_mm[1]]])
        h, w = self.gray.shape
        return max(int(ax), 0), max(int(ay), 0), min(int(bx), w), min(int(by), h)

    def support(self, poly_mm, tol_mm=0.3):
        px = self.to_px(poly_mm)
        closed = np.r_[px, px[:1]]
        samples = []
        for a, b in zip(closed[:-1], closed[1:]):
            n = max(int(np.hypot(*(b - a))), 1)
            samples.append(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
        s = np.concatenate(samples)
        h, w = self.gray.shape
        xi, yi = np.clip(s[:, 0].round().astype(int), 0, w - 1), np.clip(s[:, 1].round().astype(int), 0, h - 1)
        return float(np.mean(self.edge_dist[yi, xi] <= tol_mm * self.ppm))


def largest_blob(mask):
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea) if cs else None


def trace(o: Ortho, part: dict):
    m = part["method"]
    if m == "manual":
        return np.array(part["polygon_mm"], np.float64), {}
    x0, y0, x1, y1 = o.roi(part["roi_mm"])
    crop, gray = o.img[y0:y1, x0:x1], o.gray[y0:y1, x0:x1]
    if m == "circle":
        lo, hi = (int(r * o.ppm) for r in part["r_mm"])
        g = cv2.GaussianBlur(gray, (0, 0), 1.5)
        cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT_ALT, 1.5, lo, param1=100, param2=part.get("quality", 0.6), minRadius=lo, maxRadius=hi)
        if cs is None:
            return None, {}
        cx, cy, r = cs[0][0]
        c, r = o.to_mm([[cx + x0, cy + y0]])[0], float(r) / o.ppm
        th = np.linspace(0, 2 * np.pi, 96, endpoint=False)
        return np.c_[c[0] + r * np.cos(th), c[1] + r * np.sin(th)], {"circle": {"cx": round(float(c[0]), 3), "cy": round(float(c[1]), 3), "r": round(r, 3)}}
    if m == "threshold":
        g = cv2.GaussianBlur(gray, (0, 0), part.get("blur", 1.5))
        flag = cv2.THRESH_BINARY if part.get("polarity", "bright") == "bright" else cv2.THRESH_BINARY_INV
        if "level" in part:
            _, mask = cv2.threshold(g, part["level"], 255, flag)
        else:
            _, mask = cv2.threshold(g, 0, 255, flag + cv2.THRESH_OTSU)
    elif m == "canny":
        g = cv2.GaussianBlur(gray, (0, 0), part.get("blur", 1.5))
        e = cv2.Canny(g, part.get("canny", [30, 90])[0], part.get("canny", [30, 90])[1])
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (part.get("close_px", 9),) * 2)
        e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, k)
        # fill everything not reachable from the ROI border
        ff = cv2.copyMakeBorder(e, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        cv2.floodFill(ff, None, (0, 0), 128)
        mask = (ff[1:-1, 1:-1] != 128).astype(np.uint8) * 255
    elif m == "grabcut":
        mk = np.zeros(gray.shape, np.uint8)
        ix, iy = int(0.06 * gray.shape[1]), int(0.06 * gray.shape[0])
        cv2.grabCut(crop, mk, (ix, iy, gray.shape[1] - 2 * ix, gray.shape[0] - 2 * iy), np.zeros((1, 65)), np.zeros((1, 65)), 5, cv2.GC_INIT_WITH_RECT)
        mask = ((mk == 1) | (mk == 3)).astype(np.uint8) * 255
    else:
        raise SystemExit(f"{part['id']}: unknown method {m}")
    k = part.get("open_px", 7)
    kk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kk), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (part.get("fill_px", 15),) * 2))
    c = largest_blob(mask)
    if c is None:
        return None, {}
    if part.get("fill_holes", True):
        filled = np.zeros_like(mask)
        cv2.drawContours(filled, [c], -1, 255, -1)
        c = largest_blob(filled)
    eps = part.get("simplify_mm", 0.12) * o.ppm
    c = cv2.approxPolyDP(c, eps, True).reshape(-1, 2).astype(np.float64) + [x0, y0]
    touches = bool((c[:, 0] <= x0 + 1).any() or (c[:, 0] >= x1 - 2).any() or (c[:, 1] <= y0 + 1).any() or (c[:, 1] >= y1 - 2).any())
    return o.to_mm(c), {"touches_roi": touches}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts")
    ap.add_argument("--rectified-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug-dir")
    a = ap.parse_args()
    cfg = json.loads(Path(a.parts).read_text())
    orthos: dict[str, Ortho] = {}
    results = []
    for part in cfg["parts"]:
        o = orthos.setdefault(part["ortho"], Ortho(Path(a.rectified_dir), part["ortho"])) if part["ortho"] not in orthos else orthos[part["ortho"]]
        poly, extra = trace(o, part)
        rec = {"id": part["id"], "ortho": part["ortho"], "method": part["method"], "source": part.get("source", ""), "note": part.get("note", "")}
        if poly is None or len(poly) < 3:
            rec["status"] = "failed"
            results.append(rec)
            print(f"  ! {part['id']}: no outline found")
            continue
        area = 0.5 * abs(np.dot(poly[:, 0], np.roll(poly[:, 1], -1)) - np.dot(poly[:, 1], np.roll(poly[:, 0], -1)))
        M = cv2.moments(poly.astype(np.float32))
        cen = [M["m10"] / M["m00"], M["m01"] / M["m00"]] if M["m00"] else poly.mean(0).tolist()
        sup = o.support(poly)
        rec.update(
            {
                "status": "ok" if sup >= part.get("min_support", 0.6) and not extra.get("touches_roi") else "review",
                "edge_support": round(sup, 3),
                "bbox_mm": [round(float(v), 2) for v in (poly[:, 0].min(), poly[:, 1].min(), poly[:, 0].max(), poly[:, 1].max())],
                "size_mm": [round(float(np.ptp(poly[:, 0])), 2), round(float(np.ptp(poly[:, 1])), 2)],
                "centroid_mm": [round(float(cen[0]), 2), round(float(cen[1]), 2)],
                "area_mm2": round(float(area), 1),
                "mm_per_px_source": o.meta.get("mm_per_px"),
                **extra,
                "polygon_mm": [[round(float(x), 2), round(float(y), 2)] for x, y in poly],
            }
        )
        results.append(rec)
        px = o.to_px(poly).astype(np.int32)
        col = (0, 255, 0) if rec["status"] == "ok" else (0, 165, 255)
        cv2.polylines(o.debug, [px], True, col, 2)
        if "roi_mm" in part:
            x0, y0, x1, y1 = o.roi(part["roi_mm"])
            cv2.rectangle(o.debug, (x0, y0), (x1, y1), (255, 200, 0), 1)
        cv2.putText(o.debug, part["id"], (int(px[:, 0].min()) + 4, int(px[:, 1].min()) + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
        print(f"  {rec['status']:<6} {part['id']:<16} {part['method']:<9} size {rec['size_mm'][0]:6.2f} x {rec['size_mm'][1]:6.2f}  centre {rec['centroid_mm']}  support {sup:.2f}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"outlines": results}, indent=1))
    if a.debug_dir:
        Path(a.debug_dir).mkdir(parents=True, exist_ok=True)
        for name, o in orthos.items():
            cv2.imwrite(str(Path(a.debug_dir) / f"contours_{name}.png"), o.debug)


if __name__ == "__main__":
    main()
