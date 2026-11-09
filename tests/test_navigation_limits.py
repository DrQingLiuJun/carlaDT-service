import math
from backend.navigation_limits import corner_speed_kmh,following_limit


def test_planned_steering_reserve_preserves_nonzero_corner_speed():
    curve=[(0,1),(20,.9),(60,.8),(120,.7)]
    wheelbase=3.4
    reserved=math.degrees(math.atan(.98*math.tan(math.radians(45))))
    k=math.tan(math.radians(reserved))/wheelbase
    assert corner_speed_kmh(k,wheelbase,45,curve)>2
    # At exact full lock, speed authority does go to zero; do not fake creep
    # through an untrackable trajectory by clamping its speed upwards.
    assert corner_speed_kmh(1/wheelbase,wheelbase,45,curve)==0


def test_leading_vehicle_causes_braking_but_rear_and_adjacent_do_not_block():
    own=dict(x=0,y=0,yaw=0,v=2,length=5,width=2)
    path=[(i/10,0) for i in range(201)]
    front=dict(x=5.6,y=0,yaw=0,v=0,length=5,width=2)
    speed,emergency=following_limit(own,path,0,[front],20,.8)
    assert speed==0 and emergency
    for other in [{**front,'x':-4},{**front,'y':4}]:
        speed,emergency=following_limit(own,path,0,[other],20,.8)
        assert speed==20 and not emergency
