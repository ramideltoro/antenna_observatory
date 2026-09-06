#!/usr/bin/env python3
"""Durably upload completed readsb dump-beast batches to the remote relay."""
import argparse,hashlib,json,os,random,shutil,ssl,subprocess,time,urllib.error,urllib.request
from pathlib import Path

COMPLETE_GRACE_SECONDS=180
CORRUPT_GRACE_SECONDS=300
FREE_DISK_RESERVE=20*1024*1024*1024

def read_json(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def write_private_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_name('.'+path.name+'.tmp')
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
        json.dump(value,stream,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path);os.chmod(path,0o600)

def sha256_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

class FrameUploader:
    def __init__(self,remote,token,dump_dir,spool_dir,status_file,zstd):
        self.remote=remote.rstrip('/');self.token=token;self.dump=Path(dump_dir);self.spool=Path(spool_dir);self.status_file=Path(status_file);self.zstd=zstd
        self.quarantine=self.spool/'quarantine';self.context=ssl.create_default_context()
        for path in (self.dump,self.spool,self.quarantine):path.mkdir(parents=True,exist_ok=True,mode=0o700)
        previous=read_json(self.status_file,{})
        self.gaps=int(previous.get('gap_count',0));self.last_captured=previous.get('last_captured_at');self.last_uploaded=previous.get('last_uploaded_at');self.last_error=None
    def valid_zstd(self,path):
        try:return subprocess.run([self.zstd,'-t','--quiet',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15).returncode==0
        except (OSError,subprocess.TimeoutExpired):return False
    def claim_completed(self,now=None):
        now=time.time() if now is None else now
        files=sorted(self.dump.glob('*.zst'),key=lambda path:(path.stat().st_mtime_ns,path.name))
        newest=files[-1] if files else None
        for path in files:
            try:stat=path.stat()
            except FileNotFoundError:continue
            age=now-stat.st_mtime
            if path==newest and age<COMPLETE_GRACE_SECONDS:continue
            if not self.valid_zstd(path):
                if path!=newest and age>CORRUPT_GRACE_SECONDS:
                    target=self.quarantine/(str(stat.st_mtime_ns)+'-'+path.name)
                    os.replace(path,target);self.gaps+=1;self.last_error='Quarantined an invalid Beast batch: '+path.name
                continue
            digest=sha256_file(path);target=self.spool/(str(stat.st_mtime_ns)+'-'+digest+'.zst')
            if target.exists():path.unlink()
            else:os.replace(path,target);os.chmod(target,0o600)
            captured=stat.st_mtime
            self.last_captured=max(self.last_captured or captured,captured)
    def pending(self):
        return sorted((path for path in self.spool.glob('*.zst') if path.is_file()),key=lambda path:(path.stat().st_mtime_ns,path.name))
    def enforce_disk_reserve(self):
        pending=self.pending()
        while pending and shutil.disk_usage(self.spool).free<FREE_DISK_RESERVE:
            lost=pending.pop(0);lost.unlink();self.gaps+=1;self.last_error='Dropped the oldest unacknowledged Beast batch because disk space is critically low.'
    def upload_oldest(self):
        pending=self.pending()
        if not pending:return False
        path=pending[0];digest=path.stem.rsplit('-',1)[-1]
        if not len(digest)==64 or any(value not in '0123456789abcdef' for value in digest):raise ValueError('Invalid spooled batch name')
        body=path.read_bytes();request=urllib.request.Request(self.remote+'/'+digest,data=body,method='PUT',headers={
          'Authorization':'Bearer '+self.token,'Content-Type':'application/zstd','User-Agent':'AntennaObservatory-Frame-Uplink/1'})
        with urllib.request.urlopen(request,timeout=30,context=self.context) as response:result=json.load(response)
        if result.get('accepted') is not True or result.get('sha256')!=digest:raise ValueError('Relay acknowledgement did not match the Beast batch')
        path.unlink();self.last_uploaded=time.time();self.last_error=None
        return True
    def status(self,state=None):
        pending=self.pending();now=time.time();oldest=now-pending[0].stat().st_mtime if pending else None
        value={'state':state or ('error' if self.last_error else 'backlogged' if pending else 'live'),
          'last_captured_at':self.last_captured,'last_uploaded_at':self.last_uploaded,'pending_batches':len(pending),
          'spool_bytes':sum(path.stat().st_size for path in pending),'oldest_pending_age_s':max(0,oldest) if oldest is not None else None,
          'gap_count':self.gaps,'last_error':self.last_error,'updated_at':now}
        write_private_json(self.status_file,value);return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--remote',required=True);parser.add_argument('--token-file',required=True)
    parser.add_argument('--dump-dir',required=True);parser.add_argument('--spool-dir',required=True);parser.add_argument('--status-file',required=True)
    parser.add_argument('--zstd',default=shutil.which('zstd'));args=parser.parse_args()
    token=Path(args.token_file).read_text().strip()
    if len(token)<32:raise SystemExit('Invalid relay token')
    if not args.zstd or not Path(args.zstd).is_file():raise SystemExit('zstd is required for Beast batch validation')
    uploader=FrameUploader(args.remote,token,args.dump_dir,args.spool_dir,args.status_file,args.zstd);failures=0
    while True:
        try:
            uploader.claim_completed();uploader.enforce_disk_reserve();uploaded=uploader.upload_oldest();uploader.status()
            if failures:print('Frame uplink restored.',flush=True)
            failures=0;time.sleep(1 if uploaded else 5)
        except (OSError,ValueError,urllib.error.URLError) as error:
            failures+=1;uploader.last_error=type(error).__name__+': '+str(error);uploader.status('error')
            if failures==1 or failures%12==0:print('Frame uplink unavailable ('+type(error).__name__+'); retrying.',flush=True)
            time.sleep(min(300,2**min(failures,8))+random.random())

if __name__=='__main__':main()
