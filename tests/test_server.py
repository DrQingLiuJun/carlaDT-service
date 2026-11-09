from unittest.mock import Mock
import pytest


def test_lifecycle_uses_process_and_port_and_rejects_duplicate_actions(tmp_path):
    from backend.server import CarlaServer
    s=CarlaServer(tmp_path)
    s.processes=Mock(return_value=[]);s.port_open=Mock(return_value=False)
    assert s.state()['status']=='stopped'
    assert s.state()['can_start'] and not s.state()['can_stop']
    p=Mock();s.processes.return_value=[p]
    assert s.state()['status']=='starting'
    assert not s.state()['can_start'] and s.state()['can_stop']
    s.port_open.return_value=True
    assert s.state()['status']=='running'
    assert s.state()['can_restart'] and not s.state()['can_start']
    with pytest.raises(ValueError):s.begin('start')
    s.begin('restart')
    assert not any(s.state()[k] for k in ['can_start','can_restart','can_stop'])


def test_lifecycle_does_not_offer_stop_for_unidentified_rpc_service(tmp_path):
    from backend.server import CarlaServer
    s=CarlaServer(tmp_path);s.processes=Mock(return_value=[]);s.port_open=Mock(return_value=True)
    state=s.state()
    assert state['status']=='unmanaged'
    assert not any(state[k] for k in ['can_start','can_restart','can_stop'])


def test_start_process_command_and_stop_are_real_lifecycle_operations(tmp_path,monkeypatch):
    from backend.server import CarlaServer
    binary=tmp_path/'CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping'
    binary.parent.mkdir(parents=True);binary.touch()
    s=CarlaServer(tmp_path);s.root=tmp_path
    child=Mock();child.poll.return_value=None
    launch=Mock(return_value=child)
    monkeypatch.setattr('backend.server.subprocess.Popen',launch)
    monkeypatch.setattr(s,'port_open',lambda:True)
    s.start()
    assert launch.call_args.args[0][0]==str(binary)
    assert '-carla-rpc-port=2000' in launch.call_args.args[0]
    proc=Mock();monkeypatch.setattr(s,'processes',lambda:[proc])
    monkeypatch.setattr('backend.server.psutil.wait_procs',lambda procs,timeout:(procs,[]))
    s.stop();proc.terminate.assert_called_once()


def test_crashed_zombie_is_not_a_running_server_and_child_is_reaped(tmp_path,monkeypatch):
    import psutil
    from backend.server import CarlaServer
    s=CarlaServer(tmp_path);s.child=Mock();s.child.poll.return_value=-11
    zombie=Mock();zombie.info={'name':'CarlaUE4-Linux-','exe':None,'cmdline':None};zombie.status.return_value=psutil.STATUS_ZOMBIE
    monkeypatch.setattr('backend.server.psutil.process_iter',lambda *args:[zombie])
    monkeypatch.setattr(s,'port_open',lambda:False)
    state=s.state()
    assert state['status']=='error' and state['can_start']
    assert not state['can_restart'] and not state['can_stop']
    assert state['exit_code']==-11
    s.child.poll.assert_called()


def test_listener_detection_is_passive_and_never_opens_a_socket(tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    from backend.server import CarlaServer
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('Active TCP probing is forbidden'))
    monkeypatch.setattr('backend.server.psutil.net_connections',lambda **kw:[NS(status='LISTEN',laddr=NS(port=2000))])
    assert CarlaServer(tmp_path).port_open()


def test_stability_profile_uses_real_shipping_settings(tmp_path,monkeypatch):
    monkeypatch.delenv("CARLADT_QUALITY",raising=False)
    from backend.server import CarlaServer
    args=CarlaServer(tmp_path).profile_args()
    assert '-quality-level=Epic' in args
    assert any(a.startswith('-UserDir=') for a in args)
    settings=tmp_path/'carla-profile/Saved/Config/LinuxNoEditor'
    assert 'FrameRateLimit=30' in (settings/'GameUserSettings.ini').read_text()
    assert 't.MaxFPS=30' in (settings/'Engine.ini').read_text()
    assert not any('ExecCmds' in a for a in args)
