"""Persistent receiver intelligence derived from trusted telemetry snapshots."""

import json
import math
import statistics
import time


RETENTION_SECONDS = 7 * 86400


def initialize(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS tracks (
        ts REAL NOT NULL, hex TEXT NOT NULL, flight TEXT, lat REAL NOT NULL,
        lon REAL NOT NULL, altitude REAL, speed REAL, heading REAL,
        distance_nm REAL, bearing REAL, rssi REAL, family TEXT,
        PRIMARY KEY (ts, hex))"""
    )
    db.execute('CREATE INDEX IF NOT EXISTS tracks_ts ON tracks(ts)')
    db.execute('CREATE INDEX IF NOT EXISTS tracks_hex_ts ON tracks(hex,ts)')
    db.execute(
        """CREATE TABLE IF NOT EXISTS encounters (
        hex TEXT PRIMARY KEY, first_seen REAL NOT NULL, last_seen REAL NOT NULL,
        last_session_start REAL NOT NULL, sightings INTEGER NOT NULL,
        observations INTEGER NOT NULL, flight TEXT, family TEXT, aircraft_type TEXT,
        squawk TEXT, emergency TEXT, category TEXT, max_distance REAL,
        closest_distance REAL, strongest_rssi REAL, max_altitude REAL,
        last_lat REAL, last_lon REAL)"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS maintenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, title TEXT NOT NULL,
        details TEXT NOT NULL, category TEXT NOT NULL)"""
    )
    db.execute('CREATE INDEX IF NOT EXISTS maintenance_ts ON maintenance(ts)')
    db.commit()


def _finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def _altitude(aircraft):
    value = aircraft.get('alt_baro')
    return _finite(value)


def _extreme(old, new, fn):
    values = [value for value in (old, new) if value is not None]
    return fn(values) if values else None


def persist_snapshot(db, now, snapshot):
    """Store one compact position per live aircraft and update encounter rollups."""
    aircraft = snapshot.get('aircraft', [])
    for item in aircraft:
        if not isinstance(item, dict) or not item.get('live'):
            continue
        hex_code = str(item.get('hex', '')).lower()
        if not (1 <= len(hex_code) <= 8 and all(c in '0123456789abcdef' for c in hex_code)):
            continue
        row = db.execute(
            """SELECT first_seen,last_seen,last_session_start,sightings,observations,
            max_distance,closest_distance,strongest_rssi,max_altitude
            FROM encounters WHERE hex=?""",
            (hex_code,),
        ).fetchone()
        distance = _finite(item.get('distance_nm'))
        rssi = _finite(item.get('rssi'))
        altitude = _altitude(item)
        if row:
            first_seen, last_seen, session_start, sightings, observations, max_distance, closest, strongest, max_altitude = row
            if now - last_seen > 900:
                sightings += 1
                session_start = now
            values = (
                now,
                session_start,
                sightings,
                observations + 1,
                str(item.get('flight', ''))[:16],
                str(item.get('family', ''))[:24],
                str(item.get('type', ''))[:40],
                str(item.get('squawk', ''))[:8],
                str(item.get('emergency', ''))[:32],
                str(item.get('category', ''))[:16],
                _extreme(max_distance, distance, max),
                _extreme(closest, distance, min),
                _extreme(strongest, rssi, max),
                _extreme(max_altitude, altitude, max),
                _finite(item.get('lat')),
                _finite(item.get('lon')),
                hex_code,
            )
            db.execute(
                """UPDATE encounters SET last_seen=?,last_session_start=?,sightings=?,
                observations=?,flight=?,family=?,aircraft_type=?,squawk=?,emergency=?,
                category=?,max_distance=?,closest_distance=?,strongest_rssi=?,
                max_altitude=?,last_lat=?,last_lon=? WHERE hex=?""",
                values,
            )
        else:
            db.execute(
                """INSERT INTO encounters VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    hex_code,
                    now,
                    now,
                    now,
                    1,
                    1,
                    str(item.get('flight', ''))[:16],
                    str(item.get('family', ''))[:24],
                    str(item.get('type', ''))[:40],
                    str(item.get('squawk', ''))[:8],
                    str(item.get('emergency', ''))[:32],
                    str(item.get('category', ''))[:16],
                    distance,
                    distance,
                    rssi,
                    altitude,
                    _finite(item.get('lat')),
                    _finite(item.get('lon')),
                ),
            )
        lat, lon = _finite(item.get('lat')), _finite(item.get('lon'))
        seen_pos = _finite(item.get('seen_pos', 999))
        if lat is not None and lon is not None and seen_pos is not None and seen_pos < 15:
            db.execute(
                """INSERT OR REPLACE INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    hex_code,
                    str(item.get('flight', ''))[:16],
                    lat,
                    lon,
                    altitude,
                    _finite(item.get('gs')),
                    _finite(item.get('track')),
                    distance,
                    _finite(item.get('bearing')),
                    rssi,
                    str(item.get('family', ''))[:24],
                ),
            )
    cutoff = now - RETENTION_SECONDS
    db.execute('DELETE FROM tracks WHERE ts < ?', (cutoff,))
    db.execute('DELETE FROM encounters WHERE last_seen < ?', (cutoff,))
    db.commit()


def metric_baselines(db, hours=6):
    rows = db.execute(
        'SELECT payload FROM samples WHERE ts >= ?', (time.time() - hours * 3600,)
    ).fetchall()
    values = {'message_rate': [], 'noise': [], 'mean_signal': []}
    for (payload,) in rows:
        try:
            sample = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if sample.get('state') != 'live':
            continue
        for key in values:
            value = _finite(sample.get(key))
            if value is not None:
                values[key].append(value)
    return {
        key: round(statistics.median(items), 2) if items else None
        for key, items in values.items()
    }


def health_score(metrics, state, beast_connected, feed_connected, baselines=None):
    """Score availability, activity, radio margin, and decoder quality from 0–100."""
    baselines = baselines or {}
    availability = (20 if state == 'live' else 0) + (10 if beast_connected else 0) + (10 if feed_connected else 0)
    margin = _finite(metrics.get('signal_above_noise'))
    radio = 12 if margin is None else max(0, min(25, (margin - 3) / 17 * 25))
    quality = 0
    losses = _finite(metrics.get('samples_lost'))
    quality += 10 if losses in (None, 0) else max(0, 10 - math.log10(losses + 1) * 4)
    strong = _finite(metrics.get('strong_percent'))
    quality += 10 if strong is None else max(0, min(10, 10 - max(0, strong - 3) * 0.8))
    rate = _finite(metrics.get('message_rate'))
    baseline = _finite(baselines.get('message_rate'))
    activity = 0
    if rate is not None and rate > 0:
        activity += 8
        activity += 7 if not baseline else max(0, min(7, 7 * rate / max(1, baseline * 0.65)))
    score = round(max(0, min(100, availability + radio + quality + activity)))
    if state != 'live':
        score = min(score, 49)
    status = 'Excellent' if score >= 90 else 'Healthy' if score >= 75 else 'Attention' if score >= 55 else 'Critical'
    reasons = []
    if state != 'live': reasons.append('Receiver telemetry is not current.')
    if not beast_connected: reasons.append('The local Beast signal stream is disconnected.')
    if not feed_connected: reasons.append('The airplanes.live TCP connection is unavailable.')
    if margin is not None and margin < 8: reasons.append('Signal margin is below 8 dB.')
    if losses not in (None, 0): reasons.append(f'{int(losses)} samples have been lost since decoder start.')
    if strong is not None and strong > 10: reasons.append('More than 10% of accepted messages are very strong.')
    if rate is not None and baseline and baseline > 4 and rate < baseline * 0.25: reasons.append('Message rate is below 25% of its six-hour median.')
    if not reasons: reasons.append('Receiver, local stream, and outbound feed are operating normally.')
    return {
        'score': score,
        'status': status,
        'components': {
            'availability': round(availability),
            'radio': round(radio),
            'quality': round(quality),
            'activity': round(activity),
        },
        'reasons': reasons,
        'baseline_message_rate': baseline,
    }


def smart_alerts(snapshot, baselines=None):
    baselines = baselines or {}
    metrics = snapshot.get('metrics', {})
    alerts = []

    def add(code, severity, title, message):
        alerts.append({'code': code, 'severity': severity, 'title': title, 'message': message})

    if snapshot.get('state') != 'live': add('telemetry-stale', 'critical', 'Telemetry is stale', 'The Mac has stopped delivering current receiver measurements.')
    if not snapshot.get('beast_connected'): add('beast-offline', 'critical', 'Signal stream disconnected', 'The observatory cannot read the local Beast frame stream.')
    if snapshot.get('host', {}).get('feed_connected') is False: add('feed-offline', 'critical', 'Airplanes.live feed disconnected', 'The decoder has no established TCP connection to port 30004.')
    losses = _finite(metrics.get('samples_lost'))
    if losses and losses > 0: add('sample-loss', 'warning', 'Samples lost', f'{int(losses)} tuner samples have been lost since the decoder started.')
    strong = _finite(metrics.get('strong_percent'))
    if strong is not None and strong > 10: add('overload', 'warning', 'Possible receiver overload', f'{strong:.1f}% of accepted messages are stronger than −3 dBFS.')
    noise = _finite(metrics.get('noise'))
    baseline_noise = _finite(baselines.get('noise'))
    if noise is not None and baseline_noise is not None and noise > baseline_noise + 6: add('noise-rise', 'warning', 'Noise floor increased', f'Noise is {noise - baseline_noise:.1f} dB above its six-hour median.')
    rate = _finite(metrics.get('message_rate'))
    baseline_rate = _finite(baselines.get('message_rate'))
    if rate is not None and baseline_rate and baseline_rate > 4 and rate < baseline_rate * 0.25: add('traffic-drop', 'warning', 'Reception activity dropped', f'Message rate is {rate:.1f}/s versus a {baseline_rate:.1f}/s six-hour median.')
    for aircraft in snapshot.get('aircraft', []):
        if not aircraft.get('live'): continue
        emergency = str(aircraft.get('emergency', '')).lower()
        squawk = str(aircraft.get('squawk', ''))
        if squawk in ('7500', '7600', '7700') or emergency not in ('', 'none', 'no emergency'):
            identity = str(aircraft.get('flight') or aircraft.get('hex', '')).upper()
            add('emergency-' + str(aircraft.get('hex', '')), 'critical', f'Emergency signal · {identity}', f'Squawk {squawk or "unknown"}; status {emergency or "reported"}.')
    return alerts


def enrich_snapshot(db, snapshot):
    baselines = metric_baselines(db)
    health = health_score(
        snapshot.get('metrics', {}),
        snapshot.get('state'),
        bool(snapshot.get('beast_connected')),
        snapshot.get('host', {}).get('feed_connected') is True,
        baselines,
    )
    snapshot['health_score'] = health
    snapshot['smart_alerts'] = smart_alerts(snapshot, baselines)
    return snapshot


def coverage(db, hours):
    cutoff = time.time() - hours * 3600
    rows = db.execute(
        'SELECT bearing,distance_nm,altitude,hex FROM tracks WHERE ts>=? AND bearing IS NOT NULL AND distance_nm IS NOT NULL',
        (cutoff,),
    ).fetchall()
    bands = {
        'all': rows,
        'low': [r for r in rows if r[2] is not None and r[2] < 10000],
        'mid': [r for r in rows if r[2] is not None and 10000 <= r[2] < 25000],
        'high': [r for r in rows if r[2] is not None and r[2] >= 25000],
    }
    result = {}
    for name, items in bands.items():
        bins = []
        for index in range(72):
            sector = [row[1] for row in items if int(row[0] // 5) % 72 == index]
            bins.append({'bearing': index * 5 + 2.5, 'max_range': round(max(sector), 1) if sector else 0, 'positions': len(sector)})
        distances = [row[1] for row in items]
        result[name] = {
            'bins': bins,
            'max_range': round(max(distances), 1) if distances else None,
            'median_range': round(statistics.median(distances), 1) if distances else None,
            'positions': len(items),
            'aircraft': len({row[3] for row in items}),
            'sectors_observed': sum(1 for item in bins if item['positions']),
        }
    return {'hours': hours, 'bands': result}


def replay(db, hours):
    cutoff = time.time() - hours * 3600
    bucket = 10 if hours <= 1 else 20 if hours <= 6 else 60 if hours <= 24 else 300
    rows = db.execute(
        """SELECT MIN(ts),hex,MAX(flight),AVG(lat),AVG(lon),AVG(altitude),AVG(speed),
        AVG(heading),AVG(distance_nm),AVG(bearing),AVG(rssi),MAX(family)
        FROM tracks WHERE ts>=? GROUP BY CAST(ts / ? AS INTEGER),hex
        ORDER BY MIN(ts) LIMIT 25000""",
        (cutoff, bucket),
    ).fetchall()
    keys = ('ts', 'hex', 'flight', 'lat', 'lon', 'altitude', 'speed', 'heading', 'distance_nm', 'bearing', 'rssi', 'family')
    return {'hours': hours, 'bucket_seconds': bucket, 'points': [dict(zip(keys, row)) for row in rows]}


def encounters(db, limit=250):
    rows = db.execute(
        """SELECT hex,first_seen,last_seen,sightings,observations,flight,family,
        aircraft_type,squawk,emergency,category,max_distance,closest_distance,
        strongest_rssi,max_altitude,last_lat,last_lon FROM encounters
        ORDER BY last_seen DESC LIMIT ?""",
        (min(1000, max(1, int(limit))),),
    ).fetchall()
    keys = ('hex', 'first_seen', 'last_seen', 'sightings', 'observations', 'flight', 'family', 'aircraft_type', 'squawk', 'emergency', 'category', 'max_distance', 'closest_distance', 'strongest_rssi', 'max_altitude', 'last_lat', 'last_lon')
    return {'encounters': [dict(zip(keys, row)) for row in rows], 'retention_days': 7}


def daily_reports(db, days=7):
    cutoff = time.time() - min(7, max(1, days)) * 86400
    sample_rows = db.execute('SELECT ts,payload FROM samples WHERE ts>=? ORDER BY ts', (cutoff,)).fetchall()
    track_rows = db.execute(
        """SELECT date(ts,'unixepoch','localtime'),COUNT(*),COUNT(DISTINCT hex),MAX(distance_nm)
        FROM tracks WHERE ts>=? GROUP BY date(ts,'unixepoch','localtime')""",
        (cutoff,),
    ).fetchall()
    tracks = {row[0]: row[1:] for row in track_rows}
    groups = {}
    for ts, payload in sample_rows:
        day = time.strftime('%Y-%m-%d', time.localtime(ts))
        try: sample = json.loads(payload)
        except (TypeError, ValueError): continue
        groups.setdefault(day, []).append(sample)
    reports = []
    for day in sorted(set(groups) | set(tracks)):
        samples = groups.get(day, [])
        rates = [_finite(s.get('message_rate')) for s in samples]
        rates = [v for v in rates if v is not None]
        signals = [_finite(s.get('mean_signal')) for s in samples]
        signals = [v for v in signals if v is not None]
        live = sum(s.get('state') == 'live' for s in samples)
        positions, unique, max_range = tracks.get(day, (0, 0, None))
        reports.append({
            'day': day,
            'samples': len(samples),
            'availability_percent': round(100 * live / len(samples), 1) if samples else None,
            'average_message_rate': round(statistics.mean(rates), 2) if rates else None,
            'peak_message_rate': round(max(rates), 2) if rates else None,
            'peak_aircraft': max((_finite(s.get('aircraft')) or 0 for s in samples), default=None),
            'average_signal': round(statistics.mean(signals), 2) if signals else None,
            'unique_aircraft': unique,
            'positions': positions,
            'max_range': round(max_range, 1) if max_range is not None else None,
        })
    return {'reports': reports, 'retention_days': 7}


def _histogram(values, edges):
    counts = [0] * (len(edges) - 1)
    for value in values:
        for index in range(len(edges) - 1):
            if edges[index] <= value < edges[index + 1] or index == len(edges) - 2 and value == edges[index + 1]:
                counts[index] += 1
                break
    return [{'from': edges[i], 'to': edges[i + 1], 'count': count} for i, count in enumerate(counts)]


def signal_lab(db, snapshot, hours):
    cutoff = time.time() - hours * 3600
    rows = db.execute('SELECT altitude,distance_nm,rssi FROM tracks WHERE ts>=?', (cutoff,)).fetchall()
    recent_rssi = [_finite(frame.get('rssi')) for frame in snapshot.get('recent_frames', [])]
    recent_rssi = [value for value in recent_rssi if value is not None]
    return {
        'hours': hours,
        'rssi': _histogram(recent_rssi, [-60, -50, -40, -30, -20, -15, -10, -6, -3, 0]),
        'altitude': _histogram([r[0] for r in rows if r[0] is not None], [0, 3000, 10000, 18000, 25000, 35000, 45000, 60000]),
        'range': _histogram([r[1] for r in rows if r[1] is not None], [0, 10, 25, 50, 75, 100, 150, 200, 300, 500]),
        'baselines': metric_baselines(db, hours),
        'frames_analyzed': len(recent_rssi),
        'positions_analyzed': len(rows),
    }


def list_maintenance(db):
    rows = db.execute('SELECT id,ts,title,details,category FROM maintenance ORDER BY ts DESC LIMIT 200').fetchall()
    return {'entries': [dict(zip(('id', 'ts', 'title', 'details', 'category'), row)) for row in rows]}


def sync_maintenance(db, entries):
    """Mirror locally authored maintenance entries into the hosted relay."""
    if not isinstance(entries, list) or len(entries) > 200:
        raise ValueError('Invalid maintenance collection')
    categories = ('installation', 'antenna', 'receiver', 'software', 'incident', 'note')
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Invalid maintenance entry')
        entry_id = int(entry.get('id'))
        ts = _finite(entry.get('ts'))
        title = str(entry.get('title', '')).strip()
        details = str(entry.get('details', '')).strip()
        category = str(entry.get('category', '')).strip().lower()
        if entry_id < 1 or ts is None or not 1 <= len(title) <= 100 or len(details) > 2000 or category not in categories:
            raise ValueError('Invalid maintenance entry')
        normalized.append((entry_id, ts, title, details, category))
    db.execute('DELETE FROM maintenance')
    db.executemany('INSERT INTO maintenance(id,ts,title,details,category) VALUES (?,?,?,?,?)', normalized)
    db.commit()


def add_maintenance(db, body):
    title = str(body.get('title', '')).strip()
    details = str(body.get('details', '')).strip()
    category = str(body.get('category', 'note')).strip().lower()
    if not 1 <= len(title) <= 100: raise ValueError('Title must be 1–100 characters')
    if len(details) > 2000: raise ValueError('Details must be 2,000 characters or fewer')
    if category not in ('installation', 'antenna', 'receiver', 'software', 'incident', 'note'): raise ValueError('Unknown maintenance category')
    ts = _finite(body.get('ts')) or time.time()
    if abs(ts - time.time()) > RETENTION_SECONDS * 52: raise ValueError('Maintenance date is outside the supported range')
    cursor = db.execute('INSERT INTO maintenance(ts,title,details,category) VALUES (?,?,?,?)', (ts, title, details, category))
    db.commit()
    return {'id': cursor.lastrowid, 'ts': ts, 'title': title, 'details': details, 'category': category}


def delete_maintenance(db, entry_id):
    cursor = db.execute('DELETE FROM maintenance WHERE id=?', (int(entry_id),))
    db.commit()
    if cursor.rowcount != 1: raise ValueError('Maintenance entry not found')
    return {'deleted': int(entry_id)}


def spectrum_status(snapshot):
    spectrum = snapshot.get('spectrum')
    if isinstance(spectrum, dict) and isinstance(spectrum.get('lines'), list):
        return spectrum
    return {
        'available': False,
        'configured': False,
        'reason': 'A second SDR is required to scan the band without interrupting the active 1090 MHz aircraft feed.',
        'lines': [],
        'center_mhz': 1090,
        'span_mhz': 4,
    }
