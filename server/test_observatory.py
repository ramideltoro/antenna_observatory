"""Protocol, freshness, persistence and local API boundary regression checks."""
import http.client, json, math, tempfile, threading, time, unittest, urllib.request, urllib.error
from types import SimpleNamespace
from urllib.parse import urlencode
from pathlib import Path
from unittest.mock import patch
import observatory as app

TEST_ACCOUNT = app.AccountAuth.password_record("operator", "test-only-password")

class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_escaped_frames(self):
        payload=bytes.fromhex('8D40621D58C382D690C8AC2863A7')
        data=b'\x00\x1a\x02\x03\x04\x05\x1a'+payload
        encoded=b'\x1a3'+data.replace(b'\x1a',b'\x1a\x1a')
        for split in range(len(encoded)+1):
            parser=app.BeastParser()
            self.assertEqual(parser.feed(encoded[:split])+parser.feed(encoded[split:]),[(0x33,data)])
        parser=app.BeastParser(); result=[]
        for value in encoded*3: result+=parser.feed(bytes([value]))
        self.assertEqual(result,[(0x33,data)]*3)
    def test_corrupt_frame_resynchronizes(self):
        short=bytes(range(14)); valid=b'\x1a2'+short
        self.assertEqual(app.BeastParser().feed(b'noise\x1a3bad'+valid),[(0x32,short)])
    def test_protocol_families(self):
        self.assertEqual(app.classify_frame(0x33,bytes.fromhex('8D40621D58C382D690C8AC2863A7')),('ADS-B',17,11))
        for cf,family in enumerate(['ADS-B','ADS-B','TIS-B','TIS-B','Other','TIS-B','ADS-R','Other']):
            self.assertEqual(app.classify_frame(0x33,bytes([0x90|cf,0,0,0,19<<3])+bytes(9))[0],family)
        self.assertEqual(app.classify_frame(0x31,b'\x12\x34'),('Mode A/C',None,None))
    def test_geographic_range(self):
        dist,bearing=app.distance_bearing(0,0,0,1)
        self.assertAlmostEqual(dist,60.04,places=2);self.assertEqual(bearing,90)
        self.assertEqual(app.distance_bearing(28,-82,28,-82)[0],0)
    def test_remote_origin_configuration(self):
        self.assertIsNone(app.validated_public_origin(None))
        self.assertEqual(app.validated_public_origin('https://antenna.ramideltoro.com/'),'https://antenna.ramideltoro.com')
        for value in ('http://antenna.ramideltoro.com','https://example.com/path','https://name:secret@example.com','https://example.com:8888'):
            with self.assertRaises(ValueError): app.validated_public_origin(value)

class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.patch=patch.multiple(app,STATE=root,DATA=root/'readsb',DB=root/'history.sqlite',CONFIG=root/'settings.json')
        self.patch.start();self.obs=app.Observatory();self.obs.last_health=time.time()+1000
        self.obs.host={'cpu_percent':4.0};self.obs.beast_connected=True
        self.stamp=time.time(); self.write_data(self.stamp,100)
    def tearDown(self):
        self.obs.db.close();self.patch.stop();self.temp.cleanup()
    def write_data(self,stamp,messages):
        (app.DATA/'aircraft.json').write_text(json.dumps({'now':stamp,'messages':messages,'aircraft':[{'hex':'40621d','type':'adsb_icao','seen':1,'lat':28,'lon':-82,'seen_pos':1}]}))
        (app.DATA/'stats.json').write_text(json.dumps({'now':stamp,'gain_db':44.5,'total':{'start':stamp-100,'end':stamp,'messages_valid':messages},'last1min':{'start':stamp-60,'end':stamp,'position_count_total':120,'local':{'signal':-12,'noise':-30,'accepted':[90,10],'strong_signals':2}}}))
    def test_live_stale_and_counter_reset(self):
        self.obs.previous=(self.stamp-2,80); self.obs.collect();s=self.obs.snapshot()
        self.assertEqual(s['state'],'live');self.assertEqual(s['metrics']['message_rate'],10)
        self.assertEqual(s['metrics']['position_rate'],2);self.assertEqual(s['metrics']['corrected_percent'],10)
        self.assertEqual(s['aircraft'][0]['distance_nm'],None)
        self.write_data(self.stamp-100,110);self.obs.collect();s=self.obs.snapshot()
        self.assertEqual(s['state'],'stale');self.assertIsNone(s['metrics']['mean_signal'])
        self.assertIsNone(s['metrics']['message_rate']);self.assertFalse(s['aircraft'][0]['live'])
        self.write_data(time.time(),1);self.obs.collect()
        self.assertIsNone(self.obs.snapshot()['metrics']['message_rate'])
    def test_unavailable_stream_is_not_zero_history(self):
        self.obs.beast_connected=False;self.obs.collect()
        h=self.obs.history(1)
        self.assertIsNone(h['points'][-1]['signals']['ADS-B'])
        self.assertGreater(h['started'],0)
    def test_stale_history_is_a_gap(self):
        self.write_data(self.stamp-100,0);self.obs.collect()
        self.assertIsNone(self.obs.history(1)['points'][-1]['aircraft'])
    def test_api_rejects_foreign_host_and_bad_settings(self):
        self.obs.collect();server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);server.obs=self.obs
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        server.auth=app.AccountAuth(TEST_ACCOUNT)
        cookies={'Cookie':'antenna_local_session='+server.auth.create_session(base)}
        public_cookies={'Cookie':'__Host-antenna_session='+server.auth.create_session('https://antenna.ramideltoro.com')}
        try:
            requests=[('/api/snapshot',None,{'Host':'foreign.example'},403),('/api/history?hours=nan',None,{},400),('/api/settings',b'[]',{'Origin':base},400),('/api/settings',b'{"station_name":"Test"}',{'Origin':'https://example.com'},403),('/api/settings',b'{"station_name":"Test","latitude":99,"longitude":0}',{'Origin':base},400)]
            for path,data,headers,status in requests:
                with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers=dict(cookies,**headers)))
                self.assertEqual(error.exception.code,status)
            settings={'station_name':'Test antenna','latitude':28,'longitude':-82}
            with urllib.request.urlopen(urllib.request.Request(base+'/api/settings',data=json.dumps(settings).encode(),headers=dict(cookies,Origin=base))) as response: self.assertEqual(response.status,200)
            self.assertEqual(json.loads(app.CONFIG.read_text()),settings)
            self.obs.collect();self.assertEqual(self.obs.snapshot()['aircraft'][0]['distance_nm'],0)
            server.public_origin='https://antenna.ramideltoro.com'
            with urllib.request.urlopen(urllib.request.Request(base+'/api/health',headers=dict(public_cookies,Host='antenna.ramideltoro.com'))) as response: self.assertEqual(response.status,200)
            for origin in ('http://antenna.ramideltoro.com','https://foreign.example','http://127.0.0.1:1234'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(base+'/api/settings',data=json.dumps(settings).encode(),headers=dict(public_cookies,Host='antenna.ramideltoro.com',Origin=origin)))
                self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(base+'/api/settings',data=json.dumps(dict(settings,station_name='Anonymous change')).encode(),headers=dict(public_cookies,Host='antenna.ramideltoro.com',Origin=server.public_origin)))
            self.assertEqual(error.exception.code,403)
            self.assertEqual(json.loads(app.CONFIG.read_text()),settings)
            for host,editable in [('antenna.ramideltoro.com',False),('127.0.0.1:'+str(server.server_port),True)]:
                with urllib.request.urlopen(urllib.request.Request(base+'/api/snapshot',headers=dict(public_cookies if host=='antenna.ramideltoro.com' else cookies,Host=host))) as response:
                    self.assertEqual(json.load(response)['settings_editable'],editable)
        finally: server.shutdown();server.server_close();thread.join()

class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.patch=patch.multiple(app,STATE=root,DB=root/'history.sqlite')
        self.patch.start();self.obs=app.RelayObservatory()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.server.obs=self.obs;self.server.auth=app.AccountAuth(TEST_ACCOUNT);self.server.public_origin='https://antenna.ramideltoro.com'
        self.server.relay_mode=True;self.server.relay_token='t'*48
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.obs.db.close();self.patch.stop();self.temp.cleanup()
    def post(self,token='t'*48,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        payload=json.dumps(body or self.envelope())
        connection.request('POST','/api/ingest',payload,{'Host':'antenna.ramideltoro.com','Content-Type':'application/json','Authorization':'Bearer '+token})
        response=connection.getresponse();result=(response.status,json.loads(response.read()));connection.close();return result
    def envelope(self):
        return {'snapshot':{'now':time.time(),'source_time':time.time(),'state':'live','metrics':{'aircraft':1,'message_rate':2},'aircraft':[],'signals':[{'name':'ADS-B','rate':2}], 'events':[],'host':{'feed_connected':True},'hardware':{}},'logs':['decoder running']}
    def test_authenticated_ingest_snapshot_history_and_persistence(self):
        self.assertEqual(self.post(token='wrong')[0],401)
        self.assertEqual(self.post()[0],200)
        snap=self.obs.snapshot();self.assertEqual(snap['state'],'live');self.assertEqual(snap['metrics']['aircraft'],1)
        self.assertEqual(self.obs.logs(),['decoder running']);self.assertEqual(len(self.obs.history(1)['points']),1)
        self.assertTrue((app.STATE/'relay-latest.json').is_file())
    def test_stale_relay_marks_aircraft_inactive(self):
        envelope=self.envelope();envelope['snapshot']['aircraft']=[{'hex':'abc123','live':True}]
        self.assertEqual(self.post(body=envelope)[0],200);self.obs.received_at=time.time()-20
        snap=self.obs.snapshot();self.assertEqual(snap['state'],'stale');self.assertFalse(snap['aircraft'][0]['live'])



class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name)
        static=root/'dist/client'; static.mkdir(parents=True)
        (static/'index.html').write_text('Private dashboard')
        (static/'index.rsc').write_text('Private RSC payload')
        (static/'_next').mkdir(); (static/'_next/app.js').write_text('Private application')
        self.patch=patch.object(app,'ROOT',root); self.patch.start()
        self.auth=app.AccountAuth(TEST_ACCOUNT)
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.server.auth=self.auth; self.server.public_origin='https://antenna.ramideltoro.com'
        self.server.obs=SimpleNamespace(started=time.time(),snapshot=lambda: {'state':'live','aircraft':[]},history=lambda hours:{'points':[]},logs=lambda:['private log'])
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.host='antenna.ramideltoro.com'; self.origin='https://'+self.host
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.patch.stop();self.temp.cleanup()
    def request(self,path,method='GET',body=None,cookie=None,origin=None,host=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        headers={'Host':host or self.host}
        if cookie: headers['Cookie']=cookie
        if origin: headers['Origin']=origin
        if body is not None: headers['Content-Type']='application/x-www-form-urlencoded'
        connection.request(method,path,body=body,headers=headers)
        response=connection.getresponse(); result=(response.status,dict(response.getheaders()),response.read().decode())
        connection.close();return result
    def login(self,username='operator',password='test-only-password'):
        return self.request('/auth/login','POST',urlencode({'username':username,'password':password}),origin=self.origin)
    def test_anonymous_boundaries_and_fail_closed(self):
        for path in ('/api/snapshot','/api/history','/api/logs','/api/export','/api/health','/_next/app.js','/index.rsc'):
            self.assertEqual(self.request(path)[0],401,path)
        for path in ('/','/index.html','#ignored'):
            status,headers,body=self.request(path)
            self.assertEqual(status,303);self.assertEqual(headers['Location'],'/login');self.assertNotIn('Private dashboard',body)
        status,headers,body=self.request('/login')
        self.assertEqual(status,200);self.assertIn('name="password"',body);self.assertNotIn('test-only-password',body)
        self.assertIn('no-store',headers['Cache-Control'])
        self.assertEqual(self.request('/api/snapshot',host='127.0.0.1:'+str(self.server.server_port))[0],401)
        self.assertEqual(self.request('/api/snapshot',cookie='__Host-antenna_session=forged')[0],401)
        self.server.auth=None
        self.assertEqual(self.request('/api/snapshot')[0],401)
        self.assertEqual(self.request('/login')[0],503)
        with self.assertRaises(FileNotFoundError): app.AccountAuth.from_file(Path(self.temp.name)/'missing-account')
    def test_single_account_login_secure_cookie_and_logout(self):
        self.assertEqual(self.login(password='wrong')[0],401)
        self.assertEqual(self.login(username='someone-else')[0],401)
        status,headers,_=self.login()
        self.assertEqual(status,303);self.assertEqual(headers['Location'],'/')
        cookie=headers['Set-Cookie']; token=cookie.split(';')[0]
        for flag in ('__Host-antenna_session=','HttpOnly','Secure','SameSite=Strict','Path=/'): self.assertIn(flag,cookie)
        self.assertNotIn('Domain=',cookie)
        self.assertEqual(self.request('/',cookie=token)[2],'Private dashboard')
        for path in ('/api/snapshot','/api/history','/api/logs','/api/export','/api/health','/_next/app.js','/index.rsc'):
            self.assertEqual(self.request(path,cookie=token)[0],200,path)
        self.assertEqual(self.request('/login',cookie=token)[1]['Location'],'/')
        status,headers,_=self.request('/auth/logout','POST',cookie=token,origin=self.origin)
        self.assertEqual(status,303);self.assertIn('Max-Age=0',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/snapshot',cookie=token)[0],401)
    def test_origin_checks_expiry_and_public_settings(self):
        body=urlencode({'username':'operator','password':'test-only-password'})
        for origin in (None,'https://foreign.example','http://antenna.ramideltoro.com'):
            self.assertEqual(self.request('/auth/login','POST',body,origin=origin)[0],403)
        status,headers,_=self.login(); cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(status,303)
        self.assertEqual(self.request('/auth/logout','POST',cookie=cookie,origin='https://foreign.example')[0],403)
        self.assertEqual(self.request('/api/settings','POST','x=1',cookie=cookie,origin=self.origin)[0],403)
        self.assertEqual(self.request('/api/snapshot',cookie=cookie,host='localhost:'+str(self.server.server_port))[0],401)
        with patch.object(app.time,'time',return_value=time.time()+app.AccountAuth.session_seconds+1):
            self.assertEqual(self.request('/api/snapshot',cookie=cookie)[0],401)
    def test_rate_limiting_and_local_cookie(self):
        for _ in range(self.auth.attempt_limit): self.assertEqual(self.login(password='wrong')[0],401)
        status,headers,_=self.login()
        self.assertEqual(status,429);self.assertEqual(headers['Retry-After'],'300')
        with patch.object(app.time,'time',return_value=time.time()+self.auth.attempt_window+1):
            self.assertEqual(self.login()[0],303)
        local_host='127.0.0.1:'+str(self.server.server_port); origin='http://'+local_host
        status,headers,_=self.request('/auth/login','POST',urlencode({'username':'operator','password':'test-only-password'}),origin=origin,host=local_host)
        self.assertEqual(status,303);cookie=headers['Set-Cookie']
        self.assertIn('antenna_local_session=',cookie);self.assertNotIn('Secure',cookie)
        self.assertEqual(self.request('/api/snapshot',cookie=cookie.split(';')[0],host=local_host)[0],200)

if __name__=='__main__': unittest.main()
