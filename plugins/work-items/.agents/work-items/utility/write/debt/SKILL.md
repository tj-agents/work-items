---
name: write-debt
description: Record an intentional shortcut, deferral or known unfixed risk with its owning area, rationale and objective exit condition in the selected provider.
kind: utility
domain: work-items
profile: core
applicability: repositories recording work through an explicitly selected provider
requires: python>=3.9, git, work-items
provenance: house
---

# Record debt

Read [the recording contract](../issue/references/recording.md). Record a deliberate shortcut or
known defect/risk intentionally left unfixed while the observation is available. Name the owning
area, actual compromise, rationale, impact, dependencies and objective exit condition. A shortcut
requires evidence that it is suitable; unrelated scope explains deferral but does not erase it.
Use the selected provider's debt schema and persistence/verified-closure commands. Faulty behavior
belongs in `work-items:write-bug`; link its repair when the debt describes a distinct deferral.
Separate independently repaired owning areas retain linked items. Preserve canonical history.

```text
Decision: defer paging beyond 1,000 backlog records for the current release.
Reason: the current provider endpoint has no implemented continuation path.
Impact: large queues are visibly refused; owner: tracker transport; state: deferred.
Exit condition: fetch every page and verify no record is omitted in a queue above 1,000.
Recording: link the release decision and keep this compromise distinct from an observed bug.
```
