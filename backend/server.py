"""Local CARLA process lifecycle. Only identified CARLA processes are stopped."""
import os
import configparser
import subprocess
import time
from pathlib import Path
import psutil


class CarlaServer:
    def __init__(self, output):
        self.root=Path(os.environ.get('CARLADT_SERVER_ROOT','/home/liumeng/deepseek_workspace/carla-build/carla-runtime'))
        self.output=Path(output);self.port=2000;self.phase=None;self.error=None;self.child=None;self.exit_code=None;self._exit_seen=None;self.expected_exit=False
    def processes(self):
        found=[]
        for p in psutil.process_iter(['name','cmdline','exe']):
            try:
                if p.status() in [psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD]:continue
                if p.info['name'] not in ['CarlaUE4-Linux-Shipping','CarlaUE4-Linux-','CarlaUnreal.sh'] and Path(p.info['exe'] or '').name!='CarlaUE4-Linux-Shipping':continue
                args=p.info['cmdline'] or []
                port=next((int(a.split('=',1)[1]) for a in args if a.startswith('-carla-rpc-port=')),2000)
                if port==self.port:found.append(p)
            except (psutil.Error,ValueError):continue
        return found
    def port_open(self):
        # Never connect-and-close the RPC socket. rpclib in the current custom
        # build throws from server_session::close on this kind of probe.
        return any(c.status==psutil.CONN_LISTEN and c.laddr and c.laddr.port==self.port for c in psutil.net_connections(kind='tcp'))
    def state(self):
        if self.child:
            code=self.child.poll()  # waitpid(WNOHANG), reap a crashed child
            if code is not None:
                self.exit_code=code
                if self._exit_seen is not self.child:
                    self._exit_seen=self.child
                    if code!=0 and not self.expected_exit:self.error=f'CARLA 异常退出（退出码 {code}），可重新启动；详情见 carla-server.log'
        processes=self.processes();ready=self.port_open()
        status=self.phase or ('running' if processes and ready else 'starting' if processes else 'unmanaged' if ready else 'stopped')
        if self.error and not processes and not ready and not self.phase:status='error'
        return dict(status=status,error=self.error,port=self.port,exit_code=self.exit_code,
            can_start=not self.phase and not processes and not ready,
            can_restart=not self.phase and bool(processes) and ready,
            can_stop=not self.phase and bool(processes))
    def begin(self,action):
        if action not in ['start','restart','stop'] or not self.state().get('can_'+action):raise ValueError('当前 CARLA 状态不允许此操作')
        self.phase={'start':'starting','restart':'restarting','stop':'stopping'}[action];self.error=None
    def stop(self):
        self.expected_exit=True
        processes=self.processes()
        for p in processes:
            try:p.terminate()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(processes,timeout=12)
        for p in alive:
            try:p.kill()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(alive,timeout=3)
        if alive:raise ValueError('CARLA 进程未能停止')
    def profile_args(self):
        quality=os.environ.get('CARLADT_QUALITY','Epic')
        if quality not in ['Low','Epic']:raise ValueError('CARLADT_QUALITY 必须为 Low 或 Epic')
        fps=int(os.environ.get('CARLADT_MAX_FPS','30'))
        if not 0<=fps<=120:raise ValueError('CARLADT_MAX_FPS 必须为 0 至 120')
        profile=(self.output/'carla-profile').resolve();config=profile/'Saved/Config/LinuxNoEditor';config.mkdir(parents=True,exist_ok=True)
        for filename,section,values in [
            ('GameUserSettings.ini','/Script/Engine.GameUserSettings',{'Version':'5','FrameRateLimit':str(fps),'bUseVSync':'False','FullscreenMode':'2','ResolutionSizeX':'1280','ResolutionSizeY':'720'}),
            ('Engine.ini','SystemSettings',{'t.MaxFPS':str(fps)})]:
            p=config/filename;ini=configparser.ConfigParser(interpolation=None,strict=False);ini.optionxform=str
            if p.exists():ini.read(p)
            if not ini.has_section(section):ini.add_section(section)
            for key,value in values.items():ini.set(section,key,value)
            with p.open('w') as f:ini.write(f,space_around_delimiters=False)
        return ['-quality-level='+quality,'-UserDir='+str(profile)+'/']
    def start(self):
        binary=self.root/'CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping'
        if not binary.is_file():raise ValueError('未找到 CARLA 可执行文件：'+str(binary))
        self.output.mkdir(parents=True,exist_ok=True);self.expected_exit=False;self.exit_code=None;self.error=None
        with (self.output/'carla-server.log').open('a') as log:
            self.child=subprocess.Popen([str(binary),'CarlaUE4','-windowed','-ResX=1280','-ResY=720',f'-carla-rpc-port={self.port}',*self.profile_args()],cwd=self.root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if self.child.poll() is not None:
                self.exit_code=self.child.returncode
                raise ValueError('CARLA 启动退出（退出码 '+str(self.child.returncode)+'），请查看 runtime/carla-server.log')
            if self.port_open():return
            time.sleep(.5)
        raise ValueError('CARLA 启动超时，请查看 runtime/carla-server.log')
