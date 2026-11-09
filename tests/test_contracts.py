import json
from pathlib import Path
import pytest

from backend.config import ConsoleConfig
from backend.history import History
from backend.opendrive import geometry_points
from backend.catalog import catalog, build_command
from backend.recording import Recorder, safe_file


def test_invalid_speed_and_delay_are_rejected_before_any_vehicle_command():
    with pytest.raises(ValueError): ConsoleConfig(speed_kmh=-1)
    with pytest.raises(ValueError): ConsoleConfig(mode='physical')
    with pytest.raises(ValueError): ConsoleConfig(dt=0)
    assert ConsoleConfig().mode=='virtual'


def test_history_uses_measured_states_and_preserves_same_frame_errors():
    h = History()
    s = h.sample(0)
    assert s['source'] == 'recorded'
    assert s['virtual']['x'] == pytest.approx(-1.6001076698303223)
    assert s['physical']['y'] == pytest.approx(-115.51124572753906)
    assert s['error']['position'] == 0
    later = h.sample(11)
    assert later['error']['position'] > .1
    assert later['frame'] > s['frame']


def test_opendrive_world_conversion_reflects_y_and_handles_arc():
    line = geometry_points(10, 20, 0, 4, kind='line', step=2)
    assert line == [[10, -20], [12, -20], [14, -20]]
    arc = geometry_points(0, 0, 0, 1.5707963267948966, kind='arc', curvature=1, step=2)
    assert arc[-1] == pytest.approx([1, -1])


def test_example_catalog_covers_all_top_level_programs_and_guards_arguments():
    rows = catalog(); names = {r['id'] for r in rows}
    assert {'manual_control.py', 'no_rendering_mode.py', 'V2XDemo.py', 'vehicle_physics.py'} <= names
    assert len([r for r in rows if '/' not in r['id']]) == 30
    with pytest.raises(ValueError): build_command('../evil.py', {}, '0.9.16')
    with pytest.raises(ValueError): build_command('manual_control.py', {'--bad': 'x'}, '0.9.16')
    with pytest.raises(ValueError): build_command('manual_control.py', {}, '0.9.13')
    cmd = build_command('manual_control.py', {'--res': '1280x720'}, '0.9.16')
    assert cmd[-2:] == ['--res', '1280x720']


def test_recording_creates_source_aware_rows_and_finalizes_metadata(tmp_path):
    rec = Recorder(tmp_path); rec.start('recorded', {'mode': 'synchronized'})
    rec.write({'t': 1., 'frame': 20, 'source': 'recorded'})
    folder = Path(rec.stop()['path'])
    row = json.loads((folder/'telemetry.jsonl').read_text().strip())
    assert row['frame'] == 20
    info = json.loads((folder/'manifest.json').read_text())
    assert info['source'] == 'recorded' and info['status'] == 'saved' and info['samples'] == 1


def test_recording_download_never_escapes_output_directory(tmp_path):
    with pytest.raises(ValueError): safe_file(tmp_path, '../outside')
    p = tmp_path/'run'/'telemetry.jsonl';p.parent.mkdir();p.write_text('{}')
    assert safe_file(tmp_path, 'run/telemetry.jsonl') == p


def test_csv_keeps_states_and_obstacles_that_appear_after_recording_starts(tmp_path):
    import csv
    rec=Recorder(tmp_path);rec.start('live',{})
    rec.write({'frame':1,'physical':None,'obstacles':[]})
    rec.write({'frame':2,'physical':{'x':4.,'v':2.},'obstacles':[{'id':'obstacle-1','x':8.}]})
    folder=Path(rec.stop()['path'])
    rows=list(csv.DictReader((folder/'telemetry.csv').open()))
    assert rows[1]['physical_x']=='4.0' and rows[1]['obstacles_0_x']=='8.0'
