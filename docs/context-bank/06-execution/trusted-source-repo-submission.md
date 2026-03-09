# Trusted Source Repo Submission

## Purpose

Define the MVP path for creating a free-pack submission PR from a separate,
trusted repository into the central public free-pack repo.

This is the preferred automation layer for owner-managed repos. It keeps the
approval event in GitHub pull requests while avoiding marketplace secrets in the
public repo.

## PR-First Decision

MVP uses pull requests, not issues, for trusted source repo submission.

Why:

- the hybrid submission strategy is GitHub-first for free packs
- maintainers need a real file diff to review before approval
- merge must remain the approval event recorded by the marketplace
- central repo CI already validates untrusted PRs safely on `pull_request`

Issue-based intake remains a future fallback option, not the primary path here.

## Flow

1. A trusted source repo keeps the authored pack files.
2. A source repo workflow calls the central repo reusable workflow.
3. The reusable workflow checks out both repos, copies one pack directory into
   `packs/<creator>/<slug>/`, generates `manifest.json`, and runs the central
   validator before opening or updating a PR.
4. The PR lands in the central repo with source provenance in the body:
   source repo URL, source ref, and source pack path.
5. Central repo CI runs `validate-free-pack.yml` on the untrusted PR.
6. A maintainer reviews the PR diff and CI result, then merges if approved.
7. After merge, the central repo publish workflow generates or reuses the
   pack-only ZIP asset and refreshes `catalogs/pack-artifacts.json`.

## Security Model

### Central Public Repo

- keeps using the untrusted `pull_request` validation workflow
- stores no marketplace production secrets
- does not receive service-role keys or paid-artifact credentials

### Trusted Source Repo

- stores the submission credential
- may use a fine-grained PAT in MVP
- should scope the credential only to the central repo

Required minimum repository permissions for the central repo credential:

- `Contents: Read and write`
- `Pull requests: Read and write`
- `Metadata: Read`

## Token Choice

### Fine-Grained PAT

- simplest MVP option
- easy to create for one owner-managed repo pair
- should be restricted to the central repo only

### GitHub App

- better long-term isolation and rotation story
- preferable once multiple trusted source repos need the same automation
- more setup than needed for the first MVP

MVP recommendation: start with a fine-grained PAT, then migrate to a GitHub App
once the trusted source repo model expands.

## Source Repo Workflow Example

```yaml
name: Submit Context Bank Free Pack

on:
  workflow_dispatch:

jobs:
  submit:
    permissions:
      contents: read
    uses: tigerokuma/context-bank-free-packs/.github/workflows/submit-from-trusted-source-repo.yml@main
    with:
      pack_path: mock/packs/japan-stock-trends-sample
      creator_handle: tigerokuma
    secrets:
      central_repo_token: ${{ secrets.CONTEXT_BANK_FREE_PACK_SUBMISSION_TOKEN }}
```

## Reviewer Expectations

Trusted-source PRs should still be reviewable as normal central-repo PRs.

Maintainers should see:

- exactly one changed pack directory
- generated `manifest.json`
- authored `SKILL.md` and pack files
- source repo URL, ref, and path in the PR body
- passing central validation CI

## Post-Merge Handoff

Merge remains the approval event.

Post-merge publishing is handled inside the central repo:

1. merge the central repo PR
2. confirm `publish-pack-artifacts.yml` completed successfully
3. confirm the `pack-artifacts` release asset and `catalogs/pack-artifacts.json`
   entry were updated as expected

If publishing fails, the merged PR stays approved in GitHub, but the previous
committed artifact catalog must remain intact until the workflow succeeds.
