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
