import time,json,psutil,hashlib,httpx
from pathlib import Path
root=Path(__file__).resolve().parents[1]
client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=20)
start=time.monotonic();first=None
while time.monotonic()-start<90:
 b=client.get('/api/bootstrap').json()
 if b['server']['status']=='running' and b['connection']['connected']:
  pids=[]
  for p in psutil.process_iter(['exe','cmdline']):
   if p.info['exe']=='/home/liumeng/deepseek_workspace/carla-build/carla-runtime/CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping' and any(a=='-carla-rpc-port=2000' for a in p.info['cmdline'] or []):pids.append(p.pid)
  if pids:first=(pids[0],b);break
 if b['server']['status']=='error':raise RuntimeError(b['server'])
 time.sleep(1)
assert first,'server not ready'
pid,b=first
assert '-quality-level=Low' in psutil.Process(pid).cmdline()
assert any(a.startswith('-UserDir=') for a in psutil.Process(pid).cmdline())
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(8388608),b''):h.update(chunk)
 return h.hexdigest()
expected=sha(root/'native-fixes/packaged/CarlaUE4-Linux-Shipping')
assert sha(f'/proc/{pid}/exe')==expected
print('installed_fixed_binary_active',pid,expected,flush=True)
a=b['snapshot']['frame'];t=time.monotonic()
for i in range(12):
 time.sleep(10);b=client.get('/api/bootstrap').json()
 assert b['server']['status']=='running' and b['connection']['connected'],b['server']
 print('formal_entry_stable',10*(i+1),'seconds','frame',b['snapshot']['frame'],flush=True)
duration=time.monotonic()-t
r={'pid':pid,'sha256':expected,'stable_seconds':duration,'observed_fps':(b['snapshot']['frame']-a)/duration,'map':b['connection']['map'],'connection':b['connection']['connected'],'server':b['server']}
(root/'runtime/diagnostics/installed-fix-verification.json').write_text(json.dumps(r,indent=2))
print(json.dumps(r),flush=True)
