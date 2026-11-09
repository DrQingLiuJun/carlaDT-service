"""Measured P4 runs; never synthesize or time-shift twin data."""
import csv, json, math
from bisect import bisect_right
from .config import ALGORITHM_ROOT

RUNS = [('p4_c2_final', 'P4 受约束同步', 'C2'), ('p4_c1_final', '普通双向同步', 'C1'), ('p4_c0_final', '单向跟踪基线', 'C0')]


class History:
    def __init__(self, run='p4_c2_final'):
        if run not in {x[0] for x in RUNS}: raise ValueError('未知的实验记录')
        self.run=run; self.folder=ALGORITHM_ROOT/'data/carla_overtake'/run
        with (self.folder/'telemetry.csv').open() as f:
            self.rows=[]
            for r in csv.DictReader(f):
                row={}
                for k,v in r.items():
                    try:
                        n=float(v); row[k]=n if math.isfinite(n) else None
                    except (ValueError,TypeError): row[k]=v
                self.rows.append(row)
        self.times=[r['t'] for r in self.rows]; self.duration=self.times[-1]
        self.summary=json.loads((self.folder/'summary.json').read_text())
        frozen=json.loads((ALGORITHM_ROOT/'data/carla_overtake/p4_comparison_final/frozen_task/summary.json').read_text())
        gate=frozen['crossing_window_gates'][-1];a,b=gate['nominal_envelope_occupancy_s']
        interval=next(w for w in gate['intervals_s'] if w[0]<=a and b<=w[1])
        self.summary['console_reference_window']=[interval[0],frozen['virtual_conflict_occupancy_s'][1]+.4]
        self.summary['console_raw_crossing_free_window']=interval

    def sample(self, t):
        r=self.rows[max(0,min(len(self.rows)-1,bisect_right(self.times,t)-1))]
        def actor(prefix):
            return dict(x=r[prefix+'_x'],y=r[prefix+'_y'],yaw=r[prefix+'_yaw'],v=r[prefix+'_v'])
        return dict(source='recorded',run=self.run,t=r['t'],frame=int(r['frame']),phase=r['phase'],error_frame='world_sY_dX',
            virtual=actor('virtual'),physical=actor('ego'),
            obstacles=[dict(id='obstacle-1',x=r['obstacle1_x'],y=r['obstacle1_y'],yaw=math.pi,v=None),
                       dict(id='obstacle-2',x=r['obstacle2_x'],y=r['obstacle2_y'],yaw=math.pi/2,v=None)],
            error=dict(position=r['e_position'],longitudinal=r['e_s'],lateral=r['e_d'],heading=r['e_heading']),
            control=dict(throttle=r['throttle'],brake=r['brake'],steer=r['steer'],
                requested_throttle=r['requested_throttle'],requested_brake=r['requested_brake'],
                virtual_delta=r['virtual_delta'],target_v=r['target_v']),
            gap=min(r['gap1'],r['gap2']),iou=r['footprint_iou'],raw=r)

    def traces(self):
        return [dict(t=r['t'],vx=r['virtual_x'],vy=r['virtual_y'],px=r['ego_x'],py=r['ego_y'],rx=r['qr_x'],ry=r['qr_y'],
            vv=r['virtual_v'],pv=r['ego_v'],heading_v=r['virtual_yaw'],heading_p=r['ego_yaw'],
            error=r['e_position'],es=r['e_s'],ed=r['e_d'],eh=r['e_heading'],
            throttle=r['throttle'],brake=r['brake'],steer=r['steer'],virtual_delta=r['virtual_delta'],
            requested_throttle=r['requested_throttle'],requested_brake=r['requested_brake'],gap=min(r['gap1'],r['gap2']),iou=r['footprint_iou']) for r in self.rows]


def run_list():
    result=[]
    for name,title,group in RUNS:
        p=ALGORITHM_ROOT/'data/carla_overtake'/name/'summary.json'
        if p.exists():
            s=json.loads(p.read_text());result.append(dict(id=name,title=title,group=group,duration=s['elapsed_sim_s'],
                rmse=s['position_rmse_m'],gap=s['min_gap2_m'],iou=s['mean_footprint_iou'],collisions=len(s['collision_events'])))
    return result
