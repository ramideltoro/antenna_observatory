# Operations

## Service lifecycle

```mermaid
flowchart LR
    subgraph Mac login
      W[local.skyglow.web] --> API[Python receiver API]
      U[local.skyglow.servercheap-uplink] --> SSH[Reverse SSH]
      A[local.antenna-observatory.web] --> readsb
      K[Keep-awake service] --> Awake[Mac remains awake]
    end
    subgraph VPS reboot
      Cron[User crontab] --> Supervisor[Skyglow supervisor]
      Supervisor --> Caddy[Caddy edge]
      Existing[Existing supervisor] --> Cloudflared
    end
    SSH --> Caddy
```

## Health ladder

Check from the physical receiver outward. Each successful step narrows the failure to the next link.

```mermaid
flowchart TD
    USB{SDR visible?} -- No --> Cable[Check cable, antenna, and USB ownership]
    USB -- Yes --> Local{localhost:8790/api/session?}
    Local -- No --> WebLog[Inspect skyglow.log and launchd]
    Local -- Yes --> Remote{VPS :18790 reaches session?}
    Remote -- No --> SSHLog[Inspect uplink log and SSH listener]
    Remote -- Yes --> Edge{VPS :8790 returns site and session?}
    Edge -- No --> EdgeLog[Inspect edge supervisor and Caddy log]
    Edge -- Yes --> Public{Public HTTPS works?}
    Public -- No --> TunnelLog[Inspect cloudflared and DNS]
    Public -- Yes --> Healthy[System healthy]
```

| Check           | Command                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Mac service     | `launchctl print gui/$(id -u)/local.skyglow.web`                                               |
| Mac API         | `curl http://127.0.0.1:8790/api/session`                                                       |
| SSH uplink      | `launchctl print gui/$(id -u)/local.skyglow.servercheap-uplink`                                |
| VPS ports       | `ssh 65.75.201.18 'ss -ltn                                                                     | grep -E ":(8790 | 18790)"'` |
| VPS API path    | `ssh 65.75.201.18 'curl -H "Host: skyglow.ramideltoro.com" http://127.0.0.1:8790/api/session'` |
| Public API path | `curl https://skyglow.ramideltoro.com/api/session`                                             |

## Deployment and rollback

```mermaid
sequenceDiagram
    participant CI as GitHub Actions
    participant VPS
    participant Edge as Edge supervisor
    participant Public as Public smoke test
    CI->>VPS: Upload verified static release
    VPS->>VPS: Validate Caddy configuration
    VPS->>VPS: Create timestamped release
    VPS->>Edge: Atomically switch current symlink
    Edge->>Edge: Restart and verify static + API
    alt Verification fails
        Edge->>VPS: Restore previous symlink
        Edge->>Edge: Restart previous release
    else Verification passes
        CI->>Public: Check title and session endpoint
    end
```

Every release is stored under `~/skyglow/releases` on the VPS. `~/skyglow/current` points to the active release. The installer records the previous target and restores it if either the static page or the receiver API fails locally.

Manual recovery uses the same reviewed deployer:

```bash
pnpm build
python3 ops/servercheap/deploy.py 65.75.201.18
```

## Logs and state

| Location                                        | Content                                               |
| ----------------------------------------------- | ----------------------------------------------------- |
| `~/Library/Logs/skyglow.log`                    | Mac API, mode manager, and decoder messages           |
| `~/Library/Logs/skyglow-servercheap-uplink.log` | Persistent SSH tunnel errors                          |
| `~/Library/Application Support/Skyglow/state`   | Private settings, database, sessions, media, and logs |
| `~/.local/state/skyglow/edge.log` on VPS        | User Caddy edge and supervisor output                 |
| `~/.local/share/skyglow` on VPS                 | Supervisor lock and PID state                         |

Never paste unredacted account files, session stores, private coordinates, tunnel tokens, or radio recordings into an issue.
