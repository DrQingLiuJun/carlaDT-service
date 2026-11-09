export async function api<T=any>(path:string,body?:unknown):Promise<T>{
  const r=await fetch('/api'+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){let msg='服务请求失败';try{const d=await r.json();msg=typeof d.detail==='string'?d.detail:JSON.stringify(d.detail)}catch{}throw new Error(msg)}
  return r.json();
}
export const format=(n:number|null|undefined,digits=2)=>n==null||!Number.isFinite(n)?'—':n.toFixed(digits);
export const gib=(n:number|undefined)=>n==null?'—':(n/1073741824).toFixed(1);
export const phaseName=(s:string|undefined)=>({CROSSING:'路口通行',BORROW:'借道超车',PASS:'超越障碍',RETURN:'回归车道',PREPARING:'巡航建立',NAVIGATION:'路线导航',RESETTING:'导航归位',MANUAL:'手动驾驶'}[s||'']||s||'等待任务');
