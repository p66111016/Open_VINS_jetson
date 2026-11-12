"""Replay reviewed historical data using measurement stamps and a simulated clock."""
import argparse
from array import array
import json
import math
from pathlib import Path
import time

from .dataset import events, load_normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--speed', type=float, default=0.25)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--max-frames', type=int, default=0)
    parser.add_argument('--preroll', type=float, default=2.0)
    parser.add_argument('--subscriber-timeout', type=float, default=30.0)
    parser.add_argument('--no-wait', action='store_true', help='Publish without waiting for consumers')
    parser.add_argument('--rectify-calibration', help='ROS CameraInfo YAML; applies all distortion coefficients')
    parser.add_argument('--dry-run', action='store_true', help='Validate timeline without initializing ROS')
    parser.add_argument('--exploratory', action='store_true', help='Allow historical inputs with unreviewed timing/units')
    args, ros_args = parser.parse_known_args()
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error('speed must be finite and positive')
    if not math.isfinite(args.subscriber_timeout) or args.subscriber_timeout <= 0:
        parser.error('subscriber-timeout must be finite and positive')
    try:
        _, frames, imu = load_normalized(args.dataset, args.start, args.max_frames, args.preroll, args.exploratory)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        parser.error(str(exc))
    summary = dict(images=len(frames), imu=len(imu), speed=args.speed,
                   first_event_ns=min(frames[0][0], imu[0][0]),
                   last_event_ns=max(frames[-1][0], imu[-1][0]),
                   note='Source intervals preserved; playback speed changes wall time only.')
    print(json.dumps(summary, indent=2), flush=True)
    if args.dry_run:
        return

    import cv2
    import numpy as np
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from sensor_msgs.msg import Image, Imu
    from rosgraph_msgs.msg import Clock
    rclpy.init(args=ros_args)
    node = Node('historical_sensor_replay')
    image_pub = node.create_publisher(Image, '/openvins/input/image_raw', QoSProfile(depth=10))
    imu_pub = node.create_publisher(Imu, '/openvins/input/imu', QoSProfile(depth=1000))
    clock_pub = node.create_publisher(Clock, '/clock', QoSProfile(
        depth=1, reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL))
    calibration, maps = None, None
    try:
        if args.rectify_calibration:
            import yaml
            calibration = yaml.safe_load(Path(args.rectify_calibration).read_text())
            k = np.array(calibration['camera_matrix']['data'], dtype=float).reshape(3, 3)
            d = np.array(calibration['distortion_coefficients']['data'], dtype=float)
            size = (int(calibration['image_width']), int(calibration['image_height']))
            if calibration['distortion_model'] != 'plumb_bob':
                raise ValueError('Rectification currently supports plumb_bob only')
            maps = cv2.initUndistortRectifyMap(k, d, np.eye(3), k, size, cv2.CV_32FC1)
        if not args.no_wait:
            deadline = time.monotonic() + args.subscriber_timeout
            while rclpy.ok() and (image_pub.get_subscription_count() < 1 or imu_pub.get_subscription_count() < 1):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Timed out waiting for both image and IMU consumers')
                rclpy.spin_once(node, timeout_sec=0.1)
        begin = time.monotonic() + 0.25
        first = summary['first_event_ns']
        published = {'images': 0, 'imu': 0}
        last_log = time.monotonic()
        max_lateness_s = 0.0
        decode_times = []
        rectify_times = []
        image_publish_wall = []
        loop_start = time.monotonic()
        for stamp_ns, kind, payload in events(frames, imu):
            if not rclpy.ok():
                break
            image = None
            if kind == 1:
                decode_start = time.monotonic()
                image = cv2.imread(payload, cv2.IMREAD_GRAYSCALE)
                decode_times.append(time.monotonic() - decode_start)
                if image is None:
                    raise ValueError(f'Failed to decode {payload}')
                if calibration is not None:
                    expected = (int(calibration['image_height']), int(calibration['image_width']))
                    if image.shape != expected:
                        raise ValueError(f'Image size {image.shape} differs from calibration {expected}')
                    rectify_start = time.monotonic()
                    image = cv2.remap(image, *maps, cv2.INTER_LINEAR)
                    rectify_times.append(time.monotonic() - rectify_start)
            deadline = begin + (stamp_ns - first) / 1e9 / args.speed
            while rclpy.ok() and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=min(0.01, max(0.0, deadline - time.monotonic())))
            max_lateness_s = max(max_lateness_s, time.monotonic() - deadline)
            clock = Clock()
            clock.clock.sec, clock.clock.nanosec = divmod(stamp_ns, 1_000_000_000)
            clock_pub.publish(clock)
            if kind == 0:
                msg = Imu()
                msg.header.stamp = clock.clock
                msg.header.frame_id = 'vio_imu'
                msg.orientation_covariance[0] = -1.0
                msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z = payload[:3]
                msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z = payload[3:]
                imu_pub.publish(msg)
                published['imu'] += 1
            else:
                msg = Image()
                msg.header.stamp = clock.clock
                msg.header.frame_id = 'vio_camera_optical'
                msg.height, msg.width = image.shape
                msg.encoding = 'mono8'
                msg.step = msg.width
                msg.data = array('B', image.tobytes())
                image_pub.publish(msg)
                image_publish_wall.append(time.monotonic())
                published['images'] += 1
            rclpy.spin_once(node, timeout_sec=0.0)
            if time.monotonic() - last_log >= 5:
                node.get_logger().info(f'Published {published}; max wall lateness {max_lateness_s:.3f}s')
                last_log = time.monotonic()
        def timing(values):
            if not values:
                return None
            ms = np.asarray(values) * 1000
            return dict(count=len(values), total_s=float(sum(values)), mean_ms=float(ms.mean()),
                        median_ms=float(np.median(ms)), p95_ms=float(np.percentile(ms,95)), max_ms=float(ms.max()))
        elapsed = time.monotonic() - loop_start
        window = image_publish_wall[-1] - image_publish_wall[0] if len(image_publish_wall)>1 else None
        print(json.dumps(dict(published=published, max_wall_lateness_s=max_lateness_s,
            replay_timing=dict(wall_elapsed_s=elapsed, decode=timing(decode_times),
                rectification=timing(rectify_times), image_publication_window_s=window,
                image_publication_fps=(len(image_publish_wall)-1)/window if window else None,
                note='Measured input pipeline includes decode, rectification, serialization, DDS publication and scheduled replay waits; not estimator completion or maximum throughput.'))), flush=True)
        # Allow DDS to flush the tail. Counts here are publication counts, not estimator acknowledgements.
        flush_until = time.monotonic() + 0.5
        while rclpy.ok() and time.monotonic() < flush_until:
            rclpy.spin_once(node, timeout_sec=0.05)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
