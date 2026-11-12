# iPhone 18 Pro 量測紀錄

狀態（2026-11-11）：外觀數值齊全；內部零件已逐件描完輪廓（`tools/measure/models/iphone-18-pro/parts.json`），§5.1–5.2 是描輪廓前的紀錄，最新結果以 `measurements.json` 與 `docs/deviation.md` 為準。頂部揚聲器已在影片 11:46–11:47 找到位置（左上角）。

機器可讀版本：`tools/measure/models/iphone-18-pro/measurements.json`（由 `build_measurements.py` 產生，每個值都帶 `source` 與 `confidence`）。

## 座標與信心等級

- 座標：phone-local mm，原點在機身中心；**從螢幕側看** +x 向右、+y 向上，+z 指向螢幕。
- Apple 圖面的基準在各視圖左上角，換算：正面 `x = x圖 − 35.925`、背面 `x = 35.925 − x圖`（鏡像成正面座標）、`y = 75.005 − y圖`。
- 信心等級：
  - **A**：Apple 圖面上有標註尺寸的數值。
  - **B**：取自 Apple 圖面的向量線稿，圖上沒有標註尺寸（圖面註明 do not scale）。已用有標註的特徵驗證線稿比例，見 §2。
  - **C**：在已對位的照片／CT 上量得，附對位誤差。
  - **unknown**：沒有依據，不猜。

## 1. 來源

| 代號 | 來源 | 用途 | 備註 |
| --- | --- | --- | --- |
| APPLE | Apple《iPhone 18 Pro Dimensional Drawings》2026-09-09，5 頁向量 PDF。<https://developer.apple.com/download/files/accessories/dimensional-drawings/iphone-18-pro.pdf>（索引頁 <https://developer.apple.com/accessories/dimensional-drawings/>） | 全部外觀 | 這份就是 18 Pro 專屬圖面，不需要替代來源。頁碼以 PDF 頁為準：p.2 = sheet 1，p.3 = sheet 2（相機控制），p.4 = sheet 3（鏡頭／感測器視錐），p.5 = sheet 4（天線與 MagSafe 禁區）。 |
| IFIXIT-CT | iFixit × Lumafield CT 渲染圖 `iPhone_18_Pro_CT_01…10.png`、`CT_Re`（1206×2622）。文章 <https://www.ifixit.com/News/119329/inside-the-tiny-unfixable-eye-iphone-18-pro-and-pro-max-teardown>，圖檔 `https://valkyrie.cdn.ifixit.com/media/2026/09/22224223/iPhone_18_Pro_CT_01.png` 等 | 內部零件 XY 定位（真正射） | **eSIM 版**。10 張是同一份體積資料的不同配色，不是深度切片。 |
| IFIXIT-PHOTO | iFixit 桌布 `iPhone_18_Pro_Wallpaper_Battery / NoBattery / Hybrid`（同文章，`…/22224227/…`、`…/22224228/…`） | 內部零件輪廓 | **eSIM 版**。是透視照片，不是正射；與 CT 的取景差約 1.6%。 |
| WEKI | 微機分 WekiHome 拆解影片 <https://youtu.be/BLKegH19KGI>，4K。俯拍畫面 03:01、05:28、10:19；主板 12:00 | 實體 SIM 版特有的零件（電池、SIM 卡座）與交叉驗證 | **實體 SIM 國行版**，即 `parts.ts` 描述的那一台。 |
| IFIXIT-BENCH | iFixit 桌面照 `iPhone-18-TD_78.jpg`（全零件排列）、`Logic-board-left-SOC.jpg`、`Logic-board-right-storage.jpg`、`iPhone-18-TD_3-copy.jpg`（均熱板） | 被遮住的零件外形 | 透視、未對位，只能量比例。 |

找過但沒有的：Creative Electron X 光（查無 18 Pro 版本）；Notebookcheck 提到的上市前外流 X 光（網站拒絕存取，未取得）；有深度比例尺的側向剖面或 CT 切片（查無）。

參考影像只放在 `refs/`（已加入 `.gitignore`），只用來量測，不會進版控，也不會當貼圖。

## 2. 圖面線稿的比例驗證

`pdf_vectors.py` 把 PDF 線段串成輪廓，並以機身 71.85 × 150.01 定比例。

| 檢查 | 圖面標註 | 線稿量得 | 差 |
| --- | --- | --- | --- |
| x／y 比例一致性（正面、背面） | — | 0.029%、0.005% | — |
| 鏡頭外環直徑 | 16.58 | 16.578–16.580 | ≤ 0.002 |
| 鏡頭 1 中心（背面圖） | (14.37, 14.37) | (14.365, 14.360) | ≤ 0.01 |
| 鏡頭 3 中心 | (32.49, 23.99) | (32.488, 23.982) | ≤ 0.01 |
| 閃光燈中心／直徑 | (58.03, 13.82)／6.90 | (58.034, 13.811)／6.900 | ≤ 0.01 |
| 動態島 | 15.66 × 6.07 | 15.65 × 6.07 | 0.01 |
| 顯示區 | 66.57 × 144.73 | 66.57 × 144.72 | 0.01 |

結論：線稿是照比例輸出的，B 級輪廓的可信誤差約 ±0.05 mm。它仍然不是 Apple 承諾的尺寸。

## 3. 外觀數值

### 3.1 機身

| 項目 | 值 (mm) | 來源 | 信心 |
| --- | --- | --- | --- |
| 寬 × 高 × 厚 | 71.85 × 150.01 × 8.75 | APPLE p.2 正視圖、右視圖 | A |
| 四角輪廓點（距側邊, 距頂邊） | (0, 19.43) (0.04, 13.90) (0.92, 8.46) (3.80, 3.80) (8.46, 0.92) (13.90, 0.04) (19.43, 0) | APPLE p.2 DETAIL A | A |
| 側邊截面，螢幕側（距最外緣, z） | (0.01, 1.50) (0.15, 2.99) (0.90, 4.24) (1.20, 4.29) (2.61, 4.38) | APPLE p.2 DETAIL B | A（數值）；哪個內縮配哪個 z 是依引線判讀，信心中等 |
| 側邊截面，背面側 | (0.00, −1.44) (0.17, −2.86) (0.97, −4.01) (2.35, −4.35) (3.79, −4.38) | 同上 | 同上 |
| 螢幕玻璃 | 69.45 × 147.61，置中 | APPLE p.2 | A |
| 顯示區 | 66.57 × 144.73，距外緣 2.64 | APPLE p.2 | A |
| 正面平面起點 | 距外緣 2.61 | APPLE p.2 | A |
| 動態島 | 15.66 × 6.07，中心 (0, 67.015) | APPLE p.2 | A |
| 天線斷點位置 | unknown（圖上有畫線、沒有標註；可從線稿取，B 級，尚未擷取） | APPLE p.2 | — |
| 邊框壁厚、內部肋位 | unknown | — | — |

### 3.2 背面與鏡頭

| 項目 | 值 (mm) | 來源 | 信心 |
| --- | --- | --- | --- |
| 背板 z | −4.375 | 厚度 8.75 的一半 | A |
| 鏡頭凸台高度 | 2.78（頂面 z = −7.155） | APPLE p.2 右視圖 | A |
| 鏡頭玻璃高出凸台 | 2.11（玻璃面 z = −9.265） | APPLE p.2 右視圖 | A |
| 鏡頭外環直徑 | 16.58（3 顆） | APPLE p.2 DETAIL D | A |
| Rear Camera 1 中心 | (21.555, 60.635) | APPLE p.2 DETAIL D (14.37, 14.37) | A |
| Rear Camera 2 中心 | (21.555, 41.395) | DETAIL D (14.37, 33.61) | A |
| Rear Camera 3 中心 | (3.435, 51.015) | DETAIL D (32.49, 23.99) | A |
| 哪顆是超廣角／主鏡頭／長焦 | 1 = 超廣角、2 = 主鏡頭、3 = 潛望長焦 | IFIXIT-CT 模組外形判讀 | C |
| 閃光燈 | Ø6.90，中心 (−22.105, 61.185) | DETAIL D (58.03, 13.82) | A |
| LiDAR 視窗（Rear Sensor） | Ø6.90，中心 (−22.105, 40.845) | DETAIL D (58.03, 34.16) | A |
| 後置麥克風 | Ø1.15，中心 (−22.105, 51.015) | DETAIL D (58.03, 23.99) | A |
| 鏡頭島（凸起的那塊）外輪廓 | 61.61 × 37.73，x ±30.805，y 32.157…69.888 | APPLE p.2 背面線稿 | B |
| 凸台外緣 | x 約 ±35.17，y 約 27.05…74.26 | 同上（由三段邊帶推得） | B |
| 背蓋玻璃 | 64.07 × 97.26，x ±32.035，y −71.121…26.143，面積 6155 mm² | 同上 | B |
| Apple 標誌 | 16.32 × 20.04，中心 (−0.105, −16.195) | APPLE p.2 背面圖 | A |
| MagSafe 中心 | (0, −2.735)，禁區 Ø57.50 | APPLE p.5 (35.92, 77.74) | A |
| 鏡環各層直徑（內圈、鏡片） | 15.30／14.28／14.23／13.97／13.93／12.86／12.81 | 線稿同心圓 | B |
| 鏡頭島與凸台的倒角半徑、各層 z | unknown（圖上只有 2.78 與 2.11） | — | — |

### 3.3 側邊與底部

y 為沿邊的中心位置；長度為全長；寬度指厚度方向，全部置中於 z = 0（圖上的 4.375）。

| 項目 | y 或 x | 長 | 寬 | 凸出 | 來源 | 信心 |
| --- | --- | --- | --- | --- | --- | --- |
| 操作按鈕（左） | y 40.725 | 6.90 | 2.66 | 0.45 | APPLE p.2 左視圖 34.28、2X 3.45 | A |
| 音量＋（左） | y 26.575 | 11.20 | 2.66 | 0.45 | 48.43、4X 5.60 | A |
| 音量－（左） | y 12.375 | 11.20 | 2.66 | 0.45 | 62.63 | A |
| SIM 卡托（左） | y −36.965 | 19.44 | 2.56 | 0 | 111.97、2X 9.72、2.56 | A |
| 側邊按鈕（右） | y 19.475 | 17.70 | 2.66 | 0.45 | 右視圖 55.53、2X 8.85 | A |
| 相機控制（右） | y −23.395 | 17.10 | 3.03 | 0 | 98.40、2X 8.55、3.03；細節在 p.3 | A |
| USB-C 開口 | x 0 | 9.00 | 3.14 | — | DETAIL C | A |
| 底部螺絲 ×2 | x ±6.925 | Ø1.50 | — | — | 底視圖 29.00、42.85 | A |
| 底部左側孔 ×5（4 揚聲器＋麥克風 2） | x −20.525、−18.275、−16.015、−13.765、−11.505 | Ø1.53 | — | — | 底視圖 | A；左右方向假設底視圖是螢幕朝上繪製 |
| 底部右側孔 ×5（含麥克風 1） | x 11.505、13.765、16.015、18.275、20.525 | Ø1.53 | — | — | 底視圖 | 同上 |
| 相機控制凹陷深度與倒角 | p.3 有禁區剖面（0.18、0.40、0.63 等），尚未換算成幾何 | APPLE p.3 | 待讀 |

## 4. 影像對位結果

| 影像 | 方法 | 比例 | 誤差 |
| --- | --- | --- | --- |
| IFIXIT-CT（CT_01、CT_07） | 3 顆鏡頭中心（次像素圓擬合）＋閃光燈當控制點；模型為「單一比例＋平移，無旋轉」 | 0.0552 mm/px | 控制點 RMS 0.13、最大 0.19 mm。檢查點：USB-C 中心線 x 偏 0.27 mm；MagSafe 磁環中心量得 (0.02, −2.29)，官方 (0, −2.735)，差 0.45 mm。 |
| IFIXIT-PHOTO NoBattery | 與 CT 自動配對 17 個螺絲／螺柱，RANSAC 仿射 | 同 CT | 配對殘差 RMS 0.07、最大 0.11 mm（y 範圍 −59…56） |
| IFIXIT-PHOTO Battery | 同上，15 個配對 | 同 CT | RMS 0.10、最大 0.21 mm |
| WEKI 10:19 | 機身外框：色度分割（排除陰影）→ 四邊 RANSAC 直線 → 單應矩陣 | 0.102 mm/px | 四邊直線殘差 RMS 0.05–0.06 mm；上下邊比例差 1.2%（透視）。尚未做獨立檢查點。 |

對位的已知限制：

- CT 影像的範圍幾乎就是顯示區（−33.26…33.36 × −72.22…72.61），控制點集中在上方 20 mm。鏡頭鏡筒本身會浮動（OIS），兩顆同 x 的鏡頭量出來差 0.29 mm，所以不用它們解旋轉。**CT 座標的不確定度估為上半部 ±0.2 mm、下半部 ±0.5 mm。**
- 照片是透視影像。對位用的螺絲大多在中層，離這個平面越遠的零件視差越大；相機高度 unknown，所以視差量 unknown，目前只能靠 CT 交叉比對來界定。
- WEKI 的單應矩陣定在邊框前緣平面（z ≈ +4.4），內部零件低 1–7 mm，同樣有視差。

## 5. 內部零件

### 5.1 已量到的

| 零件 | 值 (mm) | 來源 | 信心 | 備註 |
| --- | --- | --- | --- | --- |
| MagSafe 磁環 | 外徑 52.9、內徑 47.6，中心 (0.02, −2.29) | IFIXIT-CT 07，圓擬合 | C（±0.5） | 中心應以官方 (0, −2.735) 為準 |
| A20 Pro 屏蔽蓋／導熱墊 | 15.2 × 16.7，中心 (−7.81, 23.43) | IFIXIT-PHOTO NoBattery，閾值法，邊緣吻合度 1.00 | C（±0.3） | WEKI 10:19 量得中心 (−8.05, 24.31)，但那次輪廓外溢，尺寸不可用 |
| Taptic Engine | 18.5 × 8.45，中心 (15.69, −62.71) | IFIXIT-PHOTO NoBattery，吻合度 0.93 | C（±0.5），**待覆核** | 只抓到黑色本體，兩端銀色端蓋沒算進去；CT 量到的是內部質量塊，不是外殼 |
| 電池（實體 SIM 版） | 外接範圍約 x −29.6…30.6，y −54.8…13.1；左側有 SIM 缺口、左下有揚聲器缺口 | WEKI 10:19，目視讀圖 | C（±1），**待描輪廓** | 自動閾值法外溢到 SIM 卡座與邊框支架，結果標為 review，未採用 |

### 5.2 還沒量的（工具已就緒，要逐件給搜尋框或手描）

| 零件 id | 最佳來源 | 預期做法 | 預期信心 |
| --- | --- | --- | --- |
| `vc` | IFIXIT-PHOTO Battery、WEKI 05:28 | 手描（黑底黑件，自動邊緣不可靠） | C ±0.5；eSIM 與 SIM 版外形是否相同 unknown |
| `battery` | WEKI 10:19 | 閾值法＋人工覆核 | C ±0.5 |
| `apBoard`／`rfBoard` | WEKI 12:00（板子單獨放在黑底上）定外形，IFIXIT-CT 定位置 | 外形自動、位置用螺柱對位 | 外形 C ±0.3、位置 C ±0.5 |
| `rearCamera`（3 個模組） | IFIXIT-CT 01 | 閾值法；鏡頭中心直接用官方值 | C ±0.3 |
| `faceId`、前鏡頭 | IFIXIT-PHOTO NoBattery | 手描 | C ±0.5 |
| `bottomSpeaker`、`micModule` | IFIXIT-PHOTO NoBattery、WEKI 10:19 | 手描 | C ±0.5 |
| `lidar`、`topAntenna` | IFIXIT-CT 01；視窗中心用官方值 | 手描 | C ±0.5 |
| `simReader`、`simTray` 內部 | WEKI 10:19、15:14 | 手描；卡托外露面用官方值 | C ±1 |
| `shields`、`usbFlex` | WEKI 03:24 附近、IFIXIT-BENCH | 手描 | C ±1；排線走向多半被遮住 |
| `backGlass` 內側線圈 | IFIXIT-CT 07；WEKI 03:01 | 圓擬合 | C ±0.5 |
| `topSpeaker` | 目前的俯拍畫面裡找不到它的位置 | 要再看 WEKI 11:48 一帶 | **位置 unknown** |
| `modem`、`n1`、`nand`、`soc` 內部晶粒 | IFIXIT-BENCH、WEKI 14:10–14:55 | 在板子外形內按比例定位 | C ±1（相對於板子） |

### 5.3 厚度方向（z）

| 項目 | 值 | 依據 |
| --- | --- | --- |
| 外觀各面的 z | 見 §3 | A |
| 螢幕總成厚度、均熱板厚度、電池厚度、主板各層高度、內背板位置、線圈厚度 | **unknown** | 沒有帶比例尺的側向剖面。影片給了電池體積約 19759 mm³（09:20），等電池輪廓面積量到後可以反推厚度（推算值，信心低）。 |
| 堆疊順序 | 螢幕 → 均熱板（電池黏在其背面）→ 電池、主板、鏡頭 → 內背板 → 線圈 → 背蓋玻璃 | WEKI 拆解順序 |

## 6. 重現方式

```bash
uv run tools/measure/pdf_vectors.py refs/apple/iphone-18-pro.pdf --config tools/measure/models/iphone-18-pro/pdf_views.json --out refs/out/pdf_vectors.json --debug-dir refs/out/debug
uv run tools/measure/rectify.py tools/measure/models/iphone-18-pro/jobs/ifixit-ct01.json --out-dir refs/out
uv run tools/measure/rectify.py tools/measure/models/iphone-18-pro/jobs/ifixit-ct07.json --out-dir refs/out
uv run tools/measure/rectify.py tools/measure/models/iphone-18-pro/jobs/weki-1019.json --out-dir refs/out
uv run tools/measure/register_pair.py --photo refs/ifixit/iPhone_18_Pro_Wallpaper_NoBattery-1.png --ref refs/ifixit/iPhone_18_Pro_CT_01.png --ref-rectify refs/out/ifixit-ct01.rectify.json --name ifixit-photo-NoBattery --out-dir refs/out
uv run tools/measure/contours.py tools/measure/models/iphone-18-pro/parts.json --rectified-dir refs/out --out refs/out/outlines.json --debug-dir refs/out/debug
uv run tools/measure/models/iphone-18-pro/build_measurements.py
```

換機型：複製 `tools/measure/models/iphone-18-pro/` 改設定即可，四支腳本不含機型常數。
