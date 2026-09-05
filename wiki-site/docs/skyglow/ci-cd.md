# CI/CD and automatic documentation

Every push and pull request uses the same quality gates. Only a successful `main` run can deploy. Production then receives the exact build artifact that passed the earlier stages.

## Pipeline graph

```mermaid
flowchart LR
    Commit[Push or pull request] --> Web[Format, lint, types]
    Commit --> Python[Python tests + coverage]
    Commit --> Audit[JS + Python audits]
    Commit --> Secrets[Secret scan]
    Commit --> CodeQL[CodeQL]
    Commit --> Scorecard[OpenSSF Scorecard]
    Web --> Build[Production build]
    Build --> Budget[Bundle budget]
    Budget --> Lighthouse[Mobile Lighthouse]
    Python --> Deploy{main branch?}
    Audit --> Deploy
    Secrets --> Deploy
    Lighthouse --> Deploy
    Deploy -- Yes --> VPS[Atomic VPS release]
    VPS --> Smoke[Public smoke test]
    Smoke --> Docs[Generate release docs]
    Docs --> Wiki[Publish GitHub Pages]
```

## Required gates

| Stage | Protects |
| --- | --- |
| Formatting and linting | Review clarity and common JavaScript/TypeScript mistakes |
| Type check | Component, API, and data-shape contracts |
| Python unit tests and branch coverage | Authentication, bounds, replay, paths, and receiver behavior |
| Dependency audits and PR dependency review | Known vulnerable package versions and risky upgrades |
| Gitleaks plus GitHub push protection | Credentials accidentally entering history |
| CodeQL | JavaScript/TypeScript and Python data-flow vulnerabilities |
| OpenSSF Scorecard | Repository and supply-chain hygiene |
| Production build | Reproducible deployable assets from the lockfile |
| Bundle budget | iPhone payload growth beyond explicit raw and gzip limits |
| Lighthouse | Performance, accessibility, best practices, and SEO regressions |
| Atomic deploy and smoke test | Broken configuration, missing assets, or receiver path failure |
| Documentation sync | Wiki pages and release history matching deployed behavior |

## Release sequence

```mermaid
sequenceDiagram
    participant GitHub
    participant Runner
    participant VPS
    participant Site as skyglow.ramideltoro.com
    participant WikiRepo as Documentation repository
    participant Pages as GitHub Pages
    GitHub->>Runner: Run protected main pipeline
    Runner->>Runner: Test, scan, build, budget, Lighthouse
    Runner->>VPS: Deploy with restricted SSH key
    VPS-->>Runner: Static and receiver health pass
    Runner->>Site: Public smoke test
    Site-->>Runner: HTML and session JSON pass
    Runner->>WikiRepo: Copy canonical pages and append release record
    WikiRepo->>Pages: Strict build, links, deploy
```

The production SSH key is separate from the Mac’s operational key and has forwarding and interactive access disabled. The wiki uses a different deploy key that can write only to the documentation repository. GitHub-hosted secrets are never written to release archives.

## Automatic release notes

After the public smoke test succeeds, `ops/sync_wiki.py` copies `wiki/skyglow` into the shared documentation site and generates:

- the exact deployed commit and workflow run;
- commit messages since the previous documented release;
- changed paths grouped into interface, receiver, operations, documentation, dependencies, tests, or project configuration;
- a deduplicated release-history row linking back to GitHub.

If production fails, documentation is not advanced to an undeployed commit.
