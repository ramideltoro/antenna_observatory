# Antenna Observatory

[![CI](https://github.com/ramideltoro/antenna_observatory/actions/workflows/ci.yml/badge.svg)](https://github.com/ramideltoro/antenna_observatory/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ramideltoro/antenna_observatory/actions/workflows/codeql.yml/badge.svg)](https://github.com/ramideltoro/antenna_observatory/actions/workflows/codeql.yml)

Antenna Observatory is a private, amber-themed dashboard for a 1090 MHz aircraft receiver. A Nooelec SDR connected to a Mac runs `readsb`, feeds decoded aircraft data directly to airplanes.live, and securely uploads receiver telemetry to a remote server for live charts and seven-day history.

Open the dashboard at **[antenna.ramideltoro.com](https://antenna.ramideltoro.com)**. The site requires the owner account; direct page and API paths are protected by the same login.

The dashboard includes aircraft, ADS-B and Mode S signal families, receiver health, airplanes.live connection state, history, events, raw telemetry, and station settings. It is designed for phones, tablets, and desktops.

Read the **[project documentation and setup guide](https://docs.antenna.ramideltoro.com)** for architecture diagrams, the full Mac installation, signal definitions, operations, troubleshooting, security, API behavior, and the CI/CD pipeline.

## Local development

```bash
pnpm install --frozen-lockfile
pnpm test
pnpm build
```

Receiver identifiers, passwords, tokens, deployment keys, databases, and machine-specific files are intentionally excluded from this public repository.
