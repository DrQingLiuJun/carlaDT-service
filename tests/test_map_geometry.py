import pytest


def test_native_lane_mesh_keeps_world_coordinates_and_variable_width():
    from backend.native_map import lane_mesh
    from types import SimpleNamespace as NS
    def wp(s,width):
        return NS(s=s,lane_width=width,is_junction=False,
            transform=NS(location=NS(x=10+s,y=20,z=0),rotation=NS(yaw=0)),
            left_lane_marking=NS(type='Solid',color='White'),right_lane_marking=NS(type='Broken',color='White'))
    lane=lane_mesh('1:0:-1',[wp(0,4),wp(10,6)],'Driving')
    assert lane['polygon']==[[10,18],[20,17],[20,23],[10,22]]
    assert lane['center']==[[10,20],[20,20]]
    assert lane['markings'][1]['type']=='Broken'
    assert lane['arrows'][0][2]==0


def test_opendrive_sections_do_not_accumulate_width_and_respect_lane_offset():
    from backend.opendrive import parse_map
    lane='<right><lane id="-1" type="driving"><width sOffset="0" a="4" b="0" c="0" d="0"/></lane></right>'
    xml=f'<OpenDRIVE><road id="1" length="20" junction="-1"><planView><geometry s="0" x="0" y="0" hdg="0" length="20"><line/></geometry></planView><lanes><laneOffset s="0" a="3" b="0" c="0" d="0"/><laneSection s="0">{lane}</laneSection><laneSection s="10">{lane}</laneSection></lanes></road></OpenDRIVE>'
    result=parse_map(xml,'test')
    assert len(result['lanes'])==2
    for l in result['lanes']:
        ys=[p[1] for p in l['polygon']]
        assert min(ys)==pytest.approx(-3)
        assert max(ys)==pytest.approx(1)


def test_restored_live_map_never_uses_other_maps_historical_vehicle_positions(tmp_path):
    from backend.app import create_app
    (tmp_path/'last-world.json').write_text('{"name":"HAUT_Map"}')
    session=create_app(tmp_path).state.session
    assert session.map['name']=='HAUT_Map'
    assert session.source=='live'
    assert not session.connection['connected']
    assert session.snapshot()['physical'] is None
