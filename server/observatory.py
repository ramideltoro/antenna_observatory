#!/usr/bin/env python3
"""Antenna Observatory collector, public dashboard relay, and website server."""
import argparse, collections, csv, gzip, hashlib, hmac, io, ipaddress, json, math, os, platform, re, secrets, shutil, socket, sqlite3, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import intelligence

ROOT = Path(__file__).resolve().parent.parent
LINUX = platform.system() == 'Linux'
STATE = Path(os.environ.get('ANTENNA_STATE_DIR', '/var/lib/antenna-observatory' if LINUX else Path.home() / 'Library/Application Support/AntennaObservatory/state'))
DATA = Path(os.environ.get('ANTENNA_READSB_DIR', '/run/readsb' if LINUX else STATE / 'readsb'))
BEAST_PORT = int(os.environ.get('ANTENNA_BEAST_PORT', '30005' if LINUX else '30905'))
READSB_SERVICE = os.environ.get('ANTENNA_READSB_SERVICE', 'readsb.service')
FEED_SERVICE = os.environ.get('ANTENNA_FEED_SERVICE', 'airplanes-feed.service')
CONFIG = STATE / 'settings.json'
REMOTE_CONFIG = STATE / 'remote-access.json'
DB = STATE / 'observatory.sqlite'
LOG = Path.home() / 'Library/Logs/airplanes-live.log'
RELAY_TOKEN = STATE / 'relay-token'
FRAME_UPLINK_STATUS = STATE / 'frame-uplink-status.json'
BEAST_BATCHES = STATE / 'beast-batches'
LABEL = 'local.airplanes-live.readsb'
DEVICE_MODEL = os.environ.get('ANTENNA_DEVICE_MODEL', 'Nooelec NESDR SMArt v5')
DEVICE_SERIAL = os.environ.get('ANTENNA_DEVICE_SERIAL', 'configured')
FEEDER_ID = os.environ.get('ANTENNA_FEEDER_ID', 'configured')
FAMILIES = ['ADS-B', 'Mode S', 'TIS-B', 'ADS-R', 'Mode A/C', 'Other']
DF_NAMES = {0:'Short air-to-air surveillance',4:'Altitude reply',5:'Identity reply',11:'All-call reply',16:'Long air-to-air surveillance',17:'ADS-B extended squitter',18:'Extended squitter / rebroadcast',19:'Military extended squitter',20:'Comm-B altitude reply',21:'Comm-B identity reply',24:'Comm-D extended length'}
TYPE_NAMES = {**{n:'Identification' for n in range(1,5)},**{n:'Surface position' for n in range(5,9)},**{n:'Airborne position (barometric)' for n in range(9,19)},19:'Velocity',**{n:'Airborne position (GNSS)' for n in range(20,23)},28:'Aircraft status',29:'Target state',31:'Operational status'}
STATIC_CONTENT_TYPES = {
    '.css':'text/css; charset=utf-8', '.html':'text/html; charset=utf-8', '.ico':'image/x-icon',
    '.js':'application/javascript; charset=utf-8', '.json':'application/json', '.map':'application/json',
    '.png':'image/png', '.rsc':'text/x-component; charset=utf-8', '.svg':'image/svg+xml',
    '.txt':'text/plain; charset=utf-8', '.webmanifest':'application/manifest+json', '.woff':'font/woff',
    '.woff2':'font/woff2',
}
MAX_BEAST_COMPRESSED = 16 * 1024 * 1024
MAX_BEAST_DECOMPRESSED = 64 * 1024 * 1024
BEAST_RETENTION_SECONDS = 72 * 3600

def build_static_manifest(public):
    public = public.resolve()
    if not public.is_dir(): return {}
    return {'/'+candidate.relative_to(public).as_posix(): candidate for candidate in public.rglob('*') if candidate.is_file()}

def write_private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.'+path.name+'.'+secrets.token_hex(8)+'.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'))
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass

def read_json(path, default=None):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return default if default is not None else {}

def command(args):
    try: return subprocess.run(args, capture_output=True, text=True, timeout=4).stdout
    except (OSError, subprocess.TimeoutExpired): return ''

def validated_public_origin(value):
    if not value: return None
    parsed=urlparse(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.port not in (None,443):
        raise ValueError('Public origin must be a single HTTPS hostname')
    if not re.fullmatch(r'[a-zA-Z0-9.-]+',parsed.hostname): raise ValueError('Invalid public hostname')
    return 'https://'+parsed.hostname.lower()

def aircraft_family(a):
    t=a.get('type','')
    if t.startswith('adsb'): return 'ADS-B'
    if t.startswith('tisb'): return 'TIS-B'
    if t.startswith('adsr'): return 'ADS-R'
    if t == 'mode_s': return 'Mode S'
    if t == 'mode_ac': return 'Mode A/C'
    if t == 'mlat': return 'MLAT'
    return 'Other'

def distance_bearing(lat1, lon1, lat2, lon2):
    a,b,c,d=map(math.radians,[lat1,lon1,lat2,lon2]); delta=d-b
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin(delta/2)**2
    return 3440.065*2*math.asin(min(1,math.sqrt(h))), (math.degrees(math.atan2(math.sin(delta)*math.cos(c),math.cos(a)*math.sin(c)-math.sin(a)*math.cos(c)*math.cos(delta)))+360)%360

def classify_frame(kind,payload):
    if kind==0x31: return 'Mode A/C',None,None
    df=payload[0]>>3; family='Mode S'
    if df==17: family='ADS-B'
    elif df==18:
        cf=payload[0]&7
        family='ADS-R' if cf==6 else 'TIS-B' if cf in (2,3,5) else 'ADS-B' if cf in (0,1) else 'Other'
    df=min(df,24)
    tc=payload[4]>>3 if df in (17,18) and family in ('ADS-B','ADS-R') and len(payload)>4 else None
    return family,df,tc

class BeastParser:
    """Incremental parser for escaped Beast type 1/2/3 frames, with resync."""
    lengths={0x31:9,0x32:14,0x33:21,0x34:21}
    def __init__(self): self.buf=bytearray()
    def feed(self, chunk):
        self.buf.extend(chunk); result=[]
        while len(self.buf)>=2:
            try: start=self.buf.index(0x1a)
            except ValueError: self.buf.clear(); break
            if start: del self.buf[:start]
            if len(self.buf)<2: break
            kind=self.buf[1]; length=self.lengths.get(kind)
            if length is None: del self.buf[0]; continue
            data=bytearray(); i=2; incomplete=False; corrupt=False
            while len(data)<length:
                if i>=len(self.buf): incomplete=True; break
                value=self.buf[i]
                if value==0x1a:
                    if i+1>=len(self.buf): incomplete=True; break
                    if self.buf[i+1]!=0x1a: corrupt=True; break
                    i+=1
                data.append(value); i+=1
            if incomplete: break
            if corrupt: del self.buf[:i]; continue
            del self.buf[:i]
            if kind in (0x31,0x32,0x33): result.append((kind,bytes(data)))
        return result

def parse_beast_dump(data,collect_frames=True,on_frame=None,allow_empty=False):
    """Strictly parse a readsb dump-beast stream, including wall-clock markers."""
    frames=[]; frame_count=0; offset=0; wall_ms=None; capture_start=None; capture_end=None
    lengths={0x31:9,0x32:14,0x33:21}
    while offset<len(data):
        if offset+2>len(data) or data[offset]!=0x1a: raise ValueError('Malformed Beast record boundary')
        kind=data[offset+1];offset+=2
        if kind==0xe8:
            if offset+8>len(data): raise ValueError('Truncated Beast wall-clock marker')
            wall_ms=int.from_bytes(data[offset:offset+8],'little',signed=True);offset+=8
            if wall_ms<946684800000 or wall_ms>4102444800000: raise ValueError('Invalid Beast wall-clock marker')
            capture_start=wall_ms if capture_start is None else min(capture_start,wall_ms);capture_end=max(capture_end or wall_ms,wall_ms)
            continue
        length=lengths.get(kind)
        if length is None: raise ValueError('Unsupported Beast record type')
        decoded=bytearray()
        while len(decoded)<length:
            if offset>=len(data): raise ValueError('Truncated Beast frame')
            value=data[offset];offset+=1
            if value==0x1a:
                if offset>=len(data) or data[offset]!=0x1a: raise ValueError('Invalid Beast escape sequence')
                offset+=1
            decoded.append(value)
        if wall_ms is None: raise ValueError('Beast frame precedes wall-clock marker')
        payload=bytes(decoded[7:]);family,df,tc=classify_frame(kind,payload)
        frame={'ordinal':frame_count,'ts':wall_ms/1000,'kind':kind,'receiver_ticks':int.from_bytes(decoded[:6],'big'),
          'signal':decoded[6],'payload':payload,'family':family,'df':df,'type_code':tc}
        if collect_frames:frames.append(frame)
        if on_frame:on_frame(frame)
        frame_count+=1
    if not frame_count:
        if not allow_empty:raise ValueError('Beast batch contains no decoded frames')
        return {'frames':frames,'frame_count':0,'capture_start':capture_start/1000 if capture_start else None,'capture_end':capture_end/1000 if capture_end else None}
    if capture_start is None:raise ValueError('Beast batch contains no wall-clock marker')
    if capture_end-capture_start>5*60*1000: raise ValueError('Beast batch time span is too large')
    return {'frames':frames,'frame_count':frame_count,'capture_start':capture_start/1000,'capture_end':capture_end/1000}

def decompress_zstd(path,limit=MAX_BEAST_DECOMPRESSED):
    """Decompress one bounded zstd file without allowing unbounded child output."""
    executable=os.environ.get('ANTENNA_ZSTD') or shutil.which('zstd')
    if not executable: raise RuntimeError('zstd executable is unavailable')
    process=subprocess.Popen([executable,'-dc','--quiet',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    output=bytearray()
    try:
        while True:
            chunk=process.stdout.read(min(65536,limit+1-len(output)))
            if not chunk: break
            output.extend(chunk)
            if len(output)>limit:
                process.kill();raise ValueError('Expanded Beast batch is too large')
        error=process.stderr.read(4096);code=process.wait(timeout=10)
    except BaseException:
        process.kill();process.wait();raise
    finally:
        process.stdout.close();process.stderr.close()
    if code: raise ValueError('Invalid Zstandard batch: '+error.decode('utf-8','replace').strip()[:200])
    return bytes(output)

class Observatory:
    def __init__(self):
        STATE.mkdir(parents=True,exist_ok=True); DATA.mkdir(exist_ok=True)
        self.lock=threading.RLock(); self.stop=threading.Event(); self.started=time.time()
        self.frames=collections.deque(maxlen=250000); self.recent=collections.deque(maxlen=100)
        self.totals=collections.Counter(); self.df=collections.Counter(); self.tc=collections.Counter()
        self.df_family=collections.Counter()
        self.events=collections.deque(maxlen=250); self.snap={}; self.host={}; self.beast_connected=False
        self.feed_connected=None; self.previous=None; self.last_persist=0; self.last_health=0
        self.active_alert_codes=set()
        self.settings=read_json(CONFIG, {'station_name':'Rami’s receiver','latitude':None,'longitude':None})
        self.db=sqlite3.connect(DB,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_ts ON events(ts)')
        intelligence.initialize(self.db)
        self.db.commit()
        for t,l,m in self.db.execute('SELECT ts,level,message FROM events ORDER BY ts DESC LIMIT 150').fetchall()[::-1]: self.events.append({'time':t,'level':l,'message':m})
        self.event('info','Observatory collector started')
        for line in self.logs():
            if 'Abnormal exit.' in line:
                message='Previous decoder log: '+line.strip()
                if not self.db.execute('SELECT 1 FROM events WHERE message=? LIMIT 1',(message,)).fetchone(): self.event('warning',message)
    def event(self,level,message):
        with self.lock:
            now=time.time(); self.events.append({'time':now,'level':level,'message':message})
            self.db.execute('INSERT INTO events VALUES (?,?,?)',(now,level,message)); self.db.commit()
    def start(self):
        for target in (self.beast_loop,self.collect_loop): threading.Thread(target=target,daemon=True).start()
    def beast_loop(self):
        while not self.stop.is_set():
            try:
                with socket.create_connection(('127.0.0.1',BEAST_PORT),timeout=3) as sock:
                    sock.settimeout(3); parser=BeastParser()
                    with self.lock: self.beast_connected=True
                    self.event('success','Local signal stream connected')
                    while not self.stop.is_set():
                        try: chunk=sock.recv(65536)
                        except socket.timeout: continue
                        if not chunk: break
                        now=time.time()
                        with self.lock:
                            for kind,data in parser.feed(chunk):
                                payload=data[7:]; family,df,tc=classify_frame(kind,payload)
                                if df is not None:
                                    self.df[df]+=1
                                    self.df_family[(df,family)]+=1
                                if tc is not None: self.tc[tc]+=1
                                self.frames.append((now,family,df,tc)); self.totals[family]+=1
                                self.recent.appendleft({'time':now,'family':family,'df':df,'type_code':tc,'hex':payload.hex().upper(),'rssi':round(20*math.log10(data[6]/255),1) if data[6] else None})
            except OSError: pass
            with self.lock:
                was=self.beast_connected; self.beast_connected=False
            if was: self.event('warning','Local signal stream disconnected; reconnecting')
            self.stop.wait(3)
    def inspect_host(self):
        if LINUX:
            props=dict(line.split('=',1) for line in command(['systemctl','show',READSB_SERVICE,'--property=MainPID,ActiveState']).splitlines() if '=' in line)
            pid=int(props.get('MainPID','0')) or None
            state=props.get('ActiveState','unknown')
            established=[]; cpu=None; memory=None
            if pid:
                vals=command(['ps','-p',str(pid),'-o','%cpu=,rss=']).split()
                if len(vals)==2:
                    try: cpu=float(vals[0]); memory=round(int(vals[1])/1024,1)
                    except ValueError: pass
            for line in command(['ss','-Htn','state','established']).splitlines():
                fields=line.split()
                if len(fields)<4: continue
                local,peer=fields[2:4]
                try:
                    address,port=peer.rsplit(':',1)
                    external=not ipaddress.ip_address(address.strip('[]')).is_loopback
                except ValueError: continue
                if external and port in ('30004','64004'): established.append(local+'->'+peer)
            connected=bool(established) and command(['systemctl','is-active',FEED_SERVICE]).strip()=='active'
            mlat_configured=command(['systemctl','is-enabled','airplanes-mlat.service']).strip()=='enabled'
        else:
            text=command(['/bin/launchctl','print',f'gui/{os.getuid()}/{LABEL}'])
            pid_match=re.search(r'^\s*pid = (\d+)',text,re.M); state_match=re.search(r'^\s*state = (\S+)',text,re.M)
            pid=int(pid_match.group(1)) if pid_match else None
            established=[]; cpu=None; memory=None
            if pid:
                connections=command(['/usr/sbin/lsof','-nP','-a','-p',str(pid),'-iTCP','-sTCP:ESTABLISHED','-Fn'])
                established=[line[1:] for line in connections.splitlines() if line.startswith('n') and '->' in line]
                vals=command(['/bin/ps','-p',str(pid),'-o','%cpu=,rss=']).split()
                if len(vals)==2:
                    try: cpu=float(vals[0]); memory=round(int(vals[1])/1024,1)
                    except ValueError: pass
            connected=any(re.search(r'->[^ ]+:30004(?: |$)',s) for s in established)
            state=state_match.group(1) if state_match else 'not loaded'
            mlat_configured=False
        with self.lock:
            previous_pid=self.host.get('pid')
            if previous_pid and pid and previous_pid!=pid:
                self.event('warning',f'Decoder process restarted (PID {previous_pid} → {pid}); TCP feed '+('connected' if connected else 'reconnecting'))
            if self.feed_connected is not None and connected!=self.feed_connected: self.event('success' if connected else 'warning','Airplanes.live TCP connection restored' if connected else 'Airplanes.live TCP connection unavailable')
            self.feed_connected=connected
            self.host={'pid':pid,'state':state,'cpu_percent':cpu,'memory_mb':memory,'feed_connected':connected,'connections':established,'checked_at':time.time(),'platform':platform.system(),'mlat_configured':mlat_configured,'beast_port':BEAST_PORT}
    def collect_loop(self):
        while not self.stop.is_set():
            try: self.collect()
            except Exception as exc: print('Collector error:',type(exc).__name__,str(exc),flush=True)
            self.stop.wait(1)
    def collect(self):
        now=time.time()
        if now-self.last_health>=10: self.inspect_host(); self.last_health=now
        raw=read_json(DATA/'aircraft.json'); stats=read_json(DATA/'stats.json'); receiver=read_json(DATA/'receiver.json')
        frame_pipeline=read_json(FRAME_UPLINK_STATUS,{'state':'waiting','pending_batches':0,'spool_bytes':0,'gap_count':0})
        timestamp=raw.get('now'); age=max(0,now-timestamp) if isinstance(timestamp,(int,float)) else None
        fresh=age is not None and age<6
        total=stats.get('total',{}); window=stats.get('last1min',{})
        if window.get('end',0)<=window.get('start',0): window=total
        duration=window.get('end',0)-window.get('start',0)
        local=window.get('local',{}); all_local=total.get('local',{})
        accepted=local.get('accepted',[]); total_accepted=sum(accepted)
        rate=None
        if timestamp and self.previous and timestamp>self.previous[0]:
            delta=raw.get('messages',0)-self.previous[1]
            rate=delta/(timestamp-self.previous[0]) if delta>=0 else None
        elif fresh: rate=self.snap.get('metrics',{}).get('message_rate')
        if timestamp: self.previous=(timestamp,raw.get('messages',0))
        aircraft=[]; settings=self.settings.copy()
        for original in raw.get('aircraft',[]):
            a=dict(original); a['family']=aircraft_family(a)
            a['flight']=str(a.get('flight','')).strip(); a['live']=fresh and a.get('seen',999)<15
            a['distance_nm']=None; a['bearing']=None
            if all(isinstance(x,(int,float)) for x in (a.get('lat'),a.get('lon'),settings.get('latitude'),settings.get('longitude'))):
                dist,bearing=distance_bearing(settings['latitude'],settings['longitude'],a['lat'],a['lon']); a['distance_nm']=round(dist,1); a['bearing']=round(bearing,1)
            aircraft.append(a)
        active=[a for a in aircraft if a['live']]
        located=[a for a in active if isinstance(a.get('lat'),(int,float)) and a.get('seen_pos',999)<15]
        stats_fresh=fresh and now-stats.get('now',0)<30
        signal=local.get('signal') if stats_fresh else None; noise=local.get('noise') if stats_fresh else None
        metrics={'aircraft':len(active),'with_position':len(located),'message_rate':round(rate,2) if fresh and rate is not None else None,
          'position_rate':round(window.get('position_count_total',0)/duration,2) if duration>0 and stats_fresh else None,
          'mean_signal':signal,'noise':noise,'peak_signal':local.get('peak_signal'),'signal_above_noise':round(signal-noise,1) if signal is not None and noise is not None else None,
          'gain':stats.get('gain_db'),'ppm':stats.get('estimated_ppm'),'valid_messages':total.get('messages_valid'),'mode_s_preambles':all_local.get('modes'),
          'samples_processed':all_local.get('samples_processed'),'samples_dropped':all_local.get('samples_dropped'),'samples_lost':all_local.get('samples_lost'),
          'corrected_percent':round(100*sum(accepted[1:])/total_accepted,2) if total_accepted else None,
          'strong_percent':round(100*local.get('strong_signals',0)/total_accepted,2) if total_accepted else None,
          'clean_percent':round(100*accepted[0]/total_accepted,2) if total_accepted else None,
          'positions_total':total.get('position_count_total'),'max_range_nm':max((a['distance_nm'] for a in located if a['distance_nm'] is not None),default=None),
          'cpu_percent':self.host.get('cpu_percent'),'memory_mb':self.host.get('memory_mb'),'feed_connected':self.feed_connected,'stats_window_s':round(duration,1)}
        if not stats_fresh:
            for key in ('gain','ppm','peak_signal','clean_percent','corrected_percent','strong_percent'): metrics[key]=None
        with self.lock:
            while self.frames and self.frames[0][0]<now-60: self.frames.popleft()
            elapsed=min(60,max(1,now-self.started)); counts=collections.Counter(x[1] for x in self.frames)
            recent_df=collections.Counter(x[2] for x in self.frames)
            recent_df_family=collections.Counter((x[2],x[1]) for x in self.frames)
            signals=[{'name':name,'frames':self.totals[name],'rate':round(counts[name]/elapsed,2) if self.beast_connected else None,'last60':counts[name], 'aircraft':sum(a['family']==name for a in active)} for name in FAMILIES]
            state='live' if fresh else 'stale' if timestamp else 'waiting'
            old=self.snap.get('state')
            if old and state!=old: self.event('success' if fresh else 'warning','Receiver telemetry live' if fresh else 'Receiver telemetry stopped updating')
            spectrum=read_json(STATE/'spectrum/latest.json',{})
            if isinstance(spectrum,dict) and spectrum:
                updated=spectrum.get('updated_at')
                spectrum['available']=bool(spectrum.get('lines')) and isinstance(updated,(int,float)) and now-updated<30
                spectrum['age_seconds']=max(0,now-updated) if isinstance(updated,(int,float)) else None
            self.snap={'now':now,'state':state,'source_time':timestamp,'age_seconds':age,'stats_age_seconds':now-stats.get('now',0) if stats.get('now') else None,
              'collector_started':self.started,'decoder_started':total.get('start'),'settings':settings,'metrics':metrics,'aircraft':aircraft,'signals':signals,
              'formats':[{'df':k,'name':DF_NAMES.get(k,'Other format'),'count':v,'last60':recent_df[k], 'families':{f:self.df_family[(k,f)] for f in FAMILIES}, 'last60_by_family':{f:recent_df_family[(k,f)] for f in FAMILIES}} for k,v in sorted(self.df.items())],
              'type_codes':[{'code':k,'name':TYPE_NAMES.get(k,'Reserved / other'),'count':v} for k,v in sorted(self.tc.items())],
              'recent_frames':list(self.recent),'events':list(reversed(self.events))[:100], 'host':self.host,'beast_connected':self.beast_connected,
              'receiver':receiver,'stats':stats,'raw_aircraft':raw,'frame_pipeline':frame_pipeline,'spectrum':spectrum,
              'maintenance_entries':intelligence.list_maintenance(self.db)['entries'],
              'hardware':{'model':DEVICE_MODEL,'serial':DEVICE_SERIAL,'tuner':'Rafael Micro R820T','frequency_mhz':1090,'sample_rate_msps':2.4,'feeder_id':FEEDER_ID,'mlat_configured':self.host.get('mlat_configured',False),'modeac_enabled':True}}
            intelligence.enrich_snapshot(self.db,self.snap)
            new_alerts={alert['code'] for alert in self.snap['smart_alerts']}
            for alert in self.snap['smart_alerts']:
                if alert['code'] not in self.active_alert_codes: self.event(alert['severity'],alert['title']+': '+alert['message'])
            for code in self.active_alert_codes-new_alerts: self.event('success','Alert cleared: '+code.replace('-',' '))
            self.active_alert_codes=new_alerts
            self.snap['events']=list(reversed(self.events))[:100]
            if now-self.last_persist>=10:
                sample=dict(metrics,ts=now,signals={s['name']:s['rate'] for s in signals},state=state,health_score=self.snap['health_score']['score'])
                self.db.execute('INSERT OR REPLACE INTO samples VALUES (?,?)',(now,json.dumps(sample,allow_nan=False)))
                intelligence.persist_snapshot(self.db,now,self.snap)
                self.db.execute('DELETE FROM samples WHERE ts < ?',(now-7*86400,)); self.db.execute('DELETE FROM events WHERE ts < ?',(now-7*86400,)); self.db.commit(); self.last_persist=now
    def snapshot(self):
        with self.lock:
            snap=self.snap.copy()
            if time.time()-snap.get('now',0)>10:
                snap['state']='stale'
            if snap.get('source_time'): snap['age_seconds']=max(0,time.time()-snap['source_time'])
            intelligence.enrich_snapshot(self.db,snap)
            return snap
    def history(self,hours):
        with self.lock:
            rows=self.db.execute('SELECT ts,payload FROM samples WHERE ts>=? ORDER BY ts',(time.time()-hours*3600,)).fetchall()
            first=self.db.execute('SELECT MIN(ts) FROM samples').fetchone()[0]
        step=max(1,math.ceil(len(rows)/480)); points=[]
        for i in range(0,len(rows),step):
            bucket=[json.loads(r[1]) for r in rows[i:i+step]]; p=dict(bucket[-1])
            for key in ('message_rate','position_rate','aircraft','with_position','mean_signal','noise','gain','cpu_percent','memory_mb','corrected_percent','strong_percent'):
                vals=[x[key] for x in bucket if isinstance(x.get(key),(int,float))]
                p[key]=sum(vals)/len(vals) if vals else None
            for name in FAMILIES:
                vals=[x.get('signals',{}).get(name) for x in bucket]
                p.setdefault('signals',{})[name]=sum(vals)/len(vals) if all(isinstance(v,(int,float)) for v in vals) else None
            # Averages must not draw a continuous line through missing telemetry.
            if any(x.get('state')!='live' for x in bucket) or any(b['ts']-a['ts']>30 for a,b in zip(bucket,bucket[1:])):
                for key in ('message_rate','position_rate','aircraft','with_position','mean_signal','noise','gain'): p[key]=None
                p['signals']={name:None for name in FAMILIES}
            points.append(p)
        return {'points':points,'started':first,'retention_days':7,'interval_seconds':10,'hours':hours}
    def logs(self):
        if LINUX:
            return command(['journalctl','-u',READSB_SERVICE,'-n','150','--no-pager','-o','short-iso']).splitlines()
        try:
            with LOG.open('rb') as f:
                f.seek(0,2); f.seek(max(0,f.tell()-32768)); data=f.read().decode('utf-8','replace')
            return data.splitlines()[-150:]
        except OSError: return []

class RelayObservatory:
    """Stores telemetry and durable Beast batches pushed by the receiver host."""
    def __init__(self):
        STATE.mkdir(parents=True,exist_ok=True);BEAST_BATCHES.mkdir(exist_ok=True)
        self.lock=threading.RLock();self.stop=threading.Event();self.wake=threading.Event();self.started=time.time();self.last_persist=0;self.last_cleanup=0
        self.latest=read_json(STATE/'relay-latest.json');self.log_lines=read_json(STATE/'relay-logs.json',[])
        self.received_at=self.latest.get('relay_received_at',0) if isinstance(self.latest,dict) else 0
        self.db=sqlite3.connect(DB,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA busy_timeout=5000');self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_ts ON events(ts)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS beast_batches (
          sha256 TEXT PRIMARY KEY, received_at REAL NOT NULL, capture_start REAL NOT NULL, capture_end REAL NOT NULL,
          compressed_bytes INTEGER NOT NULL, decompressed_bytes INTEGER NOT NULL, frame_count INTEGER NOT NULL,
          status TEXT NOT NULL, error TEXT, processed_at REAL)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS beast_batches_status_time ON beast_batches(status,capture_start)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS beast_frames (
          batch_sha TEXT NOT NULL, ordinal INTEGER NOT NULL, ts REAL NOT NULL, kind INTEGER NOT NULL,
          receiver_ticks INTEGER NOT NULL, signal INTEGER NOT NULL, payload BLOB NOT NULL, family TEXT NOT NULL,
          df INTEGER, type_code INTEGER, PRIMARY KEY(batch_sha,ordinal),
          FOREIGN KEY(batch_sha) REFERENCES beast_batches(sha256) ON DELETE CASCADE)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS beast_frames_ts ON beast_frames(ts)')
        self.db.execute('CREATE INDEX IF NOT EXISTS beast_frames_family_ts ON beast_frames(family,ts)')
        intelligence.initialize(self.db)
        self.db.execute("UPDATE beast_batches SET status='pending',error=NULL WHERE status='processing'");self.db.commit()
        self.recover_batches()
        self.worker=threading.Thread(target=self.worker_loop,name='beast-batch-worker',daemon=True);self.worker.start()
    def recover_batches(self):
        """Recover a durable file left between rename and the manifest commit."""
        known={row[0] for row in self.db.execute('SELECT sha256 FROM beast_batches')}
        for path in BEAST_BATCHES.glob('*.zst'):
            digest=path.stem
            if digest in known or not re.fullmatch(r'[0-9a-f]{64}',digest): continue
            try:
                expanded=decompress_zstd(path);parsed=parse_beast_dump(expanded,collect_frames=False,allow_empty=True);now=time.time();start=parsed['capture_start'] or path.stat().st_mtime;end=parsed['capture_end'] or start
                self.db.execute('INSERT INTO beast_batches VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (digest,now,start,end,path.stat().st_size,len(expanded),parsed['frame_count'],'pending',None,None))
                self.db.commit()
            except Exception as exc: print('Unable to recover Beast batch:',path.name,type(exc).__name__,str(exc),flush=True)
    def ingest_beast(self,digest,body):
        if not re.fullmatch(r'[0-9a-f]{64}',digest): raise ValueError('Invalid Beast batch digest')
        if hashlib.sha256(body).hexdigest()!=digest: raise ValueError('Beast batch checksum does not match its URL')
        with self.lock:
            row=self.db.execute('SELECT status FROM beast_batches WHERE sha256=?',(digest,)).fetchone()
            if row:return {'accepted':True,'sha256':digest,'duplicate':True,'status':row[0]}
        temporary=BEAST_BATCHES/('.'+digest+'.'+secrets.token_hex(8)+'.tmp');final=BEAST_BATCHES/(digest+'.zst')
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(body);stream.flush();os.fsync(stream.fileno())
            expanded=decompress_zstd(temporary);parsed=parse_beast_dump(expanded,collect_frames=False,allow_empty=True);now=time.time();start=parsed['capture_start'] or now;end=parsed['capture_end'] or start
            with self.lock:
                row=self.db.execute('SELECT status FROM beast_batches WHERE sha256=?',(digest,)).fetchone()
                if row:return {'accepted':True,'sha256':digest,'duplicate':True,'status':row[0]}
                os.replace(temporary,final);os.chmod(final,0o600)
                directory=os.open(BEAST_BATCHES,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
                self.db.execute('INSERT INTO beast_batches VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (digest,now,start,end,len(body),len(expanded),parsed['frame_count'],'pending',None,None))
                self.db.commit()
            self.wake.set()
            return {'accepted':True,'sha256':digest,'duplicate':False,'status':'pending'}
        finally:
            try:temporary.unlink()
            except FileNotFoundError:pass
    def process_one_batch(self):
        with self.lock:
            row=self.db.execute("SELECT sha256 FROM beast_batches WHERE status='pending' ORDER BY capture_start,received_at LIMIT 1").fetchone()
            if not row:return False
            digest=row[0];self.db.execute("UPDATE beast_batches SET status='processing',error=NULL WHERE sha256=?",(digest,));self.db.commit()
        try:
            expanded=decompress_zstd(BEAST_BATCHES/(digest+'.zst'));buffer=[];inserted=0
            with self.lock:
                self.db.execute('DELETE FROM beast_frames WHERE batch_sha=?',(digest,))
                def insert_frame(frame):
                    nonlocal inserted
                    buffer.append((digest,frame['ordinal'],frame['ts'],frame['kind'],frame['receiver_ticks'],frame['signal'],frame['payload'],frame['family'],frame['df'],frame['type_code']))
                    if len(buffer)>=1000:
                        self.db.executemany('INSERT INTO beast_frames VALUES (?,?,?,?,?,?,?,?,?,?)',buffer);inserted+=len(buffer);buffer.clear()
                parsed=parse_beast_dump(expanded,collect_frames=False,on_frame=insert_frame,allow_empty=True)
                if buffer:self.db.executemany('INSERT INTO beast_frames VALUES (?,?,?,?,?,?,?,?,?,?)',buffer);inserted+=len(buffer)
                if inserted!=parsed['frame_count']:raise ValueError('Beast frame indexing count mismatch')
                self.db.execute("UPDATE beast_batches SET status='processed',processed_at=?,error=NULL,frame_count=? WHERE sha256=?",(time.time(),inserted,digest));self.db.commit()
        except Exception as exc:
            with self.lock:
                self.db.rollback();self.db.execute('DELETE FROM beast_frames WHERE batch_sha=?',(digest,))
                self.db.execute("UPDATE beast_batches SET status='failed',error=? WHERE sha256=?",((type(exc).__name__+': '+str(exc))[:500],digest));self.db.commit()
            print('Beast batch processing failed:',digest,type(exc).__name__,str(exc),flush=True)
        return True
    def cleanup_batches(self):
        now=time.time()
        if now-self.last_cleanup<60:return
        cutoff=now-BEAST_RETENTION_SECONDS
        with self.lock:
            rows=self.db.execute("SELECT sha256 FROM beast_batches WHERE status='processed' AND capture_end<?",(cutoff,)).fetchall()
            for row in rows:
                try:(BEAST_BATCHES/(row[0]+'.zst')).unlink()
                except FileNotFoundError:pass
                self.db.execute('DELETE FROM beast_batches WHERE sha256=?',row)
            self.db.commit();self.last_cleanup=now
    def worker_loop(self):
        while not self.stop.is_set():
            try:
                worked=self.process_one_batch();self.cleanup_batches()
            except Exception as exc:
                worked=False;print('Beast worker error:',type(exc).__name__,str(exc),flush=True)
            if not worked:self.wake.wait(2);self.wake.clear()
    def pipeline_status(self):
        with self.lock:
            pending=self.db.execute("SELECT COUNT(*) FROM beast_batches WHERE status IN ('pending','processing')").fetchone()[0]
            failed=self.db.execute("SELECT COUNT(*) FROM beast_batches WHERE status='failed'").fetchone()[0]
            uploaded=self.db.execute('SELECT MAX(received_at) FROM beast_batches').fetchone()[0]
            processed=self.db.execute("SELECT MAX(processed_at) FROM beast_batches WHERE status='processed'").fetchone()[0]
            captured=self.db.execute('SELECT MAX(capture_end) FROM beast_batches').fetchone()[0]
            oldest=self.db.execute("SELECT MIN(capture_start) FROM beast_batches WHERE status IN ('pending','processing')").fetchone()[0]
        return {'server_pending_batches':pending,'failed_batches':failed,'server_last_uploaded_at':uploaded,'last_processed_at':processed,
          'server_last_captured_at':captured,'server_oldest_pending_age_s':max(0,time.time()-oldest) if oldest else None}
    def ingest(self,envelope):
        if not isinstance(envelope,dict) or not isinstance(envelope.get('snapshot'),dict): raise ValueError('Expected a telemetry snapshot')
        snap=envelope['snapshot']; required=('now','state','metrics','aircraft','signals','events','host','hardware')
        if any(key not in snap for key in required): raise ValueError('Incomplete telemetry snapshot')
        if not isinstance(snap['now'],(int,float)) or not math.isfinite(snap['now']): raise ValueError('Invalid telemetry timestamp')
        if not all(isinstance(snap.get(key),list) for key in ('aircraft','signals','events')) or not all(isinstance(snap.get(key),dict) for key in ('metrics','host','hardware')): raise ValueError('Invalid telemetry collections')
        logs=envelope.get('logs',[])
        if not isinstance(logs,list) or any(not isinstance(line,str) for line in logs): raise ValueError('Invalid decoder logs')
        now=time.time();copy=json.loads(json.dumps(snap,allow_nan=False));copy['relay_received_at']=now
        safe_logs=[line[-2000:] for line in logs[-150:]]
        with self.lock:
            if 'maintenance_entries' in copy and copy['maintenance_entries']!=self.latest.get('maintenance_entries'):
                intelligence.sync_maintenance(self.db,copy['maintenance_entries'])
            intelligence.enrich_snapshot(self.db,copy)
            self.latest=copy;self.log_lines=safe_logs;self.received_at=now
            for path,value in ((STATE/'relay-latest.json',copy),(STATE/'relay-logs.json',safe_logs)):
                tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,allow_nan=False));tmp.replace(path)
            if now-self.last_persist>=10:
                metrics=dict(copy.get('metrics',{}));metrics.update(ts=now,signals={s.get('name'):s.get('rate') for s in copy.get('signals',[])},state=copy.get('state'))
                self.db.execute('INSERT OR REPLACE INTO samples VALUES (?,?)',(now,json.dumps(metrics,allow_nan=False)))
                intelligence.persist_snapshot(self.db,now,copy)
                self.db.execute('DELETE FROM samples WHERE ts < ?',(now-7*86400,));self.db.commit();self.last_persist=now
        return {'accepted':True,'received_at':now}
    def snapshot(self):
        with self.lock:
            snap=json.loads(json.dumps(self.latest)) if self.latest else {}
            received=self.received_at
        now=time.time();snap['relay_age_seconds']=max(0,now-received) if received else None
        if not received or now-received>10:
            snap['state']='stale' if snap else 'waiting'
            for aircraft in snap.get('aircraft',[]): aircraft['live']=False
        if snap.get('source_time'): snap['age_seconds']=max(0,now-snap['source_time'])
        local=snap.get('frame_pipeline',{}) if isinstance(snap.get('frame_pipeline'),dict) else {};server=self.pipeline_status()
        local_pending=local.get('pending_batches',0) if isinstance(local.get('pending_batches'),int) else 0
        server_pending=server.get('server_pending_batches',0);oldest=[value for value in (local.get('oldest_pending_age_s'),server.get('server_oldest_pending_age_s')) if isinstance(value,(int,float))]
        pipeline=dict(local);pipeline.update(server);pipeline['pending_batches']=local_pending+server_pending;pipeline['oldest_pending_age_s']=max(oldest) if oldest else None
        pipeline['state']='error' if pipeline.get('gap_count',0) or pipeline.get('failed_batches',0) else 'backlogged' if pipeline['pending_batches'] else 'live' if pipeline.get('last_processed_at') else 'waiting'
        snap['frame_pipeline']=pipeline
        with self.lock:intelligence.enrich_snapshot(self.db,snap)
        return snap
    def history(self,hours): return Observatory.history(self,hours)
    def logs(self):
        with self.lock:return list(self.log_lines)
    def close(self):
        self.stop.set();self.wake.set();self.worker.join(timeout=15)
        if self.worker.is_alive():print('Beast worker did not stop before shutdown.',flush=True)
        else:self.db.close()

class Handler(BaseHTTPRequestHandler):
    server_version='AntennaObservatory/1'
    def log_message(self,*args): pass
    def respond(self,status,value,kind='application/json',headers=None):
        body=json.dumps(value,allow_nan=False).encode() if kind=='application/json' else value.encode() if isinstance(value,str) else value
        extra=dict(headers or {});cache=extra.pop('Cache-Control','private, no-store')
        compressible=kind.startswith(('text/','application/json','application/javascript','image/svg+xml'))
        if len(body)>=1024 and compressible and 'gzip' in self.headers.get('Accept-Encoding','').lower():
            body=gzip.compress(body,compresslevel=6);extra['Content-Encoding']='gzip';extra['Vary']='Accept-Encoding'
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control',cache)
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for name, value in extra.items(): self.send_header(name, value)
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass
    def valid_host(self):
        try:
            host=urlparse('//'+self.headers.get('Host',''))
            if host.username or host.password or host.path or host.query or host.fragment: return False
            if host.hostname in ('127.0.0.1','localhost'): return True
            public=getattr(self.server,'public_origin',None)
            return bool(public and host.hostname==urlparse(public).hostname and host.port in (None,443))
        except ValueError: return False
    def valid_origin(self):
        try:
            origin=urlparse(self.headers.get('Origin',''));host=urlparse('//'+self.headers.get('Host',''))
            if origin.username or origin.password or origin.path or origin.query or origin.fragment: return False
            if origin.hostname in ('127.0.0.1','localhost'):
                return origin.scheme=='http' and origin.hostname==host.hostname and (origin.port or 80)==(host.port or 80)
            public=getattr(self.server,'public_origin',None)
            return bool(public and validated_public_origin(self.headers.get('Origin',''))==public and host.hostname==origin.hostname)
        except ValueError: return False
    def request_origin(self):
        host = self.headers.get('Host', '').lower()
        return ('http://' if urlparse('//'+host).hostname in ('127.0.0.1', 'localhost') else 'https://') + host
    def relay_authorized(self):
        expected=getattr(self.server,'relay_token','')
        supplied=self.headers.get('Authorization','')
        return bool(expected and supplied.startswith('Bearer ') and hmac.compare_digest(supplied[7:].encode(),expected.encode()))
    def local_loopback(self):
        try:return urlparse('//'+self.headers.get('Host','')).hostname in ('127.0.0.1','localhost') and ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:return False
    def relay_ingest(self):
        if not getattr(self.server,'relay_mode',False): return self.respond(404,{'error':'Unknown endpoint'})
        if not self.relay_authorized(): return self.respond(401,{'error':'Invalid relay credential'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=2_000_000 or self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Invalid telemetry request')
            body=json.loads(self.rfile.read(length))
            return self.respond(200,self.server.obs.ingest(body))
        except (ValueError,TypeError,UnicodeError) as e:return self.respond(400,{'error':str(e)})
    def relay_beast_ingest(self,digest):
        if not getattr(self.server,'relay_mode',False): return self.respond(404,{'error':'Unknown endpoint'})
        if not self.relay_authorized(): return self.respond(401,{'error':'Invalid relay credential'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BEAST_COMPRESSED or self.headers.get('Content-Type','').split(';')[0]!='application/zstd':
                raise ValueError('Invalid Beast batch request')
            return self.respond(200,self.server.obs.ingest_beast(digest,self.rfile.read(length)))
        except (ValueError,TypeError,UnicodeError) as e:return self.respond(400,{'error':str(e)})
        except RuntimeError as e:return self.respond(503,{'error':str(e)})
    def query_number(self,parsed,name,default,minimum,maximum):
        try:
            value=float(parse_qs(parsed.query).get(name,[str(default)])[0])
            if not math.isfinite(value): raise ValueError()
            return min(maximum,max(minimum,value))
        except (ValueError,TypeError): raise ValueError('Invalid '+name)
    def intelligence_response(self,callback,*args):
        with self.server.obs.lock:
            return self.respond(200,callback(self.server.obs.db,*args))
    def redirect(self, location, headers=None):
        return self.respond(303, '', 'text/html; charset=utf-8', dict(headers or {}, Location=location))
    def do_GET(self):
        if not self.valid_host(): return self.respond(403,{'error':'Unrecognized dashboard hostname'})
        parsed=urlparse(self.path); path=parsed.path
        if path=='/api/uplink':
            if getattr(self.server,'relay_mode',False) or not self.local_loopback(): return self.respond(404,{'error':'Unknown endpoint'})
            if not self.relay_authorized(): return self.respond(401,{'error':'Invalid relay credential'})
            return self.respond(200,{'snapshot':self.server.obs.snapshot(),'logs':self.server.obs.logs()})
        if self.request_origin().startswith('https:') and self.headers.get('X-Forwarded-Proto') == 'http':
            return self.redirect(self.server.public_origin + '/')
        if path == '/login':
            return self.redirect('/')
        if path=='/api/snapshot':
            snap=self.server.obs.snapshot()
            snap['settings_editable']=self.local_loopback()
            return self.respond(200,snap)
        if path=='/api/history':
            try:
                hours=float(parse_qs(parsed.query).get('hours',['1'])[0])
                if not math.isfinite(hours): raise ValueError()
                hours=min(168,max(1,hours))
            except ValueError: return self.respond(400,{'error':'Invalid time range'})
            return self.respond(200,self.server.obs.history(hours))
        try:
            if path=='/api/coverage': return self.intelligence_response(intelligence.coverage,self.query_number(parsed,'hours',24,1,168))
            if path=='/api/replay': return self.intelligence_response(intelligence.replay,self.query_number(parsed,'hours',6,1,168))
            if path=='/api/encounters': return self.intelligence_response(intelligence.encounters,int(self.query_number(parsed,'limit',250,1,1000)))
            if path=='/api/reports': return self.intelligence_response(intelligence.daily_reports,int(self.query_number(parsed,'days',7,1,7)))
            if path=='/api/lab':
                hours=self.query_number(parsed,'hours',24,1,168)
                with self.server.obs.lock:
                    snapshot=self.server.obs.snapshot()
                    return self.respond(200,intelligence.signal_lab(self.server.obs.db,snapshot,hours))
            if path=='/api/maintenance': return self.intelligence_response(intelligence.list_maintenance)
            if path=='/api/spectrum': return self.respond(200,intelligence.spectrum_status(self.server.obs.snapshot()))
        except ValueError as error: return self.respond(400,{'error':str(error)})
        if path=='/api/logs': return self.respond(200,{'lines':self.server.obs.logs()})
        if path=='/api/export':
            snap=self.server.obs.snapshot(); out=io.StringIO(); keys=['hex','flight','family','alt_baro','gs','track','lat','lon','rssi','messages','seen','distance_nm']
            w=csv.DictWriter(out,keys,extrasaction='ignore'); w.writeheader()
            for a in snap.get('aircraft',[]):
                row={k:a.get(k) for k in keys}
                for k,v in row.items():
                    if isinstance(v,str) and v.startswith(('=','+','-','@')): row[k]="'"+v
                w.writerow(row)
            return self.respond(200,out.getvalue(),'text/csv; charset=utf-8')
        if path=='/api/health': return self.respond(200,{'service':'antenna-observatory','collector_started':self.server.obs.started})
        if path.startswith('/api/'): return self.respond(404,{'error':'Unknown endpoint'})
        target=getattr(self.server,'static_files',{}).get(path if path!='/' else '/index.html')
        if target is None and '.' not in Path(path).name: target=getattr(self.server,'static_files',{}).get('/index.html')
        if target is None: return self.respond(404,{'error':'Page not built yet'})
        cache='public, max-age=31536000, immutable' if path.startswith('/_next/static/') else 'public, no-cache'
        kind=STATIC_CONTENT_TYPES.get(target.suffix.lower(),'application/octet-stream')
        return self.respond(200,target.read_bytes(),kind,{'Cache-Control':cache})
    def do_POST(self):
        if not self.valid_host(): return self.respond(403,{'error':'Unrecognized dashboard hostname'})
        path=urlparse(self.path).path
        if path=='/api/ingest': return self.relay_ingest()
        if not self.valid_origin(): return self.respond(403,{'error':'Matching dashboard origin required'})
        if self.request_origin().startswith('https:') and self.headers.get('X-Forwarded-Proto') == 'http':
            return self.respond(403, {'error': 'HTTPS required'})
        if path=='/api/maintenance':
            if not self.local_loopback():
                return self.respond(403,{'error':'Maintenance can only be changed from the local dashboard on the receiver host.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192 or self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Invalid maintenance request')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected a maintenance object')
                with self.server.obs.lock:
                    if body.get('action')=='delete':
                        result=intelligence.delete_maintenance(self.server.obs.db,body.get('id'))
                        message='Maintenance annotation deleted'
                    else:
                        result=intelligence.add_maintenance(self.server.obs.db,body)
                        message='Maintenance annotation added: '+result['title']
                self.server.obs.event('info',message)
                return self.respond(200,result)
            except (ValueError,TypeError,KeyError) as error: return self.respond(400,{'error':str(error)})
        if not self.local_loopback():
            return self.respond(403,{'error':'Station settings can only be changed from the local dashboard on the receiver host.'})
        if path!='/api/settings': return self.respond(404,{'error':'Unknown endpoint'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096: raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('Expected a settings object')
            name=str(body.get('station_name','')).strip()
            if not 1<=len(name)<=80: raise ValueError('Station name must be 1–80 characters')
            lat=body.get('latitude'); lon=body.get('longitude')
            if (lat is None)!=(lon is None): raise ValueError('Enter both coordinates')
            if lat is not None:
                lat=float(lat);lon=float(lon)
                if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180: raise ValueError('Invalid coordinates')
            values={'station_name':name,'latitude':lat,'longitude':lon}
            with self.server.obs.lock:
                write_private_json(CONFIG,values);self.server.obs.settings=values
            self.server.obs.event('info','Local station settings updated')
            return self.respond(200,values)
        except (ValueError,TypeError,KeyError) as e: return self.respond(400,{'error':str(e)})
    def do_PUT(self):
        if not self.valid_host(): return self.respond(403,{'error':'Unrecognized dashboard hostname'})
        match=re.fullmatch(r'/api/ingest/beast/([0-9a-f]{64})',urlparse(self.path).path)
        if not match:return self.respond(404,{'error':'Unknown endpoint'})
        return self.relay_beast_ingest(match.group(1))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8787);parser.add_argument('--relay',action='store_true');args=parser.parse_args()
    public_origin=validated_public_origin(read_json(REMOTE_CONFIG).get('public_origin'))
    relay_token=RELAY_TOKEN.read_text().strip()
    if len(relay_token)<32: raise ValueError('A valid relay token is required')
    obs=RelayObservatory() if args.relay else Observatory()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.obs=obs;server.public_origin=public_origin;server.relay_mode=args.relay;server.relay_token=relay_token;server.static_files=build_static_manifest(ROOT/'dist/client')
    if not args.relay: obs.start()
    print(f'Antenna Observatory: http://127.0.0.1:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if hasattr(obs,'close'):obs.close()
        elif hasattr(obs,'stop'):obs.stop.set()
        server.server_close()
if __name__=='__main__': main()
