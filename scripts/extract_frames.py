"""Extract new review frames with FFmpeg; do not overwrite frozen evidence."""
import argparse
from pathlib import Path
import subprocess

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--step',type=float,default=.3)
    p.add_argument('--start',type=float,default=0)
    p.add_argument('--duration',type=float)
    a=p.parse_args()
    if a.step<=0 or a.start<0 or (a.duration is not None and a.duration<=0):
        p.error('step/duration must be positive and start nonnegative')
    if a.output.exists():
        p.error('Use a new output directory; existing evidence is never overwritten')
    a.output.mkdir(parents=True)
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-ss',str(a.start),'-i',str(a.video)]
    if a.duration is not None:
        cmd+=['-t',str(a.duration)]
    cmd+=['-vf',f'fps=1/{a.step}','-q:v','2',str(a.output/'frame_%06d.jpg')]
    subprocess.run(cmd,check=True)
