"""Install verified native fix with content-addressed backups and rollback manifest."""
import argparse,datetime,hashlib,json,os,shutil,stat,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CARLA=Path('/home/liumeng/deepseek_workspace/carla-build/carla')
RUNTIME=CARLA.parent/'carla-runtime'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def copy_atomic(src,dst,mode=None):
 tmp=dst.with_name(dst.name+'.native-fix.tmp')
 subprocess.run(['cp','--reflink=auto','--preserve=mode,timestamps',str(src),str(tmp)],check=True)
 if mode is not None:tmp.chmod(mode)
 os.replace(tmp,dst)

def install():
 backup=ROOT/'backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S');blobs=backup/'blobs';blobs.mkdir(parents=True)
 mappings=[]
 for base in [RUNTIME/'CarlaUE4/Binaries/Linux',CARLA/'Unreal/CarlaUE4/Binaries/Linux']:
  for suffix in ['', '.debug','.sym']:
   name='CarlaUE4-Linux-Shipping'+suffix;mappings.append((ROOT/'packaged'/name,base/name))
 for base in [CARLA/'Unreal/CarlaUE4/Plugins/Carla/CarlaDependencies',CARLA/'Build/rpclib-v2.2.1_c5-c8-libcxx-install']:
  mappings.append((ROOT/'rpc-build/librpc.a',base/'lib/librpc.a'))
  mappings.append((ROOT/'rpclib/include/rpc/detail/async_writer.h',base/'include/rpc/detail/async_writer.h'))
 records=[]
 for src,dst in mappings:
  assert src.is_file() and dst.is_file(),(src,dst)
  digest=sha(dst);blob=blobs/digest
  if not blob.exists():subprocess.run(['cp','--reflink=auto','--preserve=mode,timestamps',str(dst),str(blob)],check=True)
  records.append({'target':str(dst),'backup':str(blob),'original_sha256':digest,'new_sha256':sha(src),'mode':stat.S_IMODE(dst.stat().st_mode)})
 manifest=backup/'manifest.json';manifest.write_text(json.dumps(records,indent=2))
 for (src,dst),r in zip(mappings,records):copy_atomic(src,dst,r['mode'])
 (ROOT/'installed-manifest.txt').write_text(str(manifest)+'\n')
 print('INSTALLED',manifest,flush=True)

def restore(manifest):
 for r in json.loads(Path(manifest).read_text()):
  backup=Path(r['backup']);assert sha(backup)==r['original_sha256'];copy_atomic(backup,Path(r['target']),r['mode'])
 print('RESTORED',manifest)
p=argparse.ArgumentParser();p.add_argument('--install',action='store_true');p.add_argument('--restore');args=p.parse_args()
if args.restore:restore(args.restore)
elif args.install:install()
else:p.error('use --install or --restore MANIFEST')
