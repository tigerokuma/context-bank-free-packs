# Autonomous Agent Loop — Operating Notes

These notes complement `SKILL.md`. They explain *why* the loop is shaped the way it is, so an agent can make sound judgment calls when an edge case isn't covered explicitly.

## Why the loop is issue-driven

The parent issue tracker is the single source of truth for what is worth working on. Anything that is not an issue is not work. This rule prevents two failure modes that recur in autonomous agents:

1. **Drift** — without a tracker, a long-running agent invents adjacent work that nobody asked for.
2. **Lossy hand-off** — without a tracker, the human cannot tell what the agent did, why, or what is left.

Issues, labels, and comments form an audit trail that survives session boundaries and humans rotating in and out.

## Why one issue → one PR

Bundling multiple issues into one PR optimizes for the agent's wall-clock time and pessimizes for the human's review time. Reviewers can hold one change in their head; they cannot hold five. The constraint also makes blocker chains visible: if PR #42 is the implementation of issue #17, then "issue #19 was blocked by #17" becomes mechanically checkable.

## Why the agent never closes issues

Closing is an approval signal. The agent's signal is "PR opened, marked pending-review." Mixing the two would let a faulty pass slip into the closed pile. Humans close after review, so the closed-pile is by construction reviewed work.

## Why the agent never merges PRs

Merging is also an approval signal — and merging into a default branch is irreversible in practice once the next commit lands on top. The agent has no authority for that decision. The PR is the deliverable; the merge is the human's call.

## Why blocked-by parsing is conservative

The loop treats `Blocked by #<N>` as a hard gate even when `<N>` is `pending-review`. The reason: a pending-review PR can still come back with substantive changes, which would invalidate work that started against an unmerged interface. Waiting until the upstream issue is *closed* (i.e. merged and accepted) is cheaper than redoing work.

## Why the planner can be skipped

Some issues are already small and unambiguous — a typo fix, a one-line config change, a rename. Running a planner sub-agent on those wastes tokens and slows iteration. The rule is: skip the planner only when the issue is *already* a sprint-shaped slice, and **record that decision** so the audit trail shows it was deliberate, not lazy.

## Why the evaluator drives the running system

A spec saying "the button submits the form" is satisfied by code that compiles and is satisfied better by code that, when run, actually submits the form. Static analysis catches a subset of breakage. The evaluator's job is to catch the rest by exercising the system the way a user would.

For backend-only sprints, this becomes "exercise the API the way the calling system would" — direct HTTP, CLI, or a thin harness. For frontend or integration sprints, it becomes "drive the UI the way a person would" — browser automation, real navigation, real input.

## Why three failed evaluator passes is the cap

After three failed evaluator passes, the bottleneck is almost never "one more generator iteration would have done it." It is usually: ambiguous spec, missing dependency, environment problem, or a real architectural conflict that wasn't visible from the issue. None of those are fixed by trying harder; all of them are fixed by surfacing the blocker to the human. The cap forces that surfacing rather than letting the agent burn budget.

## Why screencasts are required for FE / integration

A passing evaluator scorecard says *the agent says it works*. A screencast says *here is the system behaving as advertised, recorded once and forever*. For frontend changes especially, this is the only artifact a reviewer can verify in seconds without checking out the branch. The cost (a few seconds of recording) is much less than the cost of a missed regression discovered in production.

## Why integration issues are flagged separately

Cross-repo issues create coordination problems: the backend change must land before the frontend change can verify, the frontend change must land before the backend can be sure of the contract, and so on. Marking an issue `integration` early triggers the right verification path (drive the running stack end-to-end) and signals that the PR may need to land in two repos at coordinated times.

## Why labels are preferred over body parsing

Labels are structured data. Body lines are prose. Prose drifts as humans edit it. Whenever the loop relies on a body line (`Blocked by #N`, `Depends on #N`), it carries the risk of drift; whenever it relies on a label, it does not. The loop reads both because humans write both, but it trusts labels first.

## Why `needs-human` exists

`needs-human` is the agent's "I tried, here is what I learned, please look" signal. Without it, repeated-failure issues either disappear into the queue or get re-attempted forever. The label makes the human's queue explicit.

## Reusable knowledge becomes a skill

When the loop discovers something that recurs across multiple sprints — a chunking heuristic, a debugging recipe, a deployment incantation — that knowledge belongs in a reusable skill, not in a one-off comment buried in a closed issue. Promote it to a skill so the next sprint inherits it.

## Surfacing blockers fast

Most autonomous-agent failure modes look like the agent silently working around something it should have stopped on:

- `gh` missing auth → silently skipped issues
- target repo subdir missing → branched in the wrong place
- evaluator tool unavailable → invented evidence
- dirty working tree on default branch → committed unrelated changes
- ambiguous routing → guessed and was wrong

The cure is the same in every case: stop, tell the user exactly what is missing or ambiguous, and wait. The cost of pausing is minutes; the cost of an unwanted action can be hours of cleanup.

## What this pack is not

This pack does not specify:

- which planner / generator / evaluator implementations to use — those are platform-specific
- which issue tracker to use beyond "GitHub via `gh`"
- which CI rules apply in the target repo — those are the target repo's responsibility
- which review policy gates merging — that is the human's domain

It specifies the *contract* the autonomous agent honors. Implementations and policies fill in the details.
