import pytest
from backend.config import ActorConfig,ConsoleConfig


def test_carla_is_only_current_vehicle_and_ros_modes_are_unavailable():
    assert ConsoleConfig().mode=='virtual'
    assert ConsoleConfig().algorithm=='navigation'
    assert 'delay_steps' not in ConsoleConfig().model_dump()
    for mode in ['physical','synchronized']:
        with pytest.raises(ValueError,match='ROS'):ConsoleConfig(mode=mode)


def test_start_and_goal_pose_headings_round_trip():
    a=ActorConfig(id='ego',role='ego',x=1,y=2,yaw=-45,goal_x=3,goal_y=4,goal_yaw=135)
    assert ActorConfig(**a.model_dump()).goal_yaw==135
    with pytest.raises(ValueError):ActorConfig(id='x',x=0,y=0,goal_yaw=float('nan'))


def test_live_snapshot_assigns_carla_pose_to_virtual_and_no_fake_physical(monkeypatch):
    from test_native_clock import adapter
    from types import SimpleNamespace as NS
    m=adapter(monkeypatch);w=m.Worker()
    a=NS(is_alive=True,get_control=lambda:NS(throttle=.2,brake=0,steer=.1),id=4)
    w.actors={'ego':a};w.world=NS(get_snapshot=lambda:NS(frame=7,timestamp=NS(elapsed_seconds=1.)))
    monkeypatch.setattr(m,'pose',lambda a:dict(x=12.,y=3.,yaw=.4,v=2.))
    result=w.sample()
    assert result['virtual']['x']==12 and result['physical'] is None and result['error'] is None
    assert result['control']['throttle']==.2
    assert not hasattr(w,'virtual_step')


def test_navigation_terminal_path_uses_requested_goal_heading(monkeypatch):
    from backend import kinematic_route
    from test_native_clock import adapter
    from types import SimpleNamespace as NS
    import sys

    class LaneWaypoint:
        road_id, section_id, lane_id, lane_width = 1, 0, -1, 4
        def __init__(self, x):
            self.s = x
            self.transform = NS(location=NS(x=x, y=0, z=0), rotation=NS(yaw=0))
        def next(self, distance):
            return [LaneWaypoint(self.s + distance)] if self.s + distance <= 11 else []

    m=adapter(monkeypatch);w=m.Worker()
    class Agent:
        def __init__(self,*args,**kwargs):pass
        def set_global_plan(self,rows):self.rows=rows
    class LocalPlanner:
        def __init__(self,*args,**kwargs):pass
    monkeypatch.setitem(sys.modules,'agents',NS())
    monkeypatch.setitem(sys.modules,'agents.navigation',NS())
    monkeypatch.setitem(sys.modules,'agents.navigation.basic_agent',NS(BasicAgent=Agent))
    monkeypatch.setitem(sys.modules,'agents.navigation.local_planner',
                        NS(LocalPlanner=LocalPlanner,RoadOption=NS(LANEFOLLOW='follow')))
    m.carla.Location=lambda **kw:NS(**kw)
    m.carla.Rotation=lambda **kw:NS(**kw)
    m.carla.Transform=lambda loc,rot:NS(location=loc,rotation=rot)
    w.world=NS(get_map=lambda:NS(get_waypoint=lambda loc:LaneWaypoint(loc.x)))
    wheels=[NS(max_steer_angle=45,position=NS(x=x,y=0)) for x in (-150,-150,150,150)]
    w.actors={'ego':NS(is_alive=True,type_id='vehicle.haut.car',
                      get_transform=lambda:NS(location=NS(x=0,y=0,z=0),rotation=NS(yaw=0),
                                              get_forward_vector=lambda:NS(x=1,y=0)),
                      get_physics_control=lambda:NS(wheels=wheels,steering_curve=[]),
                      bounding_box=NS(extent=NS(x=2,y=1)))}
    w.specs={'ego':dict(role='ego',behavior='route',x=0,y=0,yaw=0,goal_x=10,goal_y=0,goal_yaw=0)}
    w.config=ConsoleConfig().model_dump()
    w.prepare_agents()
    assert w.routes['ego'][-1]==(10,0)
    assert w.agents['ego'].rows[-1][0].transform.rotation.yaw==0
    with pytest.raises(ValueError,match='行驶方向'):
        kinematic_route.plan(LaneWaypoint(10),LaneWaypoint(0),(10,0,0),(0,0,0),3,45)
    with pytest.raises(ValueError,match='转弯半径'):
        kinematic_route.plan(LaneWaypoint(0),LaneWaypoint(2),(0,0,0),(2,0.8,0),3,45)
    w.specs['ego']['goal_yaw']=90
    with pytest.raises(ValueError,match='航向'):w.prepare_agents()
