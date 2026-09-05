#!/usr/bin/env python3
"""Replace the sole dashboard account; restart the website to apply it."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'server'))
from observatory import AccountAuth, AUTH_CONFIG

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('username')
parser.add_argument('--password-stdin', action='store_true')
args = parser.parse_args()
password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Password: ')
if not 1 <= len(args.username) <= 100 or not 1 <= len(password) <= 1024:
    raise SystemExit('A username and password are required.')
record = AccountAuth.password_record(args.username, password)
AUTH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(mode='w', dir=AUTH_CONFIG.parent, prefix='.account-', delete=False) as output:
    os.fchmod(output.fileno(), 0o600)
    json.dump(record, output)
    output.flush()
    os.fsync(output.fileno())
Path(output.name).replace(AUTH_CONFIG)
print('Single account configured. Password stored only as a salted hash.')
