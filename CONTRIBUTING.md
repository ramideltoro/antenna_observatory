# Contributing

Create a branch from `main`, keep the change focused, update `wiki-site/` when behavior or operations change, and open a pull request.

Run the required checks before pushing:

```bash
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
python3 scripts/check-public-source.py
pnpm build
pnpm check:size
```

Do not commit receiver UUIDs, rendered LaunchAgents, passwords, account hashes, relay or tunnel tokens, private keys, state databases, logs, IP addresses used only for operations, or local verification captures.

Production deployment and wiki publication run only after the protected `main` branch passes CI.
