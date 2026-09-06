#!/usr/bin/env python3
"""Safely collect a narrow spectrum waterfall from an explicitly separate RTL-SDR."""

import argparse
import collections
import csv
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True, help='Serial number of the secondary RTL-SDR')
    parser.add_argument('--protected-device', default=os.environ.get('ANTENNA_DEVICE_SERIAL', ''), help='Serial number reserved for readsb')
    parser.add_argument('--center-mhz', type=float, default=1090)
    parser.add_argument('--span-mhz', type=float, default=4)
    parser.add_argument('--interval', type=float, default=3)
    parser.add_argument('--state-dir', default=str(Path.home() / 'Library/Application Support/AntennaObservatory/state'))
    args = parser.parse_args()
    if args.device == args.protected_device:
        raise SystemExit('Refusing to use the receiver reserved for the airplanes.live feed.')
    if not 0.25 <= args.span_mhz <= 20 or not 1 <= args.interval <= 300:
        raise SystemExit('Invalid spectrum span or interval.')
    output = Path(args.state_dir) / 'spectrum/latest.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = collections.deque(maxlen=80)
    while True:
        low = (args.center_mhz - args.span_mhz / 2) * 1_000_000
        high = (args.center_mhz + args.span_mhz / 2) * 1_000_000
        command = [
            '/opt/homebrew/bin/rtl_power', '-d', args.device,
            '-f', f'{int(low)}:{int(high)}:15625', '-i', '1', '-e', '1s', '-1', '-',
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=12)
            rows = [row for row in csv.reader(result.stdout.splitlines()) if len(row) > 6]
            if not rows:
                raise ValueError('rtl_power returned no spectrum rows')
            row = rows[-1]
            values = [round(float(value), 2) for value in row[6:]]
            lines.append({'ts': time.time(), 'values': values})
            payload = {
                'available': True,
                'configured': True,
                'updated_at': time.time(),
                'center_mhz': args.center_mhz,
                'span_mhz': args.span_mhz,
                'device': args.device,
                'lines': list(lines),
            }
            temporary = output.with_suffix('.tmp')
            temporary.write_text(json.dumps(payload, separators=(',', ':')))
            temporary.replace(output)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            print(f'Spectrum collection unavailable ({type(error).__name__}); retrying.', flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
