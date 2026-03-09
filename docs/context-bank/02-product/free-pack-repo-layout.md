# Public Free-Pack Repo Layout

## Purpose

Define the canonical directory structure, per-pack manifest contract, and sync
surface for the public GitHub repository that receives free-pack pull requests.

This repo is the MVP source of truth for approved free packs after merge.

## Canonical Repo Layout

```text
<free-pack-repo>/
├── AGENTS.md
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── validate-free-pack.yml
│       └── publish-pack-artifacts.yml
├── skills/
│   └── free-pack-submission-prep/
│       ├── SKILL.md
│       └── scripts/
│           └── prepare_free_pack_submission.py
├── packs/
│   └── <creator-handle>/
│       └── <pack-slug>/
│           ├── manifest.json
│           ├── SKILL.md
│           ├── knowledge.md
│           ├── data.json
│           ├── examples/
│           ├── prompts/
│           └── assets/
├── catalogs/
│   └── pack-artifacts.json
└── README.md
```

## Directory Rules

### `packs/`

- Holds all creator-submitted free packs
- Path must be `packs/<creator-handle>/<pack-slug>/`
- One pack slug may exist only once within the repo
- All pack files for a PR-reviewed free pack must live under exactly one pack
  directory

### `catalogs/`

- Holds generated aggregate artifact metadata for downstream consumers
- Should not be hand-edited by contributors unless the PR explicitly exists to
  repair generated catalog data

### `.github/workflows/`

- `validate-free-pack.yml` validates changed pack directories in pull requests
- `publish-pack-artifacts.yml` runs after merge to publish pack-only ZIP assets
  plus the generated artifact catalog, then dispatches the downstream private
  app repo sync workflow after a successful publish
- `submit-from-trusted-source-repo.yml` can be called from a trusted source
  repo to open or update a central-repo submission PR

### `AGENTS.md` and `skills/`

- `AGENTS.md` is the short routing layer for repo-aware agents
- agents that need to prepare a submission should use the
  `free-pack-submission-prep` skill
- the skill may accept flexible local input, but the committed output must still
  end in canonical `packs/<creator-handle>/<pack-slug>/` form

## Per-Pack Directory Contract

Canonical pack path example:

```text
packs/tigerokuma/baseball-team-analysis/
```

Required files:

- `manifest.json`
- `SKILL.md`

Optional files:

- `knowledge.md`
- `data.json`
- `examples/`
- `prompts/`
- `assets/`

The internal contents of `SKILL.md` and optional pack files follow the generic
pack format rules from `pack-format.md`. This doc defines the additional repo
layout and pack artifact publishing contract for the public free-pack repository.

## `manifest.json` Contract

### Purpose

`manifest.json` is the machine-readable marketplace contract for one approved
free pack directory.

It exists so CI and the pack artifact publisher can validate pack identity and listing
metadata without parsing only markdown.

### Canonical Shape

```json
{
  "schemaVersion": 1,
  "pack": {
    "slug": "baseball-team-analysis",
    "creatorHandle": "tigerokuma",
    "title": "Baseball Team Analysis",
    "summary": "NPB team analysis pack for scouting and match preparation.",
    "category": "sports",
    "tags": ["baseball", "team-analysis", "npb"],
    "priceType": "free"
  },
  "source": {
    "type": "internal_repo",
    "repoUrl": "https://github.com/<owner>/<free-pack-repo>",
    "path": "packs/tigerokuma/baseball-team-analysis"
  },
  "support": {
    "homepage": "https://github.com/<owner>/<free-pack-repo>/tree/main/packs/tigerokuma/baseball-team-analysis",
    "issues": "https://github.com/<owner>/<free-pack-repo>/issues"
  }
}
```

### Required Fields

- `schemaVersion`
- `pack.slug`
- `pack.creatorHandle`
- `pack.title`
- `pack.summary`
- `pack.category`
- `pack.tags`
- `pack.priceType`
- `source.type`
- `source.repoUrl`
- `source.path`

### Validation Rules

- `schemaVersion` must be `1`
- `pack.priceType` must be `free`
- `pack.slug` must match the final directory segment
- `pack.creatorHandle` must match the creator directory segment
- `source.type` must be `internal_repo` in MVP
- `source.repoUrl` must point at the public free-pack repo
- `source.path` must exactly match the pack directory path
- `pack.category` must be an allowed marketplace category
- `pack.tags` must be non-empty and normalized for marketplace search
- `pack.summary` must be concise and suitable for marketplace cards

### Consistency Rules With `SKILL.md`

- `manifest.json` and `SKILL.md` must agree on slug or name identity
- `priceType` in `SKILL.md` frontmatter must also be `free`
- `category` must match between the manifest and `SKILL.md`
- Tags and short description should not materially conflict between the manifest
  and `SKILL.md`

### Submission Provenance Rules

- A PR created from another trusted repo must still land as a normal central
  repo pull request
- The PR body should include the source repository URL, source ref, and source
  pack path
- Generated `manifest.json` in the central repo remains the publishable
  contract, even when the authored pack files originate in another repo

## Normalized Source Coordinates

The private marketplace persists approved free-pack source data in this
future-proof shape:

```yaml
source:
  type: internal_repo | external_repo
  repoUrl: https://github.com/<owner>/<repo>
  ref: <merged-commit-sha-or-tag>
  path: packs/<creator>/<slug>
```

In MVP:

- `type` is always `internal_repo`
- `repoUrl` is the public free-pack repo URL
- `ref` is the merged default-branch commit SHA that introduced or updated the
  approved pack
- `path` is the pack directory path inside the public repo

## Artifact Publishing Contract

After a maintainer merges a free-pack pull request:

1. The publish workflow scans all current `packs/<creator>/<slug>/`
   directories.
2. For each pack, it resolves the latest commit that touched that directory as
   the pack `sourceRef`.
3. The workflow builds a ZIP whose extracted root is
   `<creator-handle>-<pack-slug>/` and whose contents include only that pack.
4. The workflow uploads missing ZIPs to the public `pack-artifacts` GitHub
   Release and leaves historical assets untouched.
5. The workflow rewrites `catalogs/pack-artifacts.json` to point each current
   pack at its latest pack-only ZIP.
6. After a successful publish/catalog update, the workflow sends a
   `repository_dispatch` event to `tigerokuma/context-bank` so the private app
   repo can run its `sync-free-packs.yml` workflow automatically.
7. If publishing fails, the merge remains in GitHub and the previously
   committed catalog stays intact.

## Contributor Constraints

- Free-pack contributors may add or update only free packs
- Paid metadata must not appear in public free-pack directories
- Large binary or executable payloads are not allowed
- Hidden files such as `.DS_Store` or secret-bearing dotfiles are not allowed
- Agent-assisted prep may transform arbitrary safe local files before commit,
  but the final submission contract does not change
- One pull request should target one pack directory unless a maintainer has
  explicitly requested a multi-pack operational change
