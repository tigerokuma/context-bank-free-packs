# Free Pack PR Rules

## Purpose

Define how contributors and maintainers use pull requests in the public
free-pack repo so free-pack submission stays reviewable, automatable, and safe.

## Submission Model

- Free packs are submitted through pull requests
- Pull requests target the public free-pack repo
- Merge is the approval event for a free-pack version in MVP
- The merged default-branch commit SHA becomes the approved source ref recorded
  by the marketplace

## Contributor Workflow

1. Fork the public free-pack repo or create a feature branch.
2. Add or update exactly one pack directory under `packs/<creator>/<slug>/`.
3. Update `manifest.json` and pack files together.
4. Open a pull request using the free-pack PR template.
5. Address CI failures and maintainer review comments.
6. Wait for maintainer merge before expecting marketplace publication.

## Allowed PR Scope

Default allowed scope for a submission PR:

- one pack directory under `packs/<creator>/<slug>/`
- related generated catalog changes if automation commits them
- minimal documentation changes directly needed to explain the pack

Default disallowed scope:

- multiple unrelated pack directories
- changes to paid-pack delivery code or private marketplace code
- unrelated workflow or repository administration changes
- hand-edited aggregate catalog files unless the PR exists specifically to fix
  them

## Required PR Content

Every free-pack submission PR should include:

- pack slug
- creator handle
- whether the PR creates a new pack or updates an existing pack
- short summary of what the pack does
- verification performed locally, if any
- confirmation that the pack is free

## Validation Expectations

CI should fail the PR if any of the following are true:

- `manifest.json` is missing
- `SKILL.md` is missing
- the changed path does not match `packs/<creator>/<slug>/`
- `manifest.json` and `SKILL.md` disagree on category or free pricing
- blocked executable files are present
- blocked prompt-injection or shell patterns are present
- asset or repository policy limits are exceeded

## Review Rules

- Maintainers review the PR diff, not only rendered files
- Maintainers must verify the manifest, `SKILL.md`, and changed file tree
- Rejection feedback should identify the failing file or rule and the minimum
  fix needed
- Merge means the changed pack version is approved for sync
- Maintainers may use squash merge; the resulting default-branch commit is the
  approved source ref

## Pack Update Rules

- Updates to an existing free pack must use the same directory path
- A pack update PR should not silently rename the creator handle or slug
- Renames or moves require an explicit maintainer-approved migration PR
- The previous approved marketplace version remains visible until post-merge
  sync succeeds

## Sync Rules

- Post-merge sync reads only merged default-branch state
- Marketplace publication must use the merged commit SHA, not the contributor
  branch SHA
- If sync fails, maintainers should treat the PR as merged but not yet
  published, and rerun or repair sync without asking contributors to reopen the
  submission

## Future Compatibility Rules

- Submission PRs currently use `source.type = internal_repo`
- The manifest and sync contract must stay compatible with a future
  `external_repo` model
- PR rules should avoid assumptions that would make later external-repo
  registration impossible
