---
name: item
description: Use when reading, creating, listing, moving, commenting on or linking tracker items and PRs through the repository's tj item profile.
kind: utility
domain: work-items
profile: core
applicability: any repository whose origin matches an installed work-item profile, or any GitHub repository
requires: tj-item on PATH
provenance: house
---

# Work items

The repository's origin selects the profile and tracker. Refs: `461`, `#461`, an issue or work-item URL, or `provider:scope:id`.

```text
tj item resolve <ref> [--body]
tj item create --title <title> [--body <text>] [--parent <ref>] [--field <name>=<value>]
tj item mine
tj item progress <ref> --state "In Review"
tj item comment <ref> --body-file <file>
tj item link <ref> <pull-request-url>
tj item prs <ref>
tj item profile
```

States: To Do, In Progress, Blocked, In Review, Done. Output is JSON; exit 2 is a usage or profile error, 3 a tracker error.
Pass `--profile <name>` before the action when the ref belongs to another profile's tracker.
A profile can require `--field` values on `create`; without them it fails naming each field's allowed values.

If `tj item` is missing, install it:

```text
uv tool install --from "git+https://github.com/tj-agents/work-items#subdirectory=packages/tj-work-items" tj-work-items
```

Add `--with <profile package>` for each employer profile this machine uses.
