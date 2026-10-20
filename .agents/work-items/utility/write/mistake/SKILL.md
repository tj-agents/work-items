---
name: write-mistake
description: Record an observed agent or process error with its cause, governing rule, correction and an observable prevention condition.
kind: utility
domain: work-items
profile: core
applicability: repositories recording work through an explicitly selected provider
requires: python>=3.9, git, work-items
provenance: house
---

# Record a mistake

Read [the recording contract](../issue/references/recording.md). Reconcile an existing incident and
repair owner, then record concrete evidence, impact, causal decision/failure and whether the governing
standard was missing, ambiguous or violated. Unknown causes stay unknown. State the correction as a
declarative prevention rule and give an observable condition proving it works; an apology or promise
is insufficient. Use the selected provider's mistake schema and commands and verify the persisted
record. Repeated evidence updates that incident. Link an existing causal repair and retain the
mistake as learning history. Resolve only after its own prevention condition passes.

```text
Observation: an agent retained Core writer aliases despite the loaded current-solution policy.
Cause: the agent accepted an inherited compatibility design without applying that policy.
Impact: consumers could keep using the superseded owner; repair owner: Core and Work Items.
Prevention: remove Core entries, migrate callers and verify actual Work Items resolution.
Recording: update the same incident with verification; close only after prevention passes.
```
