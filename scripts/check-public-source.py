#!/usr/bin/env python3
"""Reject machine-specific paths, live feeder IDs, and private keys."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SKIP = {'.git', 'node_modules', 'dist', 'work', '.vinext', '__pycache__'}
PATTERNS = {
    'absolute macOS user path': re.compile(rb'/Users/[A-Za-z0-9._-]+/'),
    'live airplanes.live receiver UUID': re.compile(
        rb'uuid=[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    ),
    'private key': re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}'),
}

try:
    names = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-z'],
        check=True,
        capture_output=True,
    ).stdout.decode().split('\0')
    paths = [ROOT / name for name in names if name]
except (OSError, subprocess.CalledProcessError, UnicodeError):
    paths = [
        path
        for path in ROOT.rglob('*')
        if path.is_file()
        and not any(part in SKIP for part in path.relative_to(ROOT).parts)
    ]

findings = []
for path in paths:
    try:
        data = path.read_bytes()
    except OSError:
        continue
    for name, pattern in PATTERNS.items():
        if pattern.search(data):
            findings.append(f'{path.relative_to(ROOT)}: {name}')

if findings:
    raise SystemExit('Unsafe public source:\n' + '\n'.join(findings))
print('Public-source safety checks passed.')
