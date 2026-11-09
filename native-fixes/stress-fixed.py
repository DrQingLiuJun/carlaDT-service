import carla,time,socket,json,threading,queue,concurrent.futures,math
from pathlib import Path
port=2100
client=carla.Client('127.0.0.1',port);client.set_timeout(10)
w=client.get_world();m=w.get_map();start=time.monotonic();first=w.get_snapshot().frame
errors=[];frames=[];lock=threading.Lock();camera=None;ego=None
bp=w.get_blueprint_library().find('vehicle.tesla.model3')
for t in m.get_spawn_points():
 ego=w.try_spawn_actor(bp,t)
 if ego:break
if ego:
 ego.apply_control(carla.VehicleControl(brake=1.))
 cb=w.get_blueprint_library().find('sensor.camera.rgb');cb.set_attribute('image_size_x','640');cb.set_attribute('image_size_y','360');cb.set_attribute('sensor_tick','0.1')
 camera=w.spawn_actor(cb,carla.Transform(carla.Location(x=-6,z=4),carla.Rotation(pitch=-15)),attach_to=ego)
 def image(img):
  with lock:frames.append(img.frame)
 camera.listen(image)
def churn(n):
 count=0
 for i in range(300):
  try:
   with socket.create_connection(('127.0.0.1',port),timeout=2):pass
   count+=1
  except Exception as e:errors.append('probe:'+str(e))
 return count
def rpc(n):
 count=0
 for i in range(30):
  try:
   c=carla.Client('127.0.0.1',port);c.set_timeout(5);c.get_server_version();c.get_world().get_snapshot();count+=1
  except Exception as e:errors.append('rpc:'+str(e))
 return count
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  futures=[pool.submit(churn,i) for i in range(6)]+[pool.submit(rpc,i) for i in range(2)]
  counts=[f.result() for f in futures]
 print('traffic_test_counts',counts,'errors',len(errors),flush=True)
 for n in range(18):
  time.sleep(10);s=w.get_snapshot()
  print('stable_seconds',round(time.monotonic()-start),'frame',s.frame,'camera_frames',len(frames),flush=True)
  if s.frame<=first:raise RuntimeError('simulation stopped advancing')
 result={'map':m.name,'stable_seconds':round(time.monotonic()-start),'frame_delta':s.frame-first,'camera_frames':len(frames),'raw_connections':sum(counts[:6]),'valid_rpc_sessions':sum(counts[6:]),'errors':errors}
 Path('/home/liumeng/deepseek_workspace/carlaDT-service/runtime/diagnostics/fixed-stress.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result),flush=True)
finally:
 if camera:camera.stop();camera.destroy()
 if ego:ego.destroy()
