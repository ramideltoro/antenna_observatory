# Remote operations

The Mac owns the USB receiver and decodes 1090 MHz traffic locally. A protected uplink sends a compact telemetry snapshot to an existing Linux server every two seconds. The server stores rolling history and serves the authenticated dashboard through a Cloudflare Tunnel.

Machine-specific addresses, tunnel identifiers, account records, relay tokens, and deployment keys belong in protected state directories or GitHub Actions secrets. They are intentionally absent from this repository.

## Public topology

- Dashboard: <https://antenna.ramideltoro.com>
- Documentation: <https://docs.antenna.ramideltoro.com>
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

The authenticated API, telemetry inspector, history, logs, exports, and station settings require a valid session. The relay ingestion endpoint additionally requires the private relay bearer token. Keep the Mac awake while the screen is locked so decoding and uplink processes continue.

The full operating guide and recovery procedures are maintained in the project documentation site.
