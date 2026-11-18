# Mistakes

## M001 - Dependent merge ran after delivery-binding validation failed

- Kind: mistake.
- Observed: 16 October 2026. The PR #7 delivery-binding command rejected missing What/Why sections, then the same PowerShell command continued into the normal merge. PR #7 was independently reviewed, green and within Tommy's existing delivery approval; its delivery binding was not established before landing.
- Cause: confirmed. The command sequence did not check the native process exit status between dependent operations. The governing sequential-execution requirement was clear and violated.
- Impact and priority: P2. The authorized merge landed with a missing workflow delivery record; the observed review and CI evidence remain valid.
- Source owner: this work-items delivery session, codex:01a1415f-6448-7123-8b17-c7fb67aee637; command orchestration.
- State: resolved.
- Repair: PR #7 description was corrected; its binding then correctly reported that an already merged PR owns no delivery. This incident retains the missing pre-merge record rather than claiming a retroactive binding. Landing commit 7c4dcd2147a46005020ee4f2b68db563d71a52a5; causal main CI 38836538305 passed.
- Prevention: every dependent native command must stop on a nonzero exit before the following mutation. Use checked subprocess calls or an explicit LASTEXITCODE guard.
- Resolution condition: a rejected prerequisite exits the command sequence before its following dependent action, and subsequent publication commands guard every prerequisite.
- Verification: the attempted binding reconciliation exited 2 and prevented the following run-list command from executing. The v0.1.0 publication sequence checked each preceding exit before tagging, pushing or publishing, and completed successfully.
- Next action: none; retain the incident and prevention evidence as learning history.

## M002 - Work-items delivery spent excessive time on process overhead

- Kind: mistake.
- Observed: 16 October 2026. Tommy reported roughly four hours elapsed and asked whether the recent Core slowdown fixes were active. This session acknowledged repeated review cycles and rollout preparation contributed avoidable overhead; the work is several delivered slices, not one inherently four-hour PR.
- Cause: confirmed avoidable command/path errors and repeated documentation-review cycles. Two separate record-only PRs added delivery work while personal note batching was already the intended policy. All six skill files changed by Core WorkflowProportionality PR #268 exactly match the active session snapshot, so missing that fix is ruled out. The causal share of other hook costs and CI latency is not yet established; do not blame Core from elapsed time alone.
- Impact and priority: P2. Excessive elapsed time, user interruption and loss of confidence despite delivered functionality.
- Source owner: this delivery session for orchestration; any proven standards defect remains with tj-agents/core.
- State: open.
- Repair link: docs/plans/problem-management/PLAN.md; Core WorkflowProportionality PR #268 is the existing relevant correction to reconcile, not a new repair owner.
- Prevention: apply loaded proportionality guidance; batch independent reads; avoid redundant review/verification and new recording-only delivery cycles; report remaining scope and observed delays accurately.
- Resolution condition: establish whether the active snapshot contains the recent fix, identify observed overhead against the governing rules, and verify the remaining delivery follows the applicable proportional workflow.
- Verification evidence: PR #268 commit 2380644a and installed/session snapshot comparison retained in temporary work-items-slowdown-fix-comparison.json; all six installed and session-snapshot files match. Core PR #269 independently owns the versioned-cache and latest-source cutover; it is not duplicated here. Reviews also caught genuine integrity, locking, helper-discovery and typed-admission defects, so their value must be retained in the reflection. Final elapsed-time attribution remains open.
- Next action: reconcile that comparison and the command/review history, retaining unresolved concrete defects for correction. Tommy explicitly requested keeping a note and making sure this is fixed; no new repair detour or per-record publication is started.
