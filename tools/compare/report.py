# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write docs/deviation.md from the compare tool's before/after metrics.

    uv run tools/compare/report.py [--before tools/compare/baseline/before.metrics.json]
                                   [--after refs/out/compare/after/metrics.json] [--out docs/deviation.md]

The "before" metrics of the old procedural three.js model are kept in tools/compare/baseline/ so
the table can be regenerated after that model's source was removed.
"""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--before", default="tools/compare/baseline/before.metrics.json")
ap.add_argument("--after", default="refs/out/compare/after/metrics.json")
ap.add_argument("--out", default="docs/deviation.md")
a = ap.parse_args()
B, A = json.loads(Path(a.before).read_text()), json.loads(Path(a.after).read_text())
bx = {r["feature"]: r for r in B["exterior"]}
bi = {r["part"]: r for r in B["internal"]}
f = lambda v: "—" if v is None else (f"{v:.2f}" if isinstance(v, (int, float)) else str(v))
val = lambda v: "—" if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, list) else (f"{v:g}" if isinstance(v, (int, float)) else str(v)))
ok = lambda e, g: "—" if e is None else ("✅" if e <= g else "❌")

L = ["# 各零件偏差表（重做前 vs. 重做後）", ""]
L += [
    "由 `npm run compare` 產生，請勿手改。量法定義在 `tools/compare/compare.py` 開頭；參考值的來源與信心等級在 `docs/measurements.md`。",
    "",
    "- **重做前**：原本用 three.js 程式產生的模型（`tools/compare/baseline/before.metrics.json`）。舊模型的子物件沒有名稱，外觀特徵取自舊 `build.ts` 的常數，內部零件取整個零件的投影（去掉細小突出物）。",
    "- **重做後**：Blender 產生的 `iphone-18-pro.dev.glb`，每個特徵直接從網格量。",
    "- 所有數值單位為 mm；比對前不做任何逐零件對齊。",
    "",
    "## 1. 外觀（標準：誤差 ≤ 0.5 mm）",
    "",
    "| 特徵 | 官方值 | 重做前 | 前誤差 | 重做後 | 後誤差 | 達標 |",
    "| --- | --- | --- | --- | --- | --- | --- |",
]
ext_after = [r for r in A["exterior"]]
for r in ext_after:
    b = bx.get(r["feature"], {})
    L.append(f"| {r['feature']} | {val(r['reference'])} | {val(b.get('model'))} | {f(b.get('error'))} | {val(r['model'])} | {f(r['error'])} | {ok(r['error'], 0.5)} |")
errs = [r["error"] for r in ext_after if r["error"] is not None]
berrs = [bx[r["feature"]]["error"] for r in ext_after if r["feature"] in bx and bx[r["feature"]].get("error") is not None]
L += [
    "",
    f"外觀共 {len(ext_after)} 項：重做後 {sum(e <= 0.5 for e in errs)} 項達標，最大誤差 {max(errs):.2f} mm。重做前可比的 {len(berrs)} 項裡有 {sum(e <= 0.5 for e in berrs)} 項達標，最大誤差 {max(berrs):.2f} mm。",
    "",
    "「輪廓」類的誤差是雙向最近距離 95 百分位取大值；其餘是數值差或中心點距離。鏡頭島與背蓋玻璃的參考是 Apple 圖面線稿（B 級，未標註尺寸）。",
    "",
    "## 2. 內部零件（標準：輪廓偏差 + 參考不確定度 ≤ 1 mm，只驗 XY）",
    "",
    "| 零件 | 參考影像 | 前：p95 / 形心偏移 | 後：p95 | 後：最大 | 後：形心偏移 | 參考不確定度 | p95＋不確定度 | 達標 | 另一來源交叉檢查 |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
]
unverified = []
for r in A["internal"]:
    if "contour_p95" not in r:
        unverified.append(r)
        continue
    b = bi.get(r["part"], {})
    before = f"{f(b.get('contour_p95'))} / {f(b.get('centroid_offset'))}" if "contour_p95" in b else "—"
    cross = "；".join(f"{v['source'].split('(')[0].strip()}：p95 {v['contour_p95']:.2f}、形心 {v['centroid_offset']:.2f}" for v in r.get("cross_check", {}).values()) or "—"
    gate = r.get("gate", 1.0)
    L.append(
        f"| `{r['part']}` | {r['reference'].replace('https://youtu.be/BLKegH19KGI ', '')} | {before} | {f(r['contour_p95'])} | {f(r['hausdorff'])} | {f(r['centroid_offset'])} | ±{r['uncertainty']:g} | {f(r['with_uncertainty'])} | {ok(r['with_uncertainty'], gate)}{'（標準 0.5）' if gate != 1.0 else ''} | {cross} |"
    )
done = [r for r in A["internal"] if "contour_p95" in r]
L += [
    "",
    f"有參考輪廓的 {len(done)} 個零件中 {sum(r['pass'] for r in done)} 個達標。",
    "",
    "讀這張表要注意三件事：",
    "",
    "1. 模型是照同一批參考輪廓建的，所以「後」的偏差主要反映圓角、倒角和建模簡化，**不是獨立的準確度證明**。真正獨立的證據是最後一欄（另一台機器、另一個來源量到的同一零件）和 `docs/measurements.md` §4 的對位檢查點。",
    "2. 「參考不確定度」是我對該影像的對位誤差加上描邊誤差的估計，不是量出來的統計值。",
    "3. 厚度方向沒有驗收：所有內部零件的 z 位置都是推估（見下）。",
    "",
    "## 3. 達不到標準、無法驗證的項目",
    "",
    "| 項目 | 原因 |",
    "| --- | --- |",
]
for r in unverified:
    L.append(f"| `{r['part']}` 的外形與位置 | {r.get('reason') or r.get('status')} |")
L += [
    "| 所有內部零件的 z 位置與厚度 | 沒有帶比例尺的側向剖面或 CT 切片。外觀各面的 z 用官方值；內部堆疊是依拆解順序排出來的推估值（`tools/blender/models/iphone_18_pro.py` 開頭的 Z 常數）。電池厚度 5.2 mm 由影片給的體積除以量到的面積反推。 |",
    "| `usbFlex` 的排線走向、`shields` 的螢幕排線護蓋 | 排線被電池和揚聲器蓋住；螢幕排線護蓋在可用畫面裡已經拆掉，範圍取自均熱板的缺口。 |",
    "| 零件內部的細節（接頭、屏蔽罩、螺絲、晶粒） | 只做示意，沒有逐一量測。 |",
    "| 天線斷點的寬度、邊框壁厚、內部肋位 | 圖面沒有標註，也沒有可量的影像。斷點位置取自線稿，寬度假設 1 mm。 |",
    "",
]
Path(a.out).write_text("\n".join(L))
print(f"wrote {a.out}: exterior {sum(e <= 0.5 for e in errs)}/{len(errs)} within 0.5 mm, internal {sum(r['pass'] for r in done)}/{len(done)} pass, {len(unverified)} unverified")
