# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless>=4.9", "numpy>=1.26"]
# ///
"""Draw the officially dimensioned features from measurements.json on a rectified orthoimage,
as a visual check of the registration.

    uv run tools/measure/overlay_official.py <measurements.json> <rectified-dir> <ortho-name> <out.png> [--scale 0.6]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("measurements")
ap.add_argument("rectified_dir")
ap.add_argument("name")
ap.add_argument("out")
ap.add_argument("--scale", type=float, default=0.6)
a = ap.parse_args()
m = json.loads(Path(a.measurements).read_text())
r = json.loads((Path(a.rectified_dir) / f"{a.name}.rectify.json").read_text())["ortho"]
im = cv2.imread(str(Path(a.rectified_dir) / r["file"]))
ppm, (x0, y0, x1, y1) = r["px_per_mm"], r["extent_mm"]
P = lambda x, y: (int(round((x - x0) * ppm)), int(round((y1 - y) * ppm)))
G = (0, 255, 0)
rear = m["rear"]
for k in ("backGlass", "cameraIsland"):
    if k in rear.get("outlines", {}):
        cv2.polylines(im, [np.array([P(*p) for p in rear["outlines"][k]["polygon"]])], True, G, 2)
circles = [(*v["value"], rear["lensRingDiameter"]["value"]) for v in rear["lenses"].values()]
circles += [(*rear[k]["value"]["centre"], rear[k]["value"]["diameter"]) for k in ("flash", "rearSensor", "rearMic")]
for x, y, d in circles:
    cv2.circle(im, P(x, y), int(d / 2 * ppm), G, 2)
    cv2.drawMarker(im, P(x, y), G, cv2.MARKER_CROSS, 20, 2)
cv2.drawMarker(im, P(*rear["magsafeCentre"]["value"]), G, cv2.MARKER_TILTED_CROSS, 30, 2)
b = m["sides"]["bottom"]
for x in [b["usbC"]["value"]["x"], *b["screws"]["value"]["x"]]:
    cv2.line(im, P(x, -m["body"]["height"]["value"] / 2), P(x, -66), G, 2)
aw, ah = m["front"]["activeArea"]["value"]["size"]
cv2.rectangle(im, P(-aw / 2, ah / 2), P(aw / 2, -ah / 2), (255, 255, 0), 1)
im = cv2.resize(im, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_AREA)
cv2.imwrite(a.out, im)
print("wrote", a.out)
