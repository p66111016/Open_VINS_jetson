# PX4 接口與成果輸出

## 已實作的轉換接口

`ros2 run mono_openvins_tools px4_bridge --config config/px4_bridge.json` 預設將原生 `/openvins/odomimu` 轉為 PX4 欄位格式，以 JSON 發布到 `/openvins/px4_preview`。歷史模式加 `--ros-args -p use_sim_time:=true`，並同時播放資料的 `/clock`。

已處理：global 的 Z-up 至任意航向 local FRD 旋轉、IMU 到機體 FRD 的旋轉、ROS xyzw 至 PX4 wxyz、位置及姿態 variance 旋轉、rad/s 角速度轉換、微秒時間欄、過期／未來／非遞增時間、非法協方差及位置跳動拒絕、輸出頻率限制。沒有真北依據，因此 pose_frame 使用 FRD，不冒稱 NED。position 保留 VIO IMU 量測點，飛控的 EKF2_EV_POS_* 應依實際量測點設定一次，不能重複補償。

目前不輸出可融合的 velocity：原生 Odometry 缺少完整姿態與速度交叉協方差，velocity 設為未知，正式模式以 NaN 表示。PX4 應先依韌體版本配置位置／高度／航向融合，不能啟用本介面未提供的速度量測。quality=-1 表示未知，不捏造追蹤品質。

跨程序預覽測試已接收 5 筆訊息，位置轉換 [1,2,3]→[1,-2,-3] 正確，程序退出碼為 0。18 項資料／座標測試通過。這不是飛控接收或 EKF2 融合測試。

## 正式發送仍需完成

待確認實際 PX4 韌體版本後，可執行 `bash scripts/fetch_px4_msgs.sh 1.XX`，將匹配 release 的訊息下載、解包與編譯到本專案。分支版本只提供基準；自訂韌體還需核對實際訊息定義。尚未替使用者猜版本、下載或啟動 Agent。

正式 `--publish-px4` 模式會直接使用 px4_msgs/msg/VehicleOdometry 發布 `/fmu/in/vehicle_visual_odometry`。此模式要求 live 來源、use_sim_time=false、已驗證標定／body 旋轉／訊息版本／時鐘／追蹤品質設定；另需 `/openvins/tracking_healthy` 的 Bool 健康心跳，超過 1 秒停止送出。原生 OpenVINS 沒有這個健康監控輸出，必須由後續 supervisor 根據初始化、特徵、innovation 等實際品質實作，不能只持續送 true。

估測器重置應由 lifecycle supervisor 發布 `/openvins/reset_counter`（UInt8，重置時遞增）。本接口不從位置猜測小幅重置，未提供自動恢復；時間倒退或超速會拒絕輸入。這些條件需在實機／匹配模擬資料上驗證。

現有資料標定未確認且漂移嚴重，因此 config 保持 preview，沒有連接飛控、修改 EKF2 參數或發布正式外部視覺輸入。歷史 VIO 不能直接搭配靜止飛控目前的 IMU 來驗證融合；需要同段慣性資料的 EKF2 replay，或另行錄製同步實機資料。

參考：[PX4 VehicleOdometry](https://docs.px4.io/main/en/msg_docs/VehicleOdometry)、[外部視覺融合](https://docs.px4.io/main/en/ros/external_position_estimation)。

## 與 cuVSLAM 對應的成果

最新結果為 `results/run_20261112T135330`。300 張影像、6,356 筆 IMU 全數發布，5,155 筆里程計，兩個程序退出碼均 0。266 張影像在 ±30 ms 內配到高頻 propagated odometry，狀態記為 POSE_AVAILABLE，並不等於已驗證 TRACKING。影像時間來自正規化資料的完整實際時間，不套假設 30 FPS。

- `odometry.csv`：原生高頻里程計。
- `trajectory_raw.csv`：高頻原始 XYZ／xyzw，使用 cuVSLAM 相容欄名。
- `trajectory.csv`：逐影像配對，含 Label、來源 frame_index、影像與里程計時間。
- `trajectory.frames.csv`：所有 300 張影像及有／無姿態、配對時間差。
- `trajectory_xy.png`、`trajectory_z.png`：未對齊軌跡。
- `camera_trajectory.mp4`：原圖、原始軌跡、Z、XYZ／RPY／四元數。
- `comparison/trajectory_aligned.csv`、`ground_truth.csv`、`alignment.json`、`results_report.json`。
- `results_report.json` 的 `fps` 包含來源影像頻率、重播目標／觀測頻率、OpenVINS 有計時更新的處理 FPS 與 mean/median/P95/max 毫秒、里程計輸出 Hz。處理 FPS 為更新次數除以日誌更新耗時總和，不包含影像解碼、ROS 等待與 IMU-only 工作；觀測重播 FPS 只涵蓋進度日誌窗口，不能當作整段端到端效能。
- `comparison/trajectory_xy_comparison.png`、`trajectory_z_comparison.png`。
- `comparison/camera_trajectory_comparison.mp4`：真值與全域 Sim3 對齊後的同步影片。

影片以 10 FPS 顯示，逐張對應實際來源影像，並非變動時間間隔的精確時間重採樣。沒有姿態的影格保留 NO POSE，不補造軌跡。圖與影片程式依原 cuVSLAM 專案版面複製至 scripts/report_support 後修改，原專案不變。

本次 Sim3 擬合尺度約 0.20682，位置 RMSE 約 67.50 m；保留尺度的 SE3 RMSE 約 589.87 m。相機中心與 IMU 量測點偏移也尚未知。這些結果清楚顯示目前軌跡不適合作為飛控導航輸入。Sim3 僅供離線診斷，真值擬合不回饋 OpenVINS 或 PX4，不將 EO 的 OPK 直接作為姿態誤差。

重新產生成果：

```bash
source scripts/ros_env.sh
/usr/bin/python3 scripts/export_results.py results/run_20261112T135330 --overwrite
```
