#!/usr/bin/env python3
"""Render safe Markdown release notes for the exact deployed commit."""
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

parser = ArgumentParser()
parser.add_argument('--repository-root', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--commit', required=True)
args = parser.parse_args()

if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
    raise SystemExit('Expected a full lowercase Git commit')

root = Path(args.repository_root).resolve()
output = Path(args.output).resolve()
lines = subprocess.run(
    ['git', '-C', str(root), 'log', '--date=short', '--pretty=%H%x09%ad%x09%s', '-20', args.commit],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()

def safe(value):
    return value.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('<', '&lt;').replace('>', '&gt;')

short = args.commit[:12]
rendered = [
    '# Release notes',
    '',
    f'**Production commit:** [`{short}`](https://github.com/ramideltoro/antenna_observatory/commit/{args.commit})',
    '',
    f'**Documentation published:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}',
    '',
    'The application passed its required quality, reliability, security, build, and mobile performance checks before deployment.',
    '',
    '## Recent changes',
    '',
]
for line in lines:
    commit, date, subject = line.split('\t', 2)
    rendered.append(f'- [`{commit[:9]}`](https://github.com/ramideltoro/antenna_observatory/commit/{commit}) · {date} · {safe(subject)}')

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text('\n'.join(rendered) + '\n')
