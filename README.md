# 拆機實驗室（Phone Teardown Lab）

用 3D 互動方式一層層拆開手機，讓一般人看懂手機裡的每個零件。初版收錄 **iPhone 18 Pro**，內容依據微機分 WekiHome 的拆解影片（<https://youtu.be/BLKegH19KGI>，2026-09-20）。

## 開發

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # 組裝邏輯與零件資料的單元測試
npm run build      # 型別檢查 + 打包到 dist/（純靜態網站，可放任何靜態主機）
```

## 功能

- **自由拆解＋分層限制**：只有「露出來」的零件拆得下來；被擋住時會標出擋住它的零件，也可以按「幫我拆到這裡」。
- **裝回**：會自動先移開蓋在上面的零件、放回去，再把它們裝回原位。支援復原與全部組回。
- **導覽「下一步」**：照影片的拆解順序一步步拆，每步附一句說明。
- **鏡頭**：自由環繞，加上 45°、正面、背面、側面四個預設視角；零件特寫會淡化其他零件、隱藏擋住它的零件；另有 X 光（外殼半透明）和爆炸圖滑桿。
- **零件卡**：白話說明、規格、拆解發現。每條資訊都附影片時間戳，點了直接跳到影片該處。
- **彩蛋**：MagSafe 線圈範圍、Face ID 紅外光點、撕開均熱板貼紙、掀開 A20 Pro 頂蓋看 WMCM 封裝。
- 手機版改成底部分頁面板（零件／介紹／零件盤）。另支援鍵盤操作：Esc 離開、Delete 拆下、Ctrl+Z 復原、N 下一步。

## 架構

```
src/
  core/        純邏輯（不依賴 three.js，可單元測試）
    types.ts     PartDef / PhoneModel 資料型別
    assembly.ts  安裝狀態、遮擋關係、拆卸／裝回計畫、導覽、資料驗證
  engine/      three.js
    stage.ts     renderer、相機、OrbitControls、按需重繪、鏡頭飛行
    viewer.ts    每個零件的位置／透明度／高亮／彩蛋，皆由狀態推導
    tween.ts     動畫
  builders/    共用的程序化幾何、材質與 canvas 貼圖
  data/phones/ 每支手機一個資料模組（零件清單＋幾何建構）
  ui/          DOM 介面與控制器
```

### 新增一支手機

1. 在 `src/data/phones/<model>/` 建立：
   - `parts.ts`：零件清單（`blockedBy` 遮擋關係、`removeDir`、`explode`、說明與時間戳）以及 `guideOrder`。
   - `build.ts`：用 `src/builders` 建出每個零件 id 對應的 `Object3D`（單位 mm，+z 為螢幕側）。
   - `index.ts`：匯出 `PhoneModel`。
2. 加進 `src/data/phones/index.ts` 的 `phones` 陣列。
3. 在 `tests/assembly.test.ts` 加一段 `validateParts` 檢查。它會抓出未知 id、循環遮擋，以及導覽順序中不合法的步驟。

## 資料準確度

- 規格與小知識皆來自拆解影片，並標註時間戳。
- 3D 模型由 Blender 腳本依量測資料產生（`npm run build:models`）：外觀用 Apple 官方尺寸圖，內部零件依拆解影像量測。量測來源見 `docs/measurements.md`，偏差表見 `docs/deviation.md`；厚度方向與被遮住的零件是推估值。
