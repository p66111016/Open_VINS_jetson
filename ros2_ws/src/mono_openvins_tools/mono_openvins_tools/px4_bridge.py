"""OpenVINS odomimu to PX4 VehicleOdometry; preview is the default."""
import argparse,json,math
from pathlib import Path
import numpy as np


def rotation(q):
    q=np.asarray(q,dtype=float)
    if q.shape!=(4,) or not np.isfinite(q).all() or np.linalg.norm(q)<1e-8:
        raise ValueError('Invalid quaternion')
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def quaternion_wxyz(r):
    # Robust matrix to quaternion via symmetric eigenproblem; no OpenCV dependency.
    m=np.array([[r[0,0]-r[1,1]-r[2,2],r[0,1]+r[1,0],r[0,2]+r[2,0],r[2,1]-r[1,2]],
                [r[0,1]+r[1,0],r[1,1]-r[0,0]-r[2,2],r[1,2]+r[2,1],r[0,2]-r[2,0]],
                [r[0,2]+r[2,0],r[1,2]+r[2,1],r[2,2]-r[0,0]-r[1,1],r[1,0]-r[0,1]],
                [r[2,1]-r[1,2],r[0,2]-r[2,0],r[1,0]-r[0,1],np.trace(r)]])/3
    _,v=np.linalg.eigh(m);q=v[:,-1]
    if q[3]<0:q=-q
    return q[[3,0,1,2]].tolist()


def checked_rotation(value):
    r=np.asarray(value,dtype=float)
    if r.shape!=(3,3) or not np.isfinite(r).all() or not np.allclose(r.T@r,np.eye(3),atol=1e-6) or not np.isclose(np.linalg.det(r),1):
        raise ValueError('Expected proper 3x3 rotation')
    return r


def convert(position,q_xyzw,velocity_imu,angular_imu,pose_cov,twist_cov,config,stamp_ns,now_ns):
    if stamp_ns<=0 or now_ns<stamp_ns or now_ns-stamp_ns>int(config['max_age_ms']*1e6):
        raise ValueError('Stale/future timestamp')
    p=np.asarray(position,dtype=float);v=np.asarray(velocity_imu,dtype=float);w=np.asarray(angular_imu,dtype=float)
    if not np.isfinite(np.r_[p,v,w]).all():raise ValueError('Nonfinite odometry')
    wg=checked_rotation(config['R_world_frd_from_global'])
    ib=checked_rotation(config['R_imu_from_body_frd'])
    gi=rotation(q_xyzw);pc=np.asarray(pose_cov,dtype=float).reshape(6,6)
    if not np.isfinite(pc).all() or not np.allclose(pc,pc.T,atol=1e-7) or np.linalg.eigvalsh(pc).min()<-1e-8:
        raise ValueError('Invalid pose covariance')
    pv=np.diag(wg@pc[:3,:3]@wg.T);ov=np.diag(ib.T@pc[3:,3:]@ib)
    if np.any(pv<=0) or np.any(ov<=0):raise ValueError('Missing/zero pose variances')
    result=dict(timestamp=now_ns//1000,timestamp_sample=stamp_ns//1000,pose_frame=2,
                position=(wg@p).tolist(),q=quaternion_wxyz(wg@gi@ib),
                position_variance=pv.tolist(),orientation_variance=ov.tolist(),
                velocity_frame=0,velocity=[None]*3,velocity_variance=[None]*3,
                angular_velocity=(ib.T@w).tolist(),reset_counter=0,quality=-1)
    # Keep reported position at the VIO IMU point. Configure EKF2_EV_POS_* once on PX4.
    # Native odomimu velocity is expressed in the IMU frame, not in global.
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True)
    p.add_argument('--publish-px4',action='store_true')
    args,ros_args=p.parse_known_args();config=json.loads(Path(args.config).read_text())
    if args.publish_px4:
        for k in ('calibration_verified','body_rotation_verified','px4_message_version_verified','time_sync_verified','tracking_quality_verified'):
            if config.get(k) is not True:p.error('PX4 publishing requires '+k)
        if config.get('source_mode')!='live':p.error('Historical inputs use preview; they cannot describe current PX4 motion')
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import ExternalShutdownException
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String, Bool, UInt8
    rclpy.init(args=ros_args);node=Node('openvins_px4_bridge')
    if args.publish_px4 and node.get_parameter('use_sim_time').value:p.error('Live PX4 output requires use_sim_time=false')
    if args.publish_px4:
        from px4_msgs.msg import VehicleOdometry
        pub=node.create_publisher(VehicleOdometry,'/fmu/in/vehicle_visual_odometry',qos_profile_sensor_data)
    else:pub=node.create_publisher(String,'/openvins/px4_preview',10)
    last_stamp=0;last_publish=0;last_position=None;reset=0;rejected=0;healthy_at=0
    def health(msg):
        nonlocal healthy_at
        healthy_at=node.get_clock().now().nanoseconds if msg.data else 0
    def reset_event(msg):
        nonlocal reset,last_stamp,last_position,last_publish
        if int(msg.data)!=reset:
            reset=int(msg.data);last_stamp=0;last_position=None;last_publish=0
    health_sub=node.create_subscription(Bool,'/openvins/tracking_healthy',health,10)
    reset_sub=node.create_subscription(UInt8,'/openvins/reset_counter',reset_event,10)
    def callback(msg):
        nonlocal last_stamp,last_publish,last_position,reset,rejected
        stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
        now=node.get_clock().now().nanoseconds
        try:
            if args.publish_px4 and (healthy_at==0 or now-healthy_at>1_000_000_000):raise ValueError('Tracking health watchdog expired')
            if stamp<=last_stamp:raise ValueError('Non-increasing sample time: restart stream with a new bridge')
            if msg.header.frame_id!='global' or msg.child_frame_id!='imu':raise ValueError('Expected native OpenVINS global/imu frames')
            pos=msg.pose.pose.position;q=msg.pose.pose.orientation;v=msg.twist.twist.linear;w=msg.twist.twist.angular
            xyz=np.array([pos.x,pos.y,pos.z])
            if last_position is not None:
                speed=np.linalg.norm(xyz-last_position)/((stamp-last_stamp)/1e9)
                if speed>config['max_speed_mps']:raise ValueError('Position jump or excessive speed')
            result=convert(xyz,[q.x,q.y,q.z,q.w],[v.x,v.y,v.z],[w.x,w.y,w.z],msg.pose.covariance,msg.twist.covariance,config,stamp,now)
            last_position=xyz;last_stamp=stamp
            if stamp-last_publish<1e9/config['output_hz']:return
            last_publish=stamp;result['reset_counter']=reset
            if args.publish_px4:
                out=VehicleOdometry()
                for k,value in result.items():setattr(out,k,[float('nan') if x is None else x for x in value] if isinstance(value,list) else value)
            else:
                out=String();out.data=json.dumps(result,allow_nan=False)
            pub.publish(out)
        except ValueError as exc:
            rejected+=1
            if rejected==1 or rejected%100==0:node.get_logger().warning(f'Rejected {rejected}: {exc}')
    sub=node.create_subscription(Odometry,'/openvins/odomimu',callback,100)
    try:rclpy.spin(node)
    except (KeyboardInterrupt,ExternalShutdownException):pass
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':main()
