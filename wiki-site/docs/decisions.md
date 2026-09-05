# Design decisions

## ADR-001: Decode on the Mac

**Decision:** Keep RTL-SDR ownership and readsb decoding on the Mac physically attached to the receiver.

**Reason:** Raw 2.4 MS/s IQ transport would use far more bandwidth, add latency, and make USB recovery dependent on a remote network. Compact decoded telemetry is sufficient for the dashboard.

## ADR-002: Feed airplanes.live directly

**Decision:** readsb sends BeastReduce+ directly from the Mac to airplanes.live.

**Reason:** The community feed remains independent of the dashboard relay. A website deployment or relay outage cannot interrupt a healthy receiver-to-feed path.

## ADR-003: Render remotely from protected snapshots

**Decision:** Upload a validated snapshot and bounded logs every two seconds to the existing server.

**Reason:** The remote dashboard gains history and continuous HTTPS access without moving radio decoding or opening the home network.

## ADR-004: Use SQLite for rolling history

**Decision:** Store samples and events in a local SQLite database with seven-day retention.

**Reason:** The traffic volume is small, transactions are local, backup is simple, and no paid database service is needed.

## ADR-005: Use Cloudflare Tunnel

**Decision:** Route the public hostname through a tunnel to a loopback-only relay.

**Reason:** This avoids an inbound application port, uses the existing free Cloudflare configuration, and centralizes TLS and DNS.

## ADR-006: Publish dashboard reads

**Decision:** Serve the dashboard and read APIs publicly while keeping relay ingestion token-protected and station-setting writes local-only.

**Reason:** The observatory is intended to be openly accessible and easy to use on mobile browsers. Separate write boundaries protect receiver integrity without adding a login step to public viewing.

## ADR-007: Keep documentation canonical with code

**Decision:** Author MkDocs content in `wiki-site/` in the main repository and publish it to a separate repository only after a successful release.

**Reason:** Documentation changes receive the same review and version history as code. The separate repository provides GitHub Pages and a custom documentation domain, capabilities that the built-in GitHub Wiki interface does not provide.

## ADR-008: Deploy immutable releases

**Decision:** Build in CI, upload a tested archive, use commit-named directories, and atomically switch a symlink.

**Reason:** Production never rebuilds unreviewed dependencies, rollback is fast, and credentials and history remain separate from code.
