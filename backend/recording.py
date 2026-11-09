import csv,json,uuid,threading,functools
from datetime import datetime,timezone
from pathlib import Path


def safe_file(root,relative):
    root=Path(root).resolve();p=(root/relative).resolve()
    if not p.is_relative_to(root):raise ValueError('文件路径不在记录目录内')
    if not p.is_file():raise FileNotFoundError(relative)
    return p


def locked(fn):
    @functools.wraps(fn)
    def call(self,*args,**kwargs):
        with self.lock:return fn(self,*args,**kwargs)
    return call


class Recorder:
    def __init__(self,root):
        self.root=Path(root);self.file=None;self.csv_file=None;self.writer=None;self.info=None;self.folder=None;self.lock=threading.RLock();self.last_key=None
    @property
    def active(self):return self.file is not None
    @locked
    def start(self,source,config):
        if self.active:raise ValueError('已有记录任务')
        self.folder=self.root/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);self.folder.mkdir(parents=True)
        self.info=dict(id=self.folder.name,source=source,status='recording',samples=0,config=config,started_at=datetime.now(timezone.utc).isoformat())
        self.last_key=None;self.file=(self.folder/'telemetry.jsonl').open('w');self.csv_file=(self.folder/'telemetry.csv').open('w+',newline='')
        (self.folder/'manifest.json').write_text(json.dumps(self.info,ensure_ascii=False,indent=2));return self.info
    @locked
    def write(self,row):
        if not self.active:return
        key=(row.get('source'),row.get('frame'))
        if row.get('frame') is not None and key==self.last_key:return
        self.last_key=key
        self.file.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');self.file.flush()
        flat={}
        def flatten(d,prefix=''):
            for k,v in (d.items() if isinstance(d,dict) else enumerate(d)):
                k=str(k)
                if k=='reference_path':continue  # static geometry stays in JSONL
                key=prefix+k
                if isinstance(v,(dict,list)):flatten(v,key+'_')
                else:flat[key]=v
        flatten(row)
        if self.writer is None:
            self.writer=csv.DictWriter(self.csv_file,fieldnames=list(flat),extrasaction='ignore');self.writer.writeheader()
        elif any(k not in self.writer.fieldnames for k in flat):
            fields=list(self.writer.fieldnames)+[k for k in flat if k not in self.writer.fieldnames]
            self.csv_file.flush();self.csv_file.seek(0);old=list(csv.DictReader(self.csv_file));self.csv_file.seek(0);self.csv_file.truncate()
            self.writer=csv.DictWriter(self.csv_file,fieldnames=fields,extrasaction='ignore');self.writer.writeheader();self.writer.writerows(old)
        self.writer.writerow(flat);self.csv_file.flush();self.info['samples']+=1
    @locked
    def stop(self):
        if not self.active:raise ValueError('没有正在进行的记录')
        self.file.close();self.csv_file.close();self.file=self.csv_file=None;self.writer=None
        self.info.update(status='saved',ended_at=datetime.now(timezone.utc).isoformat(),path=str(self.folder))
        (self.folder/'manifest.json').write_text(json.dumps(self.info,ensure_ascii=False,indent=2));return self.info
    def listing(self):
        out=[]
        for p in sorted(self.root.glob('*/manifest.json'),reverse=True):
            try:out.append({**json.loads(p.read_text()),'files':[x.name for x in p.parent.iterdir() if x.is_file()]})
            except (OSError,ValueError):continue
        return out[:100]
