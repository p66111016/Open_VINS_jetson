# 離線實驗與未來實機接口

依使用者要求，現階段不等待實體相機／IMU 或實測標定。使用現有歷史資料建立離線實驗路徑；實機接入與標定移到未來階段。

## 已完成的離線部分

`results/20260622_200hz/normalized_experimental` 包含 8,447 張影像的路徑／時間，以及 168,779 筆 IMU；沒有複製原始圖片或更改六軸量測。manifest 保留 `reviewed: false` 和 `exploratory: true`，不把暫定條件記成已驗證。

`config/offline_experimental` 提供 OpenVINS 啟動參數：單目、200 Hz IMU、動態初始化、約 10 Hz 視覺追蹤。沿用原 cuVSLAM 的相機內參假設，重播器先套完整五係數去畸變。未知的相機／IMU 外參暫設 identity，時間偏移暫設 0，IMU 雜訊使用通用占位值。這些設定只供流程實驗；初始化可能失敗，軌跡不能視為定位精度驗證。已完成 OpenVINS 本體載入與 100 張真實歷史影像測試；軌跡漂移明顯，沒有精度驗證。

資料準備（已完成，輸出存在時拒絕覆寫）：

```bash
source scripts/ros_env.sh
ros2 run mono_openvins_tools dataset prepare \
  --config config/dataset_20260622_200hz.json \
  --output results/20260622_200hz/normalized_experimental --exploratory
```

已用真實資料做兩個程序的 ROS 2 傳輸測試，收到 10 張原始影像、576 筆 IMU、586 筆 clock；影像 hash、時間戳與 IMU 六軸值完全一致。這是 ROS 傳輸驗證，沒有執行 OpenVINS。測試命令：

```bash
source scripts/ros_env.sh
/usr/bin/python3 scripts/smoke_replay.py \
  --dataset results/20260622_200hz/normalized_experimental \
  --max-frames 10 --exploratory
```

待原始碼下載與編譯完成，可直接啟動離線估測流程：

```bash
bash scripts/run_offline.sh \
  results/20260622_200hz/normalized_experimental \
  config/offline_experimental 300 0.25 --exploratory
```

每次輸出紀錄 dataset manifest、calibration status 與實驗模式，不啟動 PX4 publisher。上游原始碼已由使用者下載完成，本體與依賴已原生建置成功。ROS 2 關閉時的全域 publisher 生命週期問題已由 apply_source_patches.py 修補；最近一次 100 張影像測試的兩個程序退出碼均為 0。

## 實機接口

介面定義集中於 `config/sensor_interface.yaml`：

| Topic | 訊息 | 實機 driver 要求 |
|---|---|---|
| `/openvins/input/image_raw` | sensor_msgs/msg/Image | mono8，依配置已去畸變，實際曝光時間，reliable QoS |
| `/openvins/input/imu` | sensor_msgs/msg/Imu | rad/s、m/s²，保留重力效應，實際量測時間，reliable QoS |
| `/openvins/odomimu` | nav_msgs/msg/Odometry | OpenVINS 的輸出接口 |

topic 的 image_raw 名稱維持一致，但本 runner 的影像契約是已去畸變。未來 driver 若發布原始畸變影像，應接去畸變節點後再映射到這個 topic，或一起改為原始 camera model；不能只切換來源而忽略影像模型。

歷史模式發布 `/clock`，estimator 使用 `use_sim_time: true`。實機模式不啟動 replay 或 `/clock`，使用 `use_sim_time: false`，由 driver 提供共用時鐘的感測器量測時間。不要同時運作兩組 sensor publishers。driver 必須使用同一 ROS domain（專案預設 91）；目前僅驗證同主機通訊。

未來準備好實際 calibration 目錄並啟動 driver 後，入口為：

```bash
bash scripts/run_live.sh config/calibration_live
```

此入口目前只預留 estimator 啟動，不含特定硬體 driver，也不啟動 PX4 Agent。實測時以實際外參／時間偏移／噪聲與內參取代離線占位值，將 status.json 實測審查旗標設為 true；不必改寫歷史資料重播程式。

PX4 接口仍規劃為 odomimu → bridge → `/fmu/in/vehicle_visual_odometry` → uXRCE-DDS → EKF2，尚未實作或啟用。
