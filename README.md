# Antenna Observatory

[![CI](https://github.com/ramideltoro/antenna_observatory/actions/workflows/ci.yml/badge.svg)](https://github.com/ramideltoro/antenna_observatory/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ramideltoro/antenna_observatory/actions/workflows/codeql.yml/badge.svg)](https://github.com/ramideltoro/antenna_observatory/actions/workflows/codeql.yml)

Antenna Observatory is a public, amber-themed dashboard for a 1090 MHz aircraft receiver. A Nooelec SDR connected to a Raspberry Pi or Mac runs `readsb`, feeds decoded aircraft data directly to airplanes.live, and securely uploads receiver telemetry plus durable two-minute Beast batches to a remote server. The relay provides live charts, seven-day aggregate history, and a 72-hour per-frame archive.

Open the dashboard at **[antenna.ramideltoro.com](https://antenna.ramideltoro.com)**. Live views and read APIs are open without an account; telemetry ingestion and station changes remain protected.

The dashboard includes live aircraft and signal families, a historical polar coverage map, flight replay, aircraft encounters, daily reports, signal distributions, a 0–100 antenna health score, smart alerts, maintenance annotations, receiver diagnostics, and an optional second-SDR spectrum waterfall. It installs as a mobile web app and is designed for phones, tablets, and desktops.

Read the **[Antenna Observatory wiki](https://wiki.antenna.ramideltoro.com)** for architecture diagrams, Raspberry Pi and Mac installation, signal definitions, operations, troubleshooting, security, API behavior, and the CI/CD pipeline. The related [Skyglow wiki](https://wiki.skyglow.ramideltoro.com) documents the multi-band receiver project.

## Local development

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm build
```

Receiver identifiers, tokens, deployment keys, databases, and machine-specific files are intentionally excluded from this public repository.

For Linux receiver deployment and migration, see [Raspberry Pi setup](wiki-site/docs/pi-setup.md).
