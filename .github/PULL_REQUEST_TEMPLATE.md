## Free Pack Submission

Please use this PR template for free-pack submissions into the public repo.

### Submission Type

- [ ] New free pack
- [ ] Update to an existing free pack

### Required Metadata

- Creator handle:
- Pack slug:
- Pack directory: `packs/<creator>/<slug>/`
- Category:
- Confirmation that `priceType=free` in both `manifest.json` and `SKILL.md`:

### Submission Provenance

- Submission mode: `manual-pr` | `trusted-source-repo`
- Source repository URL (required for trusted-source-repo submissions):
- Source commit SHA (required for trusted-source-repo submissions):
- Source pack path (required for trusted-source-repo submissions):

### Pack Summary

Describe what the pack does in 2-4 sentences.

### Verification

List any local checks you ran. Example:

```text
python3 scripts/validate-free-pack.py --repo-root . --repo-url https://github.com/tigerokuma/context-bank-free-packs --changed-files-file /tmp/changed-files.txt
```

### Scope Checklist

- [ ] This PR changes exactly one pack directory under `packs/<creator>/<slug>/`
- [ ] `manifest.json` is present
- [ ] `SKILL.md` is present
- [ ] This pack is free and safe for public review
- [ ] No executables, symlinks, or hidden secrets are included
- [ ] I did not include paid-pack logic or private marketplace code
