# Receiver intelligence

The observatory turns current aircraft telemetry into useful station history while preserving the distinction between a measured value, a derived value, and an unavailable value.

## Feature map

```mermaid
mindmap
  root((Receiver intelligence))
    Coverage
      5 degree sectors
      Altitude bands
      Maximum range
    Replay
      Track trails
      Playhead
      1h to 7d
    Encounters
      First and last seen
      Sightings
      Range records
      Favorites
    Health
      Availability
      Radio margin
      Decoder quality
      Activity
    Alerts
      Stale telemetry
      Feed and stream
      Noise and traffic
      Sample loss and overload
      Emergency transponders
    Reports
      Daily aircraft
      Availability
      Message rate
      Range
    Laboratory
      Power histogram
      Range histogram
      Altitude histogram
      Six-hour baselines
    Operations
      Maintenance notes
      Mobile PWA
      Optional spectrum
```

## Historical coverage

Every positioned track contributes its station-relative bearing and distance. Bearings are assigned to 72 sectors, each five degrees wide. The polar outline joins the maximum measured distance in each sector.

```mermaid
flowchart LR
    P[Aircraft position] --> G[Distance and bearing]
    G --> B[5 degree sector]
    B --> X{Altitude}
    X -->|below 10,000 ft| L[Low band]
    X -->|10,000–24,999 ft| M[Mid band]
    X -->|25,000 ft or more| H[High band]
    X --> A[All altitudes]
    L --> O[Polar outline]
    M --> O
    H --> O
    A --> O
```

The shape is an observed reception envelope, not a prediction of RF propagation. Aircraft availability, altitude, terrain, buildings, antenna placement, and traffic routes all affect it.

## Flight time machine

Replay groups positions by aircraft and moves a playhead through retained time. Trails show the received path relative to the station. Resolution becomes coarser for longer ranges to bound browser and network work.

```mermaid
sequenceDiagram
    participant DB as Track database
    participant API as Replay API
    participant UI as Browser
    UI->>API: Request 6 hours
    API->>DB: Bucket by 20 seconds and aircraft
    DB-->>API: Measured positions
    API-->>UI: At most 25,000 points
    loop Playback
      UI->>UI: Advance playhead
      UI->>UI: Draw trails and current markers
    end
```

## Encounter history

An encounter is a rollup for one ICAO address within the seven-day retention window. Observations fewer than 15 minutes apart belong to one sighting. A later return increments the sighting count. The rollup retains first and last seen times, observation count, closest and farthest range, strongest decoded power, maximum altitude, and recent identity fields.

Favorites are stored in the browser’s local storage. They are a display preference and are not sent with telemetry.

## Antenna health score

```mermaid
pie showData
    title Maximum health contribution
    "Availability" : 40
    "Radio margin" : 25
    "Decoder quality" : 20
    "Reception activity" : 15
```

| Component       | Maximum | Inputs                                                                 |
| --------------- | ------: | ---------------------------------------------------------------------- |
| Availability    |      40 | Fresh telemetry, local Beast stream, airplanes.live TCP connection     |
| Radio margin    |      25 | Mean decoded signal minus decoder noise floor                          |
| Decoder quality |      20 | Sample loss and percentage of accepted messages above −3 dBFS          |
| Activity        |      15 | Nonzero message rate and comparison with the six-hour live-data median |

Status bands are **Excellent** at 90 or above, **Healthy** at 75–89, **Attention** at 55–74, and **Critical** below 55. A quiet air-traffic period does not by itself zero the score because activity contributes only 15 points.

## Smart alerts

```mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Active: rule becomes true
    Active --> Active: condition remains true
    Active --> Cleared: measurement recovers
    Cleared --> Normal
```

Rules cover stale telemetry, Beast stream loss, airplanes.live disconnect, tuner sample loss, strong-signal overload, a noise-floor rise greater than 6 dB over its six-hour median, message rate below 25% of a meaningful baseline, and emergency transponder state or squawk 7500/7600/7700.

Browser notifications are optional. They appear for new conditions while the dashboard or installed app is open. The event log retains alert transitions for seven days.

## Daily reports and signal laboratory

Daily reports group real ten-second samples and track points by the server’s local calendar day. They show availability, average and peak message rate, peak simultaneous aircraft, average decoded power, unique aircraft, position count, and maximum range.

The signal laboratory presents distributions rather than a single average:

```mermaid
flowchart TD
    F[Recent Beast frame power] --> RH[RSSI histogram]
    T[Stored track points] --> AH[Altitude histogram]
    T --> DH[Range histogram]
    S[Live history samples] --> BL[Median baselines]
    RH --> LAB[Signal laboratory]
    AH --> LAB
    DH --> LAB
    BL --> LAB
```

## Maintenance annotations

Use annotations to explain a measurable change. Useful entries include antenna relocation, element extension, coax or adapter replacement, gain changes, receiver replacement, macOS or readsb updates, weather damage, and outages. Changes are accepted only from the loopback dashboard on the receiver Mac, validated, and mirrored to the hosted timeline through the protected telemetry uplink.

## Progressive web app

```mermaid
flowchart LR
    B[Browser] --> I[Install prompt]
    I --> P[Standalone amber app]
    P --> N[Network-only service worker]
    N --> S[Public dashboard]
    S --> L[Live telemetry views]
```

The service worker intentionally has no cache handler because offline telemetry would be stale. The app icon, standalone display, and mobile layout remain available when the browser supports installation.

## Spectrum waterfall

One SDR cannot continuously decode 1090 MHz while also retuning for a spectrum sweep. The observatory protects the primary receiver and enables the waterfall only when a second serial-numbered device writes valid sidecar data.

```mermaid
flowchart LR
    A[Primary SDR] --> R[readsb] --> AL[airplanes.live]
    B[Optional second SDR] --> RP[rtl_power]
    RP --> SC[Spectrum sidecar]
    SC --> W[Bounded waterfall JSON]
    W --> C[Collector snapshot]
    C --> U[Protected telemetry uplink]
    U --> UI[Spectrum view]
```

The sidecar checks that its selected device differs from the protected readsb serial before invoking `rtl_power`. A missing second receiver produces an explanatory readiness view and never pauses the active feed.
