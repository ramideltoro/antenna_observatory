"""Regression checks for persisted receiver intelligence and derived metrics."""

import json
import sqlite3
import time
import unittest

import intelligence


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE samples (ts REAL PRIMARY KEY, payload TEXT NOT NULL)')
        intelligence.initialize(self.db)
        self.now = time.time()

    def tearDown(self):
        self.db.close()

    def snapshot(self, now=None, distance=42, bearing=90):
        return {
            'state': 'live',
            'beast_connected': True,
            'host': {'feed_connected': True},
            'metrics': {
                'message_rate': 12,
                'mean_signal': -18,
                'noise': -34,
                'signal_above_noise': 16,
                'samples_lost': 0,
                'strong_percent': 2,
            },
            'recent_frames': [{'rssi': -12}, {'rssi': -24}],
            'aircraft': [{
                'hex': 'abc123', 'flight': 'TEST1', 'family': 'ADS-B', 'type': 'adsb_icao',
                'live': True, 'seen_pos': 1, 'lat': 28.1, 'lon': -82.1,
                'alt_baro': 12000, 'gs': 240, 'track': 180,
                'distance_nm': distance, 'bearing': bearing, 'rssi': -14,
            }],
            'now': now or self.now,
        }

    def test_tracks_encounters_coverage_and_replay(self):
        intelligence.persist_snapshot(self.db, self.now, self.snapshot())
        intelligence.persist_snapshot(self.db, self.now + 10, self.snapshot(distance=55, bearing=95))
        encounter = intelligence.encounters(self.db)['encounters'][0]
        self.assertEqual(encounter['hex'], 'abc123')
        self.assertEqual(encounter['sightings'], 1)
        self.assertEqual(encounter['observations'], 2)
        self.assertEqual(encounter['max_distance'], 55)
        coverage = intelligence.coverage(self.db, 1)['bands']['all']
        self.assertEqual(coverage['positions'], 2)
        self.assertEqual(coverage['aircraft'], 1)
        self.assertEqual(coverage['max_range'], 55)
        replay = intelligence.replay(self.db, 1)
        self.assertEqual(replay['bucket_seconds'], 10)
        self.assertGreaterEqual(len(replay['points']), 1)

    def test_daily_lab_health_and_alerts(self):
        for offset, rate in ((-20, 10), (-10, 14), (0, 12)):
            sample = {'state': 'live', 'message_rate': rate, 'mean_signal': -18, 'noise': -34, 'aircraft': 2}
            self.db.execute('INSERT INTO samples VALUES (?,?)', (self.now + offset, json.dumps(sample)))
        intelligence.persist_snapshot(self.db, self.now, self.snapshot())
        report = intelligence.daily_reports(self.db)['reports'][-1]
        self.assertEqual(report['availability_percent'], 100)
        self.assertEqual(report['unique_aircraft'], 1)
        lab = intelligence.signal_lab(self.db, self.snapshot(), 1)
        self.assertEqual(lab['frames_analyzed'], 2)
        self.assertEqual(lab['positions_analyzed'], 1)
        enriched = intelligence.enrich_snapshot(self.db, self.snapshot())
        self.assertGreaterEqual(enriched['health_score']['score'], 90)
        self.assertEqual(enriched['smart_alerts'], [])
        failing = self.snapshot()
        failing['state'] = 'stale'; failing['beast_connected'] = False; failing['host']['feed_connected'] = False
        enriched = intelligence.enrich_snapshot(self.db, failing)
        self.assertLess(enriched['health_score']['score'], 55)
        self.assertEqual({a['code'] for a in enriched['smart_alerts']}, {'telemetry-stale', 'beast-offline', 'feed-offline'})
        stale_only = self.snapshot()
        stale_only['state'] = 'stale'
        self.assertLess(intelligence.enrich_snapshot(self.db, stale_only)['health_score']['score'], 55)

    def test_maintenance_validation_and_spectrum_safety(self):
        entry = intelligence.add_maintenance(self.db, {'title': 'Raised antenna', 'details': 'Moved to window', 'category': 'antenna'})
        self.assertEqual(intelligence.list_maintenance(self.db)['entries'][0]['title'], 'Raised antenna')
        self.assertEqual(intelligence.delete_maintenance(self.db, entry['id'])['deleted'], entry['id'])
        with self.assertRaises(ValueError): intelligence.add_maintenance(self.db, {'title': '', 'category': 'note'})
        status = intelligence.spectrum_status({})
        self.assertFalse(status['available'])
        self.assertIn('second SDR', status['reason'])


if __name__ == '__main__':
    unittest.main()
