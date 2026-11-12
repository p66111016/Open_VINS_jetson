#!/usr/bin/python3
"""Check exported movie frame counts and decode first/middle/final samples."""
import argparse,json
from pathlib import Path
import cv2

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run_dir',type=Path)
a=p.parse_args();r=a.run_dir
expected=json.loads((r/'comparison/results_report.json').read_text())['source_frames']
result={}
for video in (r/'camera_trajectory.mp4',r/'comparison/camera_trajectory_comparison.mp4'):
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():raise RuntimeError('Cannot open '+str(video))
    count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
    if count!=expected:raise ValueError(f'{video}: expected {expected}, got {count}')
    checked=[]
    for i in sorted({0,expected//2,expected-1}):
        cap.set(cv2.CAP_PROP_POS_FRAMES,i)
        ok,frame=cap.read()
        if not ok:raise ValueError(f'{video}: failed to decode frame {i}')
        checked.append(i)
        if i==expected//2:cv2.imwrite(str(video.with_suffix('.preview.png')),frame)
        if i==expected-1:cv2.imwrite(str(video.with_suffix('.last.png')),frame)
    cap.release()
    result[str(video)]=dict(container_frames=count,fps=fps,duration_s=count/fps,
                            decoded_sample_indices=checked,bytes=video.stat().st_size)
(r/'media_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
