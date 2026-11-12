#!/usr/bin/python3
"""Export timestamp-matched OpenVINS results using cuVSLAM's plot/video layout."""
import argparse,bisect,csv,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent/'report_support'))
from align_trajectory_sim3 import fit_sim3,rotate_quaternion,read_csv,write_csv
from plot_trajectory import plot_aligned
import render_trajectory_video as render
from fps_metrics import measure_fps

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run_dir',type=Path)
p.add_argument('--dataset',type=Path,default=Path('/home/user/mono-openvins-ros2/results/20260622_200hz/normalized_experimental'))
p.add_argument('--truth',type=Path,default=Path('/home/user/2026-06-22VTOL/EO_opk_new_with_timestamp.csv'))
p.add_argument('--max-gap-ms',type=float,default=30)
p.add_argument('--skip-video',action='store_true')
p.add_argument('--overwrite',action='store_true')
a=p.parse_args();root=a.run_dir;out=root/'comparison';out.mkdir(exist_ok=a.overwrite)
odom=read_csv(root/'odometry.csv');frames=read_csv(a.dataset/'frames.csv')
published=None
for line in (root/'replay.log').read_text().splitlines():
 try:
  item=json.loads(line)
  if isinstance(item,dict) and 'published' in item:published=item['published']
 except ValueError:pass
if published is None:raise ValueError('Replay completion counts missing')
frames=frames[:published['images']];stamps=[int(r['timestamp_ns']) for r in odom]
if any(b<=a for a,b in zip(stamps,stamps[1:])):raise ValueError('Odometry stamps not strictly increasing')
truth={r['Label']:r for r in read_csv(a.truth)}
sampled=[];diagnostics=[]
for index,f in enumerate(frames):
 t=int(f['timestamp_ns']);label=Path(f['path']).name;j=bisect.bisect_left(stamps,t)
 candidates=[k for k in (j-1,j) if 0<=k<len(stamps)]
 k=min(candidates,key=lambda k:abs(stamps[k]-t)) if candidates else None
 row=None
 if k is not None and abs(stamps[k]-t)<=a.max_gap_ms*1e6:
  o=odom[k];row=dict(stamp_ns=str(t),odom_stamp_ns=str(stamps[k]),frame_index=index,label=label,
    **{dst:float(o[src]) for dst,src in [('x','px'),('y','py'),('z','pz'),('qx','qx'),('qy','qy'),('qz','qz'),('qw','qw')]})
  sampled.append(row)
 diagnostics.append(dict(frame_index=index,label=label,stamp_ns=str(t),status='POSE_AVAILABLE' if row else 'NO_POSE',
                         match_delta_ns=stamps[k]-t if row else '',status_source='timestamp-nearest propagated odometry; not tracker status'))
if len(sampled)<3:raise ValueError('Too few image-matched odometry samples')
write_csv(root/'trajectory.csv',list(sampled[0]),sampled)
write_csv(root/'trajectory.frames.csv',list(diagnostics[0]),diagnostics)
paired=[r for r in sampled if r['label'] in truth]
src=np.array([[r[k] for k in ('x','y','z')] for r in paired]);gt=np.array([[float(truth[r['label']][k]) for k in ('X','Y','Z')] for r in paired])
scale,R,t=fit_sim3(src,gt)
aligned=[]
for row in sampled:
 pos=scale*R@np.array([row[k] for k in ('x','y','z')])+t
 q=rotate_quaternion(R,[row[k] for k in ('qx','qy','qz','qw')])
 aligned.append(dict(stamp_ns=row['stamp_ns'],frame_index=row['frame_index'],label=row['label'],**dict(zip(('x','y','z','qx','qy','qz','qw'),[*pos,*q]))))
truth_rows=[dict(frame_index=i,label=Path(f['path']).name,**{k.lower():float(truth[Path(f['path']).name][k]) for k in ('X','Y','Z')}) for i,f in enumerate(frames) if Path(f['path']).name in truth]
write_csv(out/'trajectory_aligned.csv',list(aligned[0]),aligned);write_csv(out/'ground_truth.csv',list(truth_rows[0]),truth_rows)
error=np.linalg.norm(scale*(R@src.T).T+t-gt,axis=1)
u,_,vt=np.linalg.svd((gt-gt.mean(0)).T@(src-src.mean(0)));d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt);rigid=u@d@vt
rigid_error=np.linalg.norm((rigid@(src-src.mean(0)).T).T+gt.mean(0)-gt,axis=1)
report=dict(algorithm='OpenVINS',source_frames=len(frames),matched_images=len(sampled),coverage=len(sampled)/len(frames),
 scale=scale,rotation=R.tolist(),translation=t.tolist(),position_rmse=float(np.sqrt(np.mean(error**2))),
 rigid_se3_position_rmse=float(np.sqrt(np.mean(rigid_error**2))),synchronization='actual image timestamp; nearest high-rate odometry, <= max_gap_ms',
 max_gap_ms=a.max_gap_ms,accuracy_verified=False,
 note='Sim3 is offline diagnostic only; SE3 metric retains VIO scale. EO camera center vs IMU point offset unknown. No OPK orientation comparison. Never feed aligned truth-fitted trajectory to PX4.')
report['fps']=measure_fps(root,frames,odom)
(out/'alignment.json').write_text(json.dumps(report,indent=2)+'\n');(out/'results_report.json').write_text(json.dumps(report,indent=2)+'\n')
plot_aligned(out/'trajectory_aligned.csv',out/'ground_truth.csv',out)
import subprocess
raw=[dict(stamp_ns=r['timestamp_ns'],**{dst:float(r[src]) for dst,src in [('x','px'),('y','py'),('z','pz'),('qx','qx'),('qy','qy'),('qz','qz'),('qw','qw')]}) for r in odom]
write_csv(root/'trajectory_raw.csv',list(raw[0]),raw)
subprocess.run([sys.executable,str(Path(__file__).resolve().parent/'report_support/plot_trajectory.py'),str(root/'trajectory_raw.csv')],check=True)
# Decode each source image once, then render both variants.
if not a.skip_video:
 import cv2
 contexts=[]
 try:
  for name,data in [('camera_trajectory_comparison.mp4',aligned),('camera_trajectory.mp4',sampled)]:
   poses={r['frame_index']:tuple(r[k] for k in ('x','y','z','qx','qy','qz','qw')) for r in data}
   tr={r['frame_index']:tuple(r[k] for k in ('x','y','z')) for r in truth_rows} if name.startswith('camera_trajectory_comparison') else None
   panel,pixel=render.make_plot(poses,tr);zpanel,zpixel=render.make_z_plot(poses,len(frames),tr)
   video_path=out/name if tr else root/name
   writer=cv2.VideoWriter(str(video_path),cv2.VideoWriter_fourcc(*'mp4v'),10,render.SIZE)
   if not writer.isOpened():raise RuntimeError('Cannot open movie writer')
   contexts.append(dict(name=name,poses=poses,truth=tr,panel=panel,pixel=pixel,zpanel=zpanel,zpixel=zpixel,writer=writer,last=None))
  for i,f in enumerate(frames):
   im=cv2.imread(f['path'])
   if im is None:raise ValueError('Cannot decode '+f['path'])
   camera=cv2.resize(im,(680,510))
   for ctx in contexts:
    canvas=np.full((720,1280,3),(17,20,25),np.uint8);canvas[38:548,20:700]=camera
    pose=ctx['poses'].get(i);last=ctx['last'];pixel=ctx['pixel'];zpixel=ctx['zpixel']
    if pose is not None:
     if last and last[0]==i-1:
      cv2.line(ctx['panel'],pixel(last[1]),pixel(pose),render.BLUE,2)
      cv2.line(ctx['zpanel'],zpixel(*last),zpixel(i,pose),render.BLUE,2)
     ctx['last']=last=(i,pose)
    canvas[38:548,730:1260]=ctx['panel'];canvas[580:705,730:1260]=ctx['zpanel']
    render.put(canvas,Path(f['path']).name,20,27)
    render.put(canvas,'OpenVINS '+('Sim3 diagnostic vs GT' if ctx['truth'] else 'RAW local trajectory'),730,27,.48)
    if ctx['truth']:
     render.put(canvas,'Orange: Ground truth',745,62,.42,render.TRUTH)
     render.put(canvas,'Blue: OpenVINS (Sim3 aligned)',745,84,.42,render.BLUE)
    render.put(canvas,f'Frame {i+1}/{len(frames)} | '+('POSE AVAILABLE' if pose else 'NO POSE'),20,585)
    render.put(canvas,'EXPERIMENTAL calibration | NOT PX4 validated',20,710,.44,render.RED)
    if last:
     values=last[1];angles=render.euler_deg(*values[3:])
     render.put(canvas,'XYZ: '+', '.join(f'{v:.3f}' for v in values[:3]),20,623)
     render.put(canvas,'RPY deg: '+', '.join(f'{v:.2f}' for v in angles),20,652)
     render.put(canvas,'q xyzw: '+', '.join(f'{v:.4f}' for v in values[3:]),20,680,.48)
    ctx['writer'].write(canvas)
   if (i+1)%1000==0 or i+1==len(frames):print(f'Both videos: rendered {i+1}/{len(frames)}',flush=True)
 finally:
  for ctx in contexts:ctx['writer'].release()
print(json.dumps(report,indent=2))
