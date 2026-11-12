"""Record native OpenVINS odomimu (pose in global, twist in IMU frame)."""
import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--topic', default='/openvins/odomimu')
    args, ros_args = parser.parse_known_args()
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import ExternalShutdownException
    from nav_msgs.msg import Odometry
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ns', 'frame_id', 'child_frame_id', 'px', 'py', 'pz',
                         'qx', 'qy', 'qz', 'qw', 'vx_imu', 'vy_imu', 'vz_imu',
                         'wx_imu', 'wy_imu', 'wz_imu'])
        rclpy.init(args=ros_args)
        node = Node('openvins_odometry_recorder')

        def callback(msg):
            p, q, v, w = msg.pose.pose.position, msg.pose.pose.orientation, msg.twist.twist.linear, msg.twist.twist.angular
            writer.writerow([msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec,
                             msg.header.frame_id, msg.child_frame_id,
                             p.x,p.y,p.z,q.x,q.y,q.z,q.w,v.x,v.y,v.z,w.x,w.y,w.z])
            f.flush()

        subscription = node.create_subscription(Odometry, args.topic, callback, 100)
        try:
            rclpy.spin(node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            node.destroy_subscription(subscription)
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()


if __name__ == '__main__':
    main()
