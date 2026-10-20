---
name: write-task
description: Record concrete work with scope, dependencies and a verifiable completion condition in the selected provider without starting implementation.
kind: utility
domain: work-items
profile: core
applicability: repositories recording work through an explicitly selected provider
requires: python>=3.9, git, work-items
provenance: house
---

# Record a task

Read [the recording contract](../issue/references/recording.md). Read an existing task, parent feature,
goal, session or PR before creation. Record requested work, purpose, scope, owner, priority,
dependencies, source links and an observable completion condition using known facts.
Use the selected provider's task schema and commands and verify persisted identity and facts.
Repeated requests update that task. Link any substantial implementation plan from the item and keep
delivery/verification evidence current. Recording grants no authority to start execution.
