"""CARLA's own waypoint/lane geometry, shared by live and offline native readers.

Coordinates are unchanged CARLA world metres. No display reflection or lane-width
approximation is applied here. Like no_rendering_mode.py, adjacent non-driving
lanes are read with get_left_lane/get_right_lane.
"""
import math
from collections import defaultdict


def lane_mesh(key, waypoints, kind):
    points=sorted(waypoints,key=lambda w:w.s)
    left=[];right=[];center=[];arrows=[];markings=[];last_arrow=points[0].s-7
    for i,w in enumerate(points):
        t=w.transform;x=t.location.x;y=t.location.y;a=math.radians(t.rotation.yaw)
        dx=-math.sin(a)*w.lane_width/2;dy=math.cos(a)*w.lane_width/2
        center.append([x,y]);left.append([x-dx,y-dy]);right.append([x+dx,y+dy])
        if kind.lower()=='driving' and not w.is_junction and w.s-last_arrow>=14:
            arrows.append([x,y,a]);last_arrow=w.s
    for attr,boundary in [('left_lane_marking',left),('right_lane_marking',right)]:
        run=[];last=None
        for w,p in zip(points,boundary):
            m=getattr(w,attr,None);style=(str(m.type).split('.')[-1],str(m.color).split('.')[-1]) if m and not w.is_junction else ('NONE','White')
            if style!=last:
                if last and len(run)>1 and last[0] not in ['NONE','None','Other']:markings.append(dict(points=run,type=last[0],color=last[1]))
                run=[run[-1],p] if run else [p];last=style
            else:run.append(p)
        if last and len(run)>1 and last[0] not in ['NONE','None','Other']:markings.append(dict(points=run,type=last[0],color=last[1]))
    return dict(id=key,type=kind,polygon=left+right[::-1],center=center,markings=markings,arrows=arrows,z=sum(w.transform.location.z for w in points)/len(points))


def extract_map(m,step=.5):
    groups=defaultdict(dict)
    def add(w):
        key=(w.road_id,w.section_id,w.lane_id)
        groups[key][round(w.s,5)]=w
    for w in m.generate_waypoints(step):
        add(w)
        for side in ['get_left_lane','get_right_lane']:
            q=getattr(w,side)();seen=set()
            while q and (q.road_id,q.section_id,q.lane_id) not in seen:
                key=(q.road_id,q.section_id,q.lane_id);seen.add(key)
                if str(q.lane_type).split('.')[-1]=='Driving':break
                add(q);q=getattr(q,side)()
    # Include exact topology endpoints so sections join without sampling gaps.
    for pair in m.get_topology():
        for w in pair:
            add(w)
    lanes=[]
    for key,points in groups.items():
        values=list(points.values())
        if str(values[0].lane_type).split('.')[-1] not in ['Driving','Shoulder','Parking','Sidewalk','Biking']:continue
        if len(values)<2 or max(w.lane_width for w in values)<.05:continue
        lanes.append(lane_mesh(':'.join(map(str,key)),values,str(values[0].lane_type).split('.')[-1]))
    lanes.sort(key=lambda l:(l['z'],l['type']=='Driving'))
    crosswalks=[];run=[]
    for v in m.get_crosswalks():
        p=[v.x,v.y]
        if run and math.hypot(p[0]-run[0][0],p[1]-run[0][1])<.01:
            if len(run)>=3:crosswalks.append(run)
            run=[]
        else:run.append(p)
    xy=[p for l in lanes for p in l['polygon']]
    return dict(name=m.name.split('/')[-1],roads=[],lanes=lanes,crosswalks=crosswalks,
        bbox=[min(p[0] for p in xy),min(p[1] for p in xy),max(p[0] for p in xy),max(p[1] for p in xy)],
        source='CARLA Waypoints',coordinate_system='CARLA world XY / meters',display_y='down',sample_step=step)


if __name__=='__main__':
    import sys,json,carla
    from pathlib import Path
    p=Path(sys.argv[1]);m=carla.Map(p.stem,p.read_text())
    print(json.dumps(extract_map(m),separators=(',',':')))
