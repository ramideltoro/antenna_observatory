# Antenna Observatory

<span class="status-pill">1090 MHz · live receiver</span>

Antenna Observatory turns a Nooelec software-defined radio attached to a Mac into a private, mobile-friendly aircraft reception dashboard. The Mac decodes ADS-B and Mode S traffic, sends aircraft data directly to airplanes.live, and uploads a protected telemetry snapshot to a small remote server for the public domain.

[Open the dashboard](https://antenna.ramideltoro.com){ .md-button .md-button--primary }
[Browse the source](https://github.com/ramideltoro/antenna_observatory){ .md-button }
[Open Skyglow](https://skyglow.ramideltoro.com){ .md-button }

```mermaid
flowchart LR
    A[1090 MHz antenna] --> B[Nooelec NESDR]
    B --> C[readsb on Mac]
    C -->|BeastReduce+| D[airplanes.live]
    C --> E[Local collector]
    E -->|Protected HTTPS uplink| F[Remote relay]
    F --> G[(7-day history)]
    F --> H[Cloudflare Tunnel]
    H --> I[Authenticated dashboard]
```

## Find what you need

<div class="grid cards" markdown>

- :material-apple:{ .lg .middle } **Build the receiver**

  ***

  Reproduce the complete Homebrew, RTL-SDR, readsb, airplanes.live, LaunchAgent, and keep-awake setup.

  [:octicons-arrow-right-24: Mac setup](mac-setup.md)

- :material-radar:{ .lg .middle } **Understand the signals**

  ***

  Learn how ADS-B, Mode S, TIS-B, ADS-R, and Mode A/C are classified and measured.

  [:octicons-arrow-right-24: Signal guide](signals.md)

- :material-chart-timeline-variant:{ .lg .middle } **Use the dashboard**

  ***

  Read live aircraft, signal power, receiver health, feed state, history, events, and raw telemetry.

  [:octicons-arrow-right-24: Dashboard guide](dashboard.md)

- :material-lan:{ .lg .middle } **Operate the system**

  ***

  Check services, interpret logs, recover a stale feed, deploy safely, and roll back a release.

  [:octicons-arrow-right-24: Operations runbook](operations.md)

</div>

## Skyglow: every wavelength

Skyglow extends the same local receiver into a private multi-band observatory for live aircraft, flight replay, airband and NOAA audio, Meteor satellite captures, and compatible wireless sensors. It keeps the physical SDR and private data on the Mac while a ServerCheap edge makes the iPhone interface reliable and fast.

```mermaid
flowchart LR
    A[One USB receiver] --> B{Timed mode}
    B --> C[1090 MHz aircraft]
    B --> D[Airband / NOAA audio]
    B --> E[Meteor LRPT]
    B --> F[rtl_433 sensors]
    C --> G[Skyglow iPhone interface]
    D --> G
    E --> G
    F --> G
```

[Read the Skyglow wiki](skyglow/index.md){ .md-button .md-button--primary }
[Browse Skyglow source](https://github.com/ramideltoro/skyglow){ .md-button }

## Design goals

| Goal                            | How the project meets it                                                                           |
| ------------------------------- | -------------------------------------------------------------------------------------------------- |
| Keep radio work local           | The USB receiver and `readsb` remain on the Mac.                                                   |
| Keep airplanes.live independent | `readsb` connects directly to the feed destination.                                                |
| Make history available anywhere | The relay stores a seven-day rolling sample history.                                               |
| Protect private telemetry       | One authenticated account gates every dashboard and read API route.                                |
| Recover automatically           | LaunchAgents, a keep-awake service, and the Linux supervisor restart failed processes.             |
| Ship safely                     | CI scans, tests, builds, budgets, deploys atomically, verifies, and can roll back.                 |
| Work on phones                  | Both sites use responsive layouts, touch targets, reduced motion, and amber high-contrast styling. |

!!! info "One receiver, one frequency at a time"
This receiver is dedicated to 1090 MHz aircraft traffic. Receiving FM, weather radio, airband voice, or 978 MHz UAT at the same time requires another receiver.
