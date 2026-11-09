# Work items

One work-item tracker interface, its adapters and the `tj item` CLI, published as the `tj_work_items` package
from `packages/tj-work-items`. The lifecycle commands in [`tj-agents/agent`](https://github.com/tj-agents/agent)
(`tj start`, `status`, `closeout`) and their skills move a card by calling `tj item` rather than talking to
GitHub or Azure DevOps directly; a project's profile (`personal`, or `work` resolving to the current employer
profile such as `infonetica`) selects which adapter and settings apply, so the same verb moves a GitHub
Projects card for a personal repository and an Azure DevOps work item for a work one.

```text
tj item resolve <ref> [--body]          tj item comment <ref> --body-file <file>
tj item mine                            tj item link <ref> <pull-request-url>
tj item progress <ref> --state "In Review"   tj item prs <ref>
tj item create --title TITLE [--body BODY] [--parent <ref>] [--field NAME=VALUE]
```

`tj` dispatches `tj item` to the `tj-item` console script. Install it with
`uv tool install --from "git+https://github.com/tj-agents/work-items#subdirectory=packages/tj-work-items" tj-work-items`,
adding `--with <profile package>` for each employer profile the machine uses.

## Interface

`Tracker`: `resolve(ref)`, `list_mine()`, `transition(ref, state)`, `comment(ref, text)`, `link_artifact(ref, url)`,
`linked_prs(ref)`. `tj item prs` prints `{"ref", "prs": [{"url", "state": open|merged|closed, "head", "title"}], "all_merged"}`;
`all_merged` is false when no PR is linked.
Canonical states: To Do, In Progress, Blocked, In Review, Done. Refs are `provider:scope:id`; a bare `461` or `#461`
takes the active profile's tracker and scope, and each adapter parses its own URLs.

| Adapter | Transport | State |
|---|---|---|
| `github` | `gh api` | Projects v2 Status on every project the issue is in, placing it on the repository's linked Projects when it is on none; Done closes the issue |
| `azure-devops` | REST 7.1, `az` token or `AZURE_DEVOPS_EXT_PAT` | profile map, else the ADO state category; walks intermediate states when a direct move is rejected |

Another tracker is one adapter class registered under the `tj_work_items.trackers` entry-point group.

## Profiles

A profile is configuration only: a package registering a mapping under the `tj_work_items.profiles` entry-point group.

```python
PROFILE = {
    "name": "employer",
    "tracker": "azure-devops",
    "match": {"remote_host": "github.com", "remote": "^employer/"},
    "settings": {"organization": "employer", "project": "Product", "states": {"In Review": "Resolved"}},
}
```

The repository origin selects the profile; a GitHub origin no profile matches uses the GitHub adapter with defaults.
`--profile <name>` overrides.

## Checks

```text
uv run ruff format --check && uv run ruff check && uv run mypy && uv run pytest
pwsh .agents/sync-generated.ps1 -Check
```
