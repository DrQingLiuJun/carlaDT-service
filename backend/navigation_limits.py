"""Physical steering-speed limits and footprint-aware following on planned paths."""
import math


def corner_speed_kmh(curvature,wheelbase,max_steer,steering_curve):
    peak=abs(curvature)
    limit=3.6*math.sqrt(1.5/max(peak,1e-6))
    required=math.degrees(math.atan(peak*wheelbase))/max_steer
    for (slow,scale),(fast,next_scale) in zip(steering_curve,steering_curve[1:]):
        if scale>=required>next_scale:
            # UE4 SteeringCurve keys are km/h (converted by KmHToCmS).
            limit=min(limit,slow+(fast-slow)*(scale-required)/(scale-next_scale))
            break
    return limit


def following_limit(own,path,index,others,cruise,min_gap):
    speed=cruise;emergency=False
    lookahead=max(12.,own['v']**2/3+8.)
    segments=[];station=0.
    for a,b in zip(path[index:],path[index+1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<1e-6:continue
        segments.append((a,dx/length,dy/length,length,station));station+=length
        if station>lookahead:break
    for other in others:
        best=None
        for a,tx,ty,length,s in segments:
            dx,dy=other['x']-a[0],other['y']-a[1]
            u=max(0.,min(length,dx*tx+dy*ty))
            distance=math.hypot(dx-u*tx,dy-u*ty)
            if best is None or distance<best[0]:best=(distance,s+u,tx,ty,dx*tx+dy*ty)
        if best is None:continue
        lateral,along,tx,ty,projection=best
        if along<.1 or (along<1. and projection<0):continue
        relative=other['yaw']-math.atan2(ty,tx)
        forward=(abs(math.cos(relative))*other['length']+abs(math.sin(relative))*other['width'])/2
        side=(abs(math.sin(relative))*other['length']+abs(math.cos(relative))*other['width'])/2
        if lateral>own['width']/2+side+.15:continue
        gap=along-own['length']/2-forward
        headway=min_gap+.5*own['v']
        leading_speed=max(0.,other['v']*math.cos(relative))
        target=min(math.sqrt(max(0.,3.*(gap-min_gap))),max(0.,leading_speed+1.2*(gap-headway)))
        speed=min(speed,3.6*target)
        if gap<=min_gap+.15 or gap<own['v']*.25+own['v']**2/8:
            emergency=True;speed=0.
    return speed,emergency
