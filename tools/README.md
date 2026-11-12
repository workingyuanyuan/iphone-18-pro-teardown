# tools/

量測與建模用的離線工具，不會打包進網站。Python 腳本用 `uv run` 執行，相依套件寫在各檔開頭。

## measure/

| 腳本 | 作用 |
| --- | --- |
| `pdf_vectors.py` | 從向量尺寸圖（PDF）取出輪廓，換算成 mm 多邊形，並回報比例檢查。 |
| `rectify.py` | 把俯拍影像校正成正射圖並算出 px→mm。`frame` 模式用機身外框做透視校正；`points` 模式用已知座標的控制點（外框被裁掉時）。 |
| `register_pair.py` | 用共同的螺絲／螺柱，把一張照片對位到已校正的參考影像（例如 CT）。 |
| `contours.py` | 在正射圖上逐零件描輪廓（閾值、Canny、GrabCut、圓擬合或手描），輸出 mm 多邊形與「邊緣吻合度」。 |
| `overlay_official.py` | 把 measurements.json 裡的官方特徵畫到正射圖上，用來目視檢查對位。 |

每支機型的設定與結果放在 `measure/models/<model>/`。完整指令與目前的量測結果見 `docs/measurements.md`。

參考影像放在 `refs/`（不進版控）。這些影像只用來量測，不可當貼圖或放進網站。
