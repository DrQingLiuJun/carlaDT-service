import asyncio,json,time,subprocess,psutil
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,WebSocket,WebSocketDisconnect,Body
from fastapi.responses import FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from .config import ConsoleConfig,ActorConfig,DEFAULT_ACTORS,PARAMETERS,ROOT,RUNTIME,ALGORITHM_ROOT,EXAMPLES_ROOT
from .history import History,run_list
from .opendrive import local_map,map_list,parse_map
from .recording import Recorder,safe_file
from .resources import sample_resources,resource_history
from .catalog import catalog,build_command
from .bridge import CarlaBridge,ExampleProcess
from .server import CarlaServer


class Session:
    def __init__(self,output):
        output.mkdir(parents=True,exist_ok=True);self.output=output;self.config=ConsoleConfig();self.actors=[dict(a) for a in DEFAULT_ACTORS]
        self.history=History();self.cursor=16.1;self.status='ready';self.source='live';self.rate=1.;self.resources={}
        self.recorder=Recorder(output/'recordings');self.bridge=CarlaBridge(on_snapshot=self.record_live);self.example=ExampleProcess()
        self.connection=dict(connected=False,host='127.0.0.1',port=2000,server_version=None,client_version=None,map='ZUT_Map_Ramp')
        self.events=[dict(message='虚拟车为 CARLA actor，真实物理车等待 ROS 接入',level='info',at=time.time())];self.last_record=None
        self.map=local_map();self.revision=1;self.server=CarlaServer(output);self.server_state=self.server.state();self.lifecycle_task=None;self.attach_at=0;self.attach_task=None
        saved=output/'config.json'
        if saved.exists():
            try:self.config=ConsoleConfig(**{**{k:v for k,v in json.loads(saved.read_text()).items() if k in ConsoleConfig.model_fields},'mode':'virtual','algorithm':'navigation'})
            except (ValueError,OSError):pass
        saved_scene=output/'scene.json'
        if saved_scene.exists():
            try:self.actors=[ActorConfig(**{**a,'goal_yaw':a.get('goal_yaw',a.get('yaw',90))}).model_dump() for a in json.loads(saved_scene.read_text())]
            except (ValueError,OSError,TypeError):pass
        previous=output/'last-world.json'
        if previous.exists():
            try:
                name=json.loads(previous.read_text())['name'];self.map=local_map(name)
                self.connection['map']=name;self.source='live';self.status='stopped'
            except (ValueError,OSError,KeyError):pass
    def remember_map(self):
        (self.output/'last-world.json').write_text(json.dumps({'name':self.map['name']}))
    def event(self,message,level='info'):
        self.events.append(dict(message=message,level=level,at=time.time()));self.events=self.events[-30:]
    def record_live(self,snapshot):
        if self.source=='live' and self.recorder.active:self.recorder.write(snapshot)
    def snapshot(self):
        if self.source=='live':
            s=self.bridge.snapshot or dict(source='live',t=0,frame=0,virtual=None,physical=None,obstacles=[],error=None,control={})
            if self.bridge.process and self.bridge.process.poll() is not None:s={**s,'status':'error','connection_lost':True}
            if not self.connection['connected']:s={**s,'status':'disconnected','connection_lost':True,'virtual':None,'physical':None,'error':None,'control':{},'camera':False}
            return {**s,'received_at':s.get('received_at')}
        s=self.history.sample(self.cursor)
        return {**s,'virtual':s['physical'],'physical':None,'error':None,'iou':None,'windows':None,'legacy_archive':True,'control':{k:v for k,v in s['control'].items() if k in ['throttle','brake','steer']}}
    def state(self):
        snap=self.snapshot()
        if self.bridge.disconnected or (self.bridge.process and self.bridge.process.poll() is not None):self.connection['connected']=False
        live_status=snap.get('status') if self.source=='live' else None
        return dict(snapshot=snap,status=live_status or self.status,source=self.source,cursor=self.cursor,duration=self.history.duration,
            map_name=self.map['name'],server=self.server_state,connection=self.connection,resources=self.resources,config=self.config.model_dump(),revision=self.revision,
            recording=self.recorder.info if self.recorder.active else None,events=self.events[-8:],example=self.example.state(),
            native_events=list(self.bridge.events)[-5:],rate=self.rate)
    async def attach(self):
        info=await asyncio.to_thread(self.bridge.call,'connect',host='127.0.0.1',port=self.server.port)
        geometry=info.pop('geometry',None);opendrive=info.pop('opendrive',None)
        self.connection={**info,'connected':True,'host':'127.0.0.1','port':self.server.port}
        self.source='live';self.status='ready'
        try:self.map=geometry or parse_map(opendrive,info['map']);self.remember_map()
        except (ValueError,KeyError,TypeError):pass
        self.event('已连接 CARLA '+info['server_version'])
    async def lifecycle(self,action):
        try:
            if self.attach_task and not self.attach_task.done():
                self.attach_task.cancel()
                try:await self.attach_task
                except asyncio.CancelledError:pass
            if action=='start':await asyncio.to_thread(self.bridge.close)
            if action in ['stop','restart']:
                await asyncio.to_thread(self.example.stop)
                await asyncio.to_thread(self.bridge.close)
                self.connection['connected']=False
                if self.recorder.active:self.recorder.stop()
                await asyncio.to_thread(self.server.stop)
                self.source='live';self.status='stopped';self.bridge.snapshot=None
            if action in ['start','restart']:
                await asyncio.to_thread(self.server.start)
            self.event({'start':'CARLA 已启动','stop':'CARLA 已停止','restart':'CARLA 已重启'}[action])
        except (ValueError,OSError,psutil.Error) as e:
            self.server.error=str(e);self.event(str(e),'error')
        finally:
            self.server.phase=None;self.server_state=await asyncio.to_thread(self.server.state);self.lifecycle_task=None
    async def attach_safely(self):
        try:await self.attach()
        except (ValueError,OSError) as e:self.event('CARLA 客户端连接失败：'+str(e),'error')
    async def watch_server(self):
        previous=None
        while True:
            try:
                self.server_state=await asyncio.to_thread(self.server.state)
                current=self.server_state['status']
                if current not in ['running']:
                    self.connection['connected']=False
                    if current in ['stopped','error'] and previous in ['running','starting']:
                        self.event(self.server_state.get('error') or 'CARLA 已退出，可重新启动','error' if current=='error' else 'info')
                        if self.recorder.active:self.recorder.stop()
                now=time.monotonic()
                if current=='running' and not self.connection['connected'] and now-self.attach_at>10 and not self.lifecycle_task and (not self.attach_task or self.attach_task.done()):
                    self.attach_at=now;self.attach_task=asyncio.create_task(self.attach_safely())
                previous=current
            except (OSError,psutil.Error) as e:
                self.connection['connected']=False
                self.server_state={**self.server_state,'error':'无法读取 CARLA 进程状态：'+str(e)}
            await asyncio.sleep(.5)
    async def pump(self):
        last=time.monotonic();res_at=0
        while True:
            now=time.monotonic();elapsed=now-last;last=now
            if self.source=='recorded' and self.status=='running':
                self.cursor=min(self.history.duration,self.cursor+elapsed*self.rate)
                if self.cursor>=self.history.duration:
                    self.status='completed';self.event('历史实验回放结束')
                    if self.recorder.active:self.recorder.stop()
            snap=self.snapshot()
            key=(snap.get('source'),snap.get('frame'))
            if self.recorder.active and self.source=='recorded' and key!=self.last_record:
                self.recorder.write(snap);self.last_record=key
            if now-res_at>1:
                try:self.resources=await asyncio.to_thread(sample_resources)
                except (OSError,ValueError):pass
                res_at=now
            await asyncio.sleep(.05)


def create_app(output=None):
    session=Session(Path(output) if output else RUNTIME)
    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(session.pump());monitor=asyncio.create_task(session.watch_server())
        yield
        pending=[task,monitor]+([session.attach_task] if session.attach_task else [])
        for job in pending:job.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        if session.recorder.active:session.recorder.stop()
        await asyncio.to_thread(session.example.stop);await asyncio.to_thread(session.bridge.close)
    app=FastAPI(title='CARLA DT Console',lifespan=lifespan)
    app.state.session=session
    @app.get('/api/bootstrap')
    async def bootstrap():
        return {**session.state(),'actors':session.actors,'map':session.map,'maps':map_list(),'runs':run_list(),
            'parameters':[dict(group=g,key=k,label=l,unit=u,min=lo,max=hi,default=getattr(ConsoleConfig(),k)) for g,k,l,u,lo,hi in PARAMETERS],
            'examples':catalog(),'algorithm_root':str(ALGORITHM_ROOT),'examples_root':str(EXAMPLES_ROOT)}
    @app.get('/api/health')
    async def health():return dict(ok=True,service='carlaDT-service')
    @app.get('/api/traces')
    async def traces():
        points=[]
        for p in session.history.traces():
            points.append({**p,'vx':p['px'],'vy':p['py'],'vv':p['pv'],'heading_v':p['heading_p'],'px':None,'py':None,'pv':None,'heading_p':None,'error':None,'es':None,'ed':None,'eh':None,'iou':None,'virtual_delta':None,'requested_throttle':None,'requested_brake':None})
        return dict(source='recorded',run=session.history.run,points=points,summary=session.history.summary)
    @app.get('/api/resources')
    async def resources():return dict(current=session.resources,history=resource_history())
    @app.get('/api/recordings')
    async def recordings():return dict(recordings=session.recorder.listing(),runs=run_list())
    @app.post('/api/config')
    async def config(payload:dict=Body(...)):
        if session.recorder.active:raise HTTPException(409,'请先关闭数据记录再修改配置')
        if session.status=='running' or (session.source=='live' and session.snapshot().get('status') in ['running','resetting','stopping','preparing','manual']):raise HTTPException(409,'运行中不能修改配置，请先停止')
        try:new=ConsoleConfig(**{**session.config.model_dump(),**payload})
        except ValidationError as e:raise HTTPException(422,str(e))
        session.config=new;session.revision+=1;(session.output/'config.json').write_text(new.model_dump_json(indent=2))
        session.event('实验配置已保存，将在下次启动时生效');return dict(config=new.model_dump(),revision=session.revision)
    @app.post('/api/server')
    async def server_control(payload:dict=Body(...)):
        action=payload.get('action')
        try:session.server.begin(action)
        except ValueError as e:raise HTTPException(409,str(e))
        session.server_state=session.server.state()
        session.lifecycle_task=asyncio.create_task(session.lifecycle(action))
        return session.state()
    @app.post('/api/connect')
    async def connect(payload:dict=Body(default={})):
        if session.recorder.active:raise HTTPException(409,'请先关闭数据记录再切换CARLA连接')
        if session.status=='running' or session.example.active:raise HTTPException(409,'请先停止当前会话')
        host=payload.get('host','127.0.0.1')
        try:port=int(payload.get('port',2000))
        except (TypeError,ValueError):raise HTTPException(400,'RPC端口必须是有效整数')
        if host not in ['127.0.0.1','localhost'] or not 1024<=port<=65535:raise HTTPException(400,'当前服务仅允许连接本机 CARLA 端口')
        try:info=await asyncio.to_thread(session.bridge.call,'connect',host=host,port=port)
        except (OSError,ValueError) as e:raise HTTPException(503,str(e))
        geometry=info.pop('geometry',None);opendrive=info.pop('opendrive',None)
        session.connection={**info,'connected':True,'host':host,'port':port};session.source='live';session.status='ready'
        try:session.map=geometry or parse_map(opendrive,info['map']);session.remember_map()
        except (ValueError,KeyError,TypeError):pass
        session.event('已连接 CARLA '+info['server_version']);return dict(connection=session.connection,map=session.map)
    @app.post('/api/command')
    async def command(payload:dict=Body(...)):
        action=payload.get('action')
        if action not in ['start','stop','reset','seek','source','rate','select_run','manual','release','camera','video','destroy_owned','recreate']:raise HTTPException(400,'未知操作')
        try:
            if action=='source':
                if session.recorder.active:raise ValueError('请先关闭当前数据记录，再切换来源')
                if session.status=='running' or session.example.active or (session.source=='live' and session.snapshot().get('status') in ['running','resetting','stopping']):raise ValueError('请先停止当前会话')
                if payload.get('source')!='recorded':raise ValueError('请使用连接按钮进入实时模式')
                if session.source=='live' and session.connection['connected']:await asyncio.to_thread(session.bridge.call,'release')
                session.source='recorded';session.status='ready';session.map=local_map()
            elif action=='select_run':
                if session.recorder.active:raise ValueError('请先关闭当前记录任务')
                if session.source=='live' and session.snapshot().get('status') in ['running','resetting','stopping','manual']:raise ValueError('请先停止 CARLA 控制再打开归档')
                session.source='recorded';session.map=local_map()
                session.history=History(payload['run']);session.cursor=0;session.status='ready'
            elif action=='rate':
                rate=float(payload['rate'])
                if rate not in [.25,.5,1,2,4]:raise ValueError('不支持的回放倍率')
                session.rate=rate
            elif session.source=='recorded':
                if action=='start':
                    if session.cursor>=session.history.duration:session.cursor=0
                    session.status='running';session.event('开始历史回放（非实时控制）')
                elif action=='stop':session.status='stopped';session.event('历史回放已停止')
                elif action=='reset':session.cursor=0;session.status='ready';session.event('历史回放已返回首帧；未移动车辆')
                elif action=='seek':session.cursor=max(0,min(session.history.duration,float(payload['t'])))
                else:raise ValueError('此操作需要连接实时 CARLA')
            else:
                if session.example.active:raise ValueError('示例正在独占运行，请先停止示例')
                if action=='recreate':
                    response=await asyncio.to_thread(session.bridge.call,'rebuild',config=session.config.model_dump(),actors=session.actors,destroy_all=True)
                    session.status=response.get('status','ready')
                elif action in ['start','reset']:
                    response=await asyncio.to_thread(session.bridge.call,action,config=session.config.model_dump(),actors=session.actors)
                    session.status=response.get('status','ready')
                else:await asyncio.to_thread(session.bridge.call,action,**{k:v for k,v in payload.items() if k!='action'})
                session.event({'start':'实时任务已启动','stop':'车辆受控制动中','reset':'CARLA 车辆正在导航归位','recreate':'场景动态 actor 已销毁，全部车辆已在起点重新生成'}.get(action,'操作已下发'))
            return session.state()
        except (ValueError,OSError,KeyError,TypeError) as e:raise HTTPException(409,str(e))
    @app.post('/api/actors')
    async def actors(payload:ActorConfig):
        if session.example.active:raise HTTPException(409,'请先停止正在运行的官方示例')
        if session.source!='live':raise HTTPException(409,'生成 actor 需要连接实时 CARLA，历史记录不会被修改')
        try:result=await asyncio.to_thread(session.bridge.call,'spawn',actor=payload.model_dump())
        except (ValueError,OSError) as e:raise HTTPException(409,str(e))
        session.actors=[a for a in session.actors if a['id']!=payload.id]+[payload.model_dump()];session.event('已生成 '+payload.id);return result
    @app.post('/api/actors/spawn-all')
    async def spawn_all(payload:list[ActorConfig]):
        if session.example.active:raise HTTPException(409,'请先停止正在运行的官方示例')
        if session.source!='live' or not session.connection['connected']:raise HTTPException(409,'请先连接实时 CARLA')
        ids=[a.id for a in payload]
        if not payload or len(ids)!=len(set(ids)) or sum(a.role=='ego' for a in payload)!=1 or not any(a.id=='ego' and a.role=='ego' for a in payload):
            raise HTTPException(422,'场景需要一个 id 为 ego 的自车，且角色编号不可重复')
        specs=[a.model_dump() for a in payload]
        try:result=await asyncio.to_thread(session.bridge.call,'rebuild',config=session.config.model_dump(),actors=specs)
        except (ValueError,OSError) as e:raise HTTPException(409,str(e))
        session.actors=specs;session.status='ready'
        (session.output/'scene.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2))
        session.event('全部车辆已在各自起点生成');return result
    @app.post('/api/scene')
    async def scene(payload:list[ActorConfig]):
        if session.example.active:raise HTTPException(409,'请先停止正在运行的官方示例')
        if session.snapshot().get('status') in ['running','resetting','stopping','preparing','manual']:raise HTTPException(409,'请先停止任务再保存场景')
        ids=[x.id for x in payload]
        if not payload or len(ids)!=len(set(ids)) or sum(x.role=='ego' for x in payload)!=1 or not any(x.id=='ego' and x.role=='ego' for x in payload):raise HTTPException(422,'场景需要一个id为ego的自车，且角色编号不可重复')
        session.actors=[a.model_dump() for a in payload];(session.output/'scene.json').write_text(json.dumps(session.actors,ensure_ascii=False,indent=2))
        session.event('起终点已保存；现有actor位置保持不变');return dict(actors=session.actors)
    @app.post('/api/map')
    async def choose_map(payload:dict=Body(...)):
        if session.example.active:raise HTTPException(409,'请先停止正在运行的官方示例')
        name=payload.get('name','')
        if session.source!='live':raise HTTPException(409,'历史记录绑定原地图，切换地图需要实时连接')
        try:info=await asyncio.to_thread(session.bridge.call,'map',timeout=50,name=name);session.map=info['geometry'] if 'geometry' in info else parse_map(info['opendrive'],info['map']);session.connection['map']=info['map'];session.remember_map()
        except (ValueError,OSError) as e:raise HTTPException(409,str(e))
        session.event('地图已加载：'+info['map']);return session.map
    @app.post('/api/recording')
    async def recording(payload:dict=Body(...)):
        try:
            if payload.get('enabled'):
                info=session.recorder.start(session.source,session.config.model_dump());session.last_record=None
                session.recorder.write(session.snapshot());session.last_record=(session.source,session.snapshot().get('frame'))
            else:info=session.recorder.stop()
        except ValueError as e:raise HTTPException(409,str(e))
        session.event('已开启物理量记录' if payload.get('enabled') else '记录文件已保存');return info
    @app.post('/api/examples/start')
    async def example_start(payload:dict=Body(...)):
        if session.source!='live':raise HTTPException(409,'请先连接 CARLA，并核对示例版本')
        if session.snapshot().get('status') in ['running','resetting','stopping']:raise HTTPException(409,'请先停止当前车辆任务')
        try:
            item=next((e for e in catalog() if e['id']==payload['id']),None)
            if not item:raise ValueError('未知示例')
            args=dict(payload.get('args',{}));flags={f for a in item['args'] for f in a['flags']}
            for flag,value in [('--host',session.connection['host']),('--port',session.connection['port'])]:
                if flag in flags:args.setdefault(flag,value)
            if '--port' not in flags and session.connection['port']!=2000:raise ValueError('此程序未提供RPC端口参数，请核对源码中的固定连接地址')
            cmd=build_command(payload['id'],args,session.connection.get('server_version',''))
            probe=await asyncio.to_thread(subprocess.run,[cmd[0],'-c','import carla; print(carla.Client("127.0.0.1",2000).get_client_version())'],capture_output=True,text=True,timeout=8)
            if probe.returncode or not probe.stdout.strip().startswith(item['version']):raise ValueError('示例Python环境不匹配，请通过 CARLADT_EXAMPLES_PYTHON 指定安装CARLA '+item['version']+' 的解释器')
            await asyncio.to_thread(session.bridge.call,'release')
            session.example.start(cmd,payload['id'],EXAMPLES_ROOT);session.event('示例已启动：'+payload['id']);return session.example.state()
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:raise HTTPException(409,str(e))
    @app.post('/api/examples/stop')
    async def example_stop():return await asyncio.to_thread(session.example.stop)
    @app.get('/api/files/{relative:path}')
    async def file(relative:str):
        try:return FileResponse(safe_file(session.recorder.root,relative),filename=Path(relative).name)
        except ValueError:raise HTTPException(400,'无效文件路径')
        except FileNotFoundError:raise HTTPException(404,'记录文件不存在')
    @app.get('/api/video')
    async def video(camera:bool=False,run:str|None=None):
        name=run or session.history.run
        if name not in {x['id'] for x in run_list()}:raise HTTPException(404,'实验不存在')
        p=RUNTIME/'history_video'/(name+('-camera' if camera else '')+'.mp4')
        if not p.exists() and name=='p4_c2_final':p=ALGORITHM_ROOT/'data/carla_overtake/p4_c2_final/p4_constrained_sync.mp4'
        if not p.is_file():raise HTTPException(404,'此实验暂无浏览器兼容录像，可运行 scripts/prepare_videos.py 转换本机原始AVI')
        return FileResponse(p,media_type='video/mp4')
    @app.get('/api/videos')
    async def videos():
        folder=RUNTIME/'videos';return [dict(name=p.name,size=p.stat().st_size,url='/api/videos/'+p.name) for p in sorted(folder.glob('*.mp4'),reverse=True)] if folder.exists() else []
    @app.get('/api/videos/{name}')
    async def saved_video(name:str):
        try:return FileResponse(safe_file(RUNTIME/'videos',name),filename=name)
        except (ValueError,FileNotFoundError):raise HTTPException(404,'视频不存在')
    @app.get('/api/report/{name}')
    async def report(name:str):
        if name not in ['p4_sync_results.png','p4_sync_results.pdf','p4_pose_and_safety.png','p4_pose_and_safety.pdf']:raise HTTPException(404)
        return FileResponse(ALGORITHM_ROOT/'data/carla_overtake/p4_comparison_final'/name)
    @app.get('/api/map-image')
    async def map_image():
        p=RUNTIME/'map-native.png'
        if not p.exists():raise HTTPException(404,'当前使用 OpenDRIVE 矢量底图')
        return FileResponse(p)
    @app.get('/api/camera')
    async def camera():
        if session.source!='live':raise HTTPException(409,'当前为历史回放')
        async def frames():
            while session.source=='live':
                try:
                    data=(RUNTIME/'camera.jpg').read_bytes();yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+data+b'\r\n'
                except OSError:pass
                await asyncio.sleep(.1)
        return StreamingResponse(frames(),media_type='multipart/x-mixed-replace; boundary=frame')
    @app.websocket('/ws')
    async def websocket(ws:WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(session.state());await asyncio.sleep(.1)
        except (WebSocketDisconnect,RuntimeError):pass
    dist=ROOT/'frontend/dist'
    if dist.exists():app.mount('/',StaticFiles(directory=dist,html=True),name='web')
    return app


app=create_app()
