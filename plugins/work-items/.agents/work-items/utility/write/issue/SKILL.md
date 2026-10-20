---
name: write-issue
description: Classify an untyped recording request and delegate once to its bug, mistake, debt, feature or task writer. Recording does not authorize implementation.
kind: utility
domain: work-items
profile: core
applicability: repositories recording work through an explicitly selected provider
requires: python>=3.9, git, work-items
provenance: house
---

# Record an issue

Read [the recording contract](references/recording.md), then choose one writer from the actual facts:

| Request | Writer |
| --- | --- |
| Faulty software behavior | `work-items:write-bug` |
| Observed agent or process error | `work-items:write-mistake` |
| Deliberate shortcut or deferred compromise | `work-items:write-debt` |
| New or changed product behavior | `work-items:write-feature` |
| Concrete work with a completion condition | `work-items:write-task` |

Read a supplied item before classifying it; its persisted kind may already resolve the question.
Delegate once. Ask only when missing facts leave materially different outcomes. A bug's deferral
creates a separate debt item only for a distinct compromise with its own exit condition. Preserve
identity, evidence and repair ownership. Use the specific writer for persistence; do not submit a
second record or start implementation from this classification step.

```text
Input: "The invoice export crashes when the amount is zero."
Classification: faulty software behavior.
Next owner: work-items:write-bug; reconcile existing export defects before persistence.
Result: one verified bug identity; implementation remains a separate authorized action.
```
