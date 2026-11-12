#!/usr/bin/python3
"""Release OpenVINS ROS objects before process-wide image_transport plugin teardown."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'ros2_ws/src/open_vins/ov_msckf/src/run_subscribe_msckf.cpp'
old='#elif ROS_AVAILABLE == 2\n  rclcpp::shutdown();'
new=('#elif ROS_AVAILABLE == 2\n'
     '  // Project patch: globals must release publishers before static plugin teardown.\n'
     '  viz.reset();\n'
     '  sys.reset();\n'
     '  rclcpp::shutdown();')
text=p.read_text()
if new in text:
    print('ROS 2 shutdown lifetime patch already applied')
elif text.count(old)==1:
    p.write_text(text.replace(old,new))
    print('Applied ROS 2 shutdown lifetime patch')
else:
    raise SystemExit('Unexpected upstream shutdown code; review patch before building')
