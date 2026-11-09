from types import SimpleNamespace as NS
from backend.kinematic_route import _forward_route


def test_goal_immediately_after_section_boundary_is_not_skipped_by_sampling():
    class Waypoint:
        road_id,lane_id,lane_width=1,1,4
        def __init__(self,x):
            self.s=x;self.section_id=0 if x<1 else 1
            self.transform=NS(location=NS(x=x,y=0),rotation=NS(yaw=0))
        def next(self,step):return [Waypoint(self.s+step)] if self.s<2 else []
    route=_forward_route(Waypoint(0),Waypoint(1.1))
    assert route[-1].s==1.1
    assert all(w.s<=1.1 for w in route)


def test_haut_obstacle_two_can_return_via_eastern_loop():
    import subprocess
    from pathlib import Path
    import pytest
    native=Path('/home/liumeng/miniconda3/envs/carla/bin/python')
    root=Path('/home/liumeng/deepseek_workspace/carla-build/carla-runtime/CarlaUE4/Content')
    maps=list(root.glob('**/OpenDrive/HAUT_Map.xodr'))
    if not native.exists() or not maps:pytest.skip('Requires installed native CARLA map reader')
    script='''
import carla,math,sys
from pathlib import Path
from backend.kinematic_route import plan_on_map,_forward_route,NoLaneRoute
m=carla.Map('HAUT_Map',Path(sys.argv[1]).read_text())
start=(17.7139186859,-8.3802394867,3.636)
goal=(-8.06,-8.79,.8)
def wp(x,y):return m.get_waypoint(carla.Location(x=x,y=y),project_to_road=False)
a,b=wp(*start[:2]),wp(*goal[:2])
try:_forward_route(a,b)
except NoLaneRoute:pass
else:raise AssertionError('Fixture must exercise broken native eastbound connection')
r=plan_on_map(m,wp,a,b,start,goal,2.875,70.,2.16345,4.79178)
assert math.dist(r[0][:2],start[:2])<1e-4
assert math.dist(r[-1][:2],goal[:2])<1e-4
assert max(p[0] for p in r)>50 and max(p[1] for p in r)>7
assert min(p[0] for p in r)<-20
assert max(abs(p[3]) for p in r)<=math.tan(math.radians(70))/2.875+1e-5
assert max(math.dist(a[:2],b[:2]) for a,b in zip(r,r[1:]))<.2
'''
    result=subprocess.run([str(native),'-c',script,str(maps[0])],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
