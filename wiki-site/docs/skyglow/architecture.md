# Architecture

Skyglow separates public web delivery from physical radio control. The VPS serves static assets and terminates the Cloudflare origin path. The Mac keeps the receiver, credentials, history, recordings, and decoders.

## Deployment topology

```mermaid
flowchart TB
    subgraph Internet
        Phone[iPhone / browser]
        CF[Cloudflare edge]
    end
    subgraph VPS[ServerCheap VPS]
        Tunnel[cloudflared]
        Caddy[Caddy :8790]
        Static[Versioned static release]
        Reverse[SSH loopback :18790]
    end
    subgraph Home[Mac receiver host]
        Launchd[launchd services]
        API[Skyglow Python :8790]
        DB[(SQLite and media)]
        Decoders[readsb / rtl_fm / rtl_433 / SatDump]
        USB[Nooelec NESDR]
    end
    Phone -->|HTTPS| CF
    CF --> Tunnel --> Caddy
    Caddy --> Static
    Caddy -->|/api and /media| Reverse
    Reverse -->|Encrypted reverse SSH| API
    Launchd --> API
    API --> DB
    API --> Decoders --> USB
```

Both VPS listeners are bound to loopback. The Mac opens the SSH connection outward, so the home network needs no inbound port or router rule.

## Request routing

```mermaid
sequenceDiagram
    actor Browser
    participant Cloudflare
    participant Edge as VPS Caddy
    participant SSH as Reverse SSH
    participant Mac as Mac API
    Browser->>Cloudflare: HTTPS request
    Cloudflare->>Edge: Tunnel request
    alt Static asset or SPA route
        Edge-->>Cloudflare: File from active release
    else /api/* or /media/*
        Edge->>SSH: Proxy to 127.0.0.1:18790
        SSH->>Mac: 127.0.0.1:8790
        Mac-->>Edge: Authorized response
    end
    Edge-->>Browser: Security headers and response
```

## Components

| Component | Runs on | Responsibility |
| --- | --- | --- |
| Next/Vinext client | VPS and browser | Responsive application shell, map, controls, audio, and replay UI |
| Caddy edge | VPS | Static files, compression, security headers, and API/media proxy |
| cloudflared | VPS | Public HTTPS path without opening VPS web ports directly |
| Reverse SSH LaunchAgent | Mac | Persistent encrypted loopback path to the VPS |
| Python receiver service | Mac | Authentication, APIs, history, scheduling, decoder lifecycle, and media |
| SQLite and media tree | Mac | Positions, alerts, sensors, captures, account, and recordings |
| Decoder tools | Mac | Demodulation and decoding for the active receiver mode |

## Recovery behavior

```mermaid
flowchart TD
    Failure{What failed?}
    Failure -->|Browser or Cloudflare| Static[Edge remains healthy]
    Failure -->|Reverse SSH| Reconnect[launchd restarts SSH]
    Failure -->|Mac API| RestartAPI[launchd restarts Python]
    Failure -->|Temporary decoder| Rollback[Manager stops process and restores aircraft]
    Failure -->|VPS edge| Supervisor[Linux supervisor restarts Caddy]
    Failure -->|VPS reboot| Cron[crontab starts edge and tunnel]
    Reconnect --> Healthy[Health checks recover]
    RestartAPI --> Healthy
    Rollback --> Healthy
    Supervisor --> Healthy
    Cron --> Healthy
```

The interface can still load from the VPS when the Mac is unavailable, but login, live data, media, and controls depend on the private receiver path.
