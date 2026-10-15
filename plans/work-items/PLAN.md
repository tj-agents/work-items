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
