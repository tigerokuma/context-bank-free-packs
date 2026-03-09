# Context Bank Free Packs

This repository is the public free-pack intake for Context Bank.

Its MVP purpose is narrow:

- contributors submit free packs through GitHub pull requests
- maintainers review and merge approved packs
- GitHub Actions validate packs safely without marketplace secrets
- post-merge sync produces normalized payloads for a future private marketplace
  connection

Paid packs are out of scope here. The public repo only supports free packs with
`source.type = internal_repo` in MVP.

See the source-of-truth docs:

- [Hybrid Submission Strategy](docs/context-bank/00-overview/hybrid-submission-strategy.md)
- [Public Free-Pack Repo Layout](docs/context-bank/02-product/free-pack-repo-layout.md)
- [Free Pack PR Rules](docs/context-bank/06-execution/free-pack-pr-rules.md)
- [Trusted Source Repo Submission](docs/context-bank/06-execution/trusted-source-repo-submission.md)

## Submission Flow

1. Fork this repository or create a feature branch.
2. Add or update exactly one pack directory at `packs/<creator>/<slug>/`.
3. Include both `manifest.json` and `SKILL.md`.
4. Open a pull request with the free-pack PR template.
5. GitHub Actions validate the changed pack directory only.
6. A maintainer reviews the diff and merges the PR if approved.
7. After merge, the sync workflow generates normalized metadata from the merged
   commit SHA.

Merge is the approval event in this MVP.

Owner-managed source repos may also create or update these PRs automatically by
calling the reusable workflow at
`.github/workflows/submit-from-trusted-source-repo.yml`. That flow still ends
in a normal central-repo PR and uses the same validation and merge rules.

## Directory Layout

```text
.
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── sync-marketplace.yml
│       └── validate-free-pack.yml
├── catalogs/
│   ├── index.json
│   └── latest.json
├── docs/
│   └── context-bank/
│       ├── 00-overview/
│       ├── 02-product/
│       └── 06-execution/
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
    ├── free_pack_common.py
    └── validate-free-pack.py
```

## Contributor Guide

Requirements:

- one PR should touch exactly one pack directory under `packs/<creator>/<slug>/`
- free packs only
- no executables, symlinks, or dangerous shell/prompt-injection content
- `manifest.json` and `SKILL.md` must agree on free pricing and category

Recommended steps:

1. Copy the reference pack at
   [packs/context-bank/sample-free-pack](packs/context-bank/sample-free-pack).
2. Rename the path to your own `packs/<creator>/<slug>/`.
3. Update `manifest.json`:
   - keep `schemaVersion = 1`
   - set `pack.priceType = "free"`
   - set `source.type = "internal_repo"`
   - set `source.repoUrl = "https://github.com/tigerokuma/context-bank-free-packs"`
   - set `source.path` to your pack directory
4. Update `SKILL.md` frontmatter so `slug`, `creatorHandle`, `category`, and
   `priceType` match the manifest.
5. Run local validation:

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

6. Open a pull request with the repository template.

## Maintainer Guide

When reviewing a submission PR:

1. Confirm the PR changes exactly one pack directory.
2. Review `manifest.json`, `SKILL.md`, and the changed file tree.
3. Confirm CI passed on the untrusted `pull_request` workflow.
4. Check that the pack is clearly free and safe for public review.
5. Merge when approved. Squash merge is acceptable.

After merge:

1. `sync-marketplace.yml` runs on the merged default-branch commit.
2. The workflow writes normalized payloads to an artifact.
3. MVP publication still happens by running `pnpm free-pack:sync` in the
   private marketplace repo.
4. The artifact remains the safe scaffold for a future private marketplace sync.

This repo intentionally does not publish directly into production systems yet.

## Validation Rules

The PR validator currently enforces:

- changed pack path must resolve to `packs/<creator>/<slug>/`
- only one changed pack directory is allowed in a submission PR
- `manifest.json` must exist and follow the MVP contract
- `SKILL.md` must exist and include matching frontmatter
- `pack.priceType` and `SKILL.md` `priceType` must both be `free`
- `source.type` must be `internal_repo`
- executable bits, symlinks, and blocked executable extensions are rejected
- basic dangerous shell and prompt-injection strings are rejected

The validator is intentionally conservative for public PR safety.

## Current MVP Boundaries

- no paid-pack logic
- no marketplace secrets
- no direct write into the private app
- no `external_repo` registration flow yet
- sync produces artifacts only; it does not mutate catalogs automatically
