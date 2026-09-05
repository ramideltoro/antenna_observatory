#!/usr/bin/env python3
"""Antenna Observatory collector, authenticated relay, and website server."""
import argparse, collections, csv, gzip, hashlib, hmac, html, io, ipaddress, json, math, mimetypes, os, re, secrets, socket, sqlite3, subprocess, threading, time
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get('ANTENNA_STATE_DIR', Path.home() / 'Library/Application Support/AntennaObservatory/state'))
DATA = STATE / 'readsb'
CONFIG = STATE / 'settings.json'
REMOTE_CONFIG = STATE / 'remote-access.json'
AUTH_CONFIG = STATE / 'account.json'
DB = STATE / 'observatory.sqlite'
LOG = Path.home() / 'Library/Logs/airplanes-live.log'
RELAY_TOKEN = STATE / 'relay-token'
LABEL = 'local.airplanes-live.readsb'
DEVICE_MODEL = os.environ.get('ANTENNA_DEVICE_MODEL', 'Nooelec NESDR SMArt v5')
DEVICE_SERIAL = os.environ.get('ANTENNA_DEVICE_SERIAL', 'configured')
FEEDER_ID = os.environ.get('ANTENNA_FEEDER_ID', 'configured')
FAMILIES = ['ADS-B', 'Mode S', 'TIS-B', 'ADS-R', 'Mode A/C', 'Other']
DF_NAMES = {0:'Short air-to-air surveillance',4:'Altitude reply',5:'Identity reply',11:'All-call reply',16:'Long air-to-air surveillance',17:'ADS-B extended squitter',18:'Extended squitter / rebroadcast',19:'Military extended squitter',20:'Comm-B altitude reply',21:'Comm-B identity reply',24:'Comm-D extended length'}
TYPE_NAMES = {**{n:'Identification' for n in range(1,5)},**{n:'Surface position' for n in range(5,9)},**{n:'Airborne position (barometric)' for n in range(9,19)},19:'Velocity',**{n:'Airborne position (GNSS)' for n in range(20,23)},28:'Aircraft status',29:'Target state',31:'Operational status'}

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

class AccountAuth:
    """One configured account. Opaque sessions are stored only on the server."""
    session_seconds = 12 * 3600
    attempt_window = 300
    attempt_limit = 5
    def __init__(self, account):
        if account.get('algorithm') != 'pbkdf2-sha256' or not isinstance(account.get('username'), str) or not account['username']:
            raise ValueError('A valid account configuration is required')
        self.username = account['username'].encode('utf-8')
        self.iterations = int(account['iterations'])
        self.salt = bytes.fromhex(account['salt'])
        self.password_hash = bytes.fromhex(account['password_hash'])
        if self.iterations < 600000 or len(self.salt) < 16 or len(self.password_hash) != 32:
            raise ValueError('Invalid password hash configuration')
        self.lock = threading.RLock()
        self.sessions = {}
        self.attempts = {}
        self.global_attempts = collections.deque()
    @classmethod
    def from_file(cls, path):
        # No anonymous fallback when configuration is absent or corrupt.
        return cls(json.loads(path.read_text()))
    @staticmethod
    def password_record(username, password):
        salt = secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
        return {'username': username, 'algorithm': 'pbkdf2-sha256', 'iterations': 600000,
                'salt': salt.hex(), 'password_hash': digest.hex()}
    def create_session(self, origin):
        with self.lock:
            now = time.time()
            self.sessions = {key: value for key, value in self.sessions.items() if value[0] > now}
            if len(self.sessions) >= 64:
                self.sessions.pop(min(self.sessions, key=lambda key: self.sessions[key][0]))
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (now + self.session_seconds, origin)
            return token
    def valid_session(self, token, origin):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token): return False
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            expiry, session_origin = self.sessions.get(key, (0, None))
            if expiry <= time.time():
                self.sessions.pop(key, None)
                return False
            return session_origin == origin
    def revoke(self, token):
        with self.lock: self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
    def login(self, username, password, client, origin):
        with self.lock:
            now = time.time()
            self.attempts = {key: [stamp for stamp in stamps if stamp > now - self.attempt_window]
                             for key, stamps in self.attempts.items() if stamps and stamps[-1] > now - self.attempt_window}
            while self.global_attempts and self.global_attempts[0] <= now - self.attempt_window:
                self.global_attempts.popleft()
            attempts = self.attempts.setdefault(client, [])
            if len(attempts) >= self.attempt_limit or len(self.global_attempts) >= 60:
                return 429, None
            attempts.append(now); self.global_attempts.append(now)
            if not isinstance(username, str) or not isinstance(password, str) or len(username) > 100 or len(password) > 1024:
                return 401, None
            candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), self.salt, self.iterations)
            password_ok = hmac.compare_digest(candidate, self.password_hash)
            user_ok = hmac.compare_digest(username.encode('utf-8'), self.username)
            if not (password_ok and user_ok): return 401, None
            self.attempts.pop(client, None)
            return 200, self.create_session(origin)

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

class Observatory:
    def __init__(self):
        STATE.mkdir(parents=True,exist_ok=True); DATA.mkdir(exist_ok=True)
        self.lock=threading.RLock(); self.stop=threading.Event(); self.started=time.time()
        self.frames=collections.deque(maxlen=250000); self.recent=collections.deque(maxlen=100)
        self.totals=collections.Counter(); self.df=collections.Counter(); self.tc=collections.Counter()
        self.df_family=collections.Counter()
        self.events=collections.deque(maxlen=250); self.snap={}; self.host={}; self.beast_connected=False
        self.feed_connected=None; self.previous=None; self.last_persist=0; self.last_health=0
        self.settings=read_json(CONFIG, {'station_name':'Rami’s receiver','latitude':None,'longitude':None})
        self.db=sqlite3.connect(DB,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_ts ON events(ts)')
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
                with socket.create_connection(('127.0.0.1',30905),timeout=3) as sock:
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
        with self.lock:
            previous_pid=self.host.get('pid')
            if previous_pid and pid and previous_pid!=pid:
                self.event('warning',f'Decoder process restarted (PID {previous_pid} → {pid}); TCP feed '+('connected' if connected else 'reconnecting'))
            if self.feed_connected is not None and connected!=self.feed_connected: self.event('success' if connected else 'warning','Airplanes.live TCP connection restored' if connected else 'Airplanes.live TCP connection unavailable')
            self.feed_connected=connected
            self.host={'pid':pid,'state':state_match.group(1) if state_match else 'not loaded','cpu_percent':cpu,'memory_mb':memory,'feed_connected':connected,'connections':established,'checked_at':time.time()}
    def collect_loop(self):
        while not self.stop.is_set():
            try: self.collect()
            except Exception as exc: print('Collector error:',type(exc).__name__,str(exc),flush=True)
            self.stop.wait(1)
    def collect(self):
        now=time.time()
        if now-self.last_health>=10: self.inspect_host(); self.last_health=now
        raw=read_json(DATA/'aircraft.json'); stats=read_json(DATA/'stats.json'); receiver=read_json(DATA/'receiver.json')
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
            self.snap={'now':now,'state':state,'source_time':timestamp,'age_seconds':age,'stats_age_seconds':now-stats.get('now',0) if stats.get('now') else None,
              'collector_started':self.started,'decoder_started':total.get('start'),'settings':settings,'metrics':metrics,'aircraft':aircraft,'signals':signals,
              'formats':[{'df':k,'name':DF_NAMES.get(k,'Other format'),'count':v,'last60':recent_df[k], 'families':{f:self.df_family[(k,f)] for f in FAMILIES}, 'last60_by_family':{f:recent_df_family[(k,f)] for f in FAMILIES}} for k,v in sorted(self.df.items())],
              'type_codes':[{'code':k,'name':TYPE_NAMES.get(k,'Reserved / other'),'count':v} for k,v in sorted(self.tc.items())],
              'recent_frames':list(self.recent),'events':list(reversed(self.events))[:100], 'host':self.host,'beast_connected':self.beast_connected,
              'receiver':receiver,'stats':stats,'raw_aircraft':raw,'hardware':{'model':DEVICE_MODEL,'serial':DEVICE_SERIAL,'tuner':'Rafael Micro R820T','frequency_mhz':1090,'sample_rate_msps':2.4,'feeder_id':FEEDER_ID,'mlat_configured':False,'modeac_enabled':True}}
            if now-self.last_persist>=10:
                sample=dict(metrics,ts=now,signals={s['name']:s['rate'] for s in signals},state=state)
                self.db.execute('INSERT OR REPLACE INTO samples VALUES (?,?)',(now,json.dumps(sample,allow_nan=False)))
                self.db.execute('DELETE FROM samples WHERE ts < ?',(now-7*86400,)); self.db.execute('DELETE FROM events WHERE ts < ?',(now-7*86400,)); self.db.commit(); self.last_persist=now
    def snapshot(self):
        with self.lock:
            snap=self.snap.copy()
            if time.time()-snap.get('now',0)>10:
                snap['state']='stale'
            if snap.get('source_time'): snap['age_seconds']=max(0,time.time()-snap['source_time'])
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
        try:
            with LOG.open('rb') as f:
                f.seek(0,2); f.seek(max(0,f.tell()-32768)); data=f.read().decode('utf-8','replace')
            return data.splitlines()[-150:]
        except OSError: return []

class RelayObservatory:
    """Stores telemetry pushed by the Mac while serving the public dashboard."""
    def __init__(self):
        STATE.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.started=time.time();self.last_persist=0
        self.latest=read_json(STATE/'relay-latest.json');self.log_lines=read_json(STATE/'relay-logs.json',[])
        self.received_at=self.latest.get('relay_received_at',0) if isinstance(self.latest,dict) else 0
        self.db=sqlite3.connect(DB,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_ts ON events(ts)');self.db.commit()
    def ingest(self,envelope):
        if not isinstance(envelope,dict) or not isinstance(envelope.get('snapshot'),dict): raise ValueError('Expected a telemetry snapshot')
        snap=envelope['snapshot']; required=('now','state','metrics','aircraft','signals','events','host','hardware')
        if any(key not in snap for key in required): raise ValueError('Incomplete telemetry snapshot')
        if not isinstance(snap['now'],(int,float)) or not math.isfinite(snap['now']): raise ValueError('Invalid telemetry timestamp')
        if not all(isinstance(snap.get(key),list) for key in ('aircraft','signals','events')) or not isinstance(snap.get('metrics'),dict): raise ValueError('Invalid telemetry collections')
        logs=envelope.get('logs',[])
        if not isinstance(logs,list) or any(not isinstance(line,str) for line in logs): raise ValueError('Invalid decoder logs')
        now=time.time();copy=json.loads(json.dumps(snap,allow_nan=False));copy['relay_received_at']=now
        safe_logs=[line[-2000:] for line in logs[-150:]]
        with self.lock:
            self.latest=copy;self.log_lines=safe_logs;self.received_at=now
            for path,value in ((STATE/'relay-latest.json',copy),(STATE/'relay-logs.json',safe_logs)):
                tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,allow_nan=False));tmp.replace(path)
            if now-self.last_persist>=10:
                metrics=dict(copy.get('metrics',{}));metrics.update(ts=now,signals={s.get('name'):s.get('rate') for s in copy.get('signals',[])},state=copy.get('state'))
                self.db.execute('INSERT OR REPLACE INTO samples VALUES (?,?)',(now,json.dumps(metrics,allow_nan=False)))
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
        return snap
    def history(self,hours): return Observatory.history(self,hours)
    def logs(self):
        with self.lock:return list(self.log_lines)

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
    def cookie_name(self):
        return '__Host-antenna_session' if self.request_origin().startswith('https:') else 'antenna_local_session'
    def session_token(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get('Cookie', ''))
        except CookieError: return ''
        value = cookie.get(self.cookie_name())
        return value.value if value else ''
    def authenticated(self):
        auth = getattr(self.server, 'auth', None)
        return bool(auth and auth.valid_session(self.session_token(), self.request_origin()))
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
    def session_cookie(self, token, clear=False):
        cookie = SimpleCookie(); name = self.cookie_name(); cookie[name] = token
        cookie[name]['path'] = '/'; cookie[name]['httponly'] = True; cookie[name]['samesite'] = 'Strict'
        cookie[name]['max-age'] = 0 if clear else AccountAuth.session_seconds
        if self.request_origin().startswith('https:'): cookie[name]['secure'] = True
        return cookie[name].OutputString()
    def redirect(self, location, headers=None):
        return self.respond(303, '', 'text/html; charset=utf-8', dict(headers or {}, Location=location))
    def login_page(self, status=200, message=''):
        template = Path(__file__).with_name('login.html').read_text()
        body = template.replace('{{message}}', html.escape(message)).replace('{{error_hidden}}', '' if message else 'hidden')
        return self.respond(status, body, 'text/html; charset=utf-8', {'Retry-After': '300'} if status == 429 else None)
    def login_request(self):
        auth = getattr(self.server, 'auth', None)
        if auth is None: return self.respond(503, {'error': 'Sign-in is unavailable'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096 or self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
                raise ValueError()
            fields = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True, max_num_fields=4)
            if set(fields) != {'username', 'password'} or any(len(values) != 1 for values in fields.values()): raise ValueError()
        except (ValueError, UnicodeError): return self.login_page(400, 'Enter your username and password.')
        client = self.client_address[0]
        if self.request_origin().startswith('https:'):
            try: client = str(ipaddress.ip_address(self.headers.get('CF-Connecting-IP', client)))
            except ValueError: pass
        status, token = auth.login(fields['username'][0], fields['password'][0], client, self.request_origin())
        if status == 429: return self.login_page(429, 'Too many attempts. Please try again in five minutes.')
        if status != 200: return self.login_page(401, 'Incorrect username or password.')
        # Replace any previous session presented by this browser.
        auth.revoke(self.session_token())
        return self.redirect('/', {'Set-Cookie': self.session_cookie(token)})
    def do_GET(self):
        if not self.valid_host(): return self.respond(403,{'error':'Unrecognized dashboard hostname'})
        parsed=urlparse(self.path); path=parsed.path
        if path=='/api/uplink':
            if getattr(self.server,'relay_mode',False) or not self.local_loopback(): return self.respond(404,{'error':'Unknown endpoint'})
            if not self.relay_authorized(): return self.respond(401,{'error':'Invalid relay credential'})
            return self.respond(200,{'snapshot':self.server.obs.snapshot(),'logs':self.server.obs.logs()})
        if self.request_origin().startswith('https:') and self.headers.get('X-Forwarded-Proto') == 'http':
            return self.redirect(self.server.public_origin + '/login')
        if path == '/login':
            if getattr(self.server, 'auth', None) is None: return self.respond(503, {'error': 'Sign-in is unavailable'})
            return self.redirect('/') if self.authenticated() else self.login_page()
        if not self.authenticated():
            if path.startswith('/api/') or path.startswith('/_next/') or path.endswith('.rsc'):
                return self.respond(401, {'error': 'Sign in required'})
            return self.redirect('/login')
        if path=='/api/snapshot':
            snap=self.server.obs.snapshot()
            snap['settings_editable']=urlparse('//'+self.headers.get('Host','')).hostname in ('127.0.0.1','localhost')
            return self.respond(200,snap)
        if path=='/api/history':
            try:
                hours=float(parse_qs(parsed.query).get('hours',['1'])[0])
                if not math.isfinite(hours): raise ValueError()
                hours=min(168,max(1,hours))
            except ValueError: return self.respond(400,{'error':'Invalid time range'})
            return self.respond(200,self.server.obs.history(hours))
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
        public=(ROOT/'dist/client').resolve(); relative=path.lstrip('/') or 'index.html'; target=(public/relative).resolve()
        if not target.is_relative_to(public): return self.respond(403,{'error':'Invalid path'})
        if target.is_dir(): target=target/'index.html'
        if not target.is_file() and '.' not in Path(relative).name: target=public/'index.html'
        if not target.is_file(): return self.respond(404,{'error':'Page not built yet'})
        cache='private, max-age=31536000, immutable' if path.startswith('/_next/static/') else 'private, no-cache'
        return self.respond(200,target.read_bytes(),mimetypes.guess_type(str(target))[0] or 'application/octet-stream',{'Cache-Control':cache})
    def do_POST(self):
        if not self.valid_host(): return self.respond(403,{'error':'Unrecognized dashboard hostname'})
        if urlparse(self.path).path=='/api/ingest': return self.relay_ingest()
        if not self.valid_origin(): return self.respond(403,{'error':'Matching dashboard origin required'})
        if self.request_origin().startswith('https:') and self.headers.get('X-Forwarded-Proto') == 'http':
            return self.respond(403, {'error': 'HTTPS required'})
        if urlparse(self.path).path == '/auth/login': return self.login_request()
        if not self.authenticated(): return self.respond(401, {'error': 'Sign in required'})
        if urlparse(self.path).path == '/auth/logout':
            self.server.auth.revoke(self.session_token())
            return self.redirect('/login', {'Set-Cookie': self.session_cookie('', clear=True)})
        if urlparse('//'+self.headers.get('Host','')).hostname not in ('127.0.0.1','localhost'):
            return self.respond(403,{'error':'Station settings can only be changed from the local dashboard on this Mac.'})
        if urlparse(self.path).path!='/api/settings': return self.respond(404,{'error':'Unknown endpoint'})
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
                tmp=CONFIG.with_suffix('.tmp');tmp.write_text(json.dumps(values));tmp.replace(CONFIG);self.server.obs.settings=values
            self.server.obs.event('info','Local station settings updated')
            return self.respond(200,values)
        except (ValueError,TypeError,KeyError) as e: return self.respond(400,{'error':str(e)})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8787);parser.add_argument('--relay',action='store_true');args=parser.parse_args()
    public_origin=validated_public_origin(read_json(REMOTE_CONFIG).get('public_origin'))
    auth=AccountAuth.from_file(AUTH_CONFIG)
    relay_token=RELAY_TOKEN.read_text().strip()
    if len(relay_token)<32: raise ValueError('A valid relay token is required')
    obs=RelayObservatory() if args.relay else Observatory()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.obs=obs;server.public_origin=public_origin;server.auth=auth;server.relay_mode=args.relay;server.relay_token=relay_token
    if not args.relay: obs.start()
    print(f'Antenna Observatory: http://127.0.0.1:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if hasattr(obs,'stop'):obs.stop.set()
        server.server_close()
if __name__=='__main__': main()
