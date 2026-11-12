# Mono OpenVINS on Jetson AGX Orin

最新全量成果：`results/run_20261112T143235`。8,447 張可同步影像、168,760 筆 IMU、167,121 筆里程計，正常退出；CSV、XY/Z 圖、兩支完整 MP4 與含解碼／去畸變計時的 results_report.json 已完成。暫定標定下嚴重發散，不能作為 PX4 定位輸入。全量重跑：`bash scripts/run_with_results.sh 0 2.0`；PX4 接口細節見 [接口與成果](docs/px4_and_results.md)。

原生 ROS 2 Humble 專案，以歷史單目影像與 200 Hz IMU 執行離線 VIO，預留未來實機 driver 接口。主機 OpenCV 4.8 保持原狀；Ceres、cv_bridge 與補充 Boost 函式庫均位於本專案。

OpenVINS v2.7、Ceres 2.1.0、cv_bridge 3.2.1 已完成編譯。載入檢查確認 OpenVINS 與 cv_bridge 都使用 OpenCV 4.8，以及專案私有 Ceres。歷史資料已能初始化與輸出里程計；暫定標定造成明顯漂移，尚無定位精度驗證，未接入 PX4。

## 離線執行

目前已準備 8,447 張影像與 168,779 筆 IMU。使用獨立終端，不先載入原 cuVSLAM workspace。

```bash
cd /home/user/mono-openvins-ros2
bash scripts/run_offline.sh \
  results/20260622_200hz/normalized_experimental \
  config/offline_experimental 300 0.5 --exploratory
```

0.5 是牆鐘播放速度，來源時間間隔不變。結果位於新的 results/run_* 目錄，包含 odometry.csv、節點日誌、退出碼與實驗設定。

```bash
/usr/bin/python3 scripts/summarize_run.py results/run_YYYYMMDDTHHMMSS
```

相機／IMU 外參、時間偏移與雜訊目前是占位值，metadata 保留未標定狀態。EO 真值不作為估測輸入。現階段只驗證流程可運作，不將這些里程計送入 PX4。

## 建置與檢查

```bash
bash scripts/fetch_sources.sh
bash scripts/build.sh
bash scripts/check_links.sh
bash scripts/test.sh
```

腳本不執行 sudo、apt install、pip install 或 ldconfig，不寫入 /usr/local、不修改 .bashrc。Ceres 使用 CPU、MINIGLOG 與 Eigen sparse；未啟用 CUDA。build.sh 會套用本專案的 ROS 2 關閉生命週期修補，提前釋放 OpenVINS 的全域 publisher，避免 image_transport 靜態銷毀時崩潰。

本次工具沙箱內曾出現 colcon 子程序已退出但等待不結束的情況；在可正常管理子程序的本機執行環境完成建置。預設以 2 個建置工作執行，可用 OPENVINS_BUILD_JOBS 調整。

## 未來實機接口

介面集中於 config/sensor_interface.yaml：/openvins/input/image_raw 使用 sensor_msgs/Image，/openvins/input/imu 使用 sensor_msgs/Imu，輸出為 /openvins/odomimu。預設 ROS domain 91、localhost only。

目前影像契約是已去畸變的 mono8；實機 driver 若提供原始畸變影像，需接去畸變節點或一致調整 camera model。歷史模式使用 /clock 與 use_sim_time；實機使用實際量測時間、use_sim_time=false。

實際標定與 driver 就緒後，預留入口為 scripts/run_live.sh config/calibration_live。PX4 bridge、Agent 與 EKF2 連線仍是後續階段。

詳見 [資料與時間戳檢查](docs/dataset_20260622_200hz.md)、[離線與實機接口](docs/offline_and_live.md)。舊 docs/deployment_status.md 為最初部署歷史紀錄；目前機器可讀狀態以 results/deployment_status.json 為準。
