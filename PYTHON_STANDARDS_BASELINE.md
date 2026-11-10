# Python standards baseline

Existing violations at `d01958325388b6198d2eacb4b49e763ad39664f3` are baselined by exact authored file and rule. New files receive all enabled checks. Remove an exception when repairing its source. The tool configuration owns enforcement; this document records the rollout evidence and rationale.

## Ruff

Reason: preserve existing implementations during the standards rollout. Each row records the existing count and a representative required repair. No wildcard path or whole-rule ignores were added.

| File | Rule | Existing count | Required repair |
| --- | --- | ---: | --- |
| `.agents/tests/test_azure_devops.py` | `ANN401` | 5 | Dynamically typed expressions (typing.Any) are disallowed in `body` |
| `.agents/tests/test_cli.py` | `PT011` | 1 | `pytest.raises(SystemExit)` is too broad, set the `match` parameter or use a more specific exception |
| `.agents/tests/test_github.py` | `ANN401` | 1 | Dynamically typed expressions (typing.Any) are disallowed in `**settings` |
| `packages/tj-work-items/src/tj_work_items/adapters/azure_devops.py` | `ANN401` | 3 | Dynamically typed expressions (typing.Any) are disallowed in `body` |
| `packages/tj-work-items/src/tj_work_items/adapters/azure_devops.py` | `PLR6301` | 1 | Method `_authorization` could be a function, class method, or static method |
| `packages/tj-work-items/src/tj_work_items/adapters/github.py` | `ANN401` | 2 | Dynamically typed expressions (typing.Any) are disallowed in `**variables` |
| `packages/tj-work-items/src/tj_work_items/cli.py` | `ANN401` | 1 | Dynamically typed expressions (typing.Any) are disallowed in `run` |

## Custom checker

Reason: preserve exact pre-existing custom-checker findings during the standards rollout. Each entry maps to one authored path and rule; repair the stated design issue and remove its exception. No generated or vendored path is included.

| File | Rule | Existing count | Required repair |
| --- | --- | ---: | --- |
| packages/tj-work-items/src/tj_work_items/adapters/__init__.py | PY008 | 3 | Move private initialization behind a public module boundary. |
| packages/tj-work-items/src/tj_work_items/adapters/azure_devops.py | PY016 | 1 | Inject process state or confine the read to an entry-point main. |
| packages/tj-work-items/src/tj_work_items/adapters/github.py | PY013 | 1 | Place enum-associated data on the enum member. |
| packages/tj-work-items/src/tj_work_items/tracker.py | PY011 | 2 | Introduce and use the package's shared exception root. |
