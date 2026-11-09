import {useEffect,useRef} from 'react';
import {Activity,ArrowUpRight,CarFront,Clock3,Video,Waypoints,GitCompareArrows,Check,Radio,Info} from 'lucide-react';
import {Bootstrap,State,Trace,Page} from './types';
import {Panel,Pill,Metric,Spark,C} from './components';
import {MapView} from './MapView';
import {format,phaseName,gib} from './api';

export function Camera({state,large=false}:{state:State;large?:boolean}){
 const video=useRef<HTMLVideoElement>(null);const lastSeek=useRef(0);
 useEffect(()=>{const el=video.current;if(!el)return;if(Math.abs(el.currentTime-state.cursor)>.5&&Date.now()-lastSeek.current>300){el.currentTime=state.cursor;lastSeek.current=Date.now()}if(state.status==='running'&&state.source==='recorded'){el.playbackRate=state.rate;el.play().catch(()=>{})}else el.pause()},[state.cursor,state.status,state.rate,state.source]);
 return <div className={'camera-view '+(large?'large-camera':'')}>
   {state.source==='live'?(state.snapshot.camera?<img src="/api/camera" alt="CARLA实时相机"/>:<div className="camera-unavailable"><Video size={30}/><span>相机未启用</span><span>进入驾驶感知页面开启相机</span></div>):<video ref={video} key={state.snapshot.run} src={`/api/video?camera=true&run=${state.snapshot.run}`} muted playsInline preload="auto" onLoadedMetadata={()=>{if(video.current)video.current.currentTime=state.cursor}}/>}
   <div className="camera-tag"><span className={state.source==='live'?'live-dot':'record-dot'}/>{state.source==='live'?'实时相机':'历史实验录像'}</div>
   <div className="camera-corner">{state.source==='live'?'RGB':state.snapshot.run?.replace('p4_','').replace('_final','').toUpperCase()}</div>
 </div>
}

export function Timeline({t,summary,compact=false,windows}:{t:number;summary?:any;compact?:boolean;windows?:any}){
 const events=summary?.reference_anchor_events||[];const recorded=[{id:'cross',name:'路口通行',blocked:summary?.measured_occupancy_s?.obstacle1_envelope||[],win:summary?.console_reference_window||[0,0],v:summary?.measured_occupancy_s?.virtual_body?.[0]?.[1],p:summary?.measured_occupancy_s?.physical_body?.[0]?.[1],label:'完整驶离'},...['borrow_start','return_start'].map((id,i)=>({id,name:i?'回归车道':'借道开始',win:events.find((x:any)=>x.event===id)?.window||[0,0],v:events.find((x:any)=>x.event===id&&x.actor==='virtual')?.time_s,p:events.find((x:any)=>x.event===id&&x.actor==='physical')?.time_s,label:'参考进度锚点'}))];const data=windows?[{id:'cross',name:'路口驶离',blocked:windows.protected||[],win:[windows.cross_start,windows.cross_deadline],v:null,p:null,label:'合同允许区间'},...(windows.events||[]).map((e:any)=>({id:e.name,name:e.name==='borrow_start'?'借道开始':'回归车道',win:e.window,v:null,p:null,label:'参考锚点'}))]:recorded;
 return <div className={'timeline '+(compact?'compact-timeline':'')}><div className="timeline-ticks"><span/><div>{[0,4,8,12,16,20,24].map(x=><span key={x} style={{left:`${x/24*100}%`}}>{x} s</span>)}</div><span/></div>{data.map(e=><div className="timeline-row" key={e.id}><span>{e.name}</span><div className="time-track">{((e as any).blocked||[]).map((b:number[],i:number)=><div key={i} className="blocked-interval" title={windows?'预测障碍包络占用':'实测障碍包络占用'} style={{left:`${Math.max(0,b[0])/24*100}%`,width:`${Math.max(0,Math.min(24,b[1])-Math.max(0,b[0]))/24*100}%`}}/>)}<div className="window-interval" style={{left:`${e.win[0]/24*100}%`,width:`${(e.win[1]-e.win[0])/24*100}%`}}/><div className="time-now" style={{left:`${t/24*100}%`}}/>{e.v!=null&&<i className="time-dot virtual" style={{left:`${e.v/24*100}%`}}/>}{e.p!=null&&<i className="time-dot physical" style={{left:`${e.p/24*100}%`}}/>}</div><span className="time-window-label">{e.win[0].toFixed(2)}–{e.win[1].toFixed(2)} s</span></div>)}{!compact&&<div className="timeline-note"><i className="window-key"/>参考允许区间<span><i className="dot-key" style={{background:C.obstacle}}/>{windows?'预测占用':'实测占用'}</span><span><i className="dot-key" style={{background:C.virtual}}/>QV</span><span><i className="dot-key" style={{background:C.physical}}/>QP</span><span>路口为完整驶离；借道/回归为进度锚点</span></div>}</div>
}

export default function Overview({boot,state,traces,summary,navigate}:{boot:Bootstrap;state:State;traces:Trace[];summary:any;navigate:(p:Page)=>void}){
 const s=state.snapshot;const points=traces.filter(x=>x.t<=s.t).slice(-50);const r=state.resources;const historical=state.source==='recorded';
 return <div className="overview-page page-fill">
  <div className="overview-body">
   <div className="overview-main"><Panel className="map-panel" title="实时地图平面图" icon={<Waypoints size={17}/>} action={<span className="subtle">世界坐标 · XY</span>}><MapView map={boot.map} snapshot={s} traces={traces} actors={boot.actors}/></Panel></div>
   <div className="overview-side">
    <Panel title="场景画面" icon={<Video size={17}/>} action={<button className="text-button" onClick={()=>navigate('driving')}>驾驶感知<ArrowUpRight size={14}/></button>}><Camera state={state}/></Panel>
    <Panel title="虚实车辆状态" icon={<GitCompareArrows size={17}/>} action={<Pill>同帧观测</Pill>}><div className="twin-table"><div className="twin-head"><span>状态量</span><span style={{color:C.virtual}}>CARLA 虚拟车</span><span style={{color:C.physical}}>ROS 物理车</span></div>{[['X / m',s.virtual?.x,s.physical?.x],['Y / m',s.virtual?.y,s.physical?.y],['航向 / °',s.virtual?.yaw==null?null:s.virtual.yaw*180/Math.PI,s.physical?.yaw==null?null:s.physical.yaw*180/Math.PI]].map(([name,v,p])=><div key={String(name)}><span>{name}</span><span>{format(v as number,2)}</span><span>{format(p as number,2)}</span></div>)}</div><div className="status-strip"><span className="live-dot"/>虚拟车：CARLA actor<span className="subtle">物理车：ROS 未接入</span></div></Panel>
    <Panel title="主机与事件" icon={<Activity size={17}/>} action={<button className="text-button" onClick={()=>navigate('resources')}>资源详情<ArrowUpRight size={14}/></button>}><div className="mini-resources">{[['CPU',r?.cpu],['GPU',r?.gpu],['内存',r?.memory_percent]].map(([label,v])=><div key={String(label)}><span>{label}</span><strong>{format(v as number,0)}<small>%</small></strong><div className="bar"><i style={{width:`${Number(v)||0}%`}}/></div></div>)}</div><div className="event-list">{[...state.events,...state.native_events.map(e=>({...e,at:e.timestamp||0}))].slice(-2).reverse().map((e,i)=><div key={i}><span className="event-dot"/><span>{e.message}</span><time>{e.at?new Date(e.at*1000).toLocaleTimeString('zh-CN',{hour12:false}):'—'}</time></div>)}</div></Panel>
   </div>
  </div>
 </div>
}
