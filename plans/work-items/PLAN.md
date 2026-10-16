# GitHub work-items implementation

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
