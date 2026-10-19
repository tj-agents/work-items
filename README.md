# Work items

Deterministic work-item tooling with a neutral runtime for explicitly selected tracker providers.
The included GitHub lifecycle remains opt-in per source repository. Personal and employer providers
reuse the runtime with their own credentials, field mappings and tracker policy.

## Use

The `work-items:manage` utility ships five JSON schemas, validation, Markdown rendering, the GitHub
lifecycle, and the installable `tj_work_items` runtime. Start with actual facts; an empty skeleton fails validation.

```text
python -B .agents/work-items/utility/manage/scripts/work_item.py template --kind feature
python -B .agents/work-items/utility/manage/scripts/work_item.py preview --input facts.json
python -B .agents/work-items/utility/manage/scripts/work_item.py adopt --root <source-repository> --repository owner/project
python -B .agents/work-items/utility/manage/scripts/work_item.py create --root <source-repository> --input facts.json --request-id UNIQUE-STABLE-ID
```

Use the installed skill directory when running outside this source checkout. Python 3.9+, Git,
the authenticated GitHub CLI and repository access are required. Adoption verifies origin and
coordinates `.work-items.json` with Core's `.problem-records.json`. Commit those declarations to
sync selection across computers. Installing the package alone does not adopt a tracker.

[The canonical utility](.agents/work-items/utility/manage/SKILL.md) documents current reads,
hash-checked updates, notes, links, verified close, explicit retry reconciliation and Core transport.
Persist request IDs before writes. Keep local submission receipts after uncertain outcomes; on another
computer or after receipt loss use `--reconcile-only`. Concurrent writers still require coordination.
GitHub holds canonical issue data for its lifecycle; local receipts protect retries and are not another backlog.
The shared runtime supports provider-owned Azure operations without selecting or adopting GitHub.
`azure_tracker.Tracker(root, context_config, client, journal, *, fields, lifecycle)` requires
provider-owned managed-field and lifecycle mappings. `fields` contains exactly `repository`, `request`
and `record`, mapped to distinct Azure reference names without collisions with the native fields the
tracker uses. `lifecycle` contains exactly the supported `context_config["kinds"]` keys; each entry
contains exactly `open` and `closed` nonempty native state names plus `inactive`, a sequence of nonempty
state names. `closed` must belong to `inactive`, and `open` must not. The tracker copies the validated
policy. For example, a provider may supply `{"task": {"open": "ToDo", "closed": "Done",
"inactive": ("Done", "Canceled")}}` when task is its only supported kind. State actions and list
filters use each kind's policy. Lists over 1,000 items fail explicitly so a partial queue cannot appear
complete. Azure updates test the revision read immediately before the write; callers must coordinate an
exclusive item owner across their own read, decision and write window.

## Source and checks

Author the utility once under `.agents/work-items/utility/manage`; Template generates both host
adapters and payloads. Implementation progress and remaining acceptance belong to
[the source plan](plans/work-items/PLAN.md).

```text
python -B .agents/sync_generated.py --root .
python -B .agents/sync_generated.py --root . --check
uv run pytest
```
