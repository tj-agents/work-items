# GitHub work-items implementation

Current execution checkpoint: see **Shared runtime readiness - 20 October 2026** below.
The earlier foundation/transport entries are retained history. This checkout owns shared-runtime
PR #20 and the four-PR readiness assessment requested in the handoff; it does not take over the
broader tracker/session implementation or consumer migration.

Authorized by Tommy on 16 October 2026: implement the approved optional work-items package,
shared integration, publication and personal repository adoption. Cross-repository decisions remain
in docs/plans/problem-management/PLAN.md. This source plan owns package implementation only.

Owner: codex:01a1415f-6448-7123-8b17-c7fb67aee637.
Repository: tj-agents/work-items (private). Pilot: its own issues only.

## Delivery slices

1. Feature/WorkItemTemplates from initial scaffold bea56d5: five schemas generate JSON skeletons,
   local validation and deterministic Markdown previews. Under 1,000 substantive code/test lines.
   Required: unit tests, template conformance, generated-output check, both-host mapping review.
2. GitHub transport from merged foundation: explicit source repository config, create/reconcile,
   list/read/update/link/close and live pilot; focused API-failure and duplicate-request tests.
3. Installation/selection with marketplace and Core owners; no employer changes.

## Acceptance

- Feature/task/bug/mistake/debt scaffolds and validation come from canonical JSON schemas.
- Preview is local and deterministic; invalid/missing facts never submit an issue.
- Explicit selection binds writes to the source repo and never defaults to a different tracker.
- GitHub issue identities work across machines; uncertain creates reconcile before any retry.
- Updates preserve existing evidence; resolution includes actual verification evidence.
- Both generated host adapters use the same source and include their shipped dependencies.
- Windows and Linux source CI and a live pilot pass before consumer rollout.

## Progress

Scaffold generated from current Template source, private GitHub repository created, and
pinned plugin-repository standards write/check passed (marketplace 4962303949fd60d66682c0012644e6a684e200d7).
Initial commit bea56d5 is pushed. Source implementation now starts on Feature/WorkItemTemplates.
No transport, migration, installed-host acceptance or unattended execution is claimed yet.

## Next action

Implement and verify local schema/template/preview slice, review and deliver it, then continue transport.

```agent-host-coverage
{"schema_version":1,"shared_source":".agents/work-items/utility/manage","hosts":[{"host":"claude","behavior":"Run the selected deterministic work-item script","source":".agents/work-items/utility/manage/SKILL.md","mapping":"Generated skills/manage adapter and canonical payload","verification":{"level":"planned","result":"pending","evidence":"Generator and package validation pending"}},{"host":"codex","behavior":"Run the selected deterministic work-item script","source":".agents/work-items/utility/manage/SKILL.md","mapping":"Generated skills/manage adapter and canonical payload","verification":{"level":"planned","result":"pending","evidence":"Generator and package validation pending"}}]}
```

## Dependent transport slice

Template PR #12 must land and release before the foundation can pass remote CI. Its CI-policy
merge gate and pending remote checks are a concrete parent-delivery constraint. Proceed with
the approved transport in a proper local stack while that prerequisite is validated.
Parent: Feature/WorkItemTemplates at 3855e71fb97c8f0e37c08d0911099120fe78a998.
Child: Feature/GitHubTransport, targeting the parent when published; child review covers only
transport delta, tests cover cumulative source. New worktree isolates the frozen parent review.
After the parent pin repair/merge, replay the child-only commits onto the updated base and revalidate.
The child plan now owns this package's active progress; the parent copy stays frozen for its review.

PR: not opened. Expected transport implementation and tests under 1,000 substantive changed lines.
Remote CI, live pilot and consumer writes remain pending the dependency and their actual validation.

Transport checkpoint: local create/reconcile, read/list, hash-checked update, append notes/links,
verified close and explicit adoption are implemented. Seventeen cumulative unit/CLI tests pass.
The transport uses current GitHub REST issue and repository issue-type endpoints (API 2026-03-10).
Concurrency limitations are explicit; no distributed lock or exactly-once create is claimed.
Next: independent review and controlled live pilot in tj-agents/work-items, then Core integration.

## Live pilot repair checkpoint (16 October 2026)

Initial pilot created Feature issues #1 and #2 for the same persisted request ID. Root source B001
preserves the evidence; the cause of the immediate missing list entry was not captured. Do not claim
retry acceptance from the earlier mocked tests. Durable request receipts now reserve before POST and
retain returned identities in the shared local Git metadata. Pending intent never authorizes another
POST; on another machine or after receipt loss, create --reconcile-only refuses submission when the
remote marker cannot be found. Comments use the same receipt protection. Cross-machine concurrent
creates remain explicitly outside any exactly-once claim. Twenty-three tests pass, including stale-list
and uncertain-response regression cases; 49 generated files are current. Independent repair review and
repeat live pilot are next. The foundation is PR #3 at 8ec0b6a; GitHub blocked jobs before startup due to
account billing/spending limits. User choice between public generic tooling and restoring private CI is
pending; no CI retry, green remote result or installed-host acceptance is claimed.

## Core adapter slice

Active child Feature/CoreRecordAdapter starts at parent Feature/GitHubTransport 54edc5f while the
parent's frozen retry repair is independently reviewed and the foundation's external CI block clears.
This proper dependent stack keeps each reviewed candidate unchanged. This child owns current package
progress; earlier plan copies remain frozen with their delivery candidates. No installation or migration
is claimed. The Core protocol owner is core/.worktrees/Feature-ProblemRecordBackends/plans/problem-record-backends/PLAN.md.

Scope: ship scripts/read_problem_record.py, coordinated explicit .work-items.json and .problem-records.json
adoption, deterministic optional typed disposition fences, complete shared problem facts and focused
protocol/adoption tests. Refuse an existing different provider before writing either selection. Missing
or malformed provider declarations never silently choose this package. Installed-host and live Core
admission acceptance wait for both packages' reviewed publication. Use the existing qualified foreign
plugin injector rather than adding a backend-specific registry or globally adopting personal policy.

## Verified stack checkpoint (16 October 2026)

Tommy approved making only this generic tooling repository public. Foundation PR #3 merged at
66aadc23819835469e72d8604d5a788da7b74211 after explicit CI-caller approval; causal main CI
38831521132 passed. Transport parent d7fe04f has complete native and workflow/security review.
Fresh persisted pilot #4 returned the same issue on immediate create retry, passed hash-checked
update, reused a repeated note, linked PR #3 and closed with verification. Original failed pilot
issues #1 and #2 closed with truthful evidence; source B001 retains their failure history and
does not claim a proven upstream cause. Its separate docs branch publishes that retained record.

Adapter source was committed at dc13131 and its immediate transport parent reconciled at
71de17a; all 28 tests and 53 generated files pass. The source supports explicit coordinated
tracker/provider selection and a read-only strict Core reader. Crash-interrupted adoption fails
closed until repeated adoption completes both files; no filesystem transaction is claimed.
Core's provider slice has 41 passing tests and isolated packaged entry-point checks, with its
review path finding rejected by executable evidence. No native installation, live Core admission,
producer release, consumer migration or both-host installed acceptance is claimed yet.
Next: freeze and review this adapter delta against the transport parent, deliver stack order,
publish an immutable release and register optional discovery before personal adoption.

Adapter review P2 accepted and reproduced: a manually edited body with a stale managed trailer must not reach Core. The reader now checks the same rendered-body digest as update. The regression and full package checks run before the correction checkpoint.


## Adapter review correction

Independent workflow review found metadata-only kind changes could disagree with the hashed body, and concurrent adoption could roll back another successful writer. Reject ambiguous/mismatched Tracking kinds and serialize the complete adoption operation with a crash-released OS file lock in Git runtime metadata. Keep rollback inside the lock. Claude script permissions must include command arguments. Add focused regression cases, regenerate both hosts, then review the committed correction. Transport PR #5 and retained B001 PR #6 are merged; Core PR #272 merged at 6aea302, with causal main CI 38834317856 pending.

Correction validation: 32 tests cover stale body hashes, metadata kind disagreement, overlapping adoption rollback and process-exit lock release. Generation remains 53 files. Native and workflow/security correction review follows the committed checkpoint.

Follow-up review: preserve arbitrary Markdown template examples by binding kind plus rendered text in a new optional managed metadata digest; old four-field metadata stays readable, while Core admission requires an explicit managed update to add the binding. Preflight a foreign provider before creating even runtime lock metadata, then recheck under the lock. Regression covers examples in summary/owner/links and legacy read/admission behavior.

## Shared runtime readiness - 20 October 2026

Authority: Tommy requested execution of
`C:/Users/TommySeery/.claude/plans/core/handoff-work-items-runtime.md` from this checkout.
Commit/push and PR preparation are authorized; Tommy alone merges. No new hooks, gates,
launch-time plugin refresh, credential changes or consumer cutover belong to this slice.
Owner: codex:01a15674-78c1-7703-8f6f-53e59ab10e57; registered work item
`work-items/shared-runtime`, branch `Refactor/SharedWorkItemRuntime`.

The broader source goal and its independent migration owner remain in
`C:/Users/TommySeery/source/repos/tj-agents/core/.worktrees/Feature-TrackerAwareSkills/plans/tracker-aware-skills/GOAL.md`.
That goal records the completed component assessment, accepted extraction boundaries, review
repairs and installed Windows/Linux evidence. Carry those decisions forward. Its later backend
decision selects GitHub for personal backlog content and preserves Azure for Infonetica; the
historical personal Azure organization/setup gate does not authorize a new personal Azure rollout.

Tommy's target owner for `session_store` and `work_item_sessions` is Work Items. The existing
Core Machine SQLite store remains the current implementation. This readiness slice does not
move it, create another database or claim that shared cloud-record mechanics deliver session storage.
The older additive session-reference design and any package relocation need reconciliation in
their own source slice before implementation.

### Frozen deliveries and observed checks

| Repository / PR | Exact head | Base | Observed state |
| --- | --- | --- | --- |
| tj-agents/work-items #20 | `9b2a2df1d8ff2a6c4968b39624cbdc683e33da07` | main `a69c5cd11e2f842631fdecdfa923d44fa9a494b1` | All seven reported checks pass; mergeable/CLEAN. Marked ready for review in this session; no merge. |
| tj-agents/core #298 | `23e842c62feb9203d73cb94c75e945c42b3e6ac8` | main, observed `86dbae8a9fa199e451017ef4c51bcbae6a5587a9` | Required Windows/Linux/guard/aggregate checks pass at the head; regenerate skipped by workflow. REST reports mergeable/clean. Already ready; manual published-contract hold remains. |
| tj-agents/personal #5 | `f8d00d79be792df1ec076f3482d9ada65c8edbf1` | PR #4 `Feature/PersonalWorkItemSkills`, `6d59214c199c6ecbd790b8beb185cfdfe591ec27` | Draft. Windows/Linux verify fail only at published skill-reference checks; hosts and policy pass. |
| tj-agents/infonetica #12 | `53e3baf53de06ee8cb1d1b39e48045f132f29d5f` | PR #6 `Feature/WorkCommunications`, `9546906d5358317dd249db901a56e0c2ce9226fe` | Draft. CI job never started because GitHub rejected account payments/spending limits. |

Review records were inspected directly, rather than inferred from PR prose or GitHub reviews
(the GitHub review lists are empty). All four local work orders are complete and approved at
the exact heads above. Their paths below are relative to each repository's Git common directory:

- Work Items: `agent-workflow/reviews/672e74d4092632696a902e538617c70d52e3829681dfb5b82f29c459111fa489/work-order.md`.
  The final incremental pass records actual native review and an independent valid workflow review,
  all five retained repairs resolved, 128 tests, 39 canonical unittest cases, Ruff/mypy and
  installed wheel plus five command checks on Windows/Linux (Linux Python 3.9 and 3.12).
- Core: `agent-workflow/reviews/68bd5d4e0d2089f8993b39036be4db8b5bd785a8e1eaa4585c4bf8f8fb875f24/work-order.md`.
- Personal: `agent-workflow/reviews/4364ba97b1029145f9fb7bab90f40de82b1b7acdd93876bfe762a788f5271090/work-order.md`.
  Security review also covers the current head.
- Infonetica: `agent-workflow/reviews/af02a5f4e278844e04a102b629dd81a0c71f89e5f2e19df821742114a29776e3/work-order.md`.
  Security review also covers the current head.

Fresh local checks: `pwsh -NoProfile -File .agents/sync-generated.ps1 -Check` passes
with 89 generated files current; the repository has one paired AGENTS.md/CLAUDE.md with
the exact pointer; `git diff --check` passes. Source is unchanged from the reviewed candidate.
Do not rerun broad unchanged suites merely to replace retained successful evidence.
Installed native-host/live cloud activation and coordinated consumer migration remain unverified.

### Genuine blockers and next action

1. **Personal publication dependency.** Run `39253470502` fails on both platforms for exactly
   `engineering:write-feature`, `engineering:write-task` and `engineering:write-issue` absent
   from published Core. Resolver: Tommy merges Core #298 under its existing manual hold,
   then Core publication supplies those contracts. Resume condition: published Core contains
   all three canonical skills. Next action: rerun Personal's failed CI jobs at its recorded
   head, observe both platforms, then mark ready only after all checks pass. Preserve PR #3/#4/#5
   stack order and reconcile the child after its parents land. Do not remove references or
   exempt checks to hide the missing dependency.
2. **Employer CI billing.** Run `39253473531`, job/check `118062775890`, has no step logs.
   The failure annotation says recent account payments failed or the spending limit must
   increase. Resolver: the GitHub billing/account owner (Tommy). Unblock action: restore
   Actions billing/spending capacity. Resume condition: a rerun starts actual verification
   steps. Next action: rerun the existing failed run and handle any observed source failures;
   observe its exact-head result before marking ready. Preserve PR #6/#12 stack order and
   Work/Core/shared publication dependencies. No billing settings were changed or blind
   reruns submitted.
3. **Merge boundary.** Work Items #20 and Core #298 are reviewed and green, awaiting Tommy's
   merges. No automatic merge or inferred merge authorization is permitted. After authorized
   parent merges/publication, reconcile descendant bases and validate the resulting heads.

Status: delivery-gated, not complete. The four-PR handoff has reached concrete publication and
billing boundaries; no source repair is supported by the observed failures. No CI run or
background monitor remains active. Keep the existing code heads and independent review evidence.
