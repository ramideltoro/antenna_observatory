# Architecture

The system separates radio decoding, transport, presentation, and documentation. The Mac remains the source of truth for live RF data; the Linux relay is the source of truth for remotely visible telemetry history.

## System context

```mermaid
C4Context
    title Antenna Observatory system context
    Person(owner, "Owner", "Uses the private dashboard")
    System(obs, "Antenna Observatory", "Collects, stores, and presents aircraft receiver telemetry")
    System_Ext(airplanes, "airplanes.live", "Receives BeastReduce+ aircraft messages")
    System_Ext(github, "GitHub", "Version control, CI/CD, and documentation hosting")
    System_Ext(cloudflare, "Cloudflare", "DNS and encrypted tunnel ingress")
    Rel(owner, obs, "Views", "HTTPS")
    Rel(obs, airplanes, "Feeds decoded frames", "TCP 30004")
    Rel(github, obs, "Deploys tested releases", "SSH")
    Rel(cloudflare, obs, "Routes dashboard traffic", "Tunnel")
```

## Deployment topology

```mermaid
flowchart TB
    subgraph Home[Mac receiver station]
      Ant[Antenna] --> SDR[RTL-SDR USB]
      SDR --> Readsb[readsb]
      Readsb --> JSON[JSON files]
      Readsb --> Beast[Loopback Beast port 30905]
      JSON --> Collector[Observatory collector]
      Beast --> Collector
      Awake[caffeinate LaunchAgent] -. keeps awake .-> Readsb
      Collector --> Uplink[Telemetry uploader]
    end

    Readsb -->|TCP 30004| AL[airplanes.live]
    Uplink -->|HTTPS bearer token| Ingest[Relay /api/ingest]

    subgraph VPS[Existing Linux server]
      Ingest --> Relay[Python relay]
      Relay --> SQLite[(SQLite history)]
      Relay --> Static[React static application]
      Tunnel[cloudflared] --> Relay
      Supervisor[Unprivileged supervisor] -. restarts .-> Relay
      Supervisor -. restarts .-> Tunnel
    end

    Browser[Owner browser] -->|HTTPS| CF[Cloudflare edge]
    CF --> Tunnel
```

## Process ownership

```mermaid
flowchart LR
    subgraph launchd[macOS user LaunchAgents]
      R[local.airplanes-live.readsb]
      W[local.antenna-observatory.web]
      U[local.antenna-observatory.uplink]
      K[local.antenna-observatory.keepawake]
    end
    subgraph linux[Linux user processes]
      SR[relay supervisor] --> RP[relay process]
      ST[tunnel supervisor] --> TP[cloudflared]
    end
    R --> W --> U --> RP
    K -. prevents idle sleep .-> R
    TP --> RP
```

## Trust boundaries

```mermaid
flowchart LR
    subgraph T1[Trusted Mac]
      USB[USB receiver]
      COL[Collector]
      TOKEN1[Relay token file]
    end
    subgraph T2[Public network]
      HTTPS[Encrypted HTTPS]
      TCP[Outbound aircraft feed]
    end
    subgraph T3[Trusted VPS account]
      APP[Relay application]
      TOKEN2[Matching relay token]
      AUTH[Account hash]
      DB[(History database)]
    end
    subgraph T4[Authenticated browser]
      SESSION[HttpOnly session]
    end
    USB --> COL
    TOKEN1 --> COL
    COL --> HTTPS --> APP
    TOKEN2 --> APP
    AUTH --> APP
    APP --> DB
    APP --> SESSION
    COL --> TCP
```

The relay binds only to loopback. Cloudflare Tunnel makes the application reachable without opening an inbound VPS port. SSH deployment uses a dedicated key, and the wiki synchronization uses a different repository-scoped deploy key.

## Data model

```mermaid
erDiagram
    SAMPLE {
      real ts PK
      text payload
    }
    EVENT {
      real ts
      text level
      text message
    }
    SNAPSHOT {
      real now
      string state
      object metrics
      array aircraft
      array signals
      object host
      object hardware
    }
    SNAPSHOT ||--o{ SAMPLE : summarized_into
    SNAPSHOT ||--o{ EVENT : emits
```

Samples and events use seven-day rolling retention. The latest relay snapshot and a bounded decoder-log tail are also persisted so a relay restart can recover the last known view.
