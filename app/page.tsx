'use client';
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import type { ReactNode, SubmitEvent } from 'react';
import type {
  Aircraft,
  Signal,
  Frame,
  Format,
  ReceiverEvent,
  Snapshot,
  HistoryData,
  Sort,
  StationForm,
  BrowserTool,
  ToolContext,
} from '@/lib/telemetry';
import {
  RadioTower,
  Activity,
  Plane,
  Radio,
  ArrowUpRight,
  Wifi,
  Clock3,
  Cpu,
  History,
  Terminal,
  Braces,
  Settings2,
  Search,
  Download,
  ArrowUpDown,
  MapPin,
  ShieldCheck,
  AlertTriangle,
  ExternalLink,
  Menu,
  LogOut,
  ChevronRight,
} from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';

type LocatedAircraft = Aircraft & { lat: number; lon: number };
const SignalChart = lazy(() => import('@/components/signal-chart'));
import type { ChartProps } from '@/components/signal-chart';
const COLORS: Record<string, string> = {
  'ADS-B': '#ffbb45',
  'Mode S': '#d8d0b8',
  'TIS-B': '#b9a5e6',
  'ADS-R': '#ef8d65',
  'Mode A/C': '#d5a2bd',
  MLAT: '#c3c4b4',
  Other: '#9c9b91',
};
const FAMILIES = ['ADS-B', 'Mode S', 'TIS-B', 'ADS-R', 'Mode A/C', 'Other'];
async function dashboardFetch(path: string, options?: RequestInit) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    window.location.replace('/login');
    throw new Error('Sign in required');
  }
  return response;
}
const VIEWS = [
  ['overview', 'Overview', Activity],
  ['signals', 'Signals', Radio],
  ['aircraft', 'Aircraft', Plane],
  ['receiver', 'Receiver', Cpu],
  ['feed', 'Feed', Wifi],
  ['history', 'History', History],
  ['events', 'Events', Terminal],
  ['inspector', 'Inspector', Braces],
  ['station', 'Station', Settings2],
] as const;
const TITLES: Record<string, string> = {
  overview: 'Receiver overview',
  signals: 'Signal intelligence',
  aircraft: 'Aircraft in range',
  receiver: 'Receiver health',
  feed: 'Feed connection',
  history: 'Reception history',
  events: 'Events & diagnostics',
  inspector: 'Telemetry inspector',
  station: 'Your station',
};
const DESCRIPTIONS: Record<string, string> = {
  'ADS-B': 'Aircraft broadcasting identity, position, velocity, and status.',
  'Mode S':
    'Transponder replies carrying surveillance, altitude, identity, and Comm-B data.',
  'TIS-B': 'Ground stations rebroadcasting traffic reports on 1090 MHz.',
  'ADS-R':
    'Ground rebroadcasts of ADS-B traffic received over another data link.',
  'Mode A/C':
    'Legacy identity and altitude replies. No CRC; detections may include noise.',
  Other: 'Other decoded formats observed in the local stream.',
};
const textValue = (v: unknown): string =>
  typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
    ? String(v)
    : (JSON.stringify(v) ?? '—');
const fmt = (v: unknown, d = 0) =>
  typeof v === 'number' && Number.isFinite(v)
    ? v.toLocaleString('en-US', {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      })
    : '—';
const time = (v: unknown) =>
  typeof v === 'number'
    ? new Date(v * 1000).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '—';
const age = (s: unknown) =>
  typeof s !== 'number' || !Number.isFinite(s)
    ? '—'
    : s < 60
      ? `${Math.floor(s)}s`
      : s < 3600
        ? `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`
        : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
function Stat({
  label,
  value,
  unit,
  note,
  tone,
  icon,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  note: string;
  tone?: string;
  icon?: ReactNode;
}) {
  return (
    <article className="stat">
      <div className="stat-label">
        <span className="eyebrow">{label}</span>
        {icon || <Activity size={17} />}
      </div>
      <div className={`stat-value ${tone || ''}`}>
        {value}
        <small>{unit}</small>
      </div>
      <p>{note}</p>
    </article>
  );
}
function Panel({
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
    <section className={`panel ${className}`}>
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
function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
function Badge({
  children,
  good = false,
}: {
  children: ReactNode;
  good?: boolean;
}) {
  return (
    <span className={`subtle-badge ${good ? 'success-badge' : ''}`}>
      {children}
    </span>
  );
}
function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="data-rows">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  );
}
function Choice({
  value,
  set,
  items,
}: {
  value: string;
  set: (v: string) => void;
  items: [string, string][];
}) {
  return (
    <Tabs
      className="choice-control"
      value={value}
      onValueChange={(v) => set(String(v))}
    >
      <TabsList className="choices" aria-label="Filter options">
        {items.map(([v, t]) => (
          <TabsTrigger key={v} value={v}>
            {t}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
function Chart(props: ChartProps) {
  return (
    <Suspense
      fallback={
        <div
          className="chart-loading"
          style={{ minHeight: (props.height ?? 224) + 90 }}
        >
          Loading reception chart…
        </div>
      }
    >
      <SignalChart {...props} />
    </Suspense>
  );
}
function FamilyBars({
  data,
  onPick,
}: {
  data: Partial<Snapshot>;
  onPick: (v: string) => void;
}) {
  const signals = data.signals || [];
  const max = Math.max(1, ...signals.map((s: Signal) => s.rate || 0));
  return (
    <div className="families">
      {signals
        .filter((s: Signal) => s.name !== 'Other' || s.frames > 0)
        .map((s: Signal) => (
          <button
            className="family-row"
            key={s.name}
            onClick={() => onPick(s.name)}
            aria-label={`Inspect ${s.name} signals`}
          >
            <span>
              <i style={{ background: COLORS[s.name] }} />
              {s.name}
            </span>
            <div className="family-track">
              <b
                style={{
                  width: `${((s.rate ?? 0) / max) * 100}%`,
                  background: COLORS[s.name],
                }}
              />
            </div>
            <strong>{data.beast_connected ? fmt(s.rate, 1) : '—'}</strong>
            <ArrowUpRight size={13} />
          </button>
        ))}
    </div>
  );
}
function AircraftTable({
  items,
  onSelect,
  sort,
  setSort,
}: {
  items: Aircraft[];
  onSelect: (a: Aircraft) => void;
  sort?: Sort;
  setSort?: (s: Sort) => void;
}) {
  const cols = [
    ['flight', 'Aircraft'],
    ['family', 'Signal'],
    ['alt_baro', 'Altitude'],
    ['gs', 'Speed'],
    ['rssi', 'Signal power'],
    ['messages', 'Messages'],
    ['seen', 'Last seen'],
  ];
  return (
    <div className="aircraft-panel">
      <div className="mobile-aircraft">
        {setSort && sort && (
          <div className="mobile-sort">
            <label htmlFor="aircraft-sort">Sort by</label>
            <select
              id="aircraft-sort"
              value={sort.key}
              onChange={(event) =>
                setSort({ key: event.target.value, asc: sort.asc })
              }
            >
              {cols.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <Button
              variant="outline"
              onClick={() => setSort({ ...sort, asc: !sort.asc })}
              aria-label={`Sort ${sort.asc ? 'descending' : 'ascending'}`}
            >
              <ArrowUpDown size={16} />
              {sort.asc ? 'Asc' : 'Desc'}
            </Button>
          </div>
        )}
        {items.map((aircraft) => (
          <button
            type="button"
            className={`aircraft-card ${aircraft.live ? '' : 'aging-row'}`}
            key={aircraft.hex}
            onClick={() => onSelect(aircraft)}
            aria-label={`Inspect ${aircraft.flight || aircraft.hex.toUpperCase()}`}
          >
            <span className="aircraft-card-top">
              <span className="aircraft-glyph">
                <Plane size={20} />
              </span>
              <span className="aircraft-identity">
                <strong>{aircraft.flight || aircraft.hex.toUpperCase()}</strong>
                <small>
                  {aircraft.hex.toUpperCase()} · {fmt(aircraft.seen, 1)}s ago
                </small>
              </span>
              <span
                className="signal-pill"
                style={{ color: COLORS[aircraft.family] }}
              >
                {aircraft.family}
              </span>
              <ChevronRight size={17} />
            </span>
            <span className="aircraft-card-metrics">
              <span>
                <small>Altitude</small>
                <strong>
                  {typeof aircraft.alt_baro === 'number'
                    ? fmt(aircraft.alt_baro)
                    : aircraft.alt_baro || '—'}
                  <em>{typeof aircraft.alt_baro === 'number' ? ' ft' : ''}</em>
                </strong>
              </span>
              <span>
                <small>Speed</small>
                <strong>
                  {fmt(aircraft.gs)}
                  <em>{aircraft.gs == null ? '' : ' kt'}</em>
                </strong>
              </span>
              <span>
                <small>Signal</small>
                <strong>
                  {fmt(aircraft.rssi, 1)}
                  <em>{aircraft.rssi == null ? '' : ' dBFS'}</em>
                </strong>
              </span>
            </span>
            <span className="aircraft-card-bottom">
              {fmt(aircraft.messages)} messages
              <span>
                View details <ArrowUpRight size={13} />
              </span>
            </span>
          </button>
        ))}
      </div>
      <div className="desktop-aircraft">
        <Table>
          <TableHeader>
            <TableRow>
              {cols.map(([key, label]) => (
                <TableHead
                  key={key}
                  aria-sort={
                    sort?.key === key
                      ? sort.asc
                        ? 'ascending'
                        : 'descending'
                      : undefined
                  }
                >
                  {setSort ? (
                    <button
                      className="sort-button"
                      onClick={() =>
                        setSort({
                          key,
                          asc: sort?.key === key ? !sort.asc : true,
                        })
                      }
                    >
                      {label}
                      <ArrowUpDown size={12} />
                    </button>
                  ) : (
                    label
                  )}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((a: Aircraft) => (
              <TableRow key={a.hex} className={!a.live ? 'aging-row' : ''}>
                <TableCell>
                  <button className="aircraft-link" onClick={() => onSelect(a)}>
                    <strong>{a.flight || a.hex.toUpperCase()}</strong>
                    <small className="mono secondary">
                      {a.hex.toUpperCase()}
                    </small>
                  </button>
                </TableCell>
                <TableCell>
                  <span
                    className="signal-pill"
                    style={{ color: COLORS[a.family] }}
                  >
                    {a.family}
                  </span>
                </TableCell>
                <TableCell>
                  {typeof a.alt_baro === 'number'
                    ? `${fmt(a.alt_baro)} ft`
                    : a.alt_baro || '—'}
                </TableCell>
                <TableCell>{a.gs == null ? '—' : `${fmt(a.gs)} kt`}</TableCell>
                <TableCell>
                  {a.rssi == null ? '—' : `${fmt(a.rssi, 1)} dBFS`}
                </TableCell>
                <TableCell>{fmt(a.messages)}</TableCell>
                <TableCell>
                  <span className={a.live ? 'live-age' : ''}>
                    {fmt(a.seen, 1)}s
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {items.length === 0 && (
        <Empty>
          No aircraft match this view. A quiet signal family is normal.
        </Empty>
      )}
    </div>
  );
}
function SkyPlot({
  data,
  onSelect,
  onSettings,
}: {
  data: Partial<Snapshot>;
  onSelect: (a: Aircraft) => void;
  onSettings: () => void;
}) {
  const planes = (data.aircraft || []).filter(
    (a: Aircraft): a is LocatedAircraft =>
      a.live &&
      typeof a.lat === 'number' &&
      typeof a.lon === 'number' &&
      (a.seen_pos ?? 999) < 15,
  );
  const located =
    typeof data.settings?.latitude === 'number' &&
    typeof data.settings?.longitude === 'number';
  const range = Math.max(
    25,
    Math.ceil(
      Math.max(0, ...planes.map((a: LocatedAircraft) => a.distance_nm || 0)) /
        25,
    ) * 25,
  );
  const minLat = Math.min(...planes.map((a: LocatedAircraft) => a.lat)),
    maxLat = Math.max(...planes.map((a: LocatedAircraft) => a.lat)),
    minLon = Math.min(...planes.map((a: LocatedAircraft) => a.lon)),
    maxLon = Math.max(...planes.map((a: LocatedAircraft) => a.lon));
  const midLat = (minLat + maxLat) / 2 || 0,
    midLon = (minLon + maxLon) / 2 || 0;
  const latSpan = Math.max(0.3, maxLat - minLat) * 1.5,
    lonSpan = Math.max(0.3, maxLon - minLon) * 1.5;
  function position(a: LocatedAircraft) {
    if (located) {
      const r = ((a.distance_nm ?? 0) / range) * 120,
        ang = ((a.bearing ?? 0) * Math.PI) / 180;
      return [240 + r * Math.sin(ang), 155 - r * Math.cos(ang)];
    }
    return [
      240 + ((a.lon - midLon) / lonSpan) * 350,
      155 - ((a.lat - midLat) / latSpan) * 230,
    ];
  }
  return (
    <Panel
      title={located ? 'Range & bearing' : 'Aircraft position plot'}
      note={
        located
          ? `Relative to your station · outer ring ${range} nm`
          : 'Geographic positions · centered on received aircraft'
      }
      aside={
        <Badge>
          <MapPin size={13} />
          {planes.length} positioned
        </Badge>
      }
    >
      <div className="sky-plot">
        <svg
          viewBox="0 0 480 315"
          aria-label={
            located
              ? 'Aircraft distance and direction from your station'
              : 'Aircraft locations in a latitude and longitude plot'
          }
        >
          <defs>
            <pattern
              id="sky-grid"
              width="30"
              height="30"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M30 0H0V30"
                fill="none"
                stroke="#3b3425"
                strokeWidth=".5"
              />
            </pattern>
          </defs>
          <rect x="25" y="20" width="430" height="270" fill="url(#sky-grid)" />
          {located ? (
            <g>
              {[40, 80, 120].map((r) => (
                <circle
                  key={r}
                  cx="240"
                  cy="155"
                  r={r}
                  stroke="#766036"
                  fill="none"
                  strokeDasharray="3 5"
                />
              ))}
              <circle cx="240" cy="155" r="4" fill="#ffbb45" />
              <text x="248" y="170" fill="#b7aa94" fontSize="11">
                Station
              </text>
            </g>
          ) : null}
          <text x="240" y="13" textAnchor="middle" fill="#b7aa94" fontSize="12">
            {located
              ? 'N'
              : planes.length
                ? `${fmt(midLat + latSpan / 2, 2)}° N`
                : ''}
          </text>
          <text
            x="240"
            y="308"
            textAnchor="middle"
            fill="#b7aa94"
            fontSize="12"
          >
            {located
              ? 'S'
              : planes.length
                ? `${fmt(midLat - latSpan / 2, 2)}° N`
                : ''}
          </text>
          {planes.map((a: LocatedAircraft) => {
            const [x, y] = position(a);
            return (
              <a
                key={a.hex}
                className="plane-marker"
                href="#aircraft"
                onClick={(e) => {
                  e.preventDefault();
                  onSelect(a);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(a);
                  }
                }}
                aria-label={`Inspect ${a.flight || a.hex}`}
              >
                <circle cx={x} cy={y} r="24" fill="transparent" />
                <path
                  d="M0 -7 L4 5 L0 2 L-4 5 Z"
                  transform={`translate(${x},${y}) rotate(${a.track || 0})`}
                  fill={COLORS[a.family] || COLORS.Other}
                />
                <text x={x + 10} y={y + 4} fontSize="11" fill="#efe6d6">
                  {a.flight || a.hex}
                </text>
                <title>
                  {a.flight || a.hex}: {fmt(a.lat, 3)}, {fmt(a.lon, 3)} ·{' '}
                  {fmt(a.alt_baro)} ft
                </title>
              </a>
            );
          })}
          {planes.length === 0 && (
            <text
              x="240"
              y="160"
              textAnchor="middle"
              fill="#b7aa94"
              fontSize="14"
            >
              Waiting for current aircraft positions
            </text>
          )}
        </svg>
      </div>
      {!located && (
        <div className="panel-bottom">
          <span>Set the antenna’s location to measure range.</span>
          <Button variant="ghost" onClick={onSettings}>
            Set location <ArrowUpRight />
          </Button>
        </div>
      )}
    </Panel>
  );
}
function flatten(obj: unknown, prefix = ''): [string, unknown][] {
  return Object.entries(
    obj !== null && typeof obj === 'object' ? obj : {},
  ).flatMap(([key, v]) =>
    v !== null && typeof v === 'object' && !Array.isArray(v)
      ? flatten(v, prefix + key + '.')
      : [[prefix + key, v] as [string, unknown]],
  );
}

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [data, setData] = useState<Snapshot | null>(null),
    [hist, setHist] = useState<HistoryData>({ points: [] }),
    [error, setError] = useState(''),
    [view, setView] = useState('overview');
  const [hours, setHours] = useState('1'),
    [family, setFamily] = useState('All'),
    [query, setQuery] = useState(''),
    [liveOnly, setLiveOnly] = useState(true),
    [sort, setSort] = useState<Sort>({ key: 'rssi', asc: false });
  const [selected, setSelected] = useState<Aircraft | null>(null),
    [logs, setLogs] = useState<string[]>([]),
    [logError, setLogError] = useState(''),
    [eventFilter, setEventFilter] = useState('all'),
    [inspect, setInspect] = useState('stats'),
    [inspectQuery, setInspectQuery] = useState('');
  const [form, setForm] = useState<StationForm>({
      station_name: '',
      latitude: '',
      longitude: '',
    }),
    [saved, setSaved] = useState(''),
    [saving, setSaving] = useState(false),
    [historyError, setHistoryError] = useState('');
  const initialized = useRef(false),
    dataRef = useRef<Snapshot | null>(null);
  const navigate = useCallback((next: string) => {
    setView(next);
    setMenuOpen(false);
    if (typeof window !== 'undefined') {
      window.history.replaceState(null, '', `#${next}`);
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, []);
  useEffect(() => {
    const readHash = () => {
      const hash = window.location.hash.slice(1);
      if (VIEWS.some((v) => v[0] === hash)) setView(hash);
    };
    const initial = window.requestAnimationFrame(readHash);
    const h = () => {
      const value = location.hash.slice(1);
      if (VIEWS.some((v) => v[0] === value)) setView(value);
    };
    window.addEventListener('hashchange', h);
    return () => {
      window.cancelAnimationFrame(initial);
      window.removeEventListener('hashchange', h);
    };
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const ac = new AbortController();
    const poll = async () => {
      try {
        const r = await dashboardFetch('/api/snapshot', { signal: ac.signal });
        if (!r.ok) throw Error();
        const d = (await r.json()) as Snapshot;
        if (alive) {
          setData(d);
          dataRef.current = d;
          setError('');
          if (!initialized.current && d.settings) {
            setForm({
              station_name: d.settings.station_name,
              latitude: d.settings.latitude ?? '',
              longitude: d.settings.longitude ?? '',
            });
            initialized.current = true;
          }
        }
      } catch {
        if (alive)
          setError('The local collector is unavailable. Reconnecting…');
      } finally {
        if (alive) timer = setTimeout(poll, 2000);
      }
    };
    void poll();
    return () => {
      alive = false;
      ac.abort();
      clearTimeout(timer);
    };
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const ac = new AbortController();
    const poll = async () => {
      try {
        const r = await dashboardFetch(`/api/history?hours=${hours}`, {
          signal: ac.signal,
        });
        if (!r.ok) throw Error();
        const d = (await r.json()) as HistoryData;
        if (alive) {
          setHist(d);
          setHistoryError('');
        }
      } catch {
        if (alive) setHistoryError('History is temporarily unavailable.');
      } finally {
        if (alive) timer = setTimeout(poll, 10000);
      }
    };
    void poll();
    return () => {
      alive = false;
      ac.abort();
      clearTimeout(timer);
    };
  }, [hours]);
  useEffect(() => {
    if (view !== 'events') return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const ac = new AbortController();
    const poll = async () => {
      try {
        const r = await dashboardFetch('/api/logs', { signal: ac.signal });
        if (!r.ok) throw Error();
        const d = (await r.json()) as { lines: string[] };
        if (alive) {
          setLogs(d.lines);
          setLogError('');
        }
      } catch {
        if (alive) setLogError('Decoder log is temporarily unavailable.');
      } finally {
        if (alive) timer = setTimeout(poll, 10000);
      }
    };
    void poll();
    return () => {
      alive = false;
      ac.abort();
      clearTimeout(timer);
    };
  }, [view]);
  useEffect(() => {
    const context = (document as Document & { modelContext?: ToolContext })
      .modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const register = (tool: BrowserTool) => {
      try {
        Promise.resolve(
          context.registerTool(tool, { signal: lifecycle.signal }),
        ).catch(() => {});
      } catch {}
    };
    register({
      name: 'read_receiver_status',
      description:
        'Read real local receiver health, signal family counts, and feed status.',
      inputSchema: {
        type: 'object',
        properties: {},
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true },
      execute: () => {
        const d = dataRef.current;
        return d
          ? {
              state: d.state,
              metrics: d.metrics,
              signals: d.signals,
              host: d.host,
            }
          : { state: 'loading' };
      },
    });
    register({
      name: 'open_signal_family',
      description: 'Open the Signals view filtered to a supported family.',
      inputSchema: {
        type: 'object',
        properties: { family: { type: 'string', enum: FAMILIES } },
        required: ['family'],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false },
      execute: (input: Record<string, unknown>) => {
        if (
          typeof input.family !== 'string' ||
          !FAMILIES.includes(input.family)
        )
          throw Error('Unknown signal family');
        setFamily(input.family);
        navigate('signals');
        return { view: 'signals', family: input.family };
      },
    });
    return () => lifecycle.abort();
  }, [navigate]);
  const d: Partial<Snapshot> = data || {},
    m = d.metrics || {},
    live = !error && d.state === 'live',
    sourceAges = d.age_seconds,
    isStale = !!error || d.state === 'stale';
  const points = hist.points || [],
    allAircraft = d.aircraft || [],
    current =
      (selected
        ? allAircraft.find((a: Aircraft) => a.hex === selected.hex)
        : null) || selected;
  const filtered = allAircraft
    .filter(
      (a: Aircraft) =>
        (!liveOnly || a.live) &&
        (family === 'All' || a.family === family) &&
        `${a.hex} ${a.flight} ${a.squawk || ''}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a: Aircraft, b: Aircraft) => {
      const x = a[sort.key],
        y = b[sort.key];
      if (x == null) return 1;
      if (y == null) return -1;
      const comp =
        typeof x === 'number' && typeof y === 'number'
          ? x - y
          : textValue(x).localeCompare(textValue(y));
      return sort.asc ? comp : -comp;
    });
  const selectFamily = (f: string) => {
    setFamily(f);
    navigate('signals');
  };
  const stats = d.stats || {},
    statWindow = stats.last1min || {},
    local = statWindow.local || {},
    cpu = statWindow.cpu || {},
    duration = Math.max(1, (statWindow.end || 0) - (statWindow.start || 0));
  const frameList = (d.recent_frames || []).filter(
    (f: Frame) => family === 'All' || f.family === family,
  );
  const alerts: string[] = [];
  if (isStale)
    alerts.push(
      'Measurements are stale. Check Receiver and Events for the last known status.',
    );
  if (live && d.host?.feed_connected === false)
    alerts.push(
      'Aircraft reception is live, but the airplanes.live connection is down.',
    );
  if ((m.samples_dropped ?? 0) > 0)
    alerts.push(
      `${fmt(m.samples_dropped)} samples dropped since decoder restart. Check CPU load.`,
    );
  if ((m.strong_percent ?? 0) > 10)
    alerts.push(
      'More than 10% of accepted messages exceed −3 dBFS. Strong signals may be overloading reception.',
    );
  async function saveStation(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setSaved('');
    try {
      const payload = {
        station_name: form.station_name,
        latitude: form.latitude === '' ? null : Number(form.latitude),
        longitude: form.longitude === '' ? null : Number(form.longitude),
      };
      const r = await dashboardFetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = (await r.json()) as { error?: string };
      if (!r.ok) throw Error(result.error);
      setSaved('Station settings saved on this Mac.');
    } catch (e) {
      setSaved(e instanceof Error ? e.message : 'Could not save settings.');
    } finally {
      setSaving(false);
    }
  }
  const rangePicker = (
    <Choice
      value={hours}
      set={setHours}
      items={[
        ['1', '1 hour'],
        ['6', '6 hours'],
        ['24', '24 hours'],
        ['168', '7 days'],
      ]}
    />
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#dashboard-content">
        Skip to dashboard
      </a>
      <header className="masthead">
        <div className="masthead-left">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger
              className="hamburger-button"
              aria-label="Open navigation menu"
            >
              <Menu size={25} />
            </SheetTrigger>
            <SheetContent side="left" className="navigation-sheet">
              <SheetHeader>
                <SheetTitle>Antenna Observatory</SheetTitle>
                <SheetDescription>Explore your station</SheetDescription>
              </SheetHeader>
              <nav aria-label="Dashboard sections" className="more-sections">
                {VIEWS.map(([value, label, Icon]) => (
                  <button
                    type="button"
                    key={value}
                    onClick={() => navigate(value)}
                    aria-current={view === value ? 'page' : undefined}
                  >
                    <Icon size={21} />
                    <span>{label}</span>
                    <ChevronRight size={18} />
                  </button>
                ))}
                <form
                  method="post"
                  action="/auth/logout"
                  className="sign-out-form"
                >
                  <button type="submit">
                    <LogOut size={21} />
                    <span>Sign out</span>
                  </button>
                </form>
                <a
                  className="metric-reference"
                  href="https://github.com/wiedehopf/readsb/blob/v3.16.16/README-json.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  Metric definitions <ExternalLink size={15} />
                </a>
                <a
                  className="metric-reference"
                  href="https://docs.ramideltoro.com"
                  target="_blank"
                  rel="noreferrer"
                >
                  Project documentation <ExternalLink size={15} />
                </a>
              </nav>
            </SheetContent>
          </Sheet>
          <button
            className="brand"
            onClick={() => navigate('overview')}
            aria-label="Antenna Observatory overview"
          >
            <span className="brand-symbol">
              <RadioTower size={25} />
            </span>
            <div>
              Antenna<span>OBSERVATORY</span>
            </div>
          </button>
        </div>
        <div className="masthead-right">
          <span className="local-label">LIVE FROM YOUR ANTENNA</span>
          <span className={`status ${live ? 'good' : 'warn'}`}>
            <i />
            {live
              ? 'Receiving'
              : error
                ? 'Collector offline'
                : d.state === 'stale'
                  ? 'Receiver stale'
                  : 'Waiting for receiver'}
          </span>
        </div>
      </header>
      <main id="dashboard-content" tabIndex={-1}>
        <div className="page-heading">
          <div>
            <p className="eyebrow">
              <span className="station-dot" />
              {d.settings?.station_name || 'Receiver station'}
              <span className="station-hardware">
                <span className="separator">/</span> NESDR SMArt v5
              </span>
            </p>
            <h1>{TITLES[view]}</h1>
          </div>
          <div className="frequency">
            <Radio size={19} />
            <div>
              <small>MONITORING</small>
              <strong>
                1090.000 <span>MHz</span>
              </strong>
            </div>
          </div>
        </div>
        {error && (
          <div aria-live="polite" className="notice warning">
            {error}
          </div>
        )}
        {alerts.map((a) => (
          <div key={a} className="notice warning">
            <AlertTriangle size={16} />
            {a}
          </div>
        ))}
        {!data && (
          <div aria-live="polite" className="notice">
            Connecting to local receiver telemetry…
          </div>
        )}
        {view === 'overview' && (
          <>
            <section className="stats-grid">
              <Stat
                label="Aircraft receiving"
                icon={<Plane size={18} />}
                value={live ? fmt(m.aircraft) : '—'}
                note={`${fmt(m.with_position)} with a current position`}
              />
              <Stat
                label="Message rate"
                value={live ? fmt(m.message_rate, 1) : '—'}
                unit="/s"
                note="Accepted Mode S / ADS-B · live"
              />
              <Stat
                label="Signal power"
                icon={<Radio size={18} />}
                value={fmt(m.mean_signal, 1)}
                unit="dBFS"
                note="Mean decoded signal · last minute"
              />
              <Stat
                label="Airplanes.live"
                icon={<Wifi size={18} />}
                value={
                  error
                    ? 'Unknown'
                    : d.host?.feed_connected
                      ? 'Connected'
                      : 'Disconnected'
                }
                tone={d.host?.feed_connected && !error ? 'amber-text' : ''}
                note="Verified outbound TCP connection"
              />
            </section>
            <div className="overview-grid">
              <Panel
                title="Reception activity"
                note="Valid messages and decoded positions"
                aside={
                  <Badge>
                    <Clock3 size={13} />
                    Last {hours === '168' ? '7 days' : `${hours}h`}
                  </Badge>
                }
              >
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'message_rate',
                      label: 'Messages',
                      color: COLORS['ADS-B'],
                    },
                    {
                      key: 'position_rate',
                      label: 'Positions',
                      color: COLORS['Mode S'],
                    },
                  ]}
                />
              </Panel>
              <Panel
                title="Signal families"
                note="Decoded frames / second · trailing 60s"
                aside={<Radio size={18} />}
              >
                <FamilyBars data={d} onPick={selectFamily} />
              </Panel>
            </div>
            <div className="overview-grid">
              <Panel
                title="Live aircraft"
                note="Select an aircraft to inspect every decoded field"
                className="aircraft-summary"
                aside={
                  <Button variant="ghost" onClick={() => navigate('aircraft')}>
                    View all <ArrowUpRight />
                  </Button>
                }
              >
                <AircraftTable
                  items={allAircraft
                    .filter((a: Aircraft) => a.live)
                    .slice(0, 7)}
                  onSelect={setSelected}
                />
              </Panel>
              <SkyPlot
                data={d}
                onSelect={setSelected}
                onSettings={() => navigate('station')}
              />
            </div>
            <div className="health-strip">
              <span>
                <ShieldCheck size={17} />
                {fmt(m.samples_dropped)} dropped samples
              </span>
              <span>
                <Cpu size={17} />
                {fmt(m.cpu_percent, 1)}% decoder CPU
              </span>
              <span>
                <Activity size={17} />
                Gain {fmt(m.gain, 1)} dB
              </span>
              <span>
                <Clock3 size={17} />
                Telemetry {age(sourceAges)} old
              </span>
            </div>
          </>
        )}
        {view === 'signals' && (
          <>
            <div className="section-toolbar">
              <div>
                <h2>1090 MHz signal families</h2>
                <p>
                  All decoded formats from your local receiver. Zero means no
                  frames observed.
                </p>
              </div>
              <Badge>
                {d.beast_connected
                  ? 'Live frame stream'
                  : 'Frame stream disconnected'}
              </Badge>
            </div>
            <div className="signal-cards">
              {FAMILIES.map((name) => {
                const s: Partial<Signal> =
                  d.signals?.find((x: Signal) => x.name === name) || {};
                return (
                  <button
                    className={`signal-card ${family === name ? 'selected' : ''}`}
                    aria-pressed={family === name}
                    key={name}
                    onClick={() => setFamily(family === name ? 'All' : name)}
                    style={
                      { '--signal-color': COLORS[name] } as React.CSSProperties
                    }
                  >
                    <div>
                      <span className="signal-dot" />
                      {name}
                      <ArrowUpRight size={14} />
                    </div>
                    <strong>
                      {d.beast_connected ? fmt(s.rate, 1) : '—'}
                      <small>frames/s</small>
                    </strong>
                    <p>{DESCRIPTIONS[name]}</p>
                    <div className="signal-card-totals">
                      {fmt(s.frames)} observed
                      <span>{fmt(s.aircraft)} aircraft</span>
                    </div>
                  </button>
                );
              })}
            </div>
            <div className="section-toolbar">
              <Choice
                value={family}
                set={setFamily}
                items={['All', ...FAMILIES].map((x) => [x, x])}
              />
              <span className="caption">
                Counters since {time(d.collector_started)}
              </span>
            </div>
            <div className="content-grid">
              <Panel
                title="Downlink formats"
                note="Decoded Mode S frames observed by the local collector"
              >
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Format</TableHead>
                      <TableHead>Meaning</TableHead>
                      <TableHead>Last 60s</TableHead>
                      <TableHead>Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(d.formats || [])
                      .map((f: Format) =>
                        family === 'All'
                          ? f
                          : {
                              ...f,
                              count: f.families?.[family] || 0,
                              last60: f.last60_by_family?.[family] || 0,
                            },
                      )
                      .filter((f: Format) => f.count > 0)
                      .map((f: Format) => (
                        <TableRow key={f.df}>
                          <TableCell>
                            <span className="code-badge">DF{f.df}</span>
                          </TableCell>
                          <TableCell>{f.name}</TableCell>
                          <TableCell className="mono">
                            {fmt(f.last60)}
                          </TableCell>
                          <TableCell className="mono">{fmt(f.count)}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
                {family === 'Mode A/C' && (
                  <Empty>
                    Mode A/C uses legacy short replies rather than a Mode S
                    downlink format. These detections have no CRC validation.
                  </Empty>
                )}
              </Panel>
              <Panel
                title="Extended squitter contents"
                note="All ADS-B / ADS-R type codes · counts since collector start"
              >
                <div className="type-code-list">
                  {(d.type_codes || []).map(
                    (t: { code: number; name: string; count: number }) => (
                      <div key={t.code}>
                        <span className="code-badge">TC{t.code}</span>
                        <span>{t.name}</span>
                        <strong>{fmt(t.count)}</strong>
                      </div>
                    ),
                  )}
                  {!d.type_codes?.length && (
                    <Empty>No extended squitter contents observed yet.</Empty>
                  )}
                </div>
              </Panel>
            </div>
            <Panel
              title="Recent decoded frames"
              note={`${family === 'All' ? 'All families' : family} · most recent 100 frames across the stream`}
              className="spaced"
            >
              <div className="frame-stream">
                {frameList.slice(0, 25).map((f: Frame, i: number) => (
                  <div key={`${f.time}-${i}`}>
                    <span>{time(f.time)}</span>
                    <span style={{ color: COLORS[f.family] }}>{f.family}</span>
                    <code>{f.hex}</code>
                    <span>{fmt(f.rssi, 1)} dBFS</span>
                  </div>
                ))}
                {!frameList.length && (
                  <Empty>No recent frames in this family.</Empty>
                )}
              </div>
            </Panel>
            <div className="notice info">
              MLAT is not configured. UAT 978 MHz, airband voice, FM, and other
              bands are not being received while this radio is tuned to 1090
              MHz.
            </div>
          </>
        )}
        {view === 'aircraft' && (
          <>
            <section
              className="view-controls aircraft-controls"
              aria-label="Aircraft controls"
            >
              <div className="aircraft-controls-row">
                <div className="search">
                  <Search size={17} />
                  <Input
                    aria-label="Search callsign, hex, or squawk"
                    placeholder="Search callsign, hex, or squawk"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <div className="toolbar-actions">
                  <label className="switch-label" htmlFor="active-only">
                    <Switch
                      id="active-only"
                      checked={liveOnly}
                      onCheckedChange={setLiveOnly}
                    />
                    Active only
                  </label>
                  <a
                    className="download-button"
                    href="/api/export"
                    download="aircraft.csv"
                  >
                    <Download size={15} />
                    Export all CSV
                  </a>
                </div>
              </div>
              <div className="aircraft-filter-row">
                <Choice
                  value={family}
                  set={setFamily}
                  items={['All', ...FAMILIES].map((x) => [x, x])}
                />
                <span className="caption">
                  {filtered.length} matches · active = seen within 15 seconds
                </span>
              </div>
            </section>
            <Panel
              title="Received aircraft"
              note="Sort columns or select an aircraft for position, signal, navigation, and integrity details"
            >
              <AircraftTable
                items={filtered}
                onSelect={setSelected}
                sort={sort}
                setSort={setSort}
              />
            </Panel>
            <div className="spaced">
              <SkyPlot
                data={d}
                onSelect={setSelected}
                onSettings={() => navigate('station')}
              />
            </div>
          </>
        )}
        {view === 'receiver' && (
          <>
            <section className="stats-grid">
              <Stat
                label="Tuner gain"
                value={fmt(m.gain, 1)}
                unit="dB"
                note="Automatically adjusted by readsb"
              />
              <Stat
                label="Noise power"
                value={fmt(m.noise, 1)}
                unit="dBFS"
                note="Measured input noise · last minute"
              />
              <Stat
                label="Signal above noise"
                value={fmt(m.signal_above_noise, 1)}
                unit="dB"
                note="Derived: mean signal minus noise"
              />
              <Stat
                label="USB samples lost"
                value={fmt(m.samples_lost)}
                note="Cumulative since decoder restart"
              />
            </section>
            <div className="content-grid">
              <Panel
                title="Signal & noise"
                note="Absolute levels are relative to the ADC full scale"
              >
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'mean_signal',
                      label: 'Mean signal',
                      color: COLORS['ADS-B'],
                    },
                    { key: 'noise', label: 'Noise', color: COLORS['Mode S'] },
                  ]}
                  unit="dBFS"
                />
              </Panel>
              <Panel
                title="Hardware & process"
                note="Receiver and decoder measurements"
              >
                <Rows
                  rows={[
                    ['Receiver', d.hardware?.model],
                    ['USB serial', d.hardware?.serial],
                    ['Tuner', d.hardware?.tuner],
                    ['Center frequency', '1090 MHz'],
                    ['Sampling rate', '2.4 MS/s'],
                    ['Decoder', d.receiver?.version],
                    [
                      'Process',
                      `${d.host?.state || 'Unknown'} · PID ${d.host?.pid || '—'}`,
                    ],
                    [
                      'Decoder uptime',
                      age(Number(d.now) - Number(d.decoder_started)),
                    ],
                    ['Memory (resident)', `${fmt(m.memory_mb, 1)} MB`],
                    ['Process CPU', `${fmt(m.cpu_percent, 1)}% of one core`],
                    [
                      'Clock estimate',
                      `${fmt(m.ppm, 1)} ppm (estimated, not calibrated)`,
                    ],
                  ]}
                />
              </Panel>
              <Panel
                title="Decode quality"
                note={`Last minute · ${fmt(m.stats_window_s)}s window · stats ${age(d.stats_age_seconds)} old`}
              >
                <Rows
                  rows={[
                    [
                      'Accepted without correction',
                      `${fmt(m.clean_percent, 2)}%`,
                    ],
                    [
                      'Accepted with bit correction',
                      `${fmt(m.corrected_percent, 2)}%`,
                    ],
                    [
                      'Above −3 dBFS',
                      `${fmt(m.strong_percent, 2)}% of accepted messages`,
                    ],
                    ['Peak decoded signal', `${fmt(m.peak_signal, 1)} dBFS`],
                    [
                      'Accepted Mode S messages (session)',
                      fmt(m.valid_messages),
                    ],
                    ['Mode S preambles (session)', fmt(m.mode_s_preambles)],
                    ['Invalid candidates (last minute)', fmt(local.bad)],
                    ['Unknown ICAO candidates', fmt(local.unknown_icao)],
                    [
                      'USB samples processed (session)',
                      fmt(m.samples_processed),
                    ],
                    ['Samples dropped before decoding', fmt(m.samples_dropped)],
                  ]}
                />
                <p className="panel-explanation">
                  A preamble is only a candidate radio pulse. Invalid candidates
                  are expected and do not represent lost aircraft. Power values
                  are not calibrated dBm.
                </p>
              </Panel>
              <Panel
                title="Decoder CPU work"
                note="Time spent per subsystem during the last minute"
              >
                <div className="cpu-bars">
                  {Object.entries(cpu)
                    .filter(([, v]) => Number(v) > 0)
                    .map(([k, v]) => (
                      <div key={k}>
                        <span>{k.replaceAll('_', ' ')}</span>
                        <div>
                          <b
                            style={{
                              width: `${Math.min(100, (Number(v) / (duration * 1000)) * 100)}%`,
                            }}
                          />
                        </div>
                        <strong>
                          {fmt((Number(v) / (duration * 1000)) * 100, 2)}%
                        </strong>
                      </div>
                    ))}
                </div>
                <Rows
                  rows={[
                    ['Position decodes (session)', fmt(m.positions_total)],
                    ['Global CPR successes', fmt(statWindow.cpr?.global_ok)],
                    ['Relative CPR successes', fmt(statWindow.cpr?.local_ok)],
                    [
                      'Rejected position decodes',
                      fmt(statWindow.cpr?.global_bad),
                    ],
                    ['Filtered CPR messages', fmt(statWindow.cpr?.filtered)],
                  ]}
                />
              </Panel>
            </div>
            <Panel
              title="Measurement limits"
              note="What this hardware does and does not expose"
              className="spaced"
            >
              <div className="capability-grid">
                {[
                  ['Signal power & noise', 'Measured by the decoder'],
                  ['Packet types & error counts', 'Measured by the decoder'],
                  [
                    'Antenna SWR / impedance',
                    'Unavailable · requires RF test equipment',
                  ],
                  ['Receiver temperature', 'Unavailable · no exposed sensor'],
                  [
                    'Cable loss & antenna gain',
                    'Not directly measurable by this setup',
                  ],
                  [
                    'Wideband spectrum / waterfall',
                    'Unavailable while this receiver is dedicated to ADS-B',
                  ],
                ].map(([a, b]) => (
                  <div key={a}>
                    <strong>{a}</strong>
                    <p>{b}</p>
                  </div>
                ))}
              </div>
            </Panel>
          </>
        )}
        {view === 'feed' && (
          <>
            <section className="stats-grid">
              <Stat
                label="Airplanes.live TCP"
                value={
                  error
                    ? 'Unknown'
                    : d.host?.feed_connected
                      ? 'Connected'
                      : 'Disconnected'
                }
                tone={d.host?.feed_connected && !error ? 'amber-text' : ''}
                note={`Checked ${age(Number(d.now) - Number(d.host?.checked_at))} ago`}
              />
              <Stat
                label="Position decodes"
                value={live ? fmt(m.position_rate, 2) : '—'}
                unit="/s"
                note="Local decoder · last minute"
              />
              <Stat
                label="MLAT"
                value="Not configured"
                note="No multilateration client installed"
              />
              <Stat
                label="Service uptime"
                value={age(Number(d.now) - Number(d.decoder_started))}
                note="Restarts automatically after login"
              />
            </section>
            <Panel
              title="Data path"
              note="Connection status is verified from this Mac’s actual sockets"
            >
              <div className="feed-path">
                <div>
                  <RadioTower />
                  <strong>Nooelec receiver</strong>
                  <span>
                    {live ? 'Receiving 1090 MHz' : 'No fresh telemetry'}
                  </span>
                </div>
                <ArrowUpRight />
                <div>
                  <Cpu />
                  <strong>readsb</strong>
                  <span>{d.host?.state || 'Unknown'} · 2.4 MS/s</span>
                </div>
                <ArrowUpRight />
                <div>
                  <Wifi />
                  <strong>airplanes.live</strong>
                  <span>
                    {d.host?.feed_connected
                      ? 'TCP established'
                      : 'Not connected'}{' '}
                    · port 30004
                  </span>
                </div>
              </div>
            </Panel>
            <div className="content-grid spaced">
              <Panel
                title="Feed configuration"
                note="This dashboard does not change your destination"
              >
                <Rows
                  rows={[
                    ['Destination', 'feed.airplanes.live:30004'],
                    ['Format', 'BeastReduce+'],
                    [
                      'Receiver ID',
                      <code className="wrap" key="uuid">
                        {d.hardware?.feeder_id}
                      </code>,
                    ],
                    ['Automatic start', 'At user login'],
                    [
                      'Local frame stream',
                      d.beast_connected
                        ? 'Connected · loopback only'
                        : 'Disconnected',
                    ],
                    ['Local frame endpoint', '127.0.0.1:30905'],
                  ]}
                />
                <div className="panel-bottom">
                  <span>Confirm reception at the destination.</span>
                  <a
                    href="https://airplanes.live/myfeed/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open MyFeed <ExternalLink size={14} />
                  </a>
                </div>
              </Panel>
              <Panel
                title="Established connections"
                note="Outbound feed and local observatory connection"
              >
                <div className="connections">
                  {(d.host?.connections || []).map((c: string) => (
                    <div key={c}>
                      <span className="signal-dot" />
                      <code>{c}</code>
                    </div>
                  ))}
                  {!d.host?.connections?.length && (
                    <Empty>No established decoder TCP connections.</Empty>
                  )}
                </div>
                <p className="panel-explanation">
                  A TCP connection confirms transport, not server acceptance of
                  every frame. MyFeed provides the server-side view. Its MLAT
                  badge does not establish that this Mac has an MLAT client.
                </p>
              </Panel>
            </div>
          </>
        )}
        {view === 'history' && (
          <>
            <div className="section-toolbar">
              <div>
                <h2>Your reception, over time</h2>
                <p>
                  {hist.started
                    ? `Recording since ${new Date(hist.started * 1000).toLocaleString()}`
                    : 'Waiting for the first history sample'}{' '}
                  · 7-day rolling retention
                </p>
              </div>
              {rangePicker}
            </div>
            {historyError && <div className="notice">{historyError}</div>}
            <div className="content-grid">
              <Panel
                title="Messages & positions"
                note="Real samples every 10 seconds; gaps are left empty"
              >
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'message_rate',
                      label: 'Messages',
                      color: COLORS['ADS-B'],
                    },
                    {
                      key: 'position_rate',
                      label: 'Positions',
                      color: COLORS['Mode S'],
                    },
                  ]}
                />
              </Panel>
              <Panel
                title="Aircraft receiving"
                note="Active targets and current positions"
              >
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'aircraft',
                      label: 'Aircraft',
                      color: COLORS['Mode S'],
                    },
                    {
                      key: 'with_position',
                      label: 'Positioned',
                      color: COLORS['ADS-B'],
                    },
                  ]}
                  unit="aircraft"
                />
              </Panel>
              <Panel
                title="Power & noise"
                note="Relative digital power; no fabricated historical values"
              >
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'mean_signal',
                      label: 'Signal',
                      color: COLORS['ADS-B'],
                    },
                    { key: 'noise', label: 'Noise', color: COLORS['Mode S'] },
                  ]}
                  unit="dBFS"
                />
              </Panel>
              <Panel
                title="Signal family activity"
                note="Trailing 60-second frame rates"
              >
                <Chart
                  points={points}
                  series={FAMILIES.map((name) => ({
                    key: `signals.${name}`,
                    label: name,
                    color: COLORS[name],
                  }))}
                  unit="frames / second"
                />
              </Panel>
              <Panel title="Gain adjustment" note="Automatic receiver gain">
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'gain',
                      label: 'Tuner gain',
                      color: COLORS['ADS-R'],
                    },
                  ]}
                  unit="dB"
                />
              </Panel>
              <Panel
                title="Decoder CPU"
                note="100% corresponds to one CPU core"
              >
                <Chart
                  points={points}
                  series={[
                    {
                      key: 'cpu_percent',
                      label: 'CPU',
                      color: COLORS['TIS-B'],
                    },
                  ]}
                  unit="percent"
                />
              </Panel>
            </div>
          </>
        )}
        {view === 'events' && (
          <>
            <div className="section-toolbar">
              <div>
                <h2>Receiver timeline</h2>
                <p>
                  Connection transitions and observatory changes stored on this
                  Mac
                </p>
              </div>
              <Choice
                value={eventFilter}
                set={setEventFilter}
                items={[
                  ['all', 'All events'],
                  ['warning', 'Warnings'],
                ]}
              />
            </div>
            <Panel title="Events" note="Newest first">
              <div className="event-list">
                {(d.events || [])
                  .filter(
                    (e: ReceiverEvent) =>
                      eventFilter === 'all' || e.level === 'warning',
                  )
                  .map((e: ReceiverEvent, i: number) => (
                    <div key={`${e.time}-${i}`}>
                      <span className={`event-dot ${e.level}`} />
                      <time>{new Date(e.time * 1000).toLocaleString()}</time>
                      <span>{e.message}</span>
                    </div>
                  ))}
                {!(d.events || []).some(
                  (e: ReceiverEvent) =>
                    eventFilter === 'all' || e.level === 'warning',
                ) && <Empty>No matching events recorded.</Empty>}
              </div>
            </Panel>
            <Panel
              title="Decoder log"
              note="Last 150 lines · refreshes every 10 seconds"
              className="spaced"
            >
              <pre className="log-output">
                {logError ||
                  logs.join('\n') ||
                  'No decoder log entries available.'}
              </pre>
            </Panel>
          </>
        )}
        {view === 'inspector' && (
          <>
            <section
              className="view-controls inspector-controls"
              aria-label="Telemetry controls"
            >
              <div className="inspector-source">
                <span className="control-label">Telemetry source</span>
                <Choice
                  value={inspect}
                  set={setInspect}
                  items={[
                    ['stats', 'Decoder statistics'],
                    ['receiver', 'Receiver metadata'],
                    ['raw_aircraft', 'Aircraft JSON'],
                    ['host', 'Process & sockets'],
                  ]}
                />
              </div>
              <div className="inspector-search">
                <label className="control-label" htmlFor="telemetry-search">
                  Search fields
                </label>
                <div className="search">
                  <Search size={16} />
                  <Input
                    id="telemetry-search"
                    value={inspectQuery}
                    onChange={(e) => setInspectQuery(e.target.value)}
                    placeholder="Find a field or value"
                    aria-label="Find telemetry field"
                  />
                </div>
              </div>
            </section>
            <Panel
              title="Every exposed field"
              note="Original decoder values. Missing fields mean unavailable, not zero."
            >
              <div className="inspector-table">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Field</TableHead>
                      <TableHead>Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {flatten(
                      d[
                        inspect as
                          | 'stats'
                          | 'receiver'
                          | 'raw_aircraft'
                          | 'host'
                      ] || {},
                    )
                      .filter(([k, v]) =>
                        `${k} ${JSON.stringify(v)}`
                          .toLowerCase()
                          .includes(inspectQuery.toLowerCase()),
                      )
                      .map(([k, v]) => (
                        <TableRow key={k}>
                          <TableCell>
                            <code>{k}</code>
                          </TableCell>
                          <TableCell>
                            <code>
                              {typeof v === 'object'
                                ? JSON.stringify(v)
                                : textValue(v)}
                            </code>
                          </TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </div>
            </Panel>
            <details className="raw-details">
              <summary>Complete source JSON</summary>
              <pre>
                {JSON.stringify(
                  d[
                    inspect as 'stats' | 'receiver' | 'raw_aircraft' | 'host'
                  ] || {},
                  null,
                  2,
                )}
              </pre>
            </details>
          </>
        )}
        {view === 'station' && (
          <div className="content-grid">
            <Panel
              title="Station details"
              note="Stored locally. Coordinates are used only for this dashboard’s range and bearing."
            >
              <form className="station-form" onSubmit={saveStation}>
                <label htmlFor="station-name">
                  Station name
                  <Input
                    id="station-name"
                    disabled={!d.settings_editable}
                    required
                    maxLength={80}
                    value={form.station_name}
                    onChange={(e) =>
                      setForm({ ...form, station_name: e.target.value })
                    }
                  />
                </label>
                <div className="form-grid">
                  <label htmlFor="station-latitude">
                    Latitude
                    <Input
                      type="number"
                      id="station-latitude"
                      disabled={!d.settings_editable}
                      min="-90"
                      max="90"
                      step="any"
                      placeholder="e.g. 28.00000"
                      value={form.latitude}
                      onChange={(e) =>
                        setForm({ ...form, latitude: e.target.value })
                      }
                    />
                  </label>
                  <label htmlFor="station-longitude">
                    Longitude
                    <Input
                      type="number"
                      id="station-longitude"
                      disabled={!d.settings_editable}
                      min="-180"
                      max="180"
                      step="any"
                      placeholder="e.g. −82.00000"
                      value={form.longitude}
                      onChange={(e) =>
                        setForm({ ...form, longitude: e.target.value })
                      }
                    />
                  </label>
                </div>
                <p>
                  Use the antenna’s actual location. Leave both coordinates
                  blank if you don’t want distance calculations. This does not
                  configure MLAT. Saved coordinates are visible in the protected
                  dashboard.
                </p>
                {!d.settings_editable && (
                  <p>
                    To edit station details, open http://127.0.0.1:8787 on your
                    Mac.
                  </p>
                )}
                <Button type="submit" disabled={saving || !d.settings_editable}>
                  {saving ? 'Saving…' : 'Save station details'}
                </Button>
                {saved && (
                  <p aria-live="polite" className="save-result">
                    {saved}
                  </p>
                )}
              </form>
            </Panel>
            <Panel
              title="How your observatory operates"
              note="One receiver. Live data collected on your Mac."
            >
              <Rows
                rows={[
                  ['Receiver', 'Nooelec NESDR SMArt v5'],
                  ['Radio mode', '1090 MHz aircraft reception'],
                  ['Local dashboard', 'http://127.0.0.1:8787'],
                  ['Remote dashboard', 'https://antenna.ramideltoro.com'],
                  ['Remote access', 'Private · username and password required'],
                  ['History retention', '7 days, recorded every 10 seconds'],
                  ['Page refresh', 'Every 2 seconds'],
                  [
                    'Receiver statistics',
                    'Updated by readsb, approximately every 10 seconds',
                  ],
                  ['Frame counts', 'Since observatory collector start'],
                  [
                    'Background operation',
                    'While you are logged in; display can be locked',
                  ],
                ]}
              />
              <p className="panel-explanation">
                Keep your Mac awake and the receiver connected. Other radio
                frequencies need a second receiver or an intentional pause of
                the airplane feed.
              </p>
            </Panel>
          </div>
        )}
      </main>
      <footer className="site-footer">
        <span>Antenna Observatory</span>
        <nav aria-label="Project links">
          <a
            href="https://docs.ramideltoro.com"
            target="_blank"
            rel="noreferrer"
          >
            Documentation &amp; project wiki <ExternalLink size={14} />
          </a>
          <a
            href="https://github.com/ramideltoro/antenna_observatory"
            target="_blank"
            rel="noreferrer"
          >
            Source code <ExternalLink size={14} />
          </a>
        </nav>
      </footer>
      <Sheet
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="aircraft-sheet">
          <SheetHeader>
            <SheetTitle>
              {current?.flight || current?.hex?.toUpperCase() || 'Aircraft'}
            </SheetTitle>
            <SheetDescription>
              {current?.hex?.toUpperCase()} · {current?.family} ·{' '}
              {allAircraft.some((a: Aircraft) => a.hex === current?.hex)
                ? `last seen ${fmt(current?.seen, 1)}s ago`
                : 'No longer in the current receiver snapshot'}
            </SheetDescription>
          </SheetHeader>
          {current && (
            <div className="detail-body">
              <h3>Position & movement</h3>
              <Rows
                rows={[
                  ['Latitude', fmt(current.lat, 5)],
                  ['Longitude', fmt(current.lon, 5)],
                  ['Position age', `${fmt(current.seen_pos, 1)}s`],
                  [
                    'Barometric altitude',
                    typeof current.alt_baro === 'number'
                      ? `${fmt(current.alt_baro)} ft`
                      : current.alt_baro,
                  ],
                  [
                    'GNSS altitude',
                    current.alt_geom == null
                      ? '—'
                      : `${fmt(current.alt_geom)} ft`,
                  ],
                  [
                    'Ground speed',
                    current.gs == null ? '—' : `${fmt(current.gs, 1)} kt`,
                  ],
                  [
                    'Track',
                    current.track == null ? '—' : `${fmt(current.track, 1)}°`,
                  ],
                  [
                    'Vertical rate',
                    current.baro_rate == null
                      ? '—'
                      : `${fmt(current.baro_rate)} ft/min`,
                  ],
                  [
                    'Range from station',
                    current.distance_nm == null
                      ? 'Set station coordinates'
                      : `${fmt(current.distance_nm, 1)} nm`,
                  ],
                  [
                    'Bearing',
                    current.bearing == null ? '—' : `${fmt(current.bearing)}°`,
                  ],
                ]}
              />
              <h3>Signal & identity</h3>
              <Rows
                rows={[
                  ['Received power', `${fmt(current.rssi, 1)} dBFS`],
                  ['Accepted messages', fmt(current.messages)],
                  ['Squawk', current.squawk],
                  ['Emergency status', current.emergency],
                  ['Emitter category', current.category],
                  ['Source type', current.type],
                  ['ADS-B version', current.version],
                ]}
              />
              <h3>All decoded fields</h3>
              <pre className="raw-aircraft">
                {JSON.stringify(current, null, 2)}
              </pre>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
