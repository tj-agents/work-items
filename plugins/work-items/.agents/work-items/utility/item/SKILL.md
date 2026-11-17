---
name: item
description: Use when normalizing work-item references, reading, creating, listing, moving or commenting on tracker items, or linking a PR through the project's tj item profile.
kind: utility
domain: work-items
profile: core
applicability: addressable work-item references and repositories selecting a work-item profile
requires: tj-item on PATH
provenance: house
---

# Work items

Use the project's configured or adopted profile. The
[profile and reference contract](https://github.com/tj-agents/work-items#profiles) owns selection and creation
policy. Prefer an existing reference when linking work; creation follows that policy.

```text
tj item --cwd <checkout> reference <ref>
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
`reference` normalizes a URL or qualified ref without contacting its tracker. Bare `461`, `#461` or `AB#461`
uses the project's tracker scope. Its JSON contains `ref`, `provider`, `scope` and `native_id`; retain the
returned ref when linking work through another tool. Opaque URLs remain addressable without an adapter.
Read `profile` for the effective creation policy. A denial names the profile's approval workflow and asks
for an existing reference; changing `--profile` does not remove the project's policy.
A profile can require `--field` values on `create`; without them it fails naming each field's allowed values.

If `tj item` is missing, install it:

```text
uv tool install --from "git+https://github.com/tj-agents/work-items#subdirectory=packages/tj-work-items" tj-work-items
```

Add `--with <profile package>` for each employer profile this machine uses.
