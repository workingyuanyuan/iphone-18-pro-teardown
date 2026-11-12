# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless>=4.9", "numpy>=1.26"]
# ///
"""Crop a rectified orthoimage to a millimetre window and draw a labelled mm grid on it, for
hand-tracing low-contrast parts. Optionally draws polygons from an outlines/parts JSON on top.

    uv run tools/measure/grid_view.py <rectified-dir> <ortho-name> x0 y0 x1 y1 <out.png>
        [--step 5] [--zoom 1.0] [--parts parts.json] [--gamma 0.6]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("dir")
ap.add_argument("name")
ap.add_argument("win", nargs=4, type=float)
ap.add_argument("out")
ap.add_argument("--step", type=float, default=5)
ap.add_argument("--zoom", type=float, default=1.0)
ap.add_argument("--gamma", type=float, default=1.0, help="<1 brightens dark, black-on-black areas")
ap.add_argument("--parts")
a = ap.parse_args()
r = json.loads((Path(a.dir) / f"{a.name}.rectify.json").read_text())["ortho"]
im = cv2.imread(str(Path(a.dir) / r["file"]))
ppm, (ex0, ey0, ex1, ey1) = r["px_per_mm"], r["extent_mm"]
x0, y0, x1, y1 = a.win
P = lambda x, y: (int(round((x - ex0) * ppm)), int(round((ey1 - y) * ppm)))
if a.gamma != 1.0:
    im = (255 * (im / 255.0) ** a.gamma).astype(np.uint8)
if a.parts:
    data = json.loads(Path(a.parts).read_text())
    for p in data.get("parts", data.get("outlines", [])):
        poly = p.get("polygon_mm")
        if poly and p.get("ortho", a.name) == a.name or (poly and p.get("show_on_all")):
            pts = np.array([P(*q) for q in poly])
            cv2.polylines(im, [pts], True, (0, 255, 0), 1)
            cv2.putText(im, p["id"], tuple(int(v) for v in pts.min(0) + [3, 14]), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
(ax, ay), (bx, by) = P(x0, y1), P(x1, y0)
ax, ay, bx, by = max(ax, 0), max(ay, 0), min(bx, im.shape[1]), min(by, im.shape[0])
g = np.arange(np.ceil(min(x0, x1) / a.step) * a.step, x1 + 1e-6, a.step)
for x in g:
    px = P(x, 0)[0]
    cv2.line(im, (px, ay), (px, by), (0, 255, 255) if abs(x) < 1e-6 else (255, 255, 0), 1)
for y in np.arange(np.ceil(y0 / a.step) * a.step, y1 + 1e-6, a.step):
    py = P(0, y)[1]
    cv2.line(im, (ax, py), (bx, py), (0, 255, 255) if abs(y) < 1e-6 else (255, 255, 0), 1)
crop = im[ay:by, ax:bx]
crop = cv2.resize(crop, None, fx=a.zoom, fy=a.zoom, interpolation=cv2.INTER_AREA if a.zoom < 1 else cv2.INTER_CUBIC)
for x in g:
    px = int((P(x, 0)[0] - ax) * a.zoom)
    cv2.putText(crop, f"{x:g}", (px + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
    cv2.putText(crop, f"{x:g}", (px + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
for y in np.arange(np.ceil(y0 / a.step) * a.step, y1 + 1e-6, a.step):
    py = int((P(0, y)[1] - ay) * a.zoom)
    cv2.putText(crop, f"{y:g}", (2, py - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
    cv2.putText(crop, f"{y:g}", (2, py - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
cv2.imwrite(a.out, crop)
print("wrote", a.out, crop.shape[1], "x", crop.shape[0])
