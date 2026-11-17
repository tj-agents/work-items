# Work items

One work-item tracker interface, its adapters and the `tj item` CLI, published as the `tj_work_items` package
from `packages/tj-work-items`. The lifecycle commands in [`tj-agents/agent`](https://github.com/tj-agents/agent)
(`tj start`, `status`, `closeout`) and their skills move a card by calling `tj item` rather than talking to
GitHub or Azure DevOps directly; a project's profile (`personal`, or `work` resolving to the selected
specific profile, such as an employer's) selects which adapter and settings apply, so the same verb
moves a GitHub Projects card for a personal repository and an Azure DevOps work item for a work one.

```text
tj item reference <ref>                tj item resolve <ref> [--body]
tj item comment <ref> --body-file <file>
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
Canonical states: To Do, In Progress, Blocked, In Review, Done. Refs are `provider:scope:id`; a bare `461`, `#461`
or `AB#461` takes the project's selected tracker and scope. GitHub issue and Azure Boards URLs retain their
provider-specific canonical refs. Other absolute URLs remain addressable as `url:<normalized URL>`.

`tj item reference` prints only `ref`, `provider`, `scope` and `native_id`. Fully qualified refs and URLs
need no project, installed profile, adapter or network request. Explicit triples preserve their provider,
scope and native ID; the first colon separates provider and the last separates native ID. A URL-shaped
scope is still a scope. A valid `url:<scheme>://...` wrapper preserves its scheme and complete remainder.
For a raw opaque URL, `scope` is its scheme
and `native_id` is everything after the scheme's colon; ports, queries and fragments are retained.
Bare references need a project profile and its adapter's default scope. Tracker operations still require
a registered adapter for the reference's provider; they never switch providers to satisfy a request.

```json
{"ref":"url:https://tracker.example:8443/items/42?q=x#c","provider":"url","scope":"https","native_id":"//tracker.example:8443/items/42?q=x#c"}
```

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
    "creation": "deny",
    "match": {"remote_host": "github.com", "remote": "^employer/"},
    "settings": {"organization": "employer", "project": "Product", "states": {"In Review": "Resolved"}},
}
```

The repository can select an installed profile in `.agents/settings.json`:

```json
{"configuration":{"work-items":{"profile":"employer"}}}
```

Only `profile` is accepted in this namespace. Configuration is read from the current Git checkout root,
including when invoked in a subdirectory or linked worktree. It never inherits declarations from an enclosing
repository or the worktree's main checkout. Unknown profile names, malformed declarations and ambiguous
matches fail with a usage error.

Without explicit configuration, an installed profile matching the origin or adopted as
`<profile-name>@tj-agents` in `.agents/plugins.json` selects the tracker. Explicit adoption of
`personal@tj-agents` can select the built-in `personal` GitHub profile. An installed employer match takes
precedence over personal adoption; adoption of `work@tj-agents` requires a configured or matching installed
profile. The origin host alone never selects a tracker. A missing work profile never selects GitHub.

Profiles default to `creation: "deny"`; `"allow"` opts a profile into creation. The built-in personal profile
allows creation only in projects adopting personal scope. `tj item create` checks both the project's policy
and the requested profile before loading adapters or making API calls. `--profile` alone cannot authorize
creation when the project has no selected profile, and cannot bypass a configured,
matched or adopted project's denial. A denial directs the caller to an existing reference or the selected
profile's `create-work-item` approval workflow. `tj item profile` includes the effective `creation` policy.

For existing explicit refs, a profile matching the reference's provider and scope takes precedence over an
unrelated checkout's profile. Otherwise the project's profile for that provider, or its unique installed
profile, applies. With no matching provider profile, the explicit reference selects its registered adapter
with empty settings and no creation authority. Adapters needing additional settings still require a profile.
Ambiguous matches require `--profile <name>` before the action. Unknown URLs remain usable
with `reference` even when no adapter exists for tracker operations.

## Checks

```text
uv run ruff format --check && uv run ruff check && uv run mypy && uv run pytest
pwsh .agents/sync-generated.ps1 -Check
```
