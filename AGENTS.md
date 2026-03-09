# Agent Routing

This repo accepts free-pack submissions through pull requests.

If a user asks how to submit a pack, how to prepare files for submission, how to generate or repair `manifest.json`, how to fix `SKILL.md`, or how to turn arbitrary local files into a valid free-pack PR, use the `free-pack-submission-prep` skill at `skills/free-pack-submission-prep/SKILL.md`.

Agent requirements:

- inspect the user's files first and infer answers from local content before asking questions
- avoid broad open-ended questions; ask only for missing high-impact metadata when it cannot be inferred safely
- normalize safe inputs into `packs/<creator>/<slug>/`
- ensure `manifest.json` and `SKILL.md` satisfy the repo validator and safety rules
- run local validation before claiming the pack is ready

Operational note:

- PAT-backed GitHub secrets created on 2026-03-09 use a 90-day lifetime and are expected to expire on 2026-06-07; rotate before expiry, then run an end-to-end automation test
