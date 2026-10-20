---
name: write-bug
description: Record a software defect once through the selected provider, with observed evidence, impact, repair ownership and verifiable resolution.
kind: utility
domain: work-items
profile: core
applicability: repositories recording work through an explicitly selected provider
requires: python>=3.9, git, work-items
provenance: house
---

# Record a bug

Read [the recording contract](../issue/references/recording.md). Reconcile the existing cause and
repair owner before creating a bug. Record observed faulty behavior, reproduction/evidence, impact,
confirmed cause or explicit unknown, source owner, justified priority and resolution condition.
Use the selected provider's bug schema and commands, then verify the persisted identity and facts.
Repeated reports add dated evidence to the same bug. Link a distinct intentional compromise through
`work-items:write-debt` without duplicating the bug's repair. Retain final verification and history.

```text
Observation: invoice export raises ZeroDivisionError for an invoice with amount 0.
Evidence: export invoice 318 with amount 0; request returns HTTP 500.
Cause: unknown; owner: billing export; priority: high because monthly exports stop.
Resolution: invoice 318 exports successfully and the zero-amount regression passes.
Recording: reconcile the existing cause, persist once, then read back the bug and evidence.
```
