---
name: "Autonomous Agent Loop Protocol"
slug: "autonomous-agent-loop-protocol"
creatorHandle: "tigerokuma"
category: "developer-tools"
priceType: "free"
tags:
  - "agent-loop"
  - "autonomous-agent"
  - "claude-code"
  - "planner-generator-evaluator"
  - "issue-driven"
  - "multi-repo"
  - "sub-agents"
  - "free-pack"
description: "Issue-driven autonomous loop for multi-repo workspaces: pick the highest-priority unblocked issue, run planner/generator/evaluator, open one PR, mark pending-review, unblock dependents, repeat."
---

# Autonomous Agent Loop Protocol

Use this pack when an autonomous coding agent operates across a multi-repo workspace and must drive its own work from a parent issue tracker. The protocol turns "make progress" into a deterministic loop: list issues, classify, pick one, plan, generate, evaluate, open exactly one PR, mark pending review, unblock dependents, repeat.

This pack is the operating contract, not project-specific code. It assumes one **parent workspace repo** that holds every product issue and one or more **target repos** where implementation lands. Replace placeholder names with the concrete repos used in your setup.

## When To Use

- the user gives an open-ended directive such as "work", "keep going", "continue", "run the loop", or "make progress"
- the user explicitly asks the agent to run the loop
- a one-off ad-hoc task is **not** what was asked for; one-off tasks are completed directly and the loop is offered afterward, not started silently

## Workspace Assumptions

| Slot | Role |
| --- | --- |
| `<workspace-repo>` | parent issue tracker; every product issue lives here |
| `<backend-repo>` | backend implementation target |
| `<frontend-repo>` | frontend implementation target *(optional)* |
| `<models-repo>` | shared models or contracts target *(optional)* |

Issues live in the workspace repo only. PRs are opened in the **target repo** that the issue routes to, never in the workspace repo, with one exception: workspace-docs issues whose resolved target *is* the workspace repo open their PR in that repo.

## Hard Rules

- one issue → one branch → one PR. Never bundle multiple issues.
- never close issues, never merge PRs, never push to default branches.
- never edit issue bodies authored by humans; communicate via comments and labels only.
- never invent new issues; surface scope creep to the user.
- never use `--no-verify`, `--force`, or rewrite published commits.
- respect package-level agent-instruction files inside each target repo as mandatory constraints.
- surface blockers immediately: missing auth, dirty working tree, missing tools, ambiguous routing, missing target-repo subdir, or repeated evaluator failure.

## The Loop

### Step 1 — Inventory

List open issues in the parent workspace repo:

```bash
gh issue list --repo <owner>/<workspace-repo> --state open --limit 200 \
  --json number,title,labels,assignees,body,url,updatedAt
```

Build an in-memory inventory: number, title, labels, body, blocked-by references, target repo, priority.

### Step 2 — Classify each issue

For each open issue, derive:

- **Priority** — first match wins:
  1. labels `priority/critical`, `priority/high`, `priority/medium`, `priority/low` (also accept `priority:<level>` form)
  2. `must-read` → `high`
  3. `security` → `high`
  4. otherwise → `medium`
- **Target repo** — first match wins:
  1. label `target/<repo>` where `<repo>` is one of the configured target slots → that repo
  2. label `area/backend` or `area/be` → `<backend-repo>`; `area/frontend` or `area/fe` → `<frontend-repo>`; `area/models` or `area/contracts` → `<models-repo>`; `area/docs` or `area/design` → `<workspace-repo>`
  3. infer from body — explicit file paths in one repo win; references to two or more repos mark the issue **integration**
  4. still ambiguous → **stop the loop** and ask; do not guess
- **Blocked status** — issue is **blocked** if any is true:
  1. label `blocked`
  2. body matches `Blocked by #<N>` or `Blocked by <owner>/<repo>#<N>` and that referenced issue is still **open** and not `pending-review`
  3. body matches `Depends on #<N>` referring to an open issue
- **Pending review** — issue carries label `pending-review`
- **Actionable** — `state:open` AND not `pending-review` AND not labeled `wontfix` / `duplicate` / `invalid` / `question` AND not assigned to a human (any non-agent assignee means a human owns it; ask before stealing)
- **Surface** — derived from target repo:
  - frontend target → **frontend**
  - backend or models target → **backend**
  - cross-repo or `integration` label → **integration**

If no actionable, unblocked issues remain, **stop the loop** and report counts of pending-review / blocked / ignored, plus a one-line note for each blocker chain. Do not invent work.

### Step 3 — Select the next target

From the actionable + unblocked set, pick the highest priority (`critical` > `high` > `medium` > `low`). Break ties in order:

1. smallest dependency fan-in (issues that unblock the most other work go first)
2. oldest `updatedAt`
3. lowest issue number

Announce the selection to the user in one sentence before starting work:
`Working on <workspace-repo>#<N> → <target-repo>: <title>`.

### Step 4 — Planner / Generator / Evaluator

For the selected issue:

1. **Plan** — invoke a `planner` sub-agent with issue title, body, acceptance criteria, target repo, and linked context. Planner returns a sprint-shaped specification scoped to the single issue. Skip planning only when the issue is already a tightly-scoped, unambiguous slice; record that decision.
2. **Generate** — invoke a `generator` sub-agent with the spec and target slice. Work happens on a feature branch inside the target repo's subdir:
   - branch name: `claude/issue-<N>-<short-slug>` from the target repo's default branch
   - generator commits in small reviewable chunks
   - generator must respect package-level agent-instruction files inside the target repo
3. **Evaluate** — invoke an `evaluator` sub-agent with the generator's implementation report. Evaluator drives the running app via browser automation for FE / integration work, and via direct HTTP / CLI checks for backend-only work. If a target repo is not yet present in the workspace and the sprint is unaffected by it, the evaluator records the absence in evidence and proceeds with the strongest available verification.
4. **Repair loop** — if evaluator returns `fail`, route actionable feedback back to the generator and re-run the evaluator. After **3 failed evaluator passes** on the same issue, stop, comment a blocker summary on the parent issue, leave the branch in place, label the issue `needs-human` (create the label if missing), and continue the outer loop with the next target.

### Step 5 — Capture a screencast (frontend and integration only)

Backend-only issues skip this step.

For frontend or integration issues, the evaluator must produce a recording of the primary accepted flow:

- record via the agent's browser-automation video capability and save to `docs/screencasts/issue-<N>-<YYYYMMDD-HHMM>.webm` inside the target repo
- if browser video is unavailable, fall back to screen recording or to a captured API exchange transcript with the matching extension at the same path
- commit the screencast on the feature branch in the same PR
- the PR body must embed the screencast and call out which flow it covers

### Step 6 — Open the pull request

From inside the target repo's subdir:

```bash
gh pr create \
  --title "<concise imperative title>" \
  --body "$(cat <<'EOF'
Resolves <owner>/<workspace-repo>#<N>

## Summary
- <bullet 1>
- <bullet 2>

## How this was verified
- Evaluator scorecard: <link or summary>
- Screencast: docs/screencasts/issue-<N>-<...>.webm  (FE / integration only)

## Out of scope
- <items intentionally not addressed>
EOF
)"
```

PR rules:

- the PR is opened in the **target repo**, not in the workspace repo (workspace-docs issues are the only exception)
- the body references the parent issue with `Resolves <owner>/<workspace-repo>#<N>`. Cross-repo `Resolves` does not auto-close, which is intentional — humans close.
- do not request reviewers, do not merge.

### Step 7 — Mark the parent issue pending review

```bash
gh issue edit <N> --repo <owner>/<workspace-repo> --add-label "pending-review"
gh issue comment <N> --repo <owner>/<workspace-repo> --body "PR opened: <pr-url>. Marked pending-review."
```

If the `pending-review` label does not exist, create it first:

```bash
gh label create pending-review --repo <owner>/<workspace-repo> --color FBCA04 --description "Awaiting human review"
```

Do not close the parent issue. The user closes it after review.

### Step 8 — Unblock dependents

Find every open workspace issue whose body or labels indicated it was blocked by the just-finished issue. For each:

- if the only blocker reference was the just-finished issue and the only block signal was a label, remove the `blocked` label
- if the block signal was a body line, leave the body alone (the user owns prose) but post a comment: `<workspace-repo>#<N> is now pending review; this issue may be unblocked.`
- re-run Step 2's classification on these issues so the next iteration sees them as unblocked candidates

### Step 9 — Loop

Return to Step 1. Re-list rather than reusing the stale inventory — the user may have added or edited issues while you were working. Continue until Step 2 reports no actionable, unblocked issues remain.

## Stop Conditions

The loop stops when **any** of these is true:

1. Step 2 reports no actionable, unblocked issues
2. the user interrupts
3. an unrecoverable blocker is hit: missing auth, missing tool, dirty working tree on a default branch, missing target-repo subdir, ambiguous routing, repeated evaluator failure on a single issue

On stop, report:

- issues completed this run (parent issue numbers + PR URLs)
- issues left blocked and the chain blocking each
- skills created or updated
- any `needs-human` labels applied

## Sub-Agent Contract

The loop assumes three named sub-agents — Planner, Generator, Evaluator — invokable through the host agent platform:

- **Planner** — converts an issue into a sprint specification. Returns acceptance criteria, file slice, test plan, risks.
- **Generator** — executes the spec on a feature branch in the target repo. Commits small reviewable chunks. Honors package-level agent-instruction files.
- **Evaluator** — verifies the change against the spec by exercising the running system. For FE / integration: browser automation. For backend: HTTP / CLI checks. Returns `pass` or `fail` with actionable feedback.

The orchestrator role itself is fulfilled by the main agent session interacting with the user.

## Safe Usage Notes

- never push to `main`, `master`, or any default branch directly; the PR is the deliverable
- never request reviewers and never merge — those belong to the human
- never use `--no-verify` or `--force`
- treat package-level agent-instruction files inside each target repo as mandatory constraints, not suggestions
- if the host platform's required tools (issue API, browser automation, recording) are unavailable, surface the blocker rather than papering over it
- recurring knowledge discovered during the loop should be promoted to a reusable skill, not memorized inline
