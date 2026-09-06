# Operations runbook

## Normal service chain

```mermaid
flowchart LR
    USB[USB receiver] --> R[readsb]
    R --> AL[airplanes.live]
    R --> C[collector]
    R --> F[frame dump and spool]
    C --> U[uploader]
    U --> V[remote relay]
    F --> V
    T[Cloudflare tunnel] --> V
    V --> B[browser]
```

Check from left to right. A downstream failure does not always affect an upstream service: the dashboard uplink can fail while airplanes.live continues receiving directly from readsb.

## Mac service checks

```bash
for label in \
  local.airplanes-live.readsb \
  local.antenna-observatory.web \
  local.antenna-observatory.uplink \
  local.antenna-observatory.frames \
  local.antenna-observatory.keepawake
do
  launchctl print "gui/$(id -u)/$label" | grep -E 'state =|pid =|last exit code'
done
```

`state = running` or an active PID indicates the job is loaded. `KeepAlive` restarts an unexpected exit after the configured throttle interval.

## Logs

| Component                           | macOS log                                       |
| ----------------------------------- | ----------------------------------------------- |
| readsb and airplanes.live connector | `~/Library/Logs/airplanes-live.log`             |
| Local web collector                 | `~/Library/Logs/antenna-observatory.log`        |
| Remote telemetry uploader           | `~/Library/Logs/antenna-observatory-uplink.log` |
| Durable frame uploader              | `~/Library/Logs/antenna-observatory-frames.log` |
| Old Mac tunnel rollback service     | `~/Library/Logs/antenna-observatory-tunnel.log` |

On Linux, the unprivileged supervisors write relay and tunnel logs under `~/.local/state/antenna-observatory/`.

The Feed view reports the frame pipeline state, pending batches, spool bytes, oldest pending age, last capture/upload/process times, failed batches, and recorded gaps. During a network outage, pending batches and oldest age should rise while the direct airplanes.live connection remains independent. After recovery, they should return to zero.

## Restart a Mac job

Use `kickstart` for a routine restart:

```bash
launchctl kickstart -k "gui/$(id -u)/local.airplanes-live.readsb"
```

Use the same command with another label for the collector, uploader, or keep-awake job. Avoid loading two decoder jobs because only one can claim the USB device.

## Deployments and rollback

Production releases are immutable directories named by the full Git commit. The `current` symlink changes atomically after extraction and validation. The deployment script restarts only the relay, checks its loopback dashboard, and restores the previous symlink if health does not recover.

The five newest releases are retained. To inspect the active target:

```bash
ssh antenna-observatory 'readlink "$HOME/antenna-observatory/current"'
```

## State and backup

Back up the remote state directory separately from releases. It contains:

- relay and tunnel token files;
- the SQLite history database and WAL files;
- latest accepted relay snapshot and bounded log tail;
- compressed Beast batches awaiting or completing 72-hour retention;
- content-addressed batch manifests and per-frame indexes;
- public-origin configuration.

Stop or quiesce the relay before making a raw SQLite filesystem copy, or use SQLite’s online backup command. Protect backups with the same care as production state.

## Routine maintenance

| Frequency          | Check                                                              |
| ------------------ | ------------------------------------------------------------------ |
| Daily              | Dashboard freshness and airplanes.live feed state                  |
| Daily              | Frame pipeline backlog, failures, gaps, and last processed time    |
| Weekly             | Decoder log for repeated restarts, USB loss, or reconnection loops |
| Weekly             | Dependabot and CodeQL results                                      |
| Monthly            | Range trend, strong-signal percentage, disk use, retained releases |
| After macOS update | Homebrew paths, LaunchAgent state, USB access, sleep behavior      |
| After antenna move | Position, coax connection, signal/noise trend, maximum range       |

Record antenna moves, cable changes, receiver replacements, software upgrades, and incidents in the dashboard’s **Maintenance** view. This makes a later range or noise change interpretable.

## Optional spectrum receiver

The spectrum waterfall deliberately refuses to use the serial number reserved for readsb. Connect and assign a unique serial to a second RTL-SDR, then run:

```bash
python3 "$HOME/Library/Application Support/AntennaObservatory/app/ops/spectrum-sidecar.py" \
  --device SECOND_RECEIVER_SERIAL \
  --protected-device YOUR_READSB_SERIAL
```

The sidecar writes a bounded 80-line waterfall to the observatory state directory. If the second receiver or `rtl_power` is unavailable, it retries without touching readsb. Do not configure the primary receiver serial: the sidecar fails closed to protect the airplanes.live feed.
