"""Local OpenDRIVE road geometry in CARLA's left-handed XY coordinates."""
import math, xml.etree.ElementTree as ET
from pathlib import Path
from functools import lru_cache

MAP_ROOT=Path('/home/liumeng/deepseek_workspace/carla-build/carla-runtime/CarlaUE4/Content')


def geometry_points(x,y,heading,length,kind='line',curvature=0.,step=2.,**kw):
    count=max(1,math.ceil(length/step));ss=[i*length/count for i in range(count+1)];out=[]
    for s in ss:
        if kind=='arc' and abs(curvature)>1e-10:
            u=math.sin(s*curvature)/curvature;v=(1-math.cos(s*curvature))/curvature
        elif kind=='poly3':
            u=s;v=sum(float(kw.get(k,0))*s**i for i,k in enumerate('abcd'))
        elif kind=='paramPoly3':
            p=s/length if kw.get('pRange')=='normalized' else s
            u=sum(float(kw.get(k+'U',0))*p**i for i,k in enumerate('abcd'))
            v=sum(float(kw.get(k+'V',0))*p**i for i,k in enumerate('abcd'))
        elif kind=='spiral':
            # Midpoint integration for varying curvature; 0.25m internal steps.
            n=max(1,math.ceil(s/.25));ds=s/n;u=v=0.
            k0=float(kw.get('curvStart',0));k1=float(kw.get('curvEnd',0))
            for j in range(n):
                q=(j+.5)*ds;a=k0*q+.5*(k1-k0)*q*q/max(length,1e-8);u+=ds*math.cos(a);v+=ds*math.sin(a)
        else:u=s;v=0.
        out.append([x+u*math.cos(heading)-v*math.sin(heading),-(y+u*math.sin(heading)+v*math.cos(heading))])
    return out


@lru_cache(maxsize=20)
def local_map(name='ZUT_Map_Ramp'):
    if not name.replace('_','').isalnum(): raise ValueError('无效地图名称')
    candidates=list(MAP_ROOT.glob('**/OpenDrive/'+name+'.xodr')) if MAP_ROOT.exists() else []
    if not candidates: raise ValueError('本机没有此地图的 OpenDRIVE 文件')
    import subprocess,json,hashlib
    from .config import CARLA_PYTHON,ROOT,RUNTIME
    file=candidates[0];digest=hashlib.sha256(file.read_bytes()).hexdigest()[:16]
    cache=RUNTIME/'maps'/(name+'-'+digest+'-lanes-v2.json')
    if cache.exists():return json.loads(cache.read_text())
    try:
        result=subprocess.run([CARLA_PYTHON,str(ROOT/'backend/native_map.py'),str(file)],capture_output=True,text=True,timeout=30,check=True)
        data=json.loads(result.stdout);cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps(data));return data
    except (OSError,ValueError,subprocess.SubprocessError):return parse_map(file.read_text(),name)


def parse_map(text,name):
    """Offline fallback: evaluate each lane section/width/offset independently."""
    root=ET.fromstring(text);lanes=[]
    def poly(records,s,key='s'):
        active=[r for r in records if float(r.get(key,0))<=s+1e-8]
        if not active:return 0.
        r=active[-1];q=s-float(r.get(key,0));return sum(float(r.get(k,0))*q**i for i,k in enumerate('abcd'))
    for road in root.findall('road'):
        geometries=road.findall('planView/geometry');sections=road.findall('lanes/laneSection')
        def reference(s):
            g=next((g for g in reversed(geometries) if float(g.get('s',0))<=s+1e-8),geometries[0])
            ds=max(0,s-float(g.get('s',0)));child=next(iter(g))
            def at(q):
                attrs={k:v for k,v in child.attrib.items() if k!='curvature'}
                # paramPoly3 normalization uses full geometry length.
                if child.tag=='paramPoly3' and attrs.get('pRange')=='normalized':
                    length=float(g.get('length'));attrs={k:(float(v)/length**int({'a':0,'b':1,'c':2,'d':3}[k[0]]) if k!='pRange' else 'arcLength') for k,v in attrs.items()}
                return geometry_points(float(g.get('x')),float(g.get('y')),float(g.get('hdg')),q,kind=child.tag,curvature=float(child.get('curvature',0)),step=max(q,1),**attrs)[-1]
            p=at(ds);q=at(ds+.001);a=math.atan2(q[1]-p[1],q[0]-p[0]);return p,a
        if not geometries:continue
        for i,section in enumerate(sections):
            begin=float(section.get('s',0));end=float(sections[i+1].get('s')) if i+1<len(sections) else float(road.get('length',0))
            count=max(1,math.ceil((end-begin)/.5));ss=[begin+(end-begin)*j/count for j in range(count+1)]
            for side,sign in [('left',1),('right',-1)]:
                accumulated=[0.]*len(ss)
                for lane in sorted(section.findall(side+'/lane'),key=lambda l:abs(int(l.get('id')))):
                    inner=[];outer=[];center=[];arrows=[]
                    for j,s0 in enumerate(ss):
                        p,a=reference(s0);offset=poly(road.findall('lanes/laneOffset'),s0)
                        width=max(0,poly(lane.findall('width'),s0-begin,'sOffset'))
                        near=offset+sign*accumulated[j];far=near+sign*width
                        def shifted(d):return [p[0]+math.sin(a)*d,p[1]-math.cos(a)*d]
                        inner.append(shifted(near));outer.append(shifted(far));center.append(shifted((near+far)/2));accumulated[j]+=width
                        if j%28==0 and road.get('junction','-1')=='-1':arrows.append([*center[-1],a+(math.pi if sign>0 else 0)])
                    if all(math.dist(a,b)<.05 for a,b in zip(inner,outer)):continue
                    marks=lane.findall('roadMark');mark=marks[0] if marks else None
                    marking=[] if mark is None or road.get('junction','-1')!='-1' or mark.get('type')=='none' else [dict(points=outer,type=mark.get('type','solid').title().replace(' ',''),color=mark.get('color','white').title())]
                    lanes.append(dict(id=f"{road.get('id')}:{i}:{lane.get('id')}",type=lane.get('type','Driving').title(),polygon=inner+outer[::-1],center=center,markings=marking,arrows=arrows,z=0))
    xy=[p for l in lanes for p in l['polygon']]
    bbox=[min(p[0] for p in xy),min(p[1] for p in xy),max(p[0] for p in xy),max(p[1] for p in xy)] if xy else [-100,-150,100,100]
    return dict(name=name,roads=[],lanes=lanes,crosswalks=[],bbox=bbox,source='OpenDRIVE lanes',coordinate_system='CARLA world XY / meters',display_y='down')


def map_list():
    names={p.stem for p in MAP_ROOT.glob('**/OpenDrive/*.xodr')} if MAP_ROOT.exists() else set()
    return sorted(names,key=lambda n:(not n.startswith('ZUT'),n))
