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

## Source and checks

Author the utility once under `.agents/work-items/utility/manage`; Template generates both host
adapters and payloads. Implementation progress and remaining acceptance belong to
[the source plan](plans/work-items/PLAN.md).

```text
python -B .agents/sync_generated.py --root .
python -B .agents/sync_generated.py --root . --check
python -B -m unittest discover -s .agents/tests
```
