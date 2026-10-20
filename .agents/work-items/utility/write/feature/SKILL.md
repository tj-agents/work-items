---
name: write-feature
description: Record new or changed product behavior with scope, requirements, dependencies and observable acceptance in the selected provider.
kind: utility
domain: work-items
profile: core
applicability: repositories recording work through an explicitly selected provider
requires: python>=3.9, git, work-items
provenance: house
---

# Record a feature

Read [the recording contract](../issue/references/recording.md). Reconcile an existing feature, goal,
session or PR before creation. Record intended outcome, current behavior, requirements, scope and
exclusions, acceptance criteria, owner, priority, dependencies and supporting links from actual facts.
Use the selected provider's feature schema and commands and verify persisted identity and content.
Append clarified requirements to the canonical feature. A substantial design plan stays in source
and links to that feature. Keep delivery links and evidence current; close only after acceptance.
