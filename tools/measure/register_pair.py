# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless>=4.9", "numpy>=1.26"]
# ///
"""Register a photo to an already-rectified reference of the same device using round fiducials.

A photograph of an opened phone is a perspective image and has no dimensioned landmarks of its own,
but it shares screws and standoffs with a CT / X-ray render that rectify.py has already tied to
millimetres. This script finds small circles (screw heads, bosses) in both images, pairs the ones
that land close together, fits a robust transform photo -> reference with RANSAC, and writes the
photo's own orthoimage + px->mm matrix. The inlier residual is the registration uncertainty; it
includes the photo's parallax between depth planes.

    uv run tools/measure/register_pair.py --photo P.png --ref R.png --ref-rectify R.rectify.json \\
        --name NAME --out-dir DIR [--model affine|similarity|homography] [--r-px 7 24] [--pair-px 28]

`--ref` must be the reference's original image (the one R.rectify.json's matrix applies to), and the
two images must already be roughly aligned (same framing within --pair-px pixels).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def circles(gray, rlo, rhi):
    g = cv2.GaussianBlur(gray, (0, 0), 1.2)
    cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT_ALT, 1.0, rlo * 1.5, param1=140, param2=0.82, minRadius=rlo, maxRadius=rhi)
    return np.zeros((0, 3)) if cs is None else cs[0].astype(np.float64)


def apply(H, pts):
    p = np.c_[np.asarray(pts, np.float64), np.ones(len(pts))] @ H.T
    return p[:, :2] / p[:, 2:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-rectify", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default="affine", choices=["affine", "similarity", "homography"])
    ap.add_argument("--r-px", nargs=2, type=int, default=[7, 24])
    ap.add_argument("--pair-px", type=float, default=28)
    ap.add_argument("--inlier-px", type=float, default=4.0)
    ap.add_argument("--match", default="circles", choices=["circles", "sift"], help="sift: SIFT keypoints + ratio test; for two frames of the same unit that are not pre-aligned")
    ap.add_argument("--photo-roi", nargs=4, type=int, help="x0 y0 x1 y1: only look for features here")
    ap.add_argument("--ref-roi", nargs=4, type=int)
    a = ap.parse_args()

    photo, ref = cv2.imread(a.photo), cv2.imread(a.ref)
    rr = json.loads(Path(a.ref_rectify).read_text())
    Href = np.array(rr["matrix_px_to_mm"])
    gp, gr = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)

    def roi_mask(g, roi):
        if not roi:
            return None
        m = np.zeros(g.shape, np.uint8)
        m[roi[1] : roi[3], roi[0] : roi[2]] = 255
        return m

    if a.match == "sift":
        sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02)
        clahe = cv2.createCLAHE(3.0, (8, 8))
        kp, dp = sift.detectAndCompute(clahe.apply(gp), roi_mask(gp, a.photo_roi))
        kr, dr = sift.detectAndCompute(clahe.apply(gr), roi_mask(gr, a.ref_roi))
        knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(dp, dr, k=2)
        good = [m for m, n in knn if m.distance < 0.75 * n.distance]
        if len(good) < 12:
            raise SystemExit(f"only {len(good)} SIFT matches")
        src = np.array([kp[m.queryIdx].pt for m in good])
        dst = np.array([kr[m.trainIdx].pt for m in good])
        cp, cr, pairs = np.c_[src, np.full(len(src), 4.0)], np.c_[dst, np.full(len(dst), 4.0)], [(i, i) for i in range(len(src))]
    else:
        cp, cr = circles(gp, *a.r_px), circles(gr, *a.r_px)
        # mutual nearest neighbours within pair-px
        pairs = []
        if len(cp) and len(cr):
            d = np.hypot(cp[:, None, 0] - cr[None, :, 0], cp[:, None, 1] - cr[None, :, 1])
            for i in range(len(cp)):
                j = int(d[i].argmin())
                if d[i, j] <= a.pair_px and int(d[:, j].argmin()) == i:
                    pairs.append((i, j))
        if len(pairs) < 6:
            raise SystemExit(f"only {len(pairs)} fiducial pairs found ({len(cp)} photo / {len(cr)} ref circles); adjust --r-px / --pair-px")
        src = np.array([cp[i, :2] for i, _ in pairs])
        dst = np.array([cr[j, :2] for _, j in pairs])
    if a.model == "homography":
        H, inl = cv2.findHomography(src, dst, cv2.RANSAC, a.inlier_px)
    else:
        f = cv2.estimateAffine2D if a.model == "affine" else cv2.estimateAffinePartial2D
        A, inl = f(src, dst, method=cv2.RANSAC, ransacReprojThreshold=a.inlier_px)
        H = np.vstack([A, [0, 0, 1]])
    inl = inl.ravel().astype(bool)
    Hmm = Href @ H  # photo px -> mm
    err_mm = apply(Hmm, src[inl]) - apply(Href, dst[inl])
    e = np.hypot(err_mm[:, 0], err_mm[:, 1])
    mm_all = apply(Href, dst[inl])
    report = {
        "photo": Path(a.photo).name,
        "reference": Path(a.ref).name,
        "model": a.model,
        "fiducials": {"photo_circles": len(cp), "ref_circles": len(cr), "pairs": len(pairs), "inliers": int(inl.sum())},
        "inlier_residual_mm": {"rms": round(float(np.sqrt(np.mean(e**2))), 3), "p95": round(float(np.percentile(e, 95)), 3), "max": round(float(e.max()), 3)},
        "inlier_spread_mm": {"x": [round(float(mm_all[:, 0].min()), 1), round(float(mm_all[:, 0].max()), 1)], "y": [round(float(mm_all[:, 1].min()), 1), round(float(mm_all[:, 1].max()), 1)]},
        "photo_to_ref_px": H.tolist(),
        "matrix_px_to_mm": Hmm.tolist(),
        "reference_rms_mm": rr.get("rms_mm"),
    }
    report["mm_per_px"] = rr.get("mm_per_px")
    ppm = rr["ortho"]["px_per_mm"]
    x0, y0, x1, y1 = rr["ortho"]["extent_mm"]
    M = np.array([[ppm, 0, -x0 * ppm], [0, -ppm, y1 * ppm], [0, 0, 1]])
    size = (int(round((x1 - x0) * ppm)), int(round((y1 - y0) * ppm)))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / f"{a.name}.ortho.png"), cv2.warpPerspective(photo, M @ Hmm, size, flags=cv2.INTER_LANCZOS4))
    report["ortho"] = {"file": f"{a.name}.ortho.png", "px_per_mm": ppm, "extent_mm": rr["ortho"]["extent_mm"]}
    dbg = photo.copy()
    for k, (i, j) in enumerate(pairs):
        col = (0, 255, 0) if inl[k] else (0, 0, 255)
        cv2.circle(dbg, (int(cp[i, 0]), int(cp[i, 1])), int(cp[i, 2]), col, 2)
        cv2.line(dbg, (int(cp[i, 0]), int(cp[i, 1])), (int(cr[j, 0]), int(cr[j, 1])), col, 1)
    cv2.imwrite(str(out / f"{a.name}.register.debug.png"), dbg)
    (out / f"{a.name}.rectify.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if "matrix" not in k and k != "photo_to_ref_px"}, indent=1))
    print("photo->ref px:", np.round(H, 5).tolist())


if __name__ == "__main__":
    main()
