"""Protocol, freshness, persistence, and public API boundary checks."""

import gzip, http.client, json, math, stat, tempfile, threading, time, unittest, urllib.error, urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import observatory as app


class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_escaped_frames(self):
        payload = bytes.fromhex('8D40621D58C382D690C8AC2863A7')
        data = b'\x00\x1a\x02\x03\x04\x05\x1a' + payload
        encoded = b'\x1a3' + data.replace(b'\x1a', b'\x1a\x1a')
        for split in range(len(encoded) + 1):
            parser = app.BeastParser()
            self.assertEqual(parser.feed(encoded[:split]) + parser.feed(encoded[split:]), [(0x33, data)])
        parser = app.BeastParser(); result = []
        for value in encoded * 3: result += parser.feed(bytes([value]))
        self.assertEqual(result, [(0x33, data)] * 3)

    def test_corrupt_frame_resynchronizes(self):
        short = bytes(range(14)); valid = b'\x1a2' + short
        self.assertEqual(app.BeastParser().feed(b'noise\x1a3bad' + valid), [(0x32, short)])

    def test_protocol_families(self):
        self.assertEqual(app.classify_frame(0x33, bytes.fromhex('8D40621D58C382D690C8AC2863A7')), ('ADS-B', 17, 11))
        families = ['ADS-B', 'ADS-B', 'TIS-B', 'TIS-B', 'Other', 'TIS-B', 'ADS-R', 'Other']
        for cf, family in enumerate(families):
            self.assertEqual(app.classify_frame(0x33, bytes([0x90 | cf, 0, 0, 0, 19 << 3]) + bytes(9))[0], family)
        self.assertEqual(app.classify_frame(0x31, b'\x12\x34'), ('Mode A/C', None, None))

    def test_geographic_range(self):
        distance, bearing = app.distance_bearing(0, 0, 0, 1)
        self.assertAlmostEqual(distance, 60.04, places=2); self.assertEqual(bearing, 90)
        self.assertEqual(app.distance_bearing(28, -82, 28, -82)[0], 0)

    def test_remote_origin_configuration(self):
        self.assertIsNone(app.validated_public_origin(None))
        self.assertEqual(app.validated_public_origin('https://antenna.ramideltoro.com/'), 'https://antenna.ramideltoro.com')
        invalid = ('http://antenna.ramideltoro.com', 'https://example.com/path', 'https://name:secret@example.com', 'https://example.com:8888')
        for value in invalid:
            with self.assertRaises(ValueError): app.validated_public_origin(value)


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.patch = patch.multiple(app, STATE=root, DATA=root / 'readsb', DB=root / 'history.sqlite', CONFIG=root / 'settings.json')
        self.patch.start(); self.obs = app.Observatory(); self.obs.last_health = time.time() + 1000
        self.obs.host = {'cpu_percent': 4.0}; self.obs.beast_connected = True
        self.stamp = time.time(); self.write_data(self.stamp, 100)

    def tearDown(self):
        self.obs.db.close(); self.patch.stop(); self.temp.cleanup()

    def write_data(self, stamp, messages):
        (app.DATA / 'aircraft.json').write_text(json.dumps({'now': stamp, 'messages': messages, 'aircraft': [{'hex': '40621d', 'type': 'adsb_icao', 'seen': 1, 'lat': 28, 'lon': -82, 'seen_pos': 1}]}))
        (app.DATA / 'stats.json').write_text(json.dumps({'now': stamp, 'gain_db': 44.5, 'total': {'start': stamp - 100, 'end': stamp, 'messages_valid': messages}, 'last1min': {'start': stamp - 60, 'end': stamp, 'position_count_total': 120, 'local': {'signal': -12, 'noise': -30, 'accepted': [90, 10], 'strong_signals': 2}}}))

    def test_live_stale_and_counter_reset(self):
        self.obs.previous = (self.stamp - 2, 80); self.obs.collect(); snapshot = self.obs.snapshot()
        self.assertEqual(snapshot['state'], 'live'); self.assertEqual(snapshot['metrics']['message_rate'], 10)
        self.assertEqual(snapshot['metrics']['position_rate'], 2); self.assertEqual(snapshot['metrics']['corrected_percent'], 10)
        self.assertEqual(snapshot['aircraft'][0]['distance_nm'], None)
        self.write_data(self.stamp - 100, 110); self.obs.collect(); snapshot = self.obs.snapshot()
        self.assertEqual(snapshot['state'], 'stale'); self.assertIsNone(snapshot['metrics']['mean_signal'])
        self.assertIsNone(snapshot['metrics']['message_rate']); self.assertFalse(snapshot['aircraft'][0]['live'])
        self.write_data(time.time(), 1); self.obs.collect(); self.assertIsNone(self.obs.snapshot()['metrics']['message_rate'])

    def test_unavailable_stream_is_not_zero_history(self):
        self.obs.beast_connected = False; self.obs.collect()
        history = self.obs.history(1)
        self.assertIsNone(history['points'][-1]['signals']['ADS-B']); self.assertGreater(history['started'], 0)

    def test_stale_history_is_a_gap(self):
        self.write_data(self.stamp - 100, 0); self.obs.collect()
        self.assertIsNone(self.obs.history(1)['points'][-1]['aircraft'])

    def test_api_rejects_foreign_host_and_remote_settings(self):
        self.obs.collect(); server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); server.obs = self.obs
        server.public_origin = 'https://antenna.ramideltoro.com'; server.relay_mode = False; server.relay_token = 't' * 48
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            requests = [
                ('/api/snapshot', None, {'Host': 'foreign.example'}, 403),
                ('/api/history?hours=nan', None, {}, 400),
                ('/api/settings', b'[]', {'Origin': base}, 400),
                ('/api/settings', b'{"station_name":"Test"}', {'Origin': 'https://example.com'}, 403),
                ('/api/settings', b'{"station_name":"Test","latitude":99,"longitude":0}', {'Origin': base}, 400),
            ]
            for path, data, headers, status in requests:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers))
                self.assertEqual(error.exception.code, status)
            settings = {'station_name': 'Test antenna', 'latitude': 28, 'longitude': -82}
            with urllib.request.urlopen(urllib.request.Request(base + '/api/settings', data=json.dumps(settings).encode(), headers={'Origin': base})) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(app.CONFIG.read_text()), settings); self.assertEqual(stat.S_IMODE(app.CONFIG.stat().st_mode), 0o600)
            server.public_origin = 'https://antenna.ramideltoro.com'
            with urllib.request.urlopen(urllib.request.Request(base + '/api/health', headers={'Host': 'antenna.ramideltoro.com'})) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(base + '/api/settings', data=json.dumps(settings).encode(), headers={'Host': 'antenna.ramideltoro.com', 'Origin': server.public_origin}))
            self.assertEqual(error.exception.code, 403)
            for host, editable in [('antenna.ramideltoro.com', False), ('127.0.0.1:' + str(server.server_port), True)]:
                with urllib.request.urlopen(urllib.request.Request(base + '/api/snapshot', headers={'Host': host})) as response:
                    self.assertEqual(json.load(response)['settings_editable'], editable)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.patch = patch.multiple(app, STATE=root, DB=root / 'history.sqlite')
        self.patch.start(); self.obs = app.RelayObservatory()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server.obs = self.obs; self.server.public_origin = 'https://antenna.ramideltoro.com'
        self.server.relay_mode = True; self.server.relay_token = 't' * 48
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.obs.db.close(); self.patch.stop(); self.temp.cleanup()

    def envelope(self):
        return {'snapshot': {'now': time.time(), 'source_time': time.time(), 'state': 'live', 'metrics': {'aircraft': 1, 'message_rate': 2}, 'aircraft': [], 'signals': [{'name': 'ADS-B', 'rate': 2}], 'events': [], 'host': {'feed_connected': True}, 'hardware': {}}, 'logs': ['decoder running']}

    def post(self, token='t' * 48, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        payload = json.dumps(body or self.envelope())
        connection.request('POST', '/api/ingest', payload, {'Host': 'antenna.ramideltoro.com', 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        response = connection.getresponse(); result = (response.status, json.loads(response.read())); connection.close(); return result

    def test_token_protected_ingest_snapshot_history_and_persistence(self):
        self.assertEqual(self.post(token='wrong')[0], 401); self.assertEqual(self.post()[0], 200)
        snapshot = self.obs.snapshot(); self.assertEqual(snapshot['state'], 'live'); self.assertEqual(snapshot['metrics']['aircraft'], 1)
        self.assertEqual(self.obs.logs(), ['decoder running']); self.assertEqual(len(self.obs.history(1)['points']), 1)
        self.assertTrue((app.STATE / 'relay-latest.json').is_file())

    def test_stale_relay_marks_aircraft_inactive(self):
        envelope = self.envelope(); envelope['snapshot']['aircraft'] = [{'hex': 'abc123', 'live': True}]
        self.assertEqual(self.post(body=envelope)[0], 200); self.obs.received_at = time.time() - 20
        snapshot = self.obs.snapshot(); self.assertEqual(snapshot['state'], 'stale'); self.assertFalse(snapshot['aircraft'][0]['live'])


class PublicAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        static = root / 'dist/client'; static.mkdir(parents=True)
        (static / 'index.html').write_text('Public dashboard')
        (static / 'index.rsc').write_text('Public RSC payload')
        (static / '_next').mkdir(); (static / '_next/app.js').write_text('Public application')
        (static / '_next/static/chunks').mkdir(parents=True); (static / '_next/static/chunks/app-hash.js').write_text('const publicApplication=true;' * 200)
        self.patch = patch.multiple(app, ROOT=root, CONFIG=root / 'settings.json'); self.patch.start()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server.public_origin = 'https://antenna.ramideltoro.com'; self.server.relay_mode = True; self.server.relay_token = 't' * 48
        self.server.obs = SimpleNamespace(started=time.time(), snapshot=lambda: {'state': 'live', 'aircraft': []}, history=lambda hours: {'points': []}, logs=lambda: ['public log'], lock=threading.RLock(), settings={}, event=lambda *_: None)
        self.server.static_files = app.build_static_manifest(static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.host = 'antenna.ramideltoro.com'; self.origin = 'https://' + self.host

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.patch.stop(); self.temp.cleanup()

    def request(self, path, method='GET', body=None, origin=None, host=None, content_type='application/json'):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Host': host or self.host}
        if origin: headers['Origin'] = origin
        if body is not None: headers['Content-Type'] = content_type
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse(); result = (response.status, dict(response.getheaders()), response.read().decode())
        connection.close(); return result

    def test_dashboard_and_read_apis_are_public(self):
        for path in ('/', '/api/snapshot', '/api/history', '/api/logs', '/api/export', '/api/health', '/_next/app.js', '/index.rsc'):
            self.assertEqual(self.request(path)[0], 200, path)
        self.assertEqual(self.request('/')[2], 'Public dashboard')
        status, headers, _ = self.request('/login')
        self.assertEqual(status, 303); self.assertEqual(headers['Location'], '/')
        status, _, body = self.request('/../../server/observatory.py')
        self.assertEqual(status, 404); self.assertNotIn('relay_authorized', body)

    def test_static_assets_are_compressed_and_publicly_cached(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request('GET', '/_next/static/chunks/app-hash.js', headers={'Host': self.host, 'Accept-Encoding': 'gzip'})
        response = connection.getresponse(); body = response.read(); headers = dict(response.getheaders()); connection.close()
        self.assertEqual(response.status, 200); self.assertEqual(headers['Content-Encoding'], 'gzip')
        self.assertEqual(headers['Vary'], 'Accept-Encoding'); self.assertIn('public', headers['Cache-Control']); self.assertIn('immutable', headers['Cache-Control'])
        self.assertIn(b'publicApplication', gzip.decompress(body))

    def test_writes_stay_local_and_origin_bound(self):
        settings = json.dumps({'station_name': 'Public station', 'latitude': 28, 'longitude': -82})
        self.assertEqual(self.request('/api/settings', 'POST', settings, self.origin)[0], 403)
        self.assertEqual(self.request('/api/settings', 'POST', settings, 'https://foreign.example')[0], 403)
        local_host = '127.0.0.1:' + str(self.server.server_port); local_origin = 'http://' + local_host
        self.assertEqual(self.request('/api/settings', 'POST', settings, local_origin, local_host)[0], 200)
        self.assertEqual(self.request('/auth/login', 'POST', '{}', local_origin, local_host)[0], 404)

    def test_host_and_relay_boundaries_remain_enforced(self):
        self.assertEqual(self.request('/api/snapshot', host='foreign.example')[0], 403)
        self.assertEqual(self.request('/api/ingest', 'POST', '{}', host=self.host)[0], 401)
        status, headers, _ = self.request('/', host=self.host)
        self.assertEqual(status, 200); self.assertIn('public', headers['Cache-Control'])


if __name__ == '__main__':
    unittest.main()
