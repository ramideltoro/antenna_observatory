# Raspberry Pi receiver setup

The receiver pipeline can run on a Raspberry Pi with Debian or Raspberry Pi OS and systemd. The existing remote relay, public hostname, history database, and Cloudflare Tunnel remain on the remote server. The Pi uploads live telemetry every two seconds and completed Beast batches every two minutes. No Mac login or awake session is needed.

## Prerequisites

- A working `readsb.service` with the RTL-SDR receiver, JSON in `/run/readsb`, and Beast output on loopback port 30005.
- The airplanes.live `airplanes-feed.service`; optionally `airplanes-mlat.service` with the antenna location configured.
- Python 3, `zstd`, `iproute2`, and a built copy of this repository in `/opt/antenna-observatory` (including `dist/client` for the local dashboard).
- The existing relay token, transferred privately. Never add it to the repository.

## Storage

Use a Linux filesystem for SQLite and the durable frame spool. An existing ext4 partition can be used without formatting the drive or removing its other files. Mount it by filesystem UUID in `/etc/fstab`, create a dedicated directory owned by `readsb:nogroup`, and symlink `/var/lib/antenna-observatory` to that directory. Keep other files intact.

The example units require the actual `/mnt/antenna-storage` mount as well as the state path and check `ConditionPathIsMountPoint`. Update this mount path if yours differs; a symlink alone does not establish the correct systemd mount dependency. Add the same directives to a `readsb.service` drop-in when its dump directory is on that drive. This prevents startup from silently writing receiver history to the system card when storage is missing. Keep the data drive attached while receiving.

The frame uploader accepts `--free-disk-reserve-mb`. The Pi example reserves 2048 MiB; the existing Mac default remains 20 GiB. If free space falls below the configured reserve during an outage, the oldest unacknowledged batches are dropped and counted as gaps. Acknowledged batches are deleted locally; the remote archive retains 72 hours of detailed frames.

## Configure and start

1. Copy `ops/systemd/antenna-observatory.env.example` to `/etc/antenna-observatory.env`. Set the receiver serial, current airplanes.live feeder UUID, remote ingest URLs, and disk reserve. These values belong only in the local configuration.
2. Copy the existing relay token into `/var/lib/antenna-observatory/relay-token`, owned by `readsb`, mode `0600`.
3. Migrate `settings.json` and use SQLite's online backup API to migrate `observatory.sqlite`, preserving maintenance entries. The collector's station coordinates should agree with the decoder/MLAT configuration. Preserve the remote database in place.
4. Add `--modeac --dump-beast=/var/lib/antenna-observatory/beast-dump,120,1` to readsb's decoder options. Create that directory owned by `readsb`. Add `--net-bind-address 127.0.0.1` to the network options; the collector and feeder consume the decoder locally. Keep the existing airplanes.live ports and connectors.
5. Install the three units from `ops/systemd/` into `/etc/systemd/system/`, reload systemd, and restart readsb.
6. Start `antenna-observatory.service` and verify `http://127.0.0.1:8787/api/snapshot` locally. Disable the old Mac telemetry uploader before enabling `antenna-uplink.service`, so two hosts cannot overwrite the same station snapshot.
7. Enable `antenna-frames.service` and wait for a complete two-minute batch. Confirm the remote archive has processed it with zero failed batches.
8. Enable all three units at boot. Stop and disable the old Mac collector, frame uploader, decoder and Observatory keepawake LaunchAgents after the Pi is verified. Preserve the Mac files as rollback copies.

Linux diagnostics inspect the readsb systemd unit, process CPU/memory, external feed sockets and the separate airplanes.live feeder service. MLAT configuration is reported from its systemd enablement. Decoder logs come from journald; the collector unit grants the `systemd-journal` supplementary group.

## Verify

```sh
systemctl is-active readsb airplanes-feed antenna-observatory antenna-uplink antenna-frames
journalctl -u antenna-observatory -u antenna-uplink -u antenna-frames -n 40 --no-pager
curl -fsS http://127.0.0.1:8787/api/snapshot
```

On the public portal, confirm fresh Linux host telemetry, a connected Beast stream, changing aircraft and signal counts, recent frame uploads, and processed archive batches. Restart the Pi services once to verify that capture, token access and the queue survive restart.

To edit station settings and maintenance entries from another computer, forward the private dashboard through SSH:

```sh
ssh -L 8788:127.0.0.1:8787 USER@PI_HOST
```

Then open `http://127.0.0.1:8788`. Station edits remain restricted to the loopback connection; ingestion stays authenticated. The single 1090 MHz receiver cannot also provide the optional spectrum waterfall; that still requires a second SDR.

## Rollback

Stop the Pi telemetry and frame uploaders before restoring the old producer. Restore the backed-up readsb configuration and Mac LaunchAgents if moving the receiver back to the Mac. Keep the remote database, token, and hostnames unchanged. Do not run two telemetry uploaders for the same station simultaneously.
