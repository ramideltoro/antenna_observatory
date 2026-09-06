# API reference

The browser uses same-origin HTTP endpoints. Read endpoints are public and require no session cookie. They support the dashboard rather than a versioned third-party API, so consumers should expect response shapes to evolve with the application.

## Routes

| Method | Path                         | Access                        | Purpose                                                             |
| ------ | ---------------------------- | ----------------------------- | ------------------------------------------------------------------- |
| GET    | `/login`                     | Public                        | Redirect legacy bookmarks to `/`                                    |
| GET    | `/api/snapshot`              | Public                        | Latest aircraft, signals, metrics, events, host, and hardware state |
| GET    | `/api/history?hours=1`       | Public                        | One to 168 hours of downsampled stored measurements                 |
| GET    | `/api/logs`                  | Public                        | Bounded decoder log tail                                            |
| GET    | `/api/export`                | Public                        | Aircraft snapshot as CSV                                            |
| GET    | `/api/health`                | Public                        | Application health and collector start time                         |
| POST   | `/api/settings`              | Local loopback + local origin | Validate and update station name and coordinates                    |
| GET    | `/api/uplink`                | Local loopback bearer token   | Snapshot envelope for the Mac uploader                              |
| POST   | `/api/ingest`                | Relay bearer token            | Accept a validated Mac telemetry envelope                           |
| PUT    | `/api/ingest/beast/{sha256}` | Relay bearer token            | Durably accept an idempotent Zstandard Beast batch                  |

## Snapshot state

```mermaid
classDiagram
    class Snapshot {
      number now
      string state
      number source_time
      number age_seconds
      Metrics metrics
      Aircraft[] aircraft
      Signal[] signals
      Event[] events
      Host host
      Hardware hardware
    }
    class Metrics {
      number aircraft
      number message_rate
      number mean_signal
      number noise
      number gain
      number samples_lost
      number cpu_percent
    }
    class Aircraft {
      string hex
      string flight
      string family
      number alt_baro
      number gs
      number lat
      number lon
      number rssi
      boolean live
    }
    Snapshot --> Metrics
    Snapshot --> Aircraft
```

Unknown values are represented as JSON `null` or absent source fields. Consumers must not interpret a missing measurement as zero.

`frame_pipeline` in the snapshot reports capture, upload, processing, local spool, backlog, failed-batch, and data-gap state. Beast upload URLs use the lowercase SHA-256 of the exact compressed request body. The relay acknowledges only after validating the checksum, bounded decompression, Beast framing, and durable atomic storage.

Beast uploads use `Content-Type: application/zstd`, have a 16 MiB compressed-body limit, and are safe to retry. Repeating an accepted hash returns success without inserting duplicate frames.

## Error behavior

| Status | Meaning                                                    |
| -----: | ---------------------------------------------------------- |
|    303 | Legacy `/login` redirect back to the application           |
|    400 | Invalid request size, shape, range, or encoding            |
|    401 | Missing or invalid relay token                             |
|    403 | Invalid hostname/origin/path or remote-only setting change |
|    404 | Unknown endpoint or unavailable static asset               |
