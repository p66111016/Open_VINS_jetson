# 原生部署結果：2026-11-11

OpenVINS v2.7、Ceres 2.1.0、cv_bridge 3.2.1 與資料工具已完成原生建置，colcon 共 5 個套件成功。動態連結確認 OpenVINS 與 cv_bridge 使用主機 OpenCV 4.8，Ceres 與補充 Boost component libraries 從專案內載入。Ceres 未啟用 CUDA。沒有安裝或替換系統套件。

最終驗證目錄為 `results/run_20261111T233219`：100 張真實影像、2,370 筆 IMU，成功初始化並輸出 1,271 筆有限值里程計。OpenVINS 與 recorder 退出碼均為 0，沒有 fatal log。14 項資料測試通過，原專案與系統套件清單比對維持一致。

使用暫定相機／IMU 外參、時間偏移與雜訊，軌跡漂移明顯，尚未驗證定位精度。未接入 PX4。

第一次 300 張測試雖輸出 5,064 筆里程計，關閉時卻發生 mutex assertion。GDB 將崩潰定位到全域 ROS2Visualizer 的 image_transport publisher 銷毀階段。`scripts/apply_source_patches.py` 在主程式退出前提早釋放 viz/sys，build.sh 自動套用此本地修補；不修改 VIO 更新方程。離線設定也停用背景影像發布，recorder 處理正常關閉例外，runner 保存程序退出碼。修補後以真實資料驗證正常關閉。

硬體 driver 與實測標定依使用者要求延後。ROS 2 介面與 run_live.sh 入口已保留；PX4 bridge、Agent、EKF2 尚未實作／接入。機器可讀結果位於 results/deployment_status.json、build_manifest.json、linkage.json 與最終測試的 summary.json。

## 以下為最初部署的歷史紀錄，已由上述結果更新

本次僅寫入 `/home/user/mono-openvins-ros2`，測試暫存檔使用系統暫存目錄。沒有建立容器，沒有更動原專案，也沒有連接 PX4。

| 項目 | 狀態 |
|---|---|
| 獨立目錄、環境腳本 | 已建立；系統 Python 3.10，禁用 user site-packages，預設 domain 91 |
| 原專案／主機基準 | 記錄 30 個檔案 SHA256 及系統套件版本 |
| 系統依賴 | 沒有安裝、移除或升降級套件 |
| mono_openvins_tools | colcon 編譯通過 |
| 時間與資料正確性測試 | 9 項通過 |
| 合成資料 ROS 2 重播 | 兩個程序收到 10 張影像、102 筆 IMU、112 筆 /clock；精確時間戳與影像 payload 檢查通過 |
| DDS transport | sandbox 禁止列舉介面與建立 UDP socket，會出現 Fast DDS transport errors；同主機雙程序測試仍成功，不代表外部網路或 PX4 連線已驗證 |
| 候選歷史資料 | 已審核檔案存在性、時間分布、IMU 數值與缺口；身份／時鐘來源／單位軸向仍待確認 |
| OpenVINS、Ceres、cv_bridge | 缺上游原始碼，尚未編譯 |
| 真實影像 VIO | 未執行；缺確認的標定與資料身份 |
| PX4 bridge／Agent／EKF2 | 未實作或啟用；需韌體版本與匹配的歷史慣性重播方案 |

原始碼下載失敗：目前工具環境無法解析 `codeload.github.com`。以既有 curl 指令申請提權執行也被目前權限政策拒絕，因此沒有繞過網路限制。已建立 `scripts/fetch_sources.sh` 供具備網路的本機終端下載官方版本至專案內，後續使用 `scripts/build.sh`；這兩步的成功尚未驗證。

檢查結果存於 `results/`：

- `environment_before.json`：部署前基準。
- `environment_comparison.json`：原始保護檔案無變更、dpkg 版本清單相同。
- `dataset_115_audit.json`：影像／IMU 時間與資料檢查。
- `smoke_replay.json`：合成資料雙程序 DDS 測試結果。

使用者仍需確認 data/115 是否為本次指定資料，並提供相機／IMU 安裝外參與標定來源。不能用 EO／GPS 真值替代未知標定而宣稱 VIO 已成功。
