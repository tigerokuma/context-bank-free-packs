# Hybrid Submission Strategy

## Decision Summary

Context Bank adopts a hybrid creator submission model.

- Free packs are GitHub-first.
- Paid packs remain web-submitted and Context Bank-controlled.
- The existing web submission flow stays available for creators who do not use
  GitHub confidently.

This keeps free-pack supply growth aligned with GitHub-native workflows while
preserving a simpler path for paid submissions and non-technical creators.

## Why This Change Exists

- Technical creators already package skills in Git repositories, so forcing ZIP
  upload adds avoidable friction.
- GitHub-native intake makes automated validation, CI review, and final
  approval cheaper to operate.
- Paid packs need entitlement-aware delivery and should not depend on public
  GitHub hosting.
- The marketplace still needs a web fallback so GitHub literacy does not become
  a hard requirement for participation.

## Operating Model

### Private Application Repo

- Holds the marketplace web app, auth, purchases, entitlements, admin review
  tools, and paid artifact delivery
- Remains private

### Public Free-Pack Repo

- Holds approved free-pack directories, validation workflows, and maintainer
  review history
- Accepts creator-submitted pull requests against a defined pack directory
  structure
- Becomes the canonical source for approved free listings in MVP
  See `02-product/free-pack-repo-layout.md` and
  `06-execution/free-pack-pr-rules.md`

## Channel Policy

| Pack type | Preferred submission path | Allowed fallback | Distribution policy |
| --- | --- | --- | --- |
| Free | Public GitHub repo pull request | Web submission for creators who cannot use GitHub | Public after approval |
| Paid | Web submission only | None | Entitlement-gated only |

## Review Model

### Free Packs

1. Creator forks the public free-pack repo or creates a feature branch.
2. Creator adds or updates a pack directory plus listing metadata in the
   required location.
3. GitHub Actions run validation and safety checks without privileged
   marketplace secrets.
4. Operator reviews the PR diff, README, file tree, scan result, and category
   or pricing policy.
5. Approval is represented by merging the PR into the public repo default
   branch.
6. The marketplace syncs approved metadata from the merged commit for catalog
   display.

### Paid Packs And Web Fallback Packs

1. Creator uses the web dashboard submission flow.
2. Context Bank stores the uploaded artifact privately.
3. The existing moderation queue handles approval and rejection.
4. Approved paid artifacts stay behind entitlement checks.

## Core Principles

- GitHub-first for free supply growth
- Review before publish
- Merged commit SHAs are the approvable source of truth for GitHub-submitted
  free packs
- No paid artifact distribution from public GitHub infrastructure
- Web fallback remains available for creators who need it
- Marketplace pages should render from cached or normalized metadata, not only
  from live GitHub API calls

## Architecture Consequences

- GitHub becomes the canonical source repo for approved free packs in MVP, but
  not the system of record for payments, entitlements, or payout history.
- Approved free listings should store a normalized snapshot of repository
  metadata, the merged commit SHA, and source coordinates for the pack
  directory.
- Public GitHub hosting may back free-pack downloads, but the marketplace still
  needs local records for search, moderation, analytics, and auditability.
- Paid listings continue to rely on Context Bank-controlled storage and
  authenticated delivery surfaces.

## Source Schema

Approved free listings should store source coordinates in a future-proof shape:

```yaml
source:
  type: internal_repo | external_repo
  repoUrl: https://github.com/<owner>/<repo>
  ref: <commit-sha-or-tag>
  path: packs/<creator>/<slug>
```

MVP uses `internal_repo` for GitHub-submitted free packs because the approved
source lives in the central public repo after merge. The schema is intentionally
shaped so a later external-repo registry model can use `external_repo` without
changing the marketplace contract.

## Explicit Non-Goals

- Public GitHub distribution for paid packs
- Requiring every creator to understand Git, PRs, or GitHub Actions
- Rendering marketplace pages by live-calling GitHub on every request
- Accepting mutable branch heads without tying approval to a merged commit SHA
