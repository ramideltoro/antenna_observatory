# Data pipeline

## End-to-end flow

```mermaid
sequenceDiagram
    participant Radio as 1090 MHz radio
    participant Readsb as readsb on receiver host
    participant Collector as Local collector
    participant Uploader as HTTPS uploader
    participant Frames as Frame uploader
    participant Relay as Remote relay
    participant Browser as Dashboard browser
    participant AL as airplanes.live

    Radio->>Readsb: IQ samples at 2.4 MS/s
    Readsb->>AL: BeastReduce+ frames
    Readsb->>Readsb: Rotate zstd Beast dump every two minutes
    Readsb->>Collector: aircraft.json, stats.json, receiver.json
    Readsb->>Collector: Beast frames on 127.0.0.1:30905
    loop Every second
      Collector->>Collector: Classify frames and compute live snapshot
    end
    loop Every two seconds
      Uploader->>Collector: GET /api/uplink with bearer token
      Collector-->>Uploader: Snapshot and bounded log tail
      Uploader->>Relay: POST /api/ingest with bearer token
      Relay->>Relay: Validate, sanitize, and persist
      Relay->>Relay: Update tracks, encounters, health, and alerts
    end
    loop Oldest completed batch first
      Frames->>Frames: Validate and claim into durable spool
      Frames->>Relay: PUT /api/ingest/beast/{sha256}
      Relay->>Relay: Verify, atomically store, and acknowledge
      Frames->>Frames: Delete only after matching acknowledgement
      Relay->>Relay: Index every frame asynchronously
    end
    loop Every two seconds
      Browser->>Relay: Public GET /api/snapshot
      Relay-->>Browser: Latest telemetry
    end
```

## Collector inputs

| Source                             | Contents                                                 | Typical update   |
| ---------------------------------- | -------------------------------------------------------- | ---------------- |
| `aircraft.json`                    | Aircraft fields, seen ages, positions, message totals    | 1 second         |
| `stats.json`                       | Decoder counters, gain, signal, noise, samples, CPU work | About 10 seconds |
| `receiver.json`                    | Decoder identity and runtime metadata                    | Decoder-managed  |
| Beast TCP 30005 (Pi) / 30905 (Mac) | Raw framed Mode S messages with signal byte              | Continuous       |
| Host process inspection            | PID, state, memory, CPU, established sockets             | 10 seconds       |

The collector calculates current message rate from consecutive aircraft snapshots. It classifies recent Beast frames, measures per-family rate over the trailing 60 seconds, and preserves `null` when a measurement is unavailable. It never fills telemetry gaps with invented values.

## Signal classification

```mermaid
flowchart TD
    F[Beast frame] --> DF{Downlink format}
    DF -->|DF17| ES[Extended squitter]
    DF -->|DF18| CF{Control field}
    DF -->|Other Mode S DF| MS[Mode S]
    DF -->|Mode A/C frame| AC[Mode A/C]
    ES -->|Valid aircraft broadcast| ADSB[ADS-B]
    CF -->|TIS-B control field| TISB[TIS-B]
    CF -->|ADS-R control field| ADSR[ADS-R]
    CF -->|Other| OTHER[Other]
```

See the [signal guide](signals.md) for field semantics and measurement limits.

## Uplink envelope

The uploader requests a protected local endpoint, then posts a bounded JSON object to the remote relay:

```json
{
  "snapshot": {
    "now": 0,
    "state": "live",
    "metrics": {},
    "aircraft": [],
    "signals": [],
    "events": [],
    "host": {},
    "hardware": {}
  },
  "logs": []
}
```

The relay rejects missing collections, non-finite timestamps, oversized requests, malformed logs, and incorrect bearer tokens. It copies the accepted object through strict JSON serialization before storing it.

## Complete decoded-frame archive

`readsb --dump-beast` writes every accepted Mode A/C, Mode S, and ADS-B frame with receiver ticks, signal byte, and synthetic wall-clock markers. The frame uploader never touches the SDR or changes the direct airplanes.live connector. It validates completed Zstandard files, moves them into a restart-safe spool, and uploads them oldest-first with content-addressed identities.

The relay validates each compressed batch before durable acknowledgement, then a background worker indexes its frames transactionally. Duplicate PUT requests are successful no-ops. Processed batches and frame rows expire after 72 hours; aggregate dashboard samples retain their existing seven-day window.

## Retention and freshness

```mermaid
stateDiagram-v2
    [*] --> Waiting
    Waiting --> Live: first fresh snapshot
    Live --> Stale: no uplink for 10 seconds
    Stale --> Live: uplink resumes
    Live --> Live: store sample every 10 seconds
    Stale --> Stale: keep last known values marked stale
```

Charts downsample long ranges to at most roughly 480 plotted points. Buckets containing stale data or gaps over 30 seconds retain a gap in reception-dependent series.

Track replay changes resolution with the requested range: ten seconds for one hour, twenty seconds for six hours, one minute for one day, and five minutes for seven days. Coverage uses 72 five-degree sectors. Encounter sessions increment only after a target has been absent for more than 15 minutes.
