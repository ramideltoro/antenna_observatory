export interface Aircraft extends Record<string, unknown> {
  hex: string;
  flight: string;
  family: string;
  live: boolean;
  type?: string;
  lat?: number;
  lon?: number;
  seen: number;
  seen_pos?: number;
  distance_nm?: number | null;
  bearing?: number | null;
  alt_baro?: number | string;
  alt_geom?: number;
  gs?: number;
  track?: number;
  baro_rate?: number;
  rssi?: number;
  messages?: number;
  squawk?: string;
  emergency?: string;
  category?: string;
  version?: number;
}
export interface Signal {
  name: string;
  rate: number | null;
  frames: number;
  last60: number;
  aircraft: number;
}
export interface Frame {
  time: number;
  family: string;
  hex: string;
  rssi: number | null;
  df: number | null;
  type_code: number | null;
}
export interface Format {
  df: number;
  name: string;
  count: number;
  last60: number;
  families: Record<string, number>;
  last60_by_family: Record<string, number>;
}
export interface ReceiverEvent {
  time: number;
  level: string;
  message: string;
}
export interface HealthScore {
  score: number;
  status: string;
  components: Record<string, number>;
  reasons: string[];
  baseline_message_rate?: number | null;
}
export interface SmartAlert {
  code: string;
  severity: 'warning' | 'critical' | 'info';
  title: string;
  message: string;
}
export interface CoverageBand {
  bins: { bearing: number; max_range: number; positions: number }[];
  max_range: number | null;
  median_range: number | null;
  positions: number;
  aircraft: number;
  sectors_observed: number;
}
export interface CoverageData {
  hours: number;
  bands: Record<string, CoverageBand>;
}
export interface TrackPoint {
  ts: number;
  hex: string;
  flight: string;
  lat: number;
  lon: number;
  altitude?: number | null;
  speed?: number | null;
  heading?: number | null;
  distance_nm?: number | null;
  bearing?: number | null;
  rssi?: number | null;
  family: string;
}
export interface ReplayData {
  hours: number;
  bucket_seconds: number;
  points: TrackPoint[];
}
export interface Encounter {
  hex: string;
  first_seen: number;
  last_seen: number;
  sightings: number;
  observations: number;
  flight: string;
  family: string;
  aircraft_type?: string;
  squawk?: string;
  emergency?: string;
  category?: string;
  max_distance?: number | null;
  closest_distance?: number | null;
  strongest_rssi?: number | null;
  max_altitude?: number | null;
  last_lat?: number | null;
  last_lon?: number | null;
}
export interface DailyReport {
  day: string;
  samples: number;
  availability_percent?: number | null;
  average_message_rate?: number | null;
  peak_message_rate?: number | null;
  peak_aircraft?: number | null;
  average_signal?: number | null;
  unique_aircraft: number;
  positions: number;
  max_range?: number | null;
}
export interface HistogramBin {
  from: number;
  to: number;
  count: number;
}
export interface LabData {
  hours: number;
  rssi: HistogramBin[];
  altitude: HistogramBin[];
  range: HistogramBin[];
  baselines: Record<string, number | null>;
  frames_analyzed: number;
  positions_analyzed: number;
}
export interface MaintenanceEntry {
  id: number;
  ts: number;
  title: string;
  details: string;
  category: string;
}
export interface SpectrumData {
  available: boolean;
  configured: boolean;
  reason?: string;
  updated_at?: number;
  age_seconds?: number;
  center_mhz: number;
  span_mhz: number;
  frequencies?: number[];
  lines: { ts: number; values: number[] }[];
}
export interface DecoderWindow {
  start?: number;
  end?: number;
  local?: Record<string, number>;
  cpu?: Record<string, number>;
  cpr?: Record<string, number>;
}
export interface Snapshot {
  settings_editable: boolean;
  now: number;
  state: string;
  source_time: number;
  age_seconds: number;
  stats_age_seconds?: number;
  collector_started: number;
  decoder_started: number;
  settings: {
    station_name: string;
    latitude: number | null;
    longitude: number | null;
  };
  metrics: Record<string, number | null>;
  aircraft: Aircraft[];
  signals: Signal[];
  formats: Format[];
  type_codes: { code: number; name: string; count: number }[];
  recent_frames: Frame[];
  events: ReceiverEvent[];
  health_score?: HealthScore;
  smart_alerts?: SmartAlert[];
  spectrum?: SpectrumData;
  host: {
    pid?: number;
    state?: string;
    cpu_percent?: number;
    memory_mb?: number;
    feed_connected?: boolean;
    connections?: string[];
    checked_at?: number;
  };
  beast_connected: boolean;
  receiver: { version?: string };
  stats: { last1min?: DecoderWindow; total?: DecoderWindow };
  raw_aircraft: Record<string, unknown>;
  frame_pipeline: {
    state?: string;
    last_captured_at?: number | null;
    last_uploaded_at?: number | null;
    last_processed_at?: number | null;
    pending_batches?: number;
    server_pending_batches?: number;
    spool_bytes?: number;
    oldest_pending_age_s?: number | null;
    gap_count?: number;
    failed_batches?: number;
    last_error?: string | null;
  };
  hardware: {
    model: string;
    serial: string;
    tuner: string;
    frequency_mhz: number;
    sample_rate_msps: number;
    feeder_id: string;
    mlat_configured: boolean;
    modeac_enabled: boolean;
  };
}
export interface HistoryPoint extends Record<string, unknown> {
  ts: number;
}
export interface HistoryData {
  points: HistoryPoint[];
  started?: number;
  hours?: number;
  retention_days?: number;
}
export interface Sort {
  key: string;
  asc: boolean;
}
export interface StationForm {
  station_name: string;
  latitude: number | string;
  longitude: number | string;
}
export interface BrowserTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations: Record<string, boolean>;
  execute: (input: Record<string, unknown>) => unknown;
}
export interface ToolContext {
  registerTool: (
    tool: BrowserTool,
    options: { signal: AbortSignal },
  ) => unknown;
}
