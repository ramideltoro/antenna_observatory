# Receiver modes

The receiver manager owns one exact USB SDR and serializes every mode change. A failed startup stops partial processes and restores aircraft reception.

```mermaid
stateDiagram-v2
    [*] --> Aircraft
    Aircraft --> Switching
    Switching --> Listen: rtl_fm and ffmpeg ready
    Switching --> Satellite: SatDump ready
    Switching --> Sensors: rtl_433 ready
    Switching --> Aircraft: validation or startup failed
    Listen --> Aircraft: stop or timeout
    Satellite --> Decode: capture completes
    Decode --> Aircraft: products indexed
    Sensors --> Aircraft: stop or timeout
```

## Aircraft

```mermaid
flowchart LR
    RF[1090 MHz RF] --> SDR[RTL-SDR]
    SDR --> readsb
    readsb --> JSON[aircraft.json]
    JSON --> Snapshot[Live snapshot]
    JSON --> Archive[(Position archive)]
    readsb --> Feed[airplanes.live feed]
```

- Frequency: **1090 MHz** ADS-B and Mode S.
- Local JSON is sampled every two seconds; recent positioned aircraft are archived about every ten seconds.
- The Live map uses OpenStreetMap tiles and requires no commercial map key.
- Aircraft mode is the default and the recovery target for every temporary session.

## Listen

```mermaid
flowchart LR
    RF[Airband AM or NOAA FM] --> rtl_fm
    rtl_fm --> Filter[Voice filtering]
    Filter --> FFmpeg[FFmpeg AAC encoder]
    FFmpeg --> HLS[Rotating HLS playlist]
    HLS --> Safari[Native Safari audio]
```

| Source | Range | Modulation | Useful starting point |
| --- | --- | --- | --- |
| Aircraft voice | 118.000–136.975 MHz | AM | An active Tampa tower, approach, departure, or ATIS channel |
| NOAA Weather Radio | 162.400–162.550 MHz | FM | 162.550 MHz in Tampa |

Audio is live with a small HLS buffer. Every tune resets the playlist and uses unique segment names so Safari cannot replay segments from the previous frequency.

## Satellite

```mermaid
flowchart LR
    Predict[Skyfield pass prediction] --> Schedule[Choose a visible pass]
    Schedule --> Capture[SatDump LRPT capture]
    Capture --> CADU[CADU data]
    CADU --> Products[SatDump products]
    Products --> Gallery[Skyglow capture gallery]
    Gallery --> Return[Restore aircraft]
```

- Intended for supported Meteor M2-series LRPT around 137 MHz.
- Prediction uses refreshed CelesTrak orbital elements and rejects stale data.
- Capture duration is bounded and aircraft mode returns after processing.
- Real imagery requires the active satellite frequency and symbol rate, a suitable 137 MHz antenna, an open sky view, and a usable pass.

## Sensors

```mermaid
flowchart LR
    Devices[Weather / soil / TPMS devices] --> RF[315–915 MHz transmissions]
    RF --> rtl_433
    rtl_433 --> Normalize[Validate and normalize JSON]
    Normalize --> Current[Current sensor cards]
    Normalize --> History[(24-hour readings)]
```

Selectable bands include 315, 345, 433.92, 868.3, and 915 MHz. Only protocols implemented by the installed rtl_433 version can be decoded. Many battery sensors transmit only periodically or after a value changes.

## Mode ownership rules

```mermaid
flowchart TD
    Request[Authenticated mode request] --> Validate{Valid mode, options, and duration?}
    Validate -- No --> Reject[Return bounded error]
    Validate -- Yes --> Stop[Stop current decoder]
    Stop --> Release[Wait for USB release]
    Release --> Start[Start requested decoder]
    Start --> Ready{Healthy?}
    Ready -- Yes --> Timer[Run until stop or deadline]
    Ready -- No --> Restore[Restore aircraft]
    Timer --> Restore
```

All receiver changes use authenticated POST requests. GET requests never change receiver state.
