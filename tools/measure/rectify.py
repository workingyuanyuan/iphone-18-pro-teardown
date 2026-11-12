# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless>=4.9", "numpy>=1.26"]
# ///
"""Rectify a (near) top-down reference image into an orthographic image in phone-local millimetres.

    uv run tools/measure/rectify.py <job.json> [--out-dir DIR]

Two ways to find the image -> mm mapping, chosen by "mode" in the job file:

  "frame"   The phone's outer body is visible. Its outline is segmented, a straight line is fitted
            to each of the four flat sides, and the four line intersections (the corners of the
            body's bounding rectangle) are mapped to the known width x height. Corrects perspective.
  "points"  The outer body is not visible (cropped image). Named control points with known
            millimetre positions (lens centres, ports, screws) are used instead. Points may be
            refined automatically ("refine": {"type": "circle", "r_px": [lo, hi], "search_px": n}).
            "model" selects similarity (default, 4 dof), scale_translate (3 dof, for images
            known to be axis-aligned; use when the control points span a short baseline),
            affine or homography.

Job file (JSON), paths relative to the job file:
  {"image": "frame.png", "mode": "frame", "body_mm": [71.85, 150.01], "view": "front" | "back",
   "roi_px": [x0, y0, x1, y1], "px_per_mm": 20, "margin_mm": 2,
   "segment": "grabcut" | "chroma"   (chroma: coloured body on a neutral backdrop; ignores shadows),
   "check_points": [{"name": "...", "px": [x, y], "mm": [x, y]}]}
  {"image": "ct.png", "mode": "points", "model": "similarity", "view": "front",
   "points": [{"name": "lensTele", "px": [660, 390], "mm": [3.44, 51.02], "refine": {...}}],
   "extent_mm": [-36, -75.1, 36, 75.1], "px_per_mm": 20}

Coordinates: origin at the body centre, +y up. For "view": "front" +x is to the right in the image;
for "back" the image is mirrored so the output is still expressed in front-view coordinates.

Outputs <name>.ortho.png (orthoimage, x right / y up, px_per_mm), <name>.rectify.json (3x3 matrix
image px -> mm, scale, residuals) and <name>.rectify.debug.png.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def fit_line(pts: np.ndarray):
    """Robust total-least-squares line: returns (point, unit direction)."""
    vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    return np.array([x0, y0], np.float64), np.array([vx, vy], np.float64)


def intersect(l1, l2):
    (p, d), (q, e) = l1, l2
    t = np.linalg.solve(np.c_[d, -e], q - p)
    return p + t[0] * d


def segment_body(img, roi, job):
    x0, y0, x1, y1 = roi
    crop = img[y0:y1, x0:x1]
    if job.get("segment", "grabcut") == "chroma":
        # Coloured body on a neutral backdrop: distance in Lab a/b from the backdrop (ROI border
        # median). Cast shadows change lightness, not chroma, so they stay background.
        lab = cv2.cvtColor(cv2.GaussianBlur(crop, (0, 0), 1.5), cv2.COLOR_BGR2LAB).astype(np.float32)
        border = np.concatenate([lab[:6].reshape(-1, 3), lab[-6:].reshape(-1, 3), lab[:, :6].reshape(-1, 3), lab[:, -6:].reshape(-1, 3)])
        bg = np.median(border, axis=0)
        dist = np.hypot(lab[..., 1] - bg[1], lab[..., 2] - bg[2])
        d8 = np.clip(dist * 6, 0, 255).astype(np.uint8)
        thr = job.get("chroma_threshold") or cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0] / 6
        ring = (dist > thr).astype(np.uint8) * 255
        ring = cv2.morphologyEx(ring, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        cs, _ = cv2.findContours(ring, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        fg = np.zeros_like(ring)
        if cs:
            cv2.drawContours(fg, [max(cs, key=cv2.contourArea)], -1, 255, -1)  # filled outer contour
    else:
        mask = np.zeros(crop.shape[:2], np.uint8)
        m = max(4, int(0.02 * min(crop.shape[:2])))
        rect = (m, m, crop.shape[1] - 2 * m, crop.shape[0] - 2 * m)
        bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
        cv2.grabCut(crop, mask, rect, bgd, fgd, job.get("grabcut_iters", 4), cv2.GC_INIT_WITH_RECT)
        fg = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    fg = cv2.morphologyEx(cv2.morphologyEx(fg, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
    cs, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        raise SystemExit("frame mode: no foreground found in roi_px")
    c = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(np.float64) + [x0, y0]
    return c


def frame_corners(contour, job):
    """Fit lines to the four flat sides; return corners TL, TR, BR, BL in image px and the lines."""
    (cx, cy), (w, h), ang = cv2.minAreaRect(contour.astype(np.float32))
    if w > h:  # make h the long side
        w, h, ang = h, w, ang + 90
    th = np.deg2rad(ang)
    u, v = np.array([np.cos(th), np.sin(th)]), np.array([-np.sin(th), np.cos(th)])  # short, long axes
    if v[1] < 0:
        v = -v  # long axis points down the image
    if u[0] < 0:
        u = -u  # short axis points right
    rel = contour - [cx, cy]
    a, b = rel @ u, rel @ v
    keep = job.get("side_fraction", 0.68)  # central part of each side; avoids rounded corners
    tol = 0.06 * w
    sides = {
        "left": contour[(np.abs(b) < keep * h / 2) & (np.abs(a + w / 2) < tol)],
        "right": contour[(np.abs(b) < keep * h / 2) & (np.abs(a - w / 2) < tol)],
        "top": contour[(np.abs(a) < keep * 0.55 * w / 2) & (np.abs(b + h / 2) < tol)],
        "bottom": contour[(np.abs(a) < keep * 0.55 * w / 2) & (np.abs(b - h / 2) < tol)],
    }
    for k, p in sides.items():
        if len(p) < 10:
            raise SystemExit(f"frame mode: too few edge points on the {k} side")
    # Buttons, ports and shadows make outliers: RANSAC for the dominant straight line, then a
    # least-squares refit on its inliers.
    rng = np.random.default_rng(0)
    tol_px = job.get("side_inlier_px", 1.0)
    lines = {}
    for k, p in sides.items():
        best = None
        for _ in range(400):
            i, j = rng.choice(len(p), 2, replace=False)
            d = p[j] - p[i]
            n = np.hypot(*d)
            if n < 0.2 * len(p) ** 0.5:
                continue
            dist = np.abs((p - p[i]) @ np.array([-d[1], d[0]]) / n)
            inl = dist <= tol_px
            if best is None or inl.sum() > best.sum():
                best = inl
        lines[k] = fit_line(p[best])
        sides[k] = p[best]
    tl, tr = intersect(lines["top"], lines["left"]), intersect(lines["top"], lines["right"])
    br, bl = intersect(lines["bottom"], lines["right"]), intersect(lines["bottom"], lines["left"])
    return np.array([tl, tr, br, bl]), sides


def refine_circle(gray, px, spec):
    lo, hi = spec["r_px"]
    s = int(spec.get("search_px", hi + 30))
    x, y = int(round(px[0])), int(round(px[1]))
    x0, y0 = max(x - s - hi, 0), max(y - s - hi, 0)
    roi = cv2.GaussianBlur(gray[y0 : y + s + hi, x0 : x + s + hi], (0, 0), 1.5)
    cs = cv2.HoughCircles(roi, cv2.HOUGH_GRADIENT_ALT, 1.5, 5, param1=120, param2=spec.get("quality", 0.7), minRadius=int(lo), maxRadius=int(hi))
    if cs is None:
        return None
    cs = cs[0]
    d = np.hypot(cs[:, 0] + x0 - px[0], cs[:, 1] + y0 - px[1])
    cs, d = cs[d <= s], d[d <= s]
    if len(cs) == 0:
        return None
    # Sub-pixel refinement: strongest radial edge near the Hough radius along many rays, then a
    # least-squares circle through the consistent ones (Hough alone quantises to >1 px).
    c0, r0 = np.array([cs[0][0] + x0, cs[0][1] + y0], np.float64), float(cs[0][2])
    g = cv2.GaussianBlur(gray, (0, 0), 1.0).astype(np.float32)
    for _ in range(3):
        pts = []
        rs = np.arange(r0 - 6, r0 + 6, 0.25)
        for th in np.linspace(0, 2 * np.pi, 240, endpoint=False):
            xs, ys = c0[0] + rs * np.cos(th), c0[1] + rs * np.sin(th)
            prof = cv2.remap(g, xs.astype(np.float32)[None], ys.astype(np.float32)[None], cv2.INTER_LINEAR)[0]
            gr = np.abs(np.gradient(prof))
            k = int(gr.argmax())
            if 0 < k < len(rs) - 1 and gr[k] > 2:
                pts.append([xs[k], ys[k]])
        if len(pts) < 40:
            break
        p = np.array(pts)
        for _ in range(3):
            A = np.c_[2 * p, np.ones(len(p))]
            sol, *_ = np.linalg.lstsq(A, (p**2).sum(1), rcond=None)
            c = sol[:2]
            r = float(np.sqrt(sol[2] + c @ c))
            res = np.abs(np.hypot(*(p - c).T) - r)
            p = p[res <= max(0.5, np.percentile(res, 75))]
        c0, r0 = c, r
    return [float(c0[0]), float(c0[1])], [r0]


def solve(model, src, dst, sign=1.0):
    """sign = -1 for a back view (image x runs opposite to phone x)."""
    src, dst = np.asarray(src, np.float64), np.asarray(dst, np.float64)
    if model == "homography":
        H, _ = cv2.findHomography(src, dst, 0)
    elif model == "affine":
        A, _ = cv2.estimateAffine2D(src, dst, method=cv2.LMEDS if len(src) > 6 else 0, ransacReprojThreshold=1e9)
        H = np.vstack([A, [0, 0, 1]])
    elif model == "scale_translate":  # axis-aligned image: one scale + offset, no rotation
        s2 = src * [sign, -1]
        a, b = s2 - s2.mean(0), dst - dst.mean(0)
        sc = (a * b).sum() / (a**2).sum()
        H = np.diag([sign * sc, -sc, 1.0])
        H[:2, 2] = dst.mean(0) - sc * s2.mean(0)
    else:  # similarity with reflection allowed in y (image y is down, mm y is up): fit to y-flipped src
        s2 = src * [sign, -1]
        mu_s, mu_d = s2.mean(0), dst.mean(0)
        a, b = s2 - mu_s, dst - mu_d
        U, S, Vt = np.linalg.svd(b.T @ a)
        D = np.diag([1, np.sign(np.linalg.det(U @ Vt))])
        R = U @ D @ Vt
        sc = np.trace(np.diag(S) @ D) / (a**2).sum()
        t = mu_d - sc * R @ mu_s
        H = np.eye(3)
        H[:2, :2] = sc * R @ np.diag([sign, -1])
        H[:2, 2] = t
    return H


def apply(H, pts):
    p = np.c_[np.asarray(pts, np.float64), np.ones(len(pts))] @ H.T
    return p[:, :2] / p[:, 2:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    jp = Path(a.job)
    job = json.loads(jp.read_text())
    img_path = (jp.parent / job["image"]).resolve()
    img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {img_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    out_dir = Path(a.out_dir) if a.out_dir else jp.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    name = job.get("name", jp.stem)
    back = job.get("view", "front") == "back"
    sign = -1.0 if back else 1.0
    dbg = img.copy()
    report: dict = {"image": job["image"], "mode": job["mode"], "view": job.get("view", "front")}

    if job["mode"] == "frame":
        W, Hmm = job["body_mm"]
        roi = job.get("roi_px", [0, 0, img.shape[1], img.shape[0]])
        contour = segment_body(img, roi, job)
        corners, sides = frame_corners(contour, job)
        dst = np.array([[-W / 2, Hmm / 2], [W / 2, Hmm / 2], [W / 2, -Hmm / 2], [-W / 2, -Hmm / 2]]) * [sign, 1]
        H = cv2.getPerspectiveTransform(corners.astype(np.float32), dst.astype(np.float32)).astype(np.float64)
        extent = [-W / 2 - job.get("margin_mm", 2), -Hmm / 2 - job.get("margin_mm", 2), W / 2 + job.get("margin_mm", 2), Hmm / 2 + job.get("margin_mm", 2)]
        # residual of the side edge points against the ideal rectangle sides, in mm
        res = {}
        for k, p in sides.items():
            m = apply(H, p)
            target = {"left": -W / 2 * sign, "right": W / 2 * sign, "top": Hmm / 2, "bottom": -Hmm / 2}[k]
            d = (m[:, 0] if k in ("left", "right") else m[:, 1]) - target
            res[k] = {"rms_mm": round(float(np.sqrt(np.mean(d**2))), 3), "p95_mm": round(float(np.percentile(np.abs(d), 95)), 3)}
        report["side_fit"] = res
        e = [np.hypot(*(corners[i] - corners[(i + 1) % 4])) for i in range(4)]
        report["px_per_mm_sides"] = {"top": round(float(e[0]) / W, 3), "right": round(float(e[1]) / Hmm, 3), "bottom": round(float(e[2]) / W, 3), "left": round(float(e[3]) / Hmm, 3)}
        report["corners_px"] = corners.round(2).tolist()
        cv2.polylines(dbg, [contour.astype(np.int32)], True, (0, 255, 255), 1)
        cv2.polylines(dbg, [corners.astype(np.int32)], True, (0, 0, 255), 2)
    else:
        src, dst, names = [], [], []
        for p in job["points"]:
            px = p["px"]
            if "refine" in p:
                r = refine_circle(gray, px, p["refine"])
                if r is None:
                    print(f"  ! {p['name']}: refine failed, using given px")
                else:
                    px = r[0]
            if p.get("use", True):
                src.append(px), dst.append(p["mm"]), names.append(p["name"])
            cv2.drawMarker(dbg, (int(px[0]), int(px[1])), (0, 0, 255), cv2.MARKER_CROSS, 24, 2)
            cv2.putText(dbg, p["name"], (int(px[0]) + 8, int(px[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        H = solve(job.get("model", "similarity"), src, dst, sign)
        err = apply(H, src) - np.array(dst)
        report["control_points"] = [
            {"name": n, "px": [round(s[0], 2), round(s[1], 2)], "mm": d, "residual_mm": [round(float(e[0]), 3), round(float(e[1]), 3)]}
            for n, s, d, e in zip(names, src, dst, err)
        ]
        report["rms_mm"] = round(float(np.sqrt(np.mean(np.sum(err**2, axis=1)))), 3)
        report["max_mm"] = round(float(np.max(np.hypot(err[:, 0], err[:, 1]))), 3)
        corners_img = np.array([[0, 0], [img.shape[1], 0], [img.shape[1], img.shape[0]], [0, img.shape[0]]], np.float64)
        cm = apply(H, corners_img)
        extent = job.get("extent_mm") or [float(cm[:, 0].min()), float(cm[:, 1].min()), float(cm[:, 0].max()), float(cm[:, 1].max())]
        report["image_corners_mm"] = cm.round(3).tolist()

    # local scale at the image centre (px per mm)
    c = np.array([[img.shape[1] / 2, img.shape[0] / 2]])
    j = (apply(H, c + [1, 0]) - apply(H, c))[0], (apply(H, c + [0, 1]) - apply(H, c))[0]
    report["px_per_mm"] = {"x": round(1 / float(np.hypot(*j[0])), 4), "y": round(1 / float(np.hypot(*j[1])), 4)}
    report["mm_per_px"] = round((float(np.hypot(*j[0])) + float(np.hypot(*j[1]))) / 2, 5)

    for cp in job.get("check_points", []):
        m = apply(H, [cp["px"]])[0]
        report.setdefault("check_points", []).append(
            {"name": cp["name"], "measured_mm": m.round(3).tolist(), "expected_mm": cp["mm"], "error_mm": round(float(np.hypot(*(m - cp["mm"]))), 3)}
        )

    ppm = job.get("px_per_mm", 20)
    x0, y0, x1, y1 = extent
    # mm -> ortho px: x right, y up
    M = np.array([[ppm, 0, -x0 * ppm], [0, -ppm, y1 * ppm], [0, 0, 1]])
    size = (int(round((x1 - x0) * ppm)), int(round((y1 - y0) * ppm)))
    ortho = cv2.warpPerspective(img, M @ H, size, flags=cv2.INTER_LANCZOS4)
    report.update({"matrix_px_to_mm": H.tolist(), "ortho": {"file": f"{name}.ortho.png", "px_per_mm": ppm, "extent_mm": [round(v, 3) for v in extent]}})
    cv2.imwrite(str(out_dir / f"{name}.ortho.png"), ortho)
    cv2.imwrite(str(out_dir / f"{name}.rectify.debug.png"), dbg)
    (out_dir / f"{name}.rectify.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k not in ("matrix_px_to_mm",)}, indent=1))


if __name__ == "__main__":
    main()
