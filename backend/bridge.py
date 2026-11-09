"""Native CARLA runs in its matching interpreter, never in the ASGI process."""
import json,os,subprocess,threading,queue,uuid,time
from collections import deque
from .config import ROOT,CARLA_PYTHON


class CarlaBridge:
    def __init__(self,on_snapshot=None):
        self.process=None;self.pending={};self.snapshot=None;self.info={};self.events=deque(maxlen=60);self.lock=threading.Lock();self.on_snapshot=on_snapshot;self.disconnected=False
    def start(self):
        if self.process and self.process.poll() is None:return
        self.snapshot=None
        env={**os.environ,'PYTHONUNBUFFERED':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        try:
            import imageio_ffmpeg
            env['CARLADT_FFMPEG']=imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:pass
        self.process=subprocess.Popen([CARLA_PYTHON,str(ROOT/'backend/carla_worker.py')],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env=env)
        threading.Thread(target=self._read,args=(self.process,),daemon=True).start();threading.Thread(target=self._errors,args=(self.process,),daemon=True).start()
    def _read(self,process):
        for line in process.stdout:
            try:msg=json.loads(line)
            except ValueError:continue
            if msg.get('type')=='state':
                self.snapshot=msg['data']
                if self.on_snapshot:
                    try:self.on_snapshot(self.snapshot)
                    except (OSError,ValueError) as e:self.events.append(dict(level='error',message='遥测写入失败：'+str(e),timestamp=time.time()))
            elif 'request_id' in msg:
                q=self.pending.get(msg['request_id'])
                if q:q.put(msg)
            elif msg.get('type')=='event':self.events.append(msg)
            elif msg.get('type')=='disconnected':
                self.disconnected=True
                if self.snapshot:self.snapshot={**self.snapshot,'status':'error','connection_lost':True}
        if self.process is process and self.snapshot:self.snapshot={**self.snapshot,'status':'error','connection_lost':True}
    def _errors(self,process):
        for line in process.stderr:
            if line.strip():self.events.append(dict(type='event',level='info',message=line.strip()[:500],timestamp=time.time()))
    def call(self,action,timeout=15,**payload):
        self.start();key=uuid.uuid4().hex;q=queue.Queue();self.pending[key]=q
        try:
            with self.lock:self.process.stdin.write(json.dumps(dict(action=action,request_id=key,**payload))+'\n');self.process.stdin.flush()
            msg=q.get(timeout=timeout)
            if not msg.get('ok'):raise ValueError(msg.get('error','CARLA 操作失败'))
            if action=='connect':self.disconnected=False
            return msg.get('data',{})
        except queue.Empty:raise ValueError('CARLA 响应超时，请检查服务和客户端版本')
        finally:self.pending.pop(key,None)
    def close(self):
        if self.process and self.process.poll() is None:
            try:self.call('shutdown',timeout=5)
            except (ValueError,OSError):self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process=None;self.snapshot=None;self.info={};self.disconnected=True


class ExampleProcess:
    def __init__(self):self.process=None;self.name=None;self.logs=deque(maxlen=100)
    @property
    def active(self):return bool(self.process and self.process.poll() is None)
    def start(self,command,name,cwd):
        if self.active:raise ValueError('已有示例正在运行')
        self.name=name;self.logs.clear()
        self.process=subprocess.Popen(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True,env={**os.environ,'PYTHONUNBUFFERED':'1'})
        def read():
            for line in self.process.stdout:self.logs.append(line.rstrip()[:1000])
        threading.Thread(target=read,daemon=True).start()
    def stop(self):
        import signal
        if self.active:
            os.killpg(self.process.pid,signal.SIGINT)
            try:self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGTERM)
        return self.state()
    def state(self):return dict(active=self.active,name=self.name,logs=list(self.logs),returncode=self.process.poll() if self.process else None)
