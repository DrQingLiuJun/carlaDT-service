#!/usr/bin/env python3
"""JSON-lines CARLA adapter. Native interpreter only; no ASGI dependencies.

Explicit actor ownership, one world tick owner, CARLA virtual vehicle,
navigation reset and manual-input watchdog. Explicit rebuild clears dynamic scene actors.
"""
import sys,os,json,time,math,threading,queue,signal,copy,subprocess
from pathlib import Path
from collections import deque
import carla
import numpy as np
try:from backend.native_map import extract_map
except ModuleNotFoundError:from native_map import extract_map
try:from backend.navigation_limits import corner_speed_kmh,following_limit
except ModuleNotFoundError:from navigation_limits import corner_speed_kmh,following_limit

ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'runtime';RUNTIME.mkdir(exist_ok=True)
COMMANDS=queue.Queue();OUTPUT_LOCK=threading.Lock()
def emit(message):
    with OUTPUT_LOCK:print(json.dumps(message,allow_nan=False),flush=True)
def event(message,level='info'):emit(dict(type='event',message=message,level=level,timestamp=time.time()))
def wrap(v):return (v+math.pi)%(2*math.pi)-math.pi
def velocity(a):
    v=a.get_velocity();return math.sqrt(v.x*v.x+v.y*v.y+v.z*v.z)
def pose(a):
    tf=a.get_transform();return dict(x=tf.location.x,y=tf.location.y,yaw=math.radians(tf.rotation.yaw),v=velocity(a),length=2*a.bounding_box.extent.x,width=2*a.bounding_box.extent.y)


def vehicle_gap(a,b):
    def polygon(actor):
        tf=actor.get_transform();bb=actor.bounding_box;c=math.cos(math.radians(tf.rotation.yaw));s=math.sin(math.radians(tf.rotation.yaw))
        return [(tf.location.x+c*(x+bb.location.x)-s*(y+bb.location.y),tf.location.y+s*(x+bb.location.x)+c*(y+bb.location.y)) for x,y in [(-bb.extent.x,-bb.extent.y),(bb.extent.x,-bb.extent.y),(bb.extent.x,bb.extent.y),(-bb.extent.x,bb.extent.y)]]
    p,q=polygon(a),polygon(b);separated=False
    for poly in [p,q]:
        for i in range(4):
            x,y=poly[i];xx,yy=poly[(i+1)%4];nx,ny=-(yy-y),xx-x
            u=[px*nx+py*ny for px,py in p];v=[px*nx+py*ny for px,py in q]
            if max(u)<min(v) or max(v)<min(u):separated=True
    if not separated:return 0.
    best=float('inf')
    for src,dst in [(p,q),(q,p)]:
        for x,y in src:
            for i in range(4):
                ax,ay=dst[i];bx,by=dst[(i+1)%4];dx,dy=bx-ax,by-ay
                u=max(0.,min(1.,((x-ax)*dx+(y-ay)*dy)/max(1e-10,dx*dx+dy*dy)))
                best=min(best,math.hypot(x-ax-u*dx,y-ay-u*dy))
    return best


class Worker:
    def __init__(self):
        self.client=None;self.world=None;self.actors={};self.specs={};self.agents={};self.routes={};self.route_index={};self.disconnected=False;self.endpoint=None
        self.status='ready';self.config={};self.owns_clock=False;self.original_settings=None;self.camera=None;self.camera_queue=queue.Queue(maxsize=3)
        self.camera_view='follow';self.camera_cache={};self.last_camera_frame=None;self.video=None;self.video_path=None;self.video_frames=0;self.last_manual=0.;self.control={};self.epoch=None;self.last_emit=0.;self.shutdown=False;self.brake_steps=0;self.client_info={};self.collision_sensor=None;self.collisions=deque(maxlen=256)
    def require_world(self):
        if self.world is None or self.disconnected:raise ValueError('CARLA连接已断开，请重新连接')
    def connect(self,host,port):
        if self.owns_clock and not self.disconnected:raise ValueError('请先停止当前任务')
        if self.actors and self.endpoint and self.endpoint!=(host,port):raise ValueError('切换服务器前请先清理当前自有actor')
        c=carla.Client(host,port);c.set_timeout(6.);version=c.get_server_version();local=c.get_client_version()
        if version.split('-')[0]!=local.split('-')[0]:raise ValueError('原生客户端 '+local+' 与服务端 '+version+' 不匹配，请设置 CARLADT_CARLA_PYTHON')
        new_world=c.get_world()
        if self.world and self.world.id!=new_world.id:
            self.actors={};self.specs={};self.camera=None;self.collision_sensor=None;self.owns_clock=False;self.original_settings=None
        self.client=c;self.world=new_world;self.disconnected=False;self.endpoint=(host,port);self.client_info=dict(server_version=version,client_version=local)
        if self.owns_clock:self.brake_all();self.restore();self.status='stopped'
        api=Path('/home/liumeng/deepseek_workspace/carla-build/carla-runtime/PythonAPI/carla') if version.startswith('0.9.13') else Path('/home/liumeng/deepseek_workspace/carla-0.9.16/PythonAPI/carla')
        sys.path.insert(0,str(api))
        bp=[]
        for b in self.world.get_blueprint_library().filter('vehicle.*'):
            bp.append(dict(id=b.id,colors=list(b.get_attribute('color').recommended_values) if b.has_attribute('color') else []))
        return dict(self.client_info,map=self.world.get_map().name.split('/')[-1],geometry=extract_map(self.world.get_map()),blueprints=sorted(bp,key=lambda x:x['id']),available_maps=[m.split('/')[-1] for m in c.get_available_maps()])
    def claim(self,allow_async=False):
        if self.owns_clock:return
        current=self.world.get_settings()
        if current.synchronous_mode:raise ValueError('当前世界已有同步客户端；请先结束其运行，控制台不争抢tick')
        self.original_settings=current;settings=self.world.get_settings();settings.synchronous_mode=True;settings.fixed_delta_seconds=self.config.get('dt',.05)
        settings.substepping=True;settings.max_substep_delta_time=.01;settings.max_substeps=10;self.world.apply_settings(settings);self.owns_clock=True
        # A version string alone cannot certify a custom server build. Probe
        # that the clock really waits before accepting a timed experiment.
        try:
            a=self.world.tick(5.)
            deadline=time.monotonic()+1.
            while self.world.get_snapshot().frame<a and time.monotonic()<deadline:time.sleep(.002)
            time.sleep(.06);b=self.world.get_snapshot().frame
        except Exception:
            self.restore();raise
        if b!=a:
            self.restore()
            if allow_async:
                event('服务端自主推进仿真帧；手动驾驶使用服务端时钟，时窗实验不可启动','warning');return
            raise ValueError('CARLA同步时钟校验失败：未下发tick时帧号仍从 '+str(a)+' 推进到 '+str(b)+'。请使用支持同步模式的服务端，或停止外部tick源；车辆保持驻车')
    def restore(self):
        if self.owns_clock and self.original_settings:
            self.world.apply_settings(self.original_settings)
        self.owns_clock=False;self.original_settings=None
    def spawn(self,spec):
        self.require_world()
        if self.status in ['running','resetting','preparing','stopping','manual']:raise ValueError('运行中不能更新actor')
        key=spec['id'];old=self.actors.get(key)
        if old and old.is_alive:raise ValueError('此角色已有车辆；请使用导航归位，或先清理本控制台actor')
        bp=self.world.get_blueprint_library().find(spec['blueprint']);role=spec.get('role','obstacle')
        if bp.has_attribute('color'):bp.set_attribute('color','233,145,70' if role=='ego' else '221,65,80')
        if bp.has_attribute('role_name'):bp.set_attribute('role_name','carlaDT_'+key)
        loc=carla.Location(x=spec['x'],y=spec['y'],z=spec.get('z',.5));wp=self.world.get_map().get_waypoint(loc)
        z=max(loc.z,wp.transform.location.z+.4) if wp else loc.z
        a=self.world.try_spawn_actor(bp,carla.Transform(carla.Location(x=loc.x,y=loc.y,z=z),carla.Rotation(yaw=spec['yaw'])))
        if not a:raise ValueError('生成位置被占用或不适合此车辆，请在地图上重新选点')
        a.apply_control(carla.VehicleControl(brake=1.));self.actors[key]=a;self.specs[key]=spec
        if role=='ego':
            self.collision_sensor=self.world.spawn_actor(self.world.get_blueprint_library().find('sensor.other.collision'),carla.Transform(),attach_to=a)
            self.collision_sensor.listen(lambda e:self.collisions.append(dict(frame=e.frame,other=e.other_actor.type_id)))
        event('已生成 '+key+' · actor '+str(a.id));return dict(id=key,actor_id=a.id,pose=pose(a))
    def rebuild(self,config,actors,destroy_all=False):
        self.require_world()
        if self.owns_clock or self.status in ['running','resetting','preparing','stopping','manual']:
            raise ValueError('请先停止当前任务再重新生成车辆')
        self.destroy_owned()
        if destroy_all:
            # Dynamic scene actors only: keep spectator, signals and map infrastructure.
            dynamic=[a for a in self.world.get_actors() if a.type_id.startswith(('vehicle.','walker.','sensor.','controller.ai.walker'))]
            dynamic.sort(key=lambda a:0 if a.type_id.startswith(('sensor.','controller.')) else 1)
            for a in dynamic:
                if a.is_alive:
                    if a.type_id.startswith(('sensor.','controller.')):
                        try:a.stop()
                        except RuntimeError:pass
                    a.destroy()
        self.config=config;self.status='ready';self.agents={};self.routes={};self.route_index={};self.control={}
        self.epoch=None
        try:spawned=[self.spawn(sp) for sp in actors]
        except Exception:
            self.destroy_owned()
            raise
        event('场景车辆已全部在起点重新生成')
        return dict(status='ready',actors=spawned)

    def prepare_agents(self, reset=False):
        from agents.navigation.basic_agent import BasicAgent
        from agents.navigation.local_planner import LocalPlanner, RoadOption
        try:
            from backend.kinematic_route import plan_on_map
        except ModuleNotFoundError:
            from kinematic_route import plan_on_map

        class TrajectoryTracker(LocalPlanner):
            def run_step(self, debug=False):
                location = self._vehicle.get_location()
                lookahead = self._base_min_distance + 0.5 * velocity(self._vehicle)
                # Keep the final target until Worker verifies both pose and stop.
                while len(self._waypoints_queue) > 1:
                    waypoint, _ = self._waypoints_queue[0]
                    if location.distance(waypoint.transform.location) >= lookahead:
                        break
                    self._waypoints_queue.popleft()
                if not self._waypoints_queue:
                    return carla.VehicleControl(brake=1.0)
                self.target_waypoint, self.target_road_option = self._waypoints_queue[0]
                return self._vehicle_controller.run_step(self._target_speed, self.target_waypoint)

        class ReferenceWaypoint:
            def __init__(self, base, x, y, yaw):
                self.base = base
                self.transform = carla.Transform(
                    carla.Location(x=x, y=y, z=base.transform.location.z), carla.Rotation(yaw=yaw))

            def __getattr__(self, name):
                return getattr(self.base, name)

        self.agents, self.routes, self.route_index, self.trajectories = {}, {}, {}, {}
        road_map = self.world.get_map()
        for key, actor in self.actors.items():
            if not actor.is_alive:
                continue
            spec = self.specs[key]
            if spec.get('behavior') == 'stationary' and not reset:
                self.agents[key] = None
                continue
            goal = ((spec['x'], spec['y'], spec['yaw']) if reset else
                    (spec['goal_x'], spec['goal_y'], spec.get('goal_yaw', 90)))
            tf = actor.get_transform()
            loc = tf.location
            start = loc.x, loc.y, tf.rotation.yaw
            if (math.hypot(start[0]-goal[0], start[1]-goal[1]) < self.config['arrival_distance']
                    and abs(wrap(math.radians(start[2]-goal[2]))) < math.radians(10)):
                self.agents[key] = None
                continue
            physics = actor.get_physics_control()
            wheels = physics.wheels
            steering_curve = [(p.x, p.y) for p in physics.steering_curve[:8]]
            steer = max((wheel.max_steer_angle for wheel in wheels), default=0.0)
            direction = tf.get_forward_vector()
            axle = [(wheel.position.x * direction.x + wheel.position.y * direction.y) / 100
                    for wheel in wheels]
            wheelbase = max(axle) - min(axle) if axle else 0.0
            if not 0.5 <= wheelbase <= 12 or not 0 < steer < 90:
                raise ValueError(key + ' 无法读取有效的轴距和前轮转角')
            target = carla.Location(x=goal[0], y=goal[1], z=loc.z)
            try:
                def locate_driving(x, y):
                    return road_map.get_waypoint(carla.Location(x=x, y=y, z=loc.z), project_to_road=False)

                bounds = actor.bounding_box.extent
                # Leave actuator authority for tracking; full-lock paths have
                # no nonzero speed at which the steering curve can follow them.
                planning_steer = math.degrees(math.atan(.98*math.tan(math.radians(steer))))
                samples = plan_on_map(road_map, locate_driving, road_map.get_waypoint(loc),
                                      road_map.get_waypoint(target), start, goal, wheelbase, planning_steer,
                                      2 * bounds.y, 2 * bounds.x)
            except ValueError as error:
                raise ValueError(key + '：' + str(error)) from error
            speed = (self.config['return_speed_kmh'] if reset else
                     self.config['speed_kmh'] if spec['role'] == 'ego' else spec['speed_kmh'])
            if actor.type_id == 'vehicle.haut.car':
                speed = min(speed, 25.0)
            options = {'base_min_distance': 0.4, 'max_steering': 1.0, 'ignore_vehicles': True, 'dt': self.config.get('dt', .05)}
            agent = BasicAgent(actor, target_speed=speed, opt_dict=options)
            agent._local_planner = TrajectoryTracker(actor, opt_dict=options)
            agent.set_global_plan([(ReferenceWaypoint(wp, x, y, yaw), RoadOption.LANEFOLLOW)
                                   for x, y, yaw, _, wp in samples])
            self.agents[key] = agent
            self.routes[key] = [(row[0], row[1]) for row in samples]
            self.trajectories[key] = speed, [row[3] for row in samples], wheelbase, steer, steering_curve
            self.route_index[key] = 0

    def start(self,config,actors):
        self.require_world()
        if config.get('mode')!='virtual':raise ValueError('ROS 物理车尚未接入，当前只支持 CARLA 虚拟车')
        if config.get('algorithm')!='navigation':raise ValueError('旧独立虚拟模型已废除，请使用 CARLA 路线导航')
        if self.status in ['running','resetting','stopping','manual','preparing']:raise ValueError('已有任务或驾驶控制正在运行')
        self.config=config
        for sp in actors:
            if sp['id'] in self.specs:self.specs[sp['id']]=sp
        if not self.actors:
            for spec in actors:self.spawn(spec)
            for _ in range(8):self.world.wait_for_tick(2.)
        if 'ego' not in self.actors:raise ValueError('请先生成 CARLA 自车')
        self.prepare_agents(False);self.claim();self.collisions=deque(maxlen=256);self.epoch=self.world.get_snapshot().timestamp.elapsed_seconds
        self.status='running';event('CARLA 虚拟车路线导航已启动');return dict(status=self.status)
    def reset(self,config,actors):
        self.require_world()
        if config.get('mode')!='virtual':raise ValueError('ROS 物理车尚未接入')
        if self.status in ['running','preparing','stopping','manual']:raise ValueError('请先停止运行再归位')
        self.config=config
        for sp in actors:
            if sp['id'] in self.specs:self.specs[sp['id']]=sp
        if not self.actors:raise ValueError('尚未生成车辆，无法导航归位')
        self.prepare_agents(True);self.claim();self.status='resetting';self.epoch=self.world.get_snapshot().timestamp.elapsed_seconds
        return dict(status=self.status)
    def request_stop(self):
        if self.owns_clock:self.status='stopping';self.brake_steps=0
        else:self.status='stopped';self.brake_all()
        return dict(status=self.status)
    def brake_all(self):
        for a in self.actors.values():
            if a.is_alive:a.apply_control(carla.VehicleControl(brake=1.))
        self.control.update(throttle=0.,brake=1.,steer=0.)
    def navigation_step(self):
        resetting=self.status=='resetting';arrived=[]
        ego=self.actors.get('ego');p=pose(ego) if ego and ego.is_alive else None
        for key,a in self.actors.items():
            if not a.is_alive:raise ValueError('受控actor已被外部程序删除')
            sp=self.specs[key];goal=(sp['x'],sp['y']) if resetting else (sp['goal_x'],sp['goal_y'])
            distance=math.hypot(a.get_location().x-goal[0],a.get_location().y-goal[1]);agent=self.agents.get(key)
            is_ego=key=='ego';park=not resetting and sp.get('behavior')=='stationary'
            desired_yaw=sp['yaw'] if resetting else sp.get('goal_yaw',90)
            heading_error=wrap(math.radians(desired_yaw-a.get_transform().rotation.yaw))
            reached=distance<self.config['arrival_distance'] and abs(heading_error)<math.radians(10)
            if park or reached or agent is None:a.apply_control(carla.VehicleControl(brake=1.));arrived.append(park or (reached and velocity(a)<.1));continue
            path = self.routes[key]
            cruise, curvature, wheelbase, steer, steering_curve = self.trajectories[key]
            road_limit = a.get_speed_limit()
            if road_limit > 0:
                cruise = min(cruise, road_limit)
            index = self.route_index[key]
            loc = a.get_location()
            index = min(range(index, min(len(path), index + 40)),
                        key=lambda i: math.hypot(path[i][0]-loc.x, path[i][1]-loc.y))
            self.route_index[key] = index
            peak = max(abs(k) for k in curvature[index:index + 40])
            corner_speed = corner_speed_kmh(peak,wheelbase,steer,steering_curve)
            stopping_speed = 3.6 * math.sqrt(2 * max(0.0, distance-self.config['arrival_distance']*.6))
            target_speed=min(cruise,corner_speed,stopping_speed if index>=len(path)-40 else cruise)
            traffic=[pose(b) for b in self.world.get_actors().filter('vehicle.*') if b.id!=a.id and b.is_alive] if self.world else []
            target_speed,emergency=following_limit(pose(a),path,index,traffic,target_speed,self.config.get('min_gap',.8))
            agent.set_target_speed(target_speed)
            u = agent.run_step()
            if emergency:u.throttle=0.;u.brake=1.
            if is_ego:self.control.update(target_speed_kmh=target_speed,corner_speed_kmh=corner_speed,following_brake=float(emergency))
            final_yaw = math.radians(desired_yaw)
            overshoot = (loc.x-goal[0])*math.cos(final_yaw) + (loc.y-goal[1])*math.sin(final_yaw)
            if index >= len(path)-8 and overshoot > self.config['arrival_distance']:
                raise ValueError(key + ' 越过轨迹终点，请重新规划')
            if a.type_id == 'vehicle.haut.car' and u.throttle > 0 and a.get_control().gear <= 0:
                u.manual_gear_shift, u.gear = True, 1
            if is_ego:self.control.update(throttle=u.throttle,brake=u.brake,steer=u.steer)
            a.apply_control(u);arrived.append(False)
        if arrived and all(arrived):self.status='ready' if resetting else 'completed';self.brake_all();self.restore();event('导航归位完成' if resetting else '路线任务完成')
    def camera_enable(self,view='follow'):
        if 'ego' not in self.actors:raise ValueError('请先在场景编排生成自车')
        self.camera_view=view
        if self.camera:self.update_camera();return
        bp=self.world.get_blueprint_library().find('sensor.camera.rgb')
        for k,v in [('image_size_x','1280'),('image_size_y','720'),('fov','90'),('sensor_tick','0.05')]:bp.set_attribute(k,v)
        self.camera=self.world.spawn_actor(bp,carla.Transform());self.update_camera()
        def receive(image):
            try:self.camera_queue.put_nowait(image)
            except queue.Full:
                try:self.camera_queue.get_nowait()
                except queue.Empty:pass
                try:self.camera_queue.put_nowait(image)
                except queue.Full:pass
        self.camera.listen(receive);event('RGB相机已启用')
    def update_camera(self):
        if not self.camera or 'ego' not in self.actors:return
        tf=self.actors['ego'].get_transform();p=tf.location
        if self.camera_view=='top':cam=carla.Transform(carla.Location(x=p.x,y=p.y,z=p.z+42),carla.Rotation(pitch=-89.9,yaw=90))
        elif self.camera_view=='front':
            f=tf.get_forward_vector();cam=carla.Transform(carla.Location(x=p.x+f.x*1.2,y=p.y+f.y*1.2,z=p.z+1.8),tf.rotation)
        else:
            f=tf.get_forward_vector();cam=carla.Transform(carla.Location(x=p.x-f.x*9,y=p.y-f.y*9,z=p.z+6),carla.Rotation(pitch=-18,yaw=tf.rotation.yaw))
        self.camera.set_transform(cam)
    def camera_process(self):
        if not self.camera:return
        import cv2
        image=None
        while True:
            try:image=self.camera_queue.get_nowait()
            except queue.Empty:break
        if image is None:return
        a=np.frombuffer(image.raw_data,dtype=np.uint8).reshape(image.height,image.width,4)[:,:,:3].copy()
        ok,data=cv2.imencode('.jpg',a,[cv2.IMWRITE_JPEG_QUALITY,82])
        if ok:
            tmp=RUNTIME/'camera.next.jpg';tmp.write_bytes(data.tobytes());tmp.replace(RUNTIME/'camera.jpg');self.last_camera_frame=image.frame
        if self.video:self.video.write(a);self.video_frames+=1
    def video_command(self,enabled):
        import cv2
        if enabled:
            if self.video:return dict(recording=True)
            if self.world.get_settings().no_rendering_mode:raise ValueError('当前世界关闭渲染，无法录制RGB视频')
            self.camera_enable(self.camera_view);folder=RUNTIME/'videos';folder.mkdir(exist_ok=True);self.video_path=folder/(time.strftime('%Y%m%d-%H%M%S')+'.avi')
            self.video=cv2.VideoWriter(str(self.video_path),cv2.VideoWriter_fourcc(*'MJPG'),20.,(1280,720));self.video_frames=0
            if not self.video.isOpened():self.video=None;raise ValueError('视频编码器不可用')
            return dict(recording=True,path=str(self.video_path))
        if self.video:
            self.video.release();self.video=None;path=self.video_path;frames=self.video_frames
            encoder=os.environ.get('CARLADT_FFMPEG')
            if encoder and frames:
                def transcode():
                    r=subprocess.run([encoder,'-hide_banner','-loglevel','error','-y','-i',str(path),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(path.with_suffix('.mp4'))],capture_output=True,text=True)
                    event('视频MP4已保存：'+path.with_suffix('.mp4').name if r.returncode==0 else 'MP4编码失败；原始AVI保留', 'info' if r.returncode==0 else 'error')
                threading.Thread(target=transcode,daemon=True).start()
            event('原始视频已保存：'+path.name)
        return dict(recording=False,path=str(self.video_path) if self.video_path else None)
    def step(self):
        try:
            if self.owns_clock and not self.world.get_settings().synchronous_mode:raise ValueError('世界同步模式被外部修改；已停止控制')
            if self.status in ['running','resetting']:self.navigation_step()
            elif self.status=='manual':
                if time.monotonic()-self.last_manual>.35:self.brake_all()
                self.update_camera()
            elif self.status=='stopping':
                self.brake_all();self.brake_steps+=1
                if all(velocity(a)<.08 for a in self.actors.values() if a.is_alive):self.status='stopped';self.restore();event('车辆已驻车')
            if self.owns_clock:
                self.update_camera();frame=self.world.tick(5.)
                # tick RPC completion can precede delivery of the client-side
                # snapshot. Never run the next controller step on a stale frame.
                snapshot=self.world.get_snapshot()
                if snapshot.frame<frame:snapshot=self.world.wait_for_tick(3.)
                if snapshot.frame!=frame:raise ValueError('仿真帧被外部客户端推进，已停止争用世界时钟')
            self.camera_process()
        except Exception as e:
            event(str(e),'error');self.brake_all()
            self.status='error';self.restore()
    def sample(self):
        snap=self.world.get_snapshot();elapsed=snap.timestamp.elapsed_seconds
        v=pose(self.actors['ego']) if 'ego' in self.actors and self.actors['ego'].is_alive else None
        obstacles=[dict(id=k,**pose(a)) for k,a in self.actors.items() if k!='ego' and a.is_alive]
        gaps=[vehicle_gap(self.actors['ego'],a) for k,a in self.actors.items() if k!='ego' and a.is_alive] if v else []
        if v:
            u=self.actors['ego'].get_control();self.control.update(throttle=u.throttle,brake=u.brake,steer=u.steer)
        phase='RESETTING' if self.status=='resetting' else 'MANUAL' if self.status=='manual' else 'NAVIGATION'
        return dict(source='live',vehicle_semantics='carla_virtual_ros_physical',t=max(0.,elapsed-(self.epoch if self.epoch is not None else elapsed)),world_elapsed_seconds=elapsed,frame=snap.frame,phase=phase,status=self.status,
            virtual=v,physical=None,obstacles=obstacles,error=None,reference_path=self.routes.get('ego',[]),windows=None,collisions=list(self.collisions),reference=None,control=self.control,gap=min(gaps) if gaps else None,iou=None,
            camera=bool(self.camera and self.last_camera_frame is not None),camera_frame=self.last_camera_frame,video=bool(self.video),received_at=time.time(),owned_actor_ids=[a.id for a in self.actors.values() if a.is_alive])
    def action(self,msg):
        action=msg['action']
        if action=='map_geometry':
            self.require_world();return extract_map(self.world.get_map())
        if action=='connect':return self.connect(msg.get('host','127.0.0.1'),msg.get('port',2000))
        if action=='shutdown':self.cleanup();self.shutdown=True;return {}
        self.require_world()
        if action=='spawn':return self.spawn(msg['actor'])
        if action=='rebuild':return self.rebuild(msg['config'],msg['actors'],msg.get('destroy_all',False))
        if action=='start':return self.start(msg['config'],msg['actors'])
        if action=='reset':return self.reset(msg['config'],msg['actors'])
        if action=='stop':return self.request_stop()
        if action=='camera':self.camera_enable(msg.get('view','follow'));return {}
        if action=='video':return self.video_command(msg.get('enabled',False))
        if action=='manual':
            if self.status in ['running','preparing','resetting','stopping']:raise ValueError('请先停止自动任务')
            if 'ego' not in self.actors:raise ValueError('请先生成自车')
            if msg.get('release'):self.brake_all();self.status='stopped';self.restore();return {}
            values=[float(msg.get(k,0)) for k in ('throttle','brake','steer')]
            if not all(math.isfinite(x) for x in values):self.brake_all();raise ValueError('驾驶输入必须为有限数值')
            if not self.config:
                self.config=dict(dt=.05,mode='virtual');self.epoch=self.world.get_snapshot().timestamp.elapsed_seconds
            if self.status!='manual':
                self.config['mode']='virtual';self.claim(allow_async=True);self.epoch=self.world.get_snapshot().timestamp.elapsed_seconds
            self.status='manual';self.last_manual=time.monotonic()
            th=max(0.,min(.8,float(msg.get('throttle',0))));br=max(0.,min(1.,float(msg.get('brake',0))));st=max(-.7,min(.7,float(msg.get('steer',0))))
            self.actors['ego'].apply_control(carla.VehicleControl(throttle=0. if br else th,brake=br,steer=st));self.control=dict(throttle=th,brake=br,steer=st);return {}
        if action=='release':
            if self.status in ['running','preparing','resetting','stopping']:raise ValueError('请先停止当前任务')
            self.brake_all();self.status='stopped';self.restore();return {}
        if action=='destroy_owned':
            if self.owns_clock:raise ValueError('请先停止任务')
            self.destroy_owned();return {}
        if action=='map':
            if self.owns_clock or self.actors:raise ValueError('请先停止并清理本控制台actor，再切换地图')
            name=msg['name'];available=self.client.get_available_maps();target=next((x for x in available if x.split('/')[-1]==name),None)
            if not target:raise ValueError('服务器未安装此地图')
            self.client.set_timeout(45.);self.world=self.client.load_world(target);self.client.set_timeout(6.)
            return dict(map=name,geometry=extract_map(self.world.get_map()))
        raise ValueError('未知原生操作')
    def destroy_owned(self):
        if self.video:self.video_command(False)
        if self.camera and self.camera.is_alive:self.camera.stop();self.camera.destroy()
        if self.collision_sensor and self.collision_sensor.is_alive:self.collision_sensor.stop();self.collision_sensor.destroy()
        self.collision_sensor=None;self.collisions=deque(maxlen=256)
        self.camera=None
        for a in reversed(list(self.actors.values())):
            if a.is_alive:a.destroy()
        self.actors={};self.specs={};self.agents={};self.routes={};self.route_index={};self.status='ready';self.camera_cache.clear()
    def cleanup(self):
        if self.disconnected:
            if self.video:self.video.release();self.video=None
            return
        self.brake_all();self.restore();self.destroy_owned()


def reader():
    for line in sys.stdin:
        try:COMMANDS.put(json.loads(line))
        except ValueError:pass
    COMMANDS.put(dict(action='shutdown',request_id='eof'))


def main():
    worker=Worker();threading.Thread(target=reader,daemon=True).start()
    def stop(*_):COMMANDS.put(dict(action='shutdown',request_id='signal'))
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        while not worker.shutdown:
            try:
                msg=COMMANDS.get(timeout=.001 if worker.owns_clock else .04)
                try:result=worker.action(msg);emit(dict(request_id=msg.get('request_id'),ok=True,data=result))
                except Exception as e:emit(dict(request_id=msg.get('request_id'),ok=False,error=str(e)))
            except queue.Empty:pass
            if worker.world and not worker.shutdown and not worker.disconnected:
                if worker.owns_clock or worker.status=='manual':worker.step()
                else:worker.camera_process()
                if worker.owns_clock or time.monotonic()-worker.last_emit>.09:
                    try:emit(dict(type='state',data=worker.sample()));worker.last_emit=time.monotonic()
                    except RuntimeError as e:
                        event(str(e),'error');worker.status='error';worker.disconnected=True;emit(dict(type='disconnected',message=str(e)))
    finally:worker.cleanup()


if __name__=='__main__':main()
