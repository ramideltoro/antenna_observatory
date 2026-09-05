# Remote operations

The Mac owns the USB receiver and decodes 1090 MHz traffic locally. A protected uplink sends a compact telemetry snapshot to an existing Linux server every two seconds. The server stores rolling history and serves the public dashboard through a Cloudflare Tunnel.

Machine-specific addresses, tunnel identifiers, relay tokens, and deployment keys belong in protected state directories or GitHub Actions secrets. They are intentionally absent from this repository.

## Public topology

- Dashboard: <https://antenna.ramideltoro.com>
- Documentation: <https://wiki.antenna.ramideltoro.com>
- Receiver: Nooelec NESDR SMArt v5 attached to the Mac
- Decoder: `readsb`, managed by a macOS LaunchAgent
- Aircraft feed: direct outbound BeastReduce+ connection from the Mac to airplanes.live
- Dashboard uplink: authenticated HTTPS from the Mac to the relay
- Public ingress: Cloudflare Tunnel to a loopback-only server process

## Health checks

On the Mac:

```bash
launchctl print "gui/$(id -u)/local.airplanes-live.readsb" | grep -E 'state =|pid =|last exit code'
launchctl print "gui/$(id -u)/local.antenna-observatory.uplink" | grep -E 'state =|pid =|last exit code'
tail -n 30 "$HOME/Library/Logs/airplanes-live.log"
tail -n 30 "$HOME/Library/Logs/antenna-observatory-uplink.log"
```

On the Linux host, use the saved SSH alias rather than publishing its address:

```bash
ssh antenna-observatory 'pgrep -af "observatory.py --relay|cloudflared tunnel"'
ssh antenna-observatory 'curl --fail http://127.0.0.1:8788/ready'
```

The dashboard, telemetry inspector, history, logs, and exports are public. The relay ingestion endpoint requires the private relay bearer token, and station settings can be changed only from loopback with a matching origin. Keep the Mac awake while the screen is locked so decoding and uplink processes continue.

The full operating guide and recovery procedures are maintained in the project documentation site.
