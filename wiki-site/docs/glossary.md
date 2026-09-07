# Glossary

| Term         | Meaning in this project                                                                                           |
| ------------ | ----------------------------------------------------------------------------------------------------------------- |
| ADS-B        | Automatic Dependent Surveillance–Broadcast; aircraft broadcasts carrying identity, position, velocity, and status |
| ADS-R        | ADS-B Rebroadcast; ground retransmission of ADS-B from another link                                               |
| Beast        | Framed binary format used to transport Mode S messages and signal metadata                                        |
| BeastReduce+ | Bandwidth-reduced Beast output used for the airplanes.live connection                                             |
| CPR          | Compact Position Reporting, the latitude/longitude encoding used by ADS-B                                         |
| dBFS         | Decibels relative to digital full scale; relative receiver power rather than calibrated dBm                       |
| DF           | Mode S downlink format number                                                                                     |
| Feeder UUID  | Receiver identity assigned for the airplanes.live feed                                                            |
| ICAO hex     | 24-bit aircraft address normally displayed as six hexadecimal characters                                          |
| IQ samples   | In-phase and quadrature radio samples produced by the SDR                                                         |
| LaunchAgent  | A macOS user service managed by `launchd`                                                                         |
| MLAT         | Multilateration, a server-assisted position technique requiring precise timing and a configured client            |
| Mode A/C     | Legacy transponder identity and altitude replies without a Mode S CRC                                             |
| Mode S       | Selective secondary-surveillance-radar protocol used on 1090 MHz                                                  |
| readsb       | The local decoder that owns the RTL-SDR and produces frames, aircraft JSON, and receiver statistics               |
| RTL-SDR      | Low-cost USB software-defined radio family based on the RTL2832U                                                  |
| SDR          | Software-defined radio                                                                                            |
| TIS-B        | Traffic Information Service–Broadcast; ground rebroadcast of surveillance targets                                 |
| TC           | ADS-B extended-squitter type code                                                                                 |
| UAT          | Universal Access Transceiver on 978 MHz; not received by this 1090 MHz configuration                              |
| Uplink       | Protected two-second HTTPS transfer from the Pi collector to the remote relay                                     |

The active receiver uses **systemd**, Linux’s service manager, to start and recover services at boot. LaunchAgents apply only to the legacy Mac setup. The **USB data volume** is the ext4 thumb drive holding local history and unacknowledged frame batches.
