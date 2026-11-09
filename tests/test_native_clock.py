"""Native clock contract without a simulator or CARLA binary import."""
import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path
import pytest


def adapter(monkeypatch):
    monkeypatch.setitem(sys.modules,'carla',SimpleNamespace())
    monkeypatch.setitem(sys.modules,'numpy',SimpleNamespace())
    spec=importlib.util.spec_from_file_location('test_carla_worker',Path(__file__).resolve().parents[1]/'backend/carla_worker.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    return module


class Clock:
    def __init__(self,foreign=False):self.foreign=foreign;self.frame=3;self.applied=[]
    def get_settings(self):return SimpleNamespace(synchronous_mode=False)
    def apply_settings(self,settings):self.applied.append(settings)
    def tick(self,*_):self.frame+=1;return self.frame
    def get_snapshot(self):
        if self.foreign:self.frame+=1
        return SimpleNamespace(frame=self.frame)


def test_clock_that_advances_without_ticks_is_rejected_and_restored(monkeypatch):
    m=adapter(monkeypatch);w=m.Worker();w.world=Clock(foreign=True);w.config={'dt':.05}
    with pytest.raises(ValueError,match='同步时钟校验失败'):w.claim()
    assert not w.owns_clock
    assert w.world.applied[-1].synchronous_mode is False


def test_clock_ownership_is_released_without_changing_actor_poses(monkeypatch):
    m=adapter(monkeypatch);w=m.Worker();w.world=Clock();w.config={'dt':.05}
    w.claim();assert w.owns_clock
    w.restore();assert not w.owns_clock and w.world.applied[-1].synchronous_mode is False


def test_clock_rpc_failure_still_restores_ownership(monkeypatch):
    m=adapter(monkeypatch);w=m.Worker();w.world=Clock();w.config={'dt':.05}
    def fail(*_):raise RuntimeError('timeout')
    w.world.tick=fail
    with pytest.raises(RuntimeError):w.claim()
    assert not w.owns_clock and w.world.applied[-1].synchronous_mode is False


def test_virtual_only_mode_controls_the_carla_actor(monkeypatch):
    m=adapter(monkeypatch);w=m.Worker();w.config={'mode':'virtual','arrival_distance':.5};w.status='running'
    NS=SimpleNamespace
    controls=[]
    a=NS(is_alive=True,type_id='vehicle.test',get_speed_limit=lambda:30,get_location=lambda:NS(x=0,y=0),get_transform=lambda:NS(rotation=NS(yaw=0)),apply_control=controls.append)
    w.actors={'ego':a};w.specs={'ego':dict(x=0,y=0,yaw=0,goal_x=10,goal_y=0,goal_yaw=0,behavior='route')}
    u=NS(throttle=.3,brake=0.,steer=0.)
    w.agents={'ego':NS(run_step=lambda:u,set_target_speed=lambda _:None)}
    w.routes={'ego':[(0,0),(10,0)]};w.route_index={'ego':0};w.trajectories={'ego':(20,[0,0],3,45,[])}
    monkeypatch.setattr(m,'pose',lambda _:dict(x=0,y=0,yaw=0,v=0))
    w.navigation_step()
    assert controls[-1].throttle==.3
    assert w.control['throttle']==.3
