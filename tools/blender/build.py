"""Build a phone model with headless Blender and export GLB files.

    blender -b --python tools/blender/build.py -- --model iphone_18_pro [--out public/models] [--dev-out refs/out]

Writes <out>/<model-id>.raw.glb (merged: one mesh per part / material / toggle state; compressed
afterwards by `npm run build:models`) and <dev-out>/<model-id>.dev.glb (every sub-object separate
and named, for tools/compare). Prints triangle and mesh counts per part.
"""
import argparse
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# Blender's bundled/system Python may lack numpy; `npm run build:models` installs it into .vendor.
sys.path[:0] = [str(HERE), str(HERE / "models"), str(HERE / ".vendor")]

from lib import Builder  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="iphone_18_pro")
    ap.add_argument("--out", default=str(ROOT / "public" / "models"))
    ap.add_argument("--dev-out", default=str(ROOT / "refs" / "out"))
    a = ap.parse_args(argv)
    mod = importlib.import_module(a.model)
    m = json.loads((ROOT / mod.MEASUREMENTS).read_text())
    b = Builder(mod.COLORS, mod.CLASSES, mod.SPECIALS)
    mod.build(b, m)
    out, dev = Path(a.out), Path(a.dev_out)
    out.mkdir(parents=True, exist_ok=True)
    dev.mkdir(parents=True, exist_ok=True)
    stats = b.stats()
    b.export(dev / f"{mod.MODEL_ID}.dev.glb")
    b.merge()
    merged = b.stats()
    b.export(out / f"{mod.MODEL_ID}.raw.glb")
    total = sum(s["triangles"] for s in stats.values())
    report = {
        "model": mod.MODEL_ID,
        "triangles": total,
        "meshes": sum(s["objects"] for s in merged.values()),
        "parts": {k: {"triangles": stats[k]["triangles"], "meshes": merged[k]["objects"]} for k in stats},
    }
    (out / f"{mod.MODEL_ID}.stats.json").write_text(json.dumps(report, indent=1))
    print("BUILD_REPORT", json.dumps(report))


main()
