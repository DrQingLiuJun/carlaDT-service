import os,subprocess,time
from collections import deque
import psutil
from .config import RUNTIME

_history=deque(maxlen=180)


def sample_resources():
    memory=psutil.virtual_memory();disk=psutil.disk_usage(str(RUNTIME));gpus=[]
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1.5)
        if p.returncode==0:
            for i,line in enumerate(p.stdout.strip().splitlines()):
                a=[v.strip() for v in line.split(',')];gpus.append(dict(id=i,name=a[0],utilization=float(a[1]),memory_used_mb=float(a[2]),memory_total_mb=float(a[3]),temperature=float(a[4])))
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    io=psutil.disk_io_counters()
    row=dict(t=time.time(),cpu=psutil.cpu_percent(),cores=psutil.cpu_count(),memory_used=memory.used,memory_total=memory.total,memory_percent=memory.percent,
        disk_used=disk.used,disk_total=disk.total,disk_free=disk.free,disk_percent=disk.percent,
        gpus=gpus,gpu=gpus[0]['utilization'] if gpus else None,process_memory=psutil.Process(os.getpid()).memory_info().rss,
        read_bytes=io.read_bytes if io else None,write_bytes=io.write_bytes if io else None,source='host')
    _history.append(row);return row


def resource_history():return list(_history)
