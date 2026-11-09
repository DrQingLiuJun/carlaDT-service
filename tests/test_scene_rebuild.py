from types import SimpleNamespace as NS
import pytest
from test_native_clock import adapter


def test_rebuild_removes_world_dynamic_actors_before_spawning_and_leaves_map(monkeypatch):
    m=adapter(monkeypatch);w=m.Worker();calls=[]
    class Actor:
        def __init__(self,kind):self.type_id=kind;self.is_alive=True
        def destroy(self):calls.append('destroy:'+self.type_id);self.is_alive=False
        def stop(self):calls.append('stop:'+self.type_id)
    world_actors=[Actor(k) for k in ['vehicle.external','walker.pedestrian.1','sensor.camera.rgb','traffic.traffic_light','spectator']]
    w.world=NS(get_actors=lambda:world_actors)
    monkeypatch.setattr(w,'destroy_owned',lambda:calls.append('owned'))
    monkeypatch.setattr(w,'spawn',lambda spec:(calls.append('spawn:'+spec['id']) or {'actor_id':99}))
    specs=[{'id':'ego'},{'id':'obstacle-1'}]
    result=w.rebuild({},specs,destroy_all=True)
    assert [v for v in calls if v.startswith('destroy:')]==['destroy:sensor.camera.rgb','destroy:vehicle.external','destroy:walker.pedestrian.1']
    assert calls.index('destroy:vehicle.external')<calls.index('spawn:ego')
    assert len(result['actors'])==2 and result['status']=='ready'
    assert world_actors[-1].is_alive and world_actors[-2].is_alive


def test_rebuild_rejects_active_control_and_rolls_back_partial_spawn(monkeypatch):
    m=adapter(monkeypatch);w=m.Worker();w.world=object();w.status='running'
    with pytest.raises(ValueError,match='停止'):w.rebuild({},[{'id':'ego'}])
    w.status='ready';clears=[]
    monkeypatch.setattr(w,'destroy_owned',lambda:clears.append(True))
    def spawn(spec):
        if spec['id']=='bad':raise ValueError('位置被占用')
        return {'actor_id':99}
    monkeypatch.setattr(w,'spawn',spawn)
    with pytest.raises(ValueError,match='位置被占用'):w.rebuild({},[{'id':'ego'},{'id':'bad'}])
    assert len(clears)==2
