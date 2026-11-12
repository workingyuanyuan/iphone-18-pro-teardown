# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26", "shapely>=2.0"]
# ///
"""Assemble measurements.json for the iPhone 18 Pro from the dimensioned Apple drawing values
(typed in below with their sheet reference) plus the tool outputs in refs/out/.

    uv run tools/measure/models/iphone-18-pro/build_measurements.py [--tool-out refs/out]

Coordinates: phone-local mm, origin at the body centre, +x right / +y up looking at the screen,
+z towards the screen. Apple's datums are the top-left corner of each view, so
x = x_drawing - W/2 (front view) or W/2 - x_drawing (back view), y = H/2 - y_drawing.
Confidence: A = dimensioned on Apple's drawing; B = taken from the drawing's vector line work
(not dimensioned, "do not scale"), C = measured on a registered image; U = unknown.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon, box as sbox

W, H, D = 71.85, 150.01, 8.75
APPLE = "Apple, iPhone 18 Pro Dimensional Drawings (2026-09-09)"
fx = lambda x: round(x - W / 2, 3)  # front view x
bx = lambda x: round(W / 2 - x, 3)  # back view x, mirrored into front coordinates
ty = lambda y: round(H / 2 - y, 3)


def A(value, where, note=""):
    return {"value": value, "confidence": "A", "source": f"{APPLE}, {where}", **({"note": note} if note else {})}



def catmull(points, per_seg=8, alpha=0.5):
    """Centripetal Catmull-Rom through points[1:-1] (first/last are tangent guides)."""
    P = np.asarray(points, float)
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** alpha
        t2 = t1 + np.linalg.norm(p2 - p1) ** alpha
        t3 = t2 + np.linalg.norm(p3 - p2) ** alpha
        for t in np.linspace(t1, t2, per_seg, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(P[-2])
    return np.array(out)


def body_outline(corner_pts, per_seg=6):
    """Closed CCW outline from Apple's corner-profile points; returns Nx2 and unit outward normals."""
    c = catmull([[0, 26]] + corner_pts + [[26, 0]], per_seg)  # [inset from side, inset from top], side -> top
    tl = np.c_[-W / 2 + c[:, 0], H / 2 - c[:, 1]]  # top-left corner, running from the left side up to the top edge
    tr = np.c_[-tl[::-1, 0], tl[::-1, 1]]  # top edge down to the right side
    br = np.c_[-tl[:, 0], -tl[:, 1]]
    bl = np.c_[tl[::-1, 0], -tl[::-1, 1]]
    pts = np.vstack([tr[::-1], tl[::-1], bl[::-1], br[::-1]])  # CCW: right side up -> top -> left -> bottom
    pts = np.clip(pts, [-W / 2, -H / 2], [W / 2, H / 2])  # the spline may overshoot the flat sides by a few hundredths
    keep = np.r_[True, np.hypot(*np.diff(pts, axis=0).T) > 1e-6]
    pts = pts[keep]
    if Polygon(pts).exterior.is_ccw is False:
        pts = pts[::-1]
    d = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    n = np.c_[d[:, 1], -d[:, 0]]
    n /= np.linalg.norm(n, axis=1)[:, None]
    return pts, n


def radial(poly: Polygon, centre, n):
    out = []
    for th in np.linspace(0, 2 * math.pi, n, endpoint=False):
        ray = LineString([centre, (centre[0] + 200 * math.cos(th), centre[1] + 200 * math.sin(th))])
        hit = ray.intersection(poly.exterior)
        pts = [hit] if hit.geom_type == "Point" else list(hit.geoms)
        q = max(pts, key=lambda g: (g.x - centre[0]) ** 2 + (g.y - centre[1]) ** 2)
        out.append([round(q.x, 3), round(q.y, 3)])
    return out


def derive(m):
    """Geometry computed from the measured values, ready for the Blender build."""
    r3 = lambda a: [[round(float(x), 3), round(float(y), 3)] for x, y in a]
    pts, nrm = body_outline(m["body"]["cornerProfile"]["value"])
    off = lambda d: pts - nrm * d
    prof = m["body"]["edgeProfile"]["value"]
    stations = prof["back"][::-1] + [[0.0, 0.0]] + prof["front"]  # back inner edge -> side -> front
    dense = catmull([[5.5, -4.38]] + stations + [[4.0, 4.39]], 3)
    dense[:, 0] = np.maximum(dense[:, 0], 0.0)
    rim = int(np.argmin(np.abs(dense[:, 0] - 1.20) + np.abs(dense[:, 1] - 4.29)))  # frame/glass boundary
    d = {
        "note": "computed by build_measurements.py; not measurements themselves",
        "bodyOutline": r3(pts),
        "frameRings": [{"inset": round(float(i), 4), "z": round(float(z), 4), "points": r3(off(i))} for i, z in dense[: rim + 1]],
        "glassCrownRings": [{"inset": round(float(i), 4), "z": round(float(z), 4), "points": r3(off(i))} for i, z in dense[rim:]],
        "glassOutline": r3(off(1.20)),
        "glassCrownOutline": r3(off(2.61)),
        "activeOutline": r3(off(m["front"]["activeArea"]["value"]["inset"])),
    }
    o = m["rear"].get("outlines", {})
    if "cameraIsland" in o:
        island = Polygon(o["cameraIsland"]["polygon"])
        foot = Polygon(off(0.75)).intersection(sbox(-50, o["plateauBandBottom"]["bbox"][1], 50, 100)).buffer(-11.8).buffer(11.8)
        c = (0.0, round(island.centroid.y, 3))
        d["plateau"] = {"centre": list(c), "foot": radial(foot, c, 144), "top": radial(island, c, 144), "source": "foot = body outline inset 0.75 above y=27.05 with R12 lower corners (sheet 4 R12.00 / R11.8x, sheet 1 line work); top = cameraIsland line work", "confidence": "B"}
    d["antennaBreaks"] = {"sidesY": [55.58, -55.58], "topBottomX": [-16.5, 16.5], "width": None, "confidence": "B", "source": "sheet 1 line work (segment ends of the side and top/bottom runs); width is not drawn: unknown"}
    bat = m.get("internal", {}).get("battery")
    if bat and bat.get("area_mm2"):
        d["batteryThickness"] = {"value": round(19759 / bat["area_mm2"], 2), "confidence": "inferred", "source": "WekiHome 09:20 volume 19759 mm3 / traced footprint area; ignores edge rounding"}
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool-out", default="refs/out")
    a = ap.parse_args()
    out = Path(a.tool_out)
    m: dict = {"model": "iphone-18-pro", "units": "mm", "frame": "origin body centre; +x right, +y up looking at screen; +z screen"}
    s1 = "sheet 1 (PDF p.2)"
    m["body"] = {
        "width": A(W, f"{s1}, front view 'PRODUCT WIDTH'"),
        "height": A(H, f"{s1}, front view 'PRODUCT LENGTH'"),
        "thickness": A(D, f"{s1}, right view 'PRODUCT THICKNESS'"),
        "cornerProfile": A(
            [[0, 19.43], [0.04, 13.90], [0.92, 8.46], [3.80, 3.80], [8.46, 0.92], [13.90, 0.04], [19.43, 0]],
            f"{s1}, DETAIL A 'CORNER PROFILE (ALL FOUR CORNERS)'",
            "points [inset from side, inset from top] on the corner curve; symmetric about the diagonal",
        ),
        "edgeProfile": A(
            {"front": [[0.01, 1.50], [0.15, 2.99], [0.90, 4.24], [1.20, 4.29], [2.61, 4.38]], "back": [[0.0, -1.44], [0.17, -2.86], [0.97, -4.01], [2.35, -4.35], [3.79, -4.38]]},
            f"{s1}, DETAIL B 'PROFILE (ALL SIDES)'",
            "points [inset from outermost side, z]; the pairing of the inset and z call-outs is read off leader lines (pairing confidence medium)",
        ),
    }
    m["front"] = {
        "coverGlass": A({"size": [69.45, 147.61], "centre": [0, 0]}, f"{s1}, front view 'GLASS'"),
        "activeArea": A({"size": [66.57, 144.73], "inset": 2.64}, f"{s1}, front view 'DISPLAY ACTIVE AREA', '2.64 ALL AROUND'"),
        "flatStartInset": A(2.61, f"{s1}, front view '2.61 ALL AROUND ... START OF FLAT AREA'"),
        "dynamicIsland": A({"size": [15.66, 6.07], "centre": [fx(35.92), ty(7.99)]}, f"{s1}, front view (15.66, 6.07, 7.99, 35.92)"),
    }
    m["rear"] = {
        "plateauHeight": A(2.78, f"{s1}, right view 'BACK PLATE TO CAMERA PLATEAU'"),
        "lensGlassAbovePlateau": A(2.11, f"{s1}, right view 'CAMERA PLATEAU TO REAR CAMERA GLASS'"),
        "z": {"backPlate": round(-D / 2, 3), "plateauTop": round(-D / 2 - 2.78, 3), "lensGlass": round(-D / 2 - 2.78 - 2.11, 3)},
        "lensRingDiameter": A(16.58, f"{s1}, DETAIL D '3X Ø16.58'"),
        "lenses": {
            "ultraWide": A([bx(14.37), ty(14.37)], f"{s1}, DETAIL D 'REAR CAMERA 1'", "which camera is ultra-wide/main/tele is inferred from module shapes in the iFixit CT (confidence C)"),
            "main": A([bx(14.37), ty(33.61)], f"{s1}, DETAIL D 'REAR CAMERA 2'"),
            "tele": A([bx(32.49), ty(23.99)], f"{s1}, DETAIL D 'REAR CAMERA 3'"),
        },
        "flash": A({"centre": [bx(58.03), ty(13.82)], "diameter": 6.90}, f"{s1}, DETAIL D 'FLASH'"),
        "rearSensor": A({"centre": [bx(58.03), ty(34.16)], "diameter": 6.90}, f"{s1}, DETAIL D 'REAR SENSOR' (LiDAR window)"),
        "rearMic": A({"centre": [bx(58.03), ty(23.99)], "diameter": 1.15}, f"{s1}, DETAIL D 'REAR MIC'"),
        "appleLogo": A({"size": [16.32, 20.04], "centre": [bx(36.03), ty(91.20)]}, f"{s1}, back view"),
        "magsafeCentre": A([fx(35.92), ty(77.74)], "sheet 4 (PDF p.5), magnet keep-out centre; Ø57.50 keep-out"),
    }
    zc = 0.0  # "4.375" call-outs: every side feature is centred in the thickness
    m["sides"] = {
        "note": "y = centre along the side; len = full length; width = across the thickness, centred at z = 0 (4.375 call-outs); proud = protrusion",
        "left": {
            "actionButton": A({"y": ty(34.28), "len": 6.90, "width": 2.66, "proud": 0.45, "z": zc}, f"{s1}, left view (34.28, 2X 3.45, 3X 2.66); front view 0.45"),
            "volumeUp": A({"y": ty(48.43), "len": 11.20, "width": 2.66, "proud": 0.45, "z": zc}, f"{s1}, left view (48.43, 4X 5.60)"),
            "volumeDown": A({"y": ty(62.63), "len": 11.20, "width": 2.66, "proud": 0.45, "z": zc}, f"{s1}, left view (62.63, 4X 5.60)"),
            "simTray": A({"y": ty(111.97), "len": 19.44, "width": 2.56, "proud": 0.0, "z": zc}, f"{s1}, left view (111.97, 2X 9.72, 2.56); front view 'SIM TRAY 0.00'"),
        },
        "right": {
            "sideButton": A({"y": ty(55.53), "len": 17.70, "width": 2.66, "proud": 0.45, "z": zc}, f"{s1}, right view (55.53, 2X 8.85, 2.66)"),
            "cameraControl": A({"y": ty(98.40), "len": 17.10, "width": 3.03, "proud": 0.0, "z": zc}, f"{s1}, right view (98.40, 2X 8.55, 3.03); keep-out details on sheet 2"),
        },
        "bottom": {
            "usbC": A({"x": fx(35.92), "width": 9.00, "height": 3.14, "z": zc}, f"{s1}, DETAIL C (9.00, 3.14, 35.92)", "opening edges also listed at 31.43 / 40.42"),
            "screws": A({"x": [fx(29.00), fx(42.85)], "diameter": 1.50}, f"{s1}, bottom view '2X Ø1.50 SCREW'"),
            "portsLeft": A({"x": [fx(v) for v in (15.40, 17.65, 19.91, 22.16, 24.42)], "diameter": 1.53}, f"{s1}, bottom view: 4 speaker ports + bottom mic 2"),
            "portsRight": A({"x": [fx(v) for v in (47.43, 49.69, 51.94, 54.20, 56.45)], "diameter": 1.53}, f"{s1}, bottom view: includes bottom mic 1", "left/right assumes the bottom view is drawn screen-up (camera bump drawn below)"),
        },
    }
    # ---- tool outputs -------------------------------------------------------------------
    vec = out / "pdf_vectors.json"
    if vec.exists():
        views = {v["name"]: v for v in json.loads(vec.read_text())["views"]}
        src = f"{APPLE}, {s1}, vector line work via tools/measure/pdf_vectors.py"
        m["rear"]["outlines"] = {
            k: {"bbox": f["bbox_mm"], "size": f["size_mm"], "area": f["area_mm2"], "polygon": f["points_mm"], "confidence": "B", "source": src}
            for k, f in views["back"]["faces"].items()
            if k in ("backGlass", "cameraIsland", "plateauBandTop", "plateauBandLeft", "plateauBandBottom", "appleLogo")
        }
        m["front"]["dynamicIslandOutline"] = {"polygon": views["front"]["faces"]["dynamicIsland"]["points_mm"], "confidence": "B", "source": src}
        m["pdfScaleCheck"] = {v["name"]: {"mm_per_pt": v["mm_per_pt"], "xy_anisotropy_pct": v["scale_anisotropy_pct"]} for v in views.values()}
    reg = {}
    for f in sorted(out.glob("*.rectify.json")):
        r = json.loads(f.read_text())
        reg[f.name.replace(".rectify.json", "")] = {
            k: r[k] for k in ("image", "photo", "reference", "mode", "model", "mm_per_px", "rms_mm", "max_mm", "side_fit", "check_points", "inlier_residual_mm", "fiducials") if k in r
        }
    m["registrations"] = reg
    ol = out / "outlines.json"
    if ol.exists():
        m["internal"] = {o["id"]: {k: v for k, v in o.items() if k != "id"} | {"confidence": "C"} for o in json.loads(ol.read_text())["outlines"]}
    m["derived"] = derive(m)
    dst = Path(__file__).with_name("measurements.json")
    dst.write_text(json.dumps(m, indent=1))
    print(f"wrote {dst} ({dst.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
