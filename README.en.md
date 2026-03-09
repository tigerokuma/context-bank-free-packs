# Context Bank Free Packs

[English](README.en.md) | [日本語](README.ja.md)

This repo is the central public repository for approved free packs.

## Overview

- Contributors can submit free packs by opening pull requests against this repo.
- Trusted owner-managed source repos can also open or update submission PRs automatically.
- GitHub Actions validate untrusted PRs without marketplace production secrets.
- Merge is the approval event.
- After merge, the private marketplace app can ingest the approved pack by running `pnpm free-pack:sync`.

Paid packs are out of scope here. MVP supports only free packs with `source.type = internal_repo`.

## Source Of Truth Docs

- [Hybrid Submission Strategy](docs/context-bank/00-overview/hybrid-submission-strategy.md)
- [Public Free-Pack Repo Layout](docs/context-bank/02-product/free-pack-repo-layout.md)
- [Free Pack PR Rules](docs/context-bank/06-execution/free-pack-pr-rules.md)
- [Trusted Source Repo Submission](docs/context-bank/06-execution/trusted-source-repo-submission.md)

## Flow Diagram

```mermaid
flowchart LR
    A["Creator / Contributor"] --> B["Option A: Fork free-packs repo"]
    A --> C["Option B: Trusted source repo workflow"]

    B --> D["Add or update one pack under packs/{creator}/{slug}"]
    D --> E["Open PR to central public repo"]

    C --> F["Source repo Action copies pack and opens/updates PR"]
    F --> E

    E --> G["Central repo pull_request CI"]
    G --> G1["validate-free-pack.yml"]
    G1 --> G2["manifest.json / SKILL.md checks"]
    G1 --> G3["path, free pricing, source.type checks"]
    G1 --> G4["safety scan: executables, symlinks, hidden files, blocked patterns"]

    G --> H{"Maintainer review"}
    H -->|"approve + merge"| I["Merged commit on main = approval event"]
    H -->|"request changes"| E

    I --> J["sync-marketplace.yml builds normalized artifact"]
    I --> K["Private marketplace repo: run pnpm free-pack:sync manually"]
    K --> L["Marketplace stores normalized snapshot"]
    L --> M["Catalog page / detail page render synced free pack"]
```

## Submission Paths

### Path 1: Standard contributor PR

1. Fork this repository.
2. Add or update exactly one pack directory at `packs/<creator>/<slug>/`.
3. Include both `manifest.json` and `SKILL.md`.
4. Open a pull request.
5. Wait for central repo CI and maintainer review.

No PAT is required for this path.

### Path 2: Trusted source repo automation

1. Keep the authored pack in another repo you control.
2. Run the source repo workflow.
3. The workflow opens or updates a PR in this repo.
4. Central repo CI and maintainer review still happen here.

This path needs a source-repo secret because GitHub Actions is writing to another repository.

## Directory Layout

```text
.
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── submit-from-trusted-source-repo.yml
│       ├── sync-marketplace.yml
│       └── validate-free-pack.yml
├── catalogs/
│   ├── index.json
│   └── latest.json
├── docs/
│   └── context-bank/
├── packs/
│   └── <creator>/
│       └── <slug>/
│           ├── manifest.json
│           ├── SKILL.md
│           ├── knowledge.md
│           ├── data.json
│           ├── examples/
│           ├── prompts/
│           └── assets/
└── scripts/
    ├── build-sync-payload.py
    ├── create-submission-pr.py
    ├── free_pack_common.py
    └── validate-free-pack.py
```

## Contributor Guide

- One PR should touch exactly one pack directory.
- Free packs only.
- No executables, symlinks, hidden files, or dangerous prompt/shell content.
- `manifest.json` and `SKILL.md` must agree on free pricing and category.

Recommended local validation:

```bash
printf '%s\n' \
  packs/<creator>/<slug>/manifest.json \
  packs/<creator>/<slug>/SKILL.md \
  > /tmp/changed-files.txt

python3 scripts/validate-free-pack.py \
  --repo-root . \
  --repo-url https://github.com/tigerokuma/context-bank-free-packs \
  --changed-files-file /tmp/changed-files.txt
```

## Maintainer Guide

1. Confirm the PR changes exactly one pack directory.
2. Review `manifest.json`, `SKILL.md`, and the changed file tree.
3. Confirm the `pull_request` validation workflow passed.
4. Merge if approved. Squash merge is acceptable.
5. After merge, run `pnpm free-pack:sync` in the private marketplace repo when you want marketplace visibility to update.

## Current MVP Boundaries

- No paid-pack logic.
- No marketplace production secrets in public PR validation.
- No direct write from this public repo into the private app.
- No `external_repo` registration flow yet.
- Post-merge marketplace reflection is still manual sync.
