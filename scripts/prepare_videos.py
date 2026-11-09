"""Convert the existing archived AVI files; never modify original experiment data."""
from pathlib import Path
import subprocess
import imageio_ffmpeg
from backend.config import ALGORITHM_ROOT,RUNTIME

def main():
    out=RUNTIME/'history_video';out.mkdir(parents=True,exist_ok=True);ff=imageio_ffmpeg.get_ffmpeg_exe()
    for run in ['p4_c2_final','p4_c0_final','p4_c1_final']:
        src=ALGORITHM_ROOT/'data/carla_overtake'/run/('p4_constrained_sync.mp4' if run=='p4_c2_final' else 'p4_sync.avi')
        if not src.exists():print('跳过缺失录像',src);continue
        for camera in [False,True]:
            if not camera and run=='p4_c2_final':continue
            dst=out/(run+('-camera' if camera else '')+'.mp4')
            if dst.exists():continue
            filters=['-vf','crop=1280:794:0:106'] if camera else []
            subprocess.run([ff,'-v','error','-y','-i',str(src),*filters,'-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(dst)],check=True)
            print('已转换',dst)

if __name__=='__main__':main()
