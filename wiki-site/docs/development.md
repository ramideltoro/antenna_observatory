# Development

## Repository layout

```text
app/                 React application and amber responsive theme
components/          Charts and reusable UI components
lib/                 Shared telemetry types and helpers
server/              Python collector, relay, authentication, and tests
ops/                 LaunchAgent templates and deployment utilities
scripts/             CI source-safety and bundle-budget checks
wiki-site/           Canonical MkDocs project documentation
.github/              CI, security, release, and maintenance automation
```

## Local requirements

- Node.js 22 or newer
- pnpm 10.17.1
- Python 3.9 or newer for the server; CI uses Python 3.12
- readsb and an RTL-SDR only when testing live radio collection

## Frontend development

Install exact dependencies and start the Vinext development server:

```bash
pnpm install --frozen-lockfile
pnpm dev
```

The development server listens on loopback. Its API proxy targets a Python server on port 8788, so run a collector or relay there when exercising live data.

## Required checks

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
python3 scripts/check-public-source.py
pnpm build
pnpm check:size
```

Avoid committing `dist`, `work`, state directories, databases, logs, account records, tokens, keys, rendered LaunchAgents, or machine-specific verification captures.

## Backend test fixture

The tests create temporary state and static directories. They cover password hashing, session and origin binding, login throttling, authenticated/anonymous routing, telemetry ingestion validation, history behavior, local-only writes, CSV safety, and path confinement without requiring a physical receiver.

## Documentation preview

```bash
cd wiki-site
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
mkdocs serve
```

Edit documentation in the main repository. The release pipeline owns synchronization into the wiki repository.

## Change flow

1. Create a branch from `main`.
2. Make a focused code and documentation change.
3. Run the required checks locally.
4. Open a pull request and let every required check finish.
5. Merge after the protected branch gate succeeds.
6. Watch Release deploy, verify, and publish matching documentation.
