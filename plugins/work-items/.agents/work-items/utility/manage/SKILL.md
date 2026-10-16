---
name: manage
description: Generate, validate and preview deterministic feature, task, bug, mistake and technical-debt records for an explicitly selected GitHub tracker.
kind: utility
domain: work-items
profile: core
applicability: repositories explicitly adopting GitHub work items
requires: python
provenance: house
---

# Manage work items

Use the script beside this skill. Substitute its actual installed directory for `<skill-directory>`;
use `python3` on Linux/macOS and `python` on Windows. Do not guess another skill's location.

```text
python -B <skill-directory>/scripts/work_item.py template --kind bug
python -B <skill-directory>/scripts/work_item.py schema --kind feature
python -B <skill-directory>/scripts/work_item.py validate --input facts.json
python -B <skill-directory>/scripts/work_item.py preview --input facts.json
```

`--input -` reads stdin. Output is compact JSON; preview returns `title` and `body`.
The five schemas under `templates/` generate both the input skeleton and Markdown sections.
Supply substantive facts and acceptance/verification conditions; scripts own boilerplate.
An empty skeleton deliberately fails validation. Unknown causes must be stated as unknown.
Do not invent priorities, causes, repro steps or passed verification. Keep source links and
legacy identities when migrating an existing record. A repeated observation belongs to its
existing canonical item, selected by cause and repair owner.

This slice performs local validation and preview only. GitHub submission is not yet available.
Installing the package alone does not select a tracker or change employer policy. Existing
Core repair workflows retain ownership of diagnosis and delivery. Keep work repository evidence
in its authorized repository. Plans and curated knowledge stay with source; live backlog storage
will use issues in that same repository after explicit adoption.
