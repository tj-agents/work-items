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
