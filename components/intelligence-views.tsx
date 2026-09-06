'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode, SubmitEvent } from 'react';
import {
  Activity,
  AlertTriangle,
  BellRing,
  CalendarDays,
  CheckCircle2,
  Database,
  FlaskConical,
  Heart,
  Pause,
  Plane,
  Play,
  Plus,
  Radio,
  RotateCcw,
  Search,
  Trash2,
  Waves,
  Wrench,
} from 'lucide-react';
import type {
  CoverageBand,
  CoverageData,
  DailyReport,
  Encounter,
  HistogramBin,
  LabData,
  MaintenanceEntry,
  ReplayData,
  SmartAlert,
  Snapshot,
  SpectrumData,
  TrackPoint,
} from '@/lib/telemetry';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const COLORS: Record<string, string> = {
  'ADS-B': '#ffbb45',
  'Mode S': '#d8d0b8',
  'TIS-B': '#b9a5e6',
  'ADS-R': '#ef8d65',
  'Mode A/C': '#d5a2bd',
  Other: '#9c9b91',
};

const number = (value: unknown, digits = 0) =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('en-US', { maximumFractionDigits: digits })
    : '—';

async function apiFetch(path: string, options?: RequestInit) {
  return fetch(path, options);
}

function useFeature<T>(path: string, refresh = 30000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const response = await apiFetch(path, { signal: controller.signal });
        if (!response.ok)
          throw new Error('The analysis service is unavailable.');
        const value = (await response.json()) as T;
        if (alive) {
          setData(value);
          setError('');
        }
      } catch (reason) {
        if (alive && !controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : 'Could not load this view.',
          );
      } finally {
        if (alive && refresh) timer = setTimeout(load, refresh);
      }
    };
    void load();
    return () => {
      alive = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, refresh, revision]);
  return { data, error, reload: () => setRevision((value) => value + 1) };
}

function FeaturePanel({
  title,
  note,
  aside,
  children,
  className = '',
}: {
  title: string;
  note?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel intelligence-panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Loading({ error }: { error?: string }) {
  return (
    <div className={`feature-loading ${error ? 'error' : ''}`}>
      {error ? <AlertTriangle size={20} /> : <Activity size={20} />}
      {error || 'Building this view from receiver history…'}
    </div>
  );
}

function TimeRange({
  value,
  setValue,
}: {
  value: string;
  setValue: (value: string) => void;
}) {
  return (
    <div className="compact-choice" aria-label="Time range">
      {[
        ['1', '1h'],
        ['6', '6h'],
        ['24', '24h'],
        ['168', '7d'],
      ].map(([key, label]) => (
        <button
          key={key}
          type="button"
          className={value === key ? 'active' : ''}
          onClick={() => setValue(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note: string;
}) {
  return (
    <div className="feature-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function PolarChart({ band }: { band: CoverageBand }) {
  const max = Math.max(25, Math.ceil((band.max_range || 0) / 25) * 25);
  const points = band.bins
    .map((bin) => {
      const angle = (bin.bearing * Math.PI) / 180;
      const radius = (bin.max_range / max) * 154;
      return `${200 + Math.sin(angle) * radius},${200 - Math.cos(angle) * radius}`;
    })
    .join(' ');
  return (
    <div className="polar-wrap">
      <svg
        viewBox="0 0 400 400"
        aria-label={`Historical reception coverage to ${number(band.max_range, 1)} nautical miles`}
      >
        <defs>
          <radialGradient id="coverage-fill">
            <stop offset="0" stopColor="#ffbb45" stopOpacity=".42" />
            <stop offset="1" stopColor="#ff8f32" stopOpacity=".16" />
          </radialGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map((ratio) => (
          <g key={ratio}>
            <circle cx="200" cy="200" r={154 * ratio} className="polar-ring" />
            <text x="206" y={200 - 154 * ratio + 13} className="polar-label">
              {number(max * ratio)} nm
            </text>
          </g>
        ))}
        {[0, 45, 90, 135].map((degree) => {
          const angle = (degree * Math.PI) / 180;
          return (
            <line
              key={degree}
              x1={200 - Math.sin(angle) * 154}
              y1={200 - Math.cos(angle) * 154}
              x2={200 + Math.sin(angle) * 154}
              y2={200 + Math.cos(angle) * 154}
              className="polar-spoke"
            />
          );
        })}
        <text x="200" y="23" textAnchor="middle" className="polar-direction">
          N
        </text>
        <text x="377" y="205" textAnchor="middle" className="polar-direction">
          E
        </text>
        <text x="200" y="388" textAnchor="middle" className="polar-direction">
          S
        </text>
        <text x="23" y="205" textAnchor="middle" className="polar-direction">
          W
        </text>
        {band.positions > 0 && (
          <polygon
            points={points}
            fill="url(#coverage-fill)"
            className="coverage-outline"
          />
        )}
        <circle cx="200" cy="200" r="5" className="station-point" />
      </svg>
    </div>
  );
}

function CoverageView() {
  const [hours, setHours] = useState('24');
  const [altitude, setAltitude] = useState('all');
  const { data, error } = useFeature<CoverageData>(
    `/api/coverage?hours=${hours}`,
  );
  const band = data?.bands[altitude];
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Measured reception envelope</h2>
          <p>
            Maximum decoded range in 5° sectors, calculated from stored aircraft
            positions.
          </p>
        </div>
        <TimeRange value={hours} setValue={setHours} />
      </div>
      <div className="altitude-tabs" aria-label="Altitude band">
        {[
          ['all', 'All altitudes'],
          ['low', 'Below 10k ft'],
          ['mid', '10–25k ft'],
          ['high', 'Above 25k ft'],
        ].map(([key, label]) => (
          <button
            type="button"
            key={key}
            className={altitude === key ? 'active' : ''}
            onClick={() => setAltitude(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {!band ? (
        <Loading error={error} />
      ) : (
        <div className="coverage-layout">
          <FeaturePanel
            title="Polar coverage"
            note={`${number(band.sectors_observed)} of 72 directional sectors observed`}
          >
            <PolarChart band={band} />
          </FeaturePanel>
          <div className="feature-metrics-grid coverage-metrics">
            <Metric
              label="Farthest reception"
              value={`${number(band.max_range, 1)} nm`}
              note="Maximum positioned aircraft range"
            />
            <Metric
              label="Median range"
              value={`${number(band.median_range, 1)} nm`}
              note="Across stored position samples"
            />
            <Metric
              label="Unique aircraft"
              value={number(band.aircraft)}
              note="Aircraft represented in this band"
            />
            <Metric
              label="Position samples"
              value={number(band.positions)}
              note="Real observations used in the outline"
            />
            <FeaturePanel
              title="Directional consistency"
              note="Samples by compass quadrant"
              className="quadrant-panel"
            >
              <div className="quadrant-bars">
                {['North', 'East', 'South', 'West'].map((label, index) => {
                  const start = index * 18;
                  const count = band.bins
                    .slice(start, start + 18)
                    .reduce((sum, bin) => sum + bin.positions, 0);
                  const maxCount = Math.max(
                    1,
                    ...[0, 1, 2, 3].map((q) =>
                      band.bins
                        .slice(q * 18, q * 18 + 18)
                        .reduce((sum, bin) => sum + bin.positions, 0),
                    ),
                  );
                  return (
                    <div key={label}>
                      <span>{label}</span>
                      <i>
                        <b style={{ width: `${(count / maxCount) * 100}%` }} />
                      </i>
                      <strong>{number(count)}</strong>
                    </div>
                  );
                })}
              </div>
            </FeaturePanel>
          </div>
        </div>
      )}
    </>
  );
}

function ReplayPlot({
  points,
  playhead,
}: {
  points: TrackPoint[];
  playhead: number;
}) {
  const selected = points.filter((point) => point.ts <= playhead);
  const grouped = new Map<string, TrackPoint[]>();
  selected.forEach((point) => {
    const list = grouped.get(point.hex) || [];
    list.push(point);
    grouped.set(point.hex, list);
  });
  const active = [...grouped.values()]
    .filter((list) => playhead - list[list.length - 1].ts < 180)
    .sort((a, b) => b[b.length - 1].ts - a[a.length - 1].ts)
    .slice(0, 80);
  const maxRange = Math.max(
    25,
    ...selected.map((point) => point.distance_nm || 0),
  );
  const position = (point: TrackPoint) => {
    const angle = ((point.bearing || 0) * Math.PI) / 180;
    const radius = ((point.distance_nm || 0) / maxRange) * 150;
    return [200 + Math.sin(angle) * radius, 200 - Math.cos(angle) * radius];
  };
  return (
    <div className="replay-map">
      <svg
        viewBox="0 0 400 400"
        aria-label={`Aircraft replay at ${new Date(playhead * 1000).toLocaleString()}`}
      >
        {[50, 100, 150].map((radius) => (
          <circle
            key={radius}
            cx="200"
            cy="200"
            r={radius}
            className="polar-ring"
          />
        ))}
        <line x1="200" y1="50" x2="200" y2="350" className="polar-spoke" />
        <line x1="50" y1="200" x2="350" y2="200" className="polar-spoke" />
        {[...grouped.values()].slice(0, 120).map((list) => {
          const trail = list
            .slice(-60)
            .map((point) => position(point).join(','))
            .join(' ');
          return (
            <polyline
              key={list[0].hex}
              points={trail}
              className="replay-trail"
              style={{ stroke: COLORS[list[0].family] || COLORS.Other }}
            />
          );
        })}
        {active.map((list) => {
          const point = list[list.length - 1];
          const [x, y] = position(point);
          return (
            <g
              key={point.hex}
              transform={`translate(${x},${y}) rotate(${point.heading || 0})`}
            >
              <path
                d="M0 -7 L4 5 L0 2 L-4 5 Z"
                fill={COLORS[point.family] || COLORS.Other}
              >
                <title>
                  {point.flight || point.hex.toUpperCase()} ·{' '}
                  {number(point.altitude)} ft
                </title>
              </path>
            </g>
          );
        })}
        <circle cx="200" cy="200" r="5" className="station-point" />
      </svg>
      <div className="replay-map-key">
        <span>{active.length} aircraft at playhead</span>
        <span>Outer ring {number(maxRange)} nm</span>
      </div>
    </div>
  );
}

function ReplayView() {
  const [hours, setHours] = useState('6');
  const { data, error } = useFeature<ReplayData>(
    `/api/replay?hours=${hours}`,
    60000,
  );
  const [progress, setProgress] = useState(100);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const min = data?.points[0]?.ts || 0;
  const max = data?.points[data.points.length - 1]?.ts || min;
  const playhead = min + ((max - min) * progress) / 100;
  useEffect(() => {
    if (!playing || !data?.points.length) return;
    const timer = setInterval(
      () =>
        setProgress((value) => {
          if (value >= 100) {
            setPlaying(false);
            return 100;
          }
          return Math.min(100, value + speed * 0.35);
        }),
      250,
    );
    return () => clearInterval(timer);
  }, [playing, speed, data]);
  const changeHours = (value: string) => {
    setProgress(100);
    setPlaying(false);
    setHours(value);
  };
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Flight time machine</h2>
          <p>
            Replay real station-relative tracks retained by the observatory.
          </p>
        </div>
        <TimeRange value={hours} setValue={changeHours} />
      </div>
      {!data ? (
        <Loading error={error} />
      ) : data.points.length === 0 ? (
        <Loading error="No historical track points have been stored yet. This view fills automatically as aircraft are received." />
      ) : (
        <div className="replay-layout">
          <FeaturePanel
            title="Historical sky"
            note={`${number(data.points.length)} compressed track points · ${number(data.bucket_seconds)}s resolution`}
          >
            <ReplayPlot points={data.points} playhead={playhead} />
          </FeaturePanel>
          <FeaturePanel
            title="Playback controls"
            note={new Date(playhead * 1000).toLocaleString()}
            className="playback-panel"
          >
            <div className="playback-controls">
              <Button
                aria-label={playing ? 'Pause replay' : 'Play replay'}
                onClick={() => {
                  if (progress >= 100) setProgress(0);
                  setPlaying(!playing);
                }}
              >
                {playing ? <Pause size={17} /> : <Play size={17} />}
                {playing ? 'Pause' : 'Play'}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setPlaying(false);
                  setProgress(0);
                }}
              >
                <RotateCcw size={16} />
                Restart
              </Button>
              <label>
                Speed
                <select
                  value={speed}
                  onChange={(event) => setSpeed(Number(event.target.value))}
                >
                  <option value="1">1×</option>
                  <option value="4">4×</option>
                  <option value="12">12×</option>
                </select>
              </label>
            </div>
            <input
              className="timeline-slider"
              type="range"
              min="0"
              max="100"
              step="0.1"
              value={progress}
              onChange={(event) => {
                setProgress(Number(event.target.value));
                setPlaying(false);
              }}
              aria-label="Replay timeline"
            />
            <div className="timeline-labels">
              <span>{new Date(min * 1000).toLocaleString()}</span>
              <span>{new Date(max * 1000).toLocaleString()}</span>
            </div>
          </FeaturePanel>
        </div>
      )}
    </>
  );
}

function EncountersView() {
  const { data, error } = useFeature<{
    encounters: Encounter[];
    retention_days: number;
  }>('/api/encounters?limit=500', 30000);
  const [query, setQuery] = useState('');
  const [favorites, setFavorites] = useState<string[]>(() => {
    if (typeof window === 'undefined') return [];
    try {
      return JSON.parse(
        localStorage.getItem('antenna-favorites') || '[]',
      ) as string[];
    } catch {
      return [];
    }
  });
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const toggle = (hex: string) =>
    setFavorites((current) => {
      const next = current.includes(hex)
        ? current.filter((item) => item !== hex)
        : [...current, hex];
      localStorage.setItem('antenna-favorites', JSON.stringify(next));
      return next;
    });
  const items = (data?.encounters || []).filter(
    (item) =>
      (!favoritesOnly || favorites.includes(item.hex)) &&
      `${item.hex} ${item.flight} ${item.squawk}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Aircraft encounter history</h2>
          <p>
            Seven-day identity, range, signal, and sighting summaries built from
            your receiver.
          </p>
        </div>
        <span className="data-pill">
          <Database size={14} /> {number(data?.encounters.length)} aircraft
        </span>
      </div>
      <div className="encounter-tools">
        <div className="search">
          <Search size={16} />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search flight, hex, or squawk"
            aria-label="Search encounter history"
          />
        </div>
        <Button
          variant={favoritesOnly ? 'default' : 'outline'}
          onClick={() => setFavoritesOnly(!favoritesOnly)}
        >
          <Heart size={16} fill={favoritesOnly ? 'currentColor' : 'none'} />
          Favorites
        </Button>
      </div>
      {!data ? (
        <Loading error={error} />
      ) : (
        <FeaturePanel
          title="Received aircraft"
          note="A new sighting begins after a 15-minute reception gap"
        >
          <div className="encounter-list">
            {items.map((item) => (
              <article key={item.hex} className="encounter-card">
                <button
                  className="favorite-button"
                  onClick={() => toggle(item.hex)}
                  aria-label={`${favorites.includes(item.hex) ? 'Remove' : 'Add'} ${item.flight || item.hex} favorite`}
                >
                  <Heart
                    size={17}
                    fill={
                      favorites.includes(item.hex) ? 'currentColor' : 'none'
                    }
                  />
                </button>
                <div className="encounter-identity">
                  <span className="aircraft-glyph">
                    <Plane size={18} />
                  </span>
                  <div>
                    <strong>{item.flight || item.hex.toUpperCase()}</strong>
                    <small>
                      {item.hex.toUpperCase()} ·{' '}
                      {item.family || 'Unknown signal'}
                    </small>
                  </div>
                </div>
                <div className="encounter-stats">
                  <span>
                    <small>Last seen</small>
                    <strong>
                      {new Date(item.last_seen * 1000).toLocaleString()}
                    </strong>
                  </span>
                  <span>
                    <small>Sightings</small>
                    <strong>{number(item.sightings)}</strong>
                  </span>
                  <span>
                    <small>Farthest</small>
                    <strong>{number(item.max_distance, 1)} nm</strong>
                  </span>
                  <span>
                    <small>Strongest</small>
                    <strong>{number(item.strongest_rssi, 1)} dBFS</strong>
                  </span>
                  <span>
                    <small>Max altitude</small>
                    <strong>{number(item.max_altitude)} ft</strong>
                  </span>
                </div>
              </article>
            ))}
            {items.length === 0 && (
              <div className="feature-empty">
                No encounters match this filter.
              </div>
            )}
          </div>
        </FeaturePanel>
      )}
    </>
  );
}

function MiniBars({
  items,
  value,
  label,
}: {
  items: DailyReport[];
  value: (item: DailyReport) => number;
  label: string;
}) {
  const max = Math.max(1, ...items.map(value));
  return (
    <div className="daily-bars" aria-label={label}>
      {items.map((item) => (
        <div key={item.day}>
          <span className="bar-value">{number(value(item), 1)}</span>
          <i style={{ height: `${Math.max(2, (value(item) / max) * 100)}%` }} />
          <time>
            {new Date(`${item.day}T12:00:00`).toLocaleDateString([], {
              weekday: 'short',
            })}
          </time>
        </div>
      ))}
    </div>
  );
}

function ReportsView() {
  const { data, error } = useFeature<{
    reports: DailyReport[];
    retention_days: number;
  }>('/api/reports?days=7', 60000);
  const reports = data?.reports || [];
  const latest = reports[reports.length - 1];
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Daily reception report</h2>
          <p>A comparable station scorecard for every retained calendar day.</p>
        </div>
        <span className="data-pill">
          <CalendarDays size={14} /> 7-day retention
        </span>
      </div>
      {!data ? (
        <Loading error={error} />
      ) : reports.length === 0 ? (
        <Loading error="The first report will appear after reception samples are stored." />
      ) : (
        <>
          <div className="feature-metrics-grid report-summary">
            <Metric
              label="Today’s unique aircraft"
              value={number(latest?.unique_aircraft)}
              note="Distinct transponder addresses"
            />
            <Metric
              label="Peak aircraft"
              value={number(latest?.peak_aircraft)}
              note="Highest simultaneous target count"
            />
            <Metric
              label="Farthest aircraft"
              value={`${number(latest?.max_range, 1)} nm`}
              note="Maximum stored position range"
            />
            <Metric
              label="Availability"
              value={`${number(latest?.availability_percent, 1)}%`}
              note="Samples with current telemetry"
            />
          </div>
          <div className="content-grid report-grid">
            <FeaturePanel
              title="Aircraft by day"
              note="Unique transponder addresses"
            >
              <MiniBars
                items={reports}
                value={(item) => item.unique_aircraft}
                label="Unique aircraft received by day"
              />
            </FeaturePanel>
            <FeaturePanel
              title="Average message rate"
              note="Accepted messages per second"
            >
              <MiniBars
                items={reports}
                value={(item) => item.average_message_rate || 0}
                label="Average message rate by day"
              />
            </FeaturePanel>
          </div>
          <FeaturePanel
            title="Daily details"
            note="All values come from stored 10-second samples and positioned tracks"
          >
            <div className="report-table">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Availability</th>
                    <th>Unique aircraft</th>
                    <th>Positions</th>
                    <th>Avg / peak messages</th>
                    <th>Max range</th>
                    <th>Avg signal</th>
                  </tr>
                </thead>
                <tbody>
                  {[...reports].reverse().map((item) => (
                    <tr key={item.day}>
                      <td>
                        {new Date(`${item.day}T12:00:00`).toLocaleDateString()}
                      </td>
                      <td>{number(item.availability_percent, 1)}%</td>
                      <td>{number(item.unique_aircraft)}</td>
                      <td>{number(item.positions)}</td>
                      <td>
                        {number(item.average_message_rate, 1)} /{' '}
                        {number(item.peak_message_rate, 1)}
                      </td>
                      <td>{number(item.max_range, 1)} nm</td>
                      <td>{number(item.average_signal, 1)} dBFS</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </FeaturePanel>
        </>
      )}
    </>
  );
}

function Histogram({ bins, unit }: { bins: HistogramBin[]; unit: string }) {
  const max = Math.max(1, ...bins.map((bin) => bin.count));
  return (
    <div className="histogram">
      {bins.map((bin) => (
        <div key={`${bin.from}-${bin.to}`}>
          <span>{number(bin.count)}</span>
          <i>
            <b style={{ height: `${(bin.count / max) * 100}%` }} />
          </i>
          <small>
            {number(bin.from)}–{number(bin.to)}
            {unit}
          </small>
        </div>
      ))}
    </div>
  );
}

function LaboratoryView({ snapshot }: { snapshot: Partial<Snapshot> }) {
  const [hours, setHours] = useState('24');
  const { data, error } = useFeature<LabData>(`/api/lab?hours=${hours}`, 30000);
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Signal laboratory</h2>
          <p>
            Distributions expose range, altitude, and decoded power patterns
            hidden by averages.
          </p>
        </div>
        <TimeRange value={hours} setValue={setHours} />
      </div>
      {!data ? (
        <Loading error={error} />
      ) : (
        <>
          <div className="feature-metrics-grid">
            <Metric
              label="Frames in power sample"
              value={number(data.frames_analyzed)}
              note="Most recent decoded Beast frames"
            />
            <Metric
              label="Position samples"
              value={number(data.positions_analyzed)}
              note={`Stored across ${hours === '168' ? '7 days' : `${hours} hours`}`}
            />
            <Metric
              label="Message baseline"
              value={`${number(data.baselines.message_rate, 1)}/s`}
              note="Median while telemetry is live"
            />
            <Metric
              label="Signal margin"
              value={`${number(snapshot.metrics?.signal_above_noise, 1)} dB`}
              note="Mean decoded signal above noise"
            />
          </div>
          <div className="lab-grid">
            <FeaturePanel
              title="Decoded frame power"
              note="dBFS; values closer to zero are stronger"
            >
              <Histogram bins={data.rssi} unit="" />
            </FeaturePanel>
            <FeaturePanel
              title="Aircraft range"
              note="Position observations by nautical-mile band"
            >
              <Histogram bins={data.range} unit=" nm" />
            </FeaturePanel>
            <FeaturePanel
              title="Aircraft altitude"
              note="Barometric altitude distribution"
            >
              <Histogram bins={data.altitude} unit=" ft" />
            </FeaturePanel>
            <FeaturePanel
              title="Interpretation"
              note="Current measurements compared with recent baselines"
            >
              <div className="lab-insights">
                <p>
                  <Radio size={18} />
                  <span>
                    <strong>
                      {number(snapshot.metrics?.mean_signal, 1)} dBFS current
                      mean power
                    </strong>
                    Six-hour median {number(data.baselines.mean_signal, 1)}{' '}
                    dBFS.
                  </span>
                </p>
                <p>
                  <Waves size={18} />
                  <span>
                    <strong>
                      {number(snapshot.metrics?.noise, 1)} dBFS current noise
                      floor
                    </strong>
                    Six-hour median {number(data.baselines.noise, 1)} dBFS.
                  </span>
                </p>
                <p>
                  <FlaskConical size={18} />
                  <span>
                    <strong>
                      {number(snapshot.metrics?.corrected_percent, 1)}%
                      corrected messages
                    </strong>
                    Lower values usually indicate cleaner decoding.
                  </span>
                </p>
              </div>
            </FeaturePanel>
          </div>
        </>
      )}
    </>
  );
}

function MaintenanceView({ editable }: { editable: boolean }) {
  const { data, error, reload } = useFeature<{ entries: MaintenanceEntry[] }>(
    '/api/maintenance',
    60000,
  );
  const [title, setTitle] = useState('');
  const [details, setDetails] = useState('');
  const [category, setCategory] = useState('note');
  const [result, setResult] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editable) return;
    setSaving(true);
    setResult('');
    try {
      const response = await apiFetch('/api/maintenance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, details, category }),
      });
      const value = (await response.json()) as { error?: string };
      if (!response.ok)
        throw new Error(value.error || 'Could not save this entry.');
      setTitle('');
      setDetails('');
      setCategory('note');
      setResult('Maintenance entry saved.');
      reload();
    } catch (reason) {
      setResult(
        reason instanceof Error ? reason.message : 'Could not save this entry.',
      );
    } finally {
      setSaving(false);
    }
  };
  const remove = async (id: number) => {
    if (!editable) return;
    setResult('');
    try {
      const response = await apiFetch('/api/maintenance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      if (!response.ok) throw new Error('Could not delete this entry.');
      setResult('Maintenance entry deleted.');
      reload();
    } catch (reason) {
      setResult(
        reason instanceof Error
          ? reason.message
          : 'Could not delete this entry.',
      );
    }
  };
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Maintenance log</h2>
          <p>
            Connect signal changes to physical or software work on the station.
          </p>
        </div>
        <span className="data-pill">
          <Wrench size={14} /> {number(data?.entries.length)} annotations
        </span>
      </div>
      <div className="maintenance-layout">
        <FeaturePanel
          title={editable ? 'Add annotation' : 'Read-only timeline'}
          note={
            editable
              ? 'Authored locally, synchronized securely'
              : 'Editing is available on the Mac'
          }
        >
          {editable ? (
            <form className="maintenance-form" onSubmit={submit}>
              <label htmlFor="maintenance-category">Category</label>
              <select
                id="maintenance-category"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="note">General note</option>
                <option value="installation">Installation</option>
                <option value="antenna">Antenna</option>
                <option value="receiver">Receiver</option>
                <option value="software">Software</option>
                <option value="incident">Incident</option>
              </select>
              <label htmlFor="maintenance-title">Title</label>
              <Input
                id="maintenance-title"
                required
                maxLength={100}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="What changed?"
              />
              <label htmlFor="maintenance-details">Details</label>
              <textarea
                id="maintenance-details"
                maxLength={2000}
                value={details}
                onChange={(event) => setDetails(event.target.value)}
                placeholder="Placement, cable, gain, weather, or result"
              />
              <Button type="submit" disabled={saving}>
                <Plus size={16} />
                {saving ? 'Saving…' : 'Add to timeline'}
              </Button>
              {result && (
                <p className="save-result" aria-live="polite">
                  {result}
                </p>
              )}
            </form>
          ) : (
            <div className="feature-empty maintenance-readonly">
              Open <strong>http://127.0.0.1:8787</strong> on the receiver Mac to
              add or delete an annotation. The protected telemetry uplink will
              mirror it here automatically.
            </div>
          )}
        </FeaturePanel>
        <FeaturePanel title="Station timeline" note="Newest first">
          {!data ? (
            <Loading error={error} />
          ) : (
            <div className="maintenance-timeline">
              {data.entries.map((entry) => (
                <article key={entry.id}>
                  <i />
                  <div>
                    <span>{entry.category}</span>
                    <time>{new Date(entry.ts * 1000).toLocaleString()}</time>
                    <h3>{entry.title}</h3>
                    {entry.details && <p>{entry.details}</p>}
                  </div>
                  {editable && (
                    <button
                      onClick={() => void remove(entry.id)}
                      aria-label={`Delete ${entry.title}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </article>
              ))}
              {data.entries.length === 0 && (
                <div className="feature-empty">
                  No maintenance annotations yet.
                </div>
              )}
            </div>
          )}
        </FeaturePanel>
      </div>
    </>
  );
}

function SpectrumView() {
  const { data, error } = useFeature<SpectrumData>('/api/spectrum', 10000);
  const values = data?.lines || [];
  const color = (value: number) => {
    const level = Math.max(0, Math.min(1, (value + 70) / 65));
    return `hsl(${42 - level * 26} 95% ${12 + level * 54}%)`;
  };
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>1090 MHz spectrum</h2>
          <p>
            A spectrum-side view that never retunes the receiver feeding
            airplanes.live.
          </p>
        </div>
        <span className={`data-pill ${data?.available ? 'available' : ''}`}>
          <Waves size={14} />{' '}
          {data?.available ? 'Second SDR live' : 'Primary SDR protected'}
        </span>
      </div>
      {!data ? (
        <Loading error={error} />
      ) : data.available && values.length ? (
        <FeaturePanel
          title="Spectrum waterfall"
          note={`${number(data.center_mhz, 3)} MHz center · ${number(data.span_mhz, 1)} MHz span`}
        >
          <div
            className="waterfall"
            aria-label="Recent 1090 MHz spectrum intensity waterfall"
          >
            {values.slice(-80).map((line, lineIndex) => (
              <div key={`${line.ts}-${lineIndex}`}>
                {line.values.map((value, index) => (
                  <i key={index} style={{ background: color(value) }} />
                ))}
              </div>
            ))}
          </div>
          <div className="spectrum-axis">
            <span>{number(data.center_mhz - data.span_mhz / 2, 3)} MHz</span>
            <strong>1090 MHz</strong>
            <span>{number(data.center_mhz + data.span_mhz / 2, 3)} MHz</span>
          </div>
        </FeaturePanel>
      ) : (
        <div className="spectrum-ready">
          <div className="spectrum-orbit">
            <Radio size={38} />
            <i />
            <i />
            <i />
          </div>
          <div>
            <span className="data-pill">
              <CheckCircle2 size={14} /> Existing feed stays live
            </span>
            <h2>Spectrum input is ready for a second SDR</h2>
            <p>{data.reason}</p>
            <div className="spectrum-steps">
              <span>
                <b>1</b>Connect a second RTL-SDR with its own serial number.
              </span>
              <span>
                <b>2</b>Run the included spectrum sidecar against that serial.
              </span>
              <span>
                <b>3</b>The waterfall appears here automatically.
              </span>
            </div>
          </div>
        </div>
      )}
      <div className="content-grid spaced">
        <FeaturePanel
          title="Why a second receiver?"
          note="One tuner can listen to one frequency window at a time"
        >
          <div className="explain-card">
            <p>
              The NESDR currently samples 1090 MHz continuously. Retuning it for
              a scan would create holes in aircraft reception and in the
              airplanes.live feed.
            </p>
            <p>
              The observatory therefore accepts waterfall data only from an
              explicitly selected second device.
            </p>
          </div>
        </FeaturePanel>
        <FeaturePanel
          title="Spectrum capability"
          note="Designed for safe expansion"
        >
          <div className="lab-insights">
            <p>
              <Radio size={18} />
              <span>
                <strong>Primary · serial protected</strong>Aircraft decoding and
                BeastReduce+ uplink.
              </span>
            </p>
            <p>
              <Waves size={18} />
              <span>
                <strong>Secondary · optional</strong>FFT sweep around the 1090
                MHz center.
              </span>
            </p>
          </div>
        </FeaturePanel>
      </div>
    </>
  );
}

function AlertsView({ snapshot }: { snapshot: Partial<Snapshot> }) {
  const alerts = useMemo(
    () => snapshot.smart_alerts || [],
    [snapshot.smart_alerts],
  );
  const [permission, setPermission] = useState(
    typeof Notification === 'undefined'
      ? 'unsupported'
      : Notification.permission,
  );
  const enable = async () => {
    if (typeof Notification === 'undefined') return;
    const next = await Notification.requestPermission();
    setPermission(next);
    window.dispatchEvent(new Event('antenna-notification-permission'));
  };
  return (
    <>
      <div className="section-toolbar feature-toolbar">
        <div>
          <h2>Smart alerts</h2>
          <p>
            Live checks compare availability, decoder quality, and signal
            behavior with recent baselines.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void enable()}
          disabled={permission === 'unsupported' || permission === 'granted'}
        >
          <BellRing size={16} />
          {permission === 'granted'
            ? 'Browser alerts enabled'
            : permission === 'unsupported'
              ? 'Notifications unavailable'
              : 'Enable browser alerts'}
        </Button>
      </div>
      <div className="feature-metrics-grid alert-summary">
        <Metric
          label="Active alerts"
          value={number(alerts.length)}
          note="Evaluated every telemetry refresh"
        />
        <Metric
          label="Station health"
          value={`${number(snapshot.health_score?.score)}/100`}
          note={snapshot.health_score?.status || 'Waiting for score'}
        />
        <Metric
          label="Traffic baseline"
          value={`${number(snapshot.health_score?.baseline_message_rate, 1)}/s`}
          note="Six-hour median message rate"
        />
        <Metric
          label="Browser notifications"
          value={permission === 'granted' ? 'On' : 'Off'}
          note="Delivered while this installed app is open"
        />
      </div>
      <FeaturePanel
        title="Active conditions"
        note="Clears automatically when measurements recover"
      >
        <div className="active-alerts">
          {alerts.map((alert: SmartAlert) => (
            <article key={alert.code} className={alert.severity}>
              <AlertTriangle size={20} />
              <div>
                <span>{alert.severity}</span>
                <h3>{alert.title}</h3>
                <p>{alert.message}</p>
              </div>
            </article>
          ))}
          {alerts.length === 0 && (
            <div className="all-clear">
              <CheckCircle2 size={28} />
              <div>
                <strong>No active conditions</strong>
                <span>
                  Receiver and feed measurements are inside their expected
                  ranges.
                </span>
              </div>
            </div>
          )}
        </div>
      </FeaturePanel>
    </>
  );
}

export default function IntelligenceViews({
  view,
  snapshot,
}: {
  view: string;
  snapshot: Partial<Snapshot>;
}) {
  if (view === 'coverage') return <CoverageView />;
  if (view === 'replay') return <ReplayView />;
  if (view === 'encounters') return <EncountersView />;
  if (view === 'reports') return <ReportsView />;
  if (view === 'laboratory') return <LaboratoryView snapshot={snapshot} />;
  if (view === 'maintenance')
    return <MaintenanceView editable={snapshot.settings_editable === true} />;
  if (view === 'spectrum') return <SpectrumView />;
  if (view === 'alerts') return <AlertsView snapshot={snapshot} />;
  return null;
}
