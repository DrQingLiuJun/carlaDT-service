from fastapi.testclient import TestClient
from backend.app import create_app


def test_offline_session_controls_real_history_without_claiming_live(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        b=c.get('/api/bootstrap').json()
        assert b['snapshot']['source']=='live' and b['snapshot']['physical'] is None and not b['connection']['connected']
        assert c.post('/api/command',json={'action':'select_run','run':'p4_c2_final'}).status_code==200
        assert c.post('/api/actors',json={'id':'x','x':0,'y':0}).status_code==409
        assert c.post('/api/command',json={'action':'start'}).json()['status']=='running'
        assert c.post('/api/command',json={'action':'stop'}).json()['status']=='stopped'
        assert c.post('/api/command',json={'action':'reset'}).json()['cursor']==0
        assert c.post('/api/config',json={'speed_kmh':-1}).status_code==422
        assert c.post('/api/config',json={'speed_kmh':20}).status_code==200
        assert c.get('/api/bootstrap').json()['config']['speed_kmh']==20


def test_recording_api_saves_and_exposes_files_without_path_escape(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        assert c.post('/api/recording',json={'enabled':True}).status_code==200
        assert c.post('/api/recording',json={'enabled':False}).status_code==200
        rows=c.get('/api/recordings').json()['recordings']
        assert rows and rows[0]['status']=='saved'
        name=rows[0]['id']
        assert c.get('/api/files/'+name+'/manifest.json').status_code==200
        assert c.get('/api/files/%2E%2E/%2E%2E/etc/passwd').status_code in [400,404]
        assert c.post('/api/command',json={'action':'not-a-command'}).status_code==400


def test_source_cannot_change_inside_an_active_recording(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        c.post('/api/recording',json={'enabled':True})
        assert c.post('/api/connect',json={}).status_code==409
        assert c.post('/api/command',json={'action':'source','source':'recorded'}).status_code==409
        c.post('/api/recording',json={'enabled':False})


def test_scene_save_validates_full_actor_set_and_does_not_require_live_control(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        assert c.post('/api/scene',json=[]).status_code==422
        a=c.get('/api/bootstrap').json()['actors'];a[0]['goal_y']=30
        assert c.post('/api/scene',json=a).status_code==200
        assert c.get('/api/bootstrap').json()['actors'][0]['goal_y']==30
        assert c.get('/api/bootstrap').json()['source']=='live'


def test_server_controls_report_pending_state_and_reject_duplicate_requests(tmp_path,monkeypatch):
    import asyncio
    app=create_app(tmp_path);session=app.state.session
    monkeypatch.setattr(session.server,'processes',lambda:[])
    monkeypatch.setattr(session.server,'port_open',lambda:False)
    session.server_state=session.server.state()
    async def pending(action):await asyncio.sleep(30)
    monkeypatch.setattr(session,'lifecycle',pending)
    with TestClient(app) as c:
        state=c.get('/api/bootstrap').json()['server']
        assert state['can_start'] and not state['can_stop']
        assert c.post('/api/server',json={'action':'unknown'}).status_code==409
        state=c.post('/api/server',json={'action':'start'}).json()['server']
        assert state['status']=='starting'
        assert not state['can_start'] and not state['can_restart'] and not state['can_stop']
        assert c.post('/api/server',json={'action':'start'}).status_code==409


def test_crash_monitor_keeps_updating_while_rpc_attach_is_stuck(tmp_path,monkeypatch):
    import asyncio
    app=create_app(tmp_path);s=app.state.session
    mode={'up':True}
    def state():return dict(status='running' if mode['up'] else 'error',can_start=not mode['up'],can_stop=mode['up'],can_restart=mode['up'],error=None if mode['up'] else 'exit -11',exit_code=None if mode['up'] else -11)
    monkeypatch.setattr(s.server,'state',state)
    async def blocked_attach():await asyncio.sleep(30)
    monkeypatch.setattr(s,'attach_safely',blocked_attach)
    async def verify():
        job=asyncio.create_task(s.watch_server())
        try:
            await asyncio.sleep(.05)
            assert s.attach_task and not s.attach_task.done()
            mode['up']=False
            await asyncio.sleep(.55)
            assert s.server_state['can_start'] and not s.connection['connected']
        finally:
            job.cancel()
            if s.attach_task:s.attach_task.cancel()
            await asyncio.gather(job,s.attach_task,return_exceptions=True)
    asyncio.run(verify())


def test_batch_spawn_and_recreate_use_saved_full_scene(tmp_path,monkeypatch):
    app=create_app(tmp_path);s=app.state.session;s.connection['connected']=True;calls=[]
    def call(action,**kw):
        calls.append((action,kw));return dict(status='ready',actors=[dict(id=a['id']) for a in kw['actors']])
    monkeypatch.setattr(s.bridge,'call',call)
    with TestClient(app) as c:
        actors=[dict(a) for a in s.actors]
        actors[0]['yaw']=35
        assert c.post('/api/actors/spawn-all',json=actors).status_code==200
        assert calls[-1][0]=='rebuild' and len(calls[-1][1]['actors'])==len(actors)
        assert c.post('/api/command',json={'action':'recreate'}).status_code==200
        assert calls[-1][1]['destroy_all'] is True
        assert calls[-1][1]['actors'][0]['yaw']==35
        before=len(calls)
        assert c.post('/api/actors/spawn-all',json=actors+[actors[0]]).status_code==422
        assert len(calls)==before
