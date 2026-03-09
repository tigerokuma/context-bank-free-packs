# Public Free-Pack Repo Layout

## Purpose

Define the canonical directory structure, per-pack manifest contract, and sync
surface for the public GitHub repository that receives free-pack pull requests.

This repo is the MVP source of truth for approved free packs after merge.

## Canonical Repo Layout

```text
<free-pack-repo>/
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── validate-free-pack.yml
│       └── sync-marketplace.yml
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
│   ├── index.json
│   └── latest.json
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

- Holds generated or maintainer-controlled aggregate manifests used for sync
- Should not be hand-edited by contributors unless the PR explicitly exists to
  repair generated catalog data

### `.github/workflows/`

- `validate-free-pack.yml` validates changed pack directories in pull requests
- `sync-marketplace.yml` runs after merge to publish normalized metadata to the
  private marketplace system
- `submit-from-trusted-source-repo.yml` can be called from a trusted source
  repo to open or update a central-repo submission PR

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
layout and marketplace sync contract for the public free-pack repository.

## `manifest.json` Contract

### Purpose

`manifest.json` is the machine-readable marketplace contract for one approved
free pack directory.

It exists so CI and the marketplace sync can validate pack identity and listing
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

## Sync Contract

After a maintainer merges a free-pack pull request:

1. The sync workflow identifies changed `packs/<creator>/<slug>/` directories.
2. The workflow reads `manifest.json`, `SKILL.md`, and the merged commit SHA.
3. The private marketplace stores a normalized snapshot for listing, preview,
   audit, and install metadata.
4. If sync fails, the merge remains in GitHub but the listing must stay
   unpublished until sync succeeds.

## Contributor Constraints

- Free-pack contributors may add or update only free packs
- Paid metadata must not appear in public free-pack directories
- Large binary or executable payloads are not allowed
- Hidden files such as `.DS_Store` or secret-bearing dotfiles are not allowed
- One pull request should target one pack directory unless a maintainer has
  explicitly requested a multi-pack operational change
