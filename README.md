# Work items

Optional deterministic work-item tooling for personal GitHub repositories. Each project keeps its
own feature, task, bug, mistake and technical-debt issues. Core remains shared engineering helpers;
Infonetica retains its Azure DevOps workflow.

The initial slice supplies five JSON schemas, input skeletons, local validation and Markdown previews:

```text
python -B .agents/work-items/utility/manage/scripts/work_item.py template --kind feature
python -B .agents/work-items/utility/manage/scripts/work_item.py preview --input facts.json
```

Fill the skeleton with actual facts. Scripts format the template; agents supply the substance.
No GitHub writes occur in this initial slice. GitHub transport and explicit per-repository adoption
follow under plans/work-items/PLAN.md.

Author the utility once under `.agents/work-items/utility/manage`; the Template generator publishes
both host adapters and payloads. Run `python -B .agents/sync_generated.py --root .`, then the same
command with `--check`, and `python -B -m unittest discover -s .agents/tests -p "test_*.py"`.
