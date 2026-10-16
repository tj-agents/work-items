# Work items

Optional deterministic work-item tooling for personal GitHub repositories. Each project keeps its
own feature, task, bug, mistake and technical-debt issues. Core remains shared engineering helpers;
Infonetica retains its Azure DevOps workflow.

The package supplies five JSON schemas, input skeletons, local validation and Markdown previews:

```text
python -B .agents/work-items/utility/manage/scripts/work_item.py template --kind feature
python -B .agents/work-items/utility/manage/scripts/work_item.py preview --input facts.json
```

Fill the skeleton with actual facts. Scripts format the template; agents supply the substance.
Use the same script's `adopt --root . --repository owner/project` command to select the source
GitHub tracker explicitly, then `create`, `read`, `list`, `update`, `note`, `link` and `close`.
The shared utility documents full command inputs and retry/ownership limits. Only `.work-items.json`
configuration is committed; issue contents live remotely. No Firebase or separate service is needed.
Implementation and pilot progress are in plans/work-items/PLAN.md.

Author the utility once under `.agents/work-items/utility/manage`; the Template generator publishes
both host adapters and payloads. Run `python -B .agents/sync_generated.py --root .`, then the same
command with `--check`, and `python -B -m unittest discover -s .agents/tests -p "test_*.py"`.
