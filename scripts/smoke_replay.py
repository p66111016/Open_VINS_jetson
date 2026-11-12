#!/usr/bin/python3
"""Synthetic two-process DDS replay check. Does not start OpenVINS or PX4."""
import csv
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', help='Use actual normalized historical data instead of synthetic fixture')
    parser.add_argument('--max-frames', type=int, default=10)
    parser.add_argument('--exploratory', action='store_true')
    args=parser.parse_args()
    import cv2
    import numpy as np
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile
    from sensor_msgs.msg import Image, Imu
    from rosgraph_msgs.msg import Clock
    root = Path(__file__).resolve().parents[1]
    result = dict(synthetic=not bool(args.dataset), success=False, image_count=0, imu_count=0, clock_count=0)
    with tempfile.TemporaryDirectory(prefix='openvins-smoke-') as tmp:
        directory = Path(tmp)
        image_path = directory/'synthetic.png'
        cv2.imwrite(str(image_path), np.arange(48, dtype=np.uint8).reshape(6,8))
        (directory/'manifest.json').write_text(json.dumps(dict(schema_version=1, mode='historical', reviewed=True, synthetic=True)))
        with (directory/'frames.csv').open('w') as f:
            w=csv.writer(f)
            w.writerow(['timestamp_ns','path'])
            for i in range(10):
                w.writerow([1_020_000_000+i*20_000_000, str(image_path)])
        with (directory/'imu.csv').open('w') as f:
            w=csv.writer(f)
            w.writerow(['timestamp_ns','wx','wy','wz','ax','ay','az'])
            for i in range(102):
                w.writerow([1_000_000_000+i*2_000_000,0,0,0,0,0,9.81])
        if args.dataset:
            directory=Path(args.dataset)
        from mono_openvins_tools.dataset import load_normalized
        _,expected_frames,expected_samples=load_normalized(directory,max_frames=args.max_frames,exploratory=args.exploratory)
        expected_images=[t for t,_ in expected_frames]
        expected_imu=[t for t,_ in expected_samples]
        expected_payload={}
        for t,path in expected_frames:
            pixels=cv2.imread(path,cv2.IMREAD_GRAYSCALE)
            expected_payload[t]=(pixels.shape,hashlib.sha256(pixels.tobytes()).hexdigest())
        bad_imu=[]
        expected_imu_values=dict(expected_samples)
        rclpy.init()
        node=rclpy.create_node('synthetic_replay_observer')
        executor=SingleThreadedExecutor()
        executor.add_node(node)
        received={'image':[], 'imu':[], 'clock':[]}
        bad_images=[]
        def stamp(s):
            return s.sec*1_000_000_000+s.nanosec
        def image(msg):
            received['image'].append(stamp(msg.header.stamp))
            actual=((msg.height,msg.width),hashlib.sha256(bytes(msg.data)).hexdigest())
            if actual!=expected_payload.get(stamp(msg.header.stamp)) or msg.encoding!='mono8' or msg.step!=msg.width:
                bad_images.append(True)
        def imu(msg):
            t=stamp(msg.header.stamp)
            received['imu'].append(t)
            a,w=msg.linear_acceleration,msg.angular_velocity
            if (w.x,w.y,w.z,a.x,a.y,a.z)!=expected_imu_values.get(t):
                bad_imu.append(True)
        subscriptions=[
            node.create_subscription(Image,'/openvins/input/image_raw',image,QoSProfile(depth=100)),
            node.create_subscription(Imu,'/openvins/input/imu',imu,QoSProfile(depth=1000)),
            node.create_subscription(Clock,'/clock',lambda m: received['clock'].append(stamp(m.clock)),QoSProfile(depth=1000)),
        ]
        env=os.environ.copy()
        env['PYTHONPATH']=str(root/'ros2_ws/src/mono_openvins_tools')+':'+env.get('PYTHONPATH','')
        child_log=root/('logs/realdata-replay-child.log' if args.dataset else 'logs/smoke-replay-child.log')
        child_log.parent.mkdir(parents=True,exist_ok=True)
        try:
            with child_log.open('w') as log:
                proc=subprocess.Popen([sys.executable,'-m','mono_openvins_tools.replay',
                    '--dataset',str(directory),'--max-frames',str(args.max_frames),'--speed','1.0','--subscriber-timeout','5']+
                    (['--exploratory'] if args.exploratory else []),env=env,stdout=log,stderr=log)
                try:
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        executor.spin_once(timeout_sec=0.02)
                        if proc.poll() is not None and len(received['image'])==len(expected_images) and len(received['imu'])==len(expected_imu):
                            break
                    if proc.poll() is None:
                        proc.terminate()
                    proc.wait(timeout=3)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
            result.update(image_count=len(received['image']),imu_count=len(received['imu']),
                          clock_count=len(received['clock']),child_exit_code=proc.returncode,
                          child_log=str(child_log))
            result['success']=(proc.returncode==0 and received['image']==expected_images and received['imu']==expected_imu
                               and len(received['clock'])>0 and not bad_images and not bad_imu)
            if not result['success']:
                result['error']='DDS delivery, stamps, or image payload check failed. Inspect child and terminal transport errors.'
        finally:
            for subscription in subscriptions:
                node.destroy_subscription(subscription)
            executor.shutdown()
            node.destroy_node()
            rclpy.shutdown()
    (root/('results/realdata_replay.json' if args.dataset else 'results/smoke_replay.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['success'] else 1


if __name__=='__main__':
    sys.exit(main())
