# Mistakes

## M001 - Dependent merge ran after delivery-binding validation failed

- Kind: mistake.
- Observed: 16 October 2026. The PR #7 delivery-binding command rejected missing What/Why sections, then the same PowerShell command continued into the normal merge. PR #7 was independently reviewed, green and within Tommy's existing delivery approval; its delivery binding was not established before landing.
- Cause: confirmed. The command sequence did not check the native process exit status between dependent operations. The governing sequential-execution requirement was clear and violated.
- Impact and priority: P2. The authorized merge landed with a missing workflow delivery record; the observed review and CI evidence remain valid.
- Source owner: this work-items delivery session, codex:01a1415f-6448-7123-8b17-c7fb67aee637; command orchestration.
- State: resolved.
- Repair: PR #7 description was corrected; its binding then correctly reported that an already merged PR owns no delivery. This incident retains the missing pre-merge record rather than claiming a retroactive binding. Landing commit 7c4dcd2147a46005020ee4f2b68db563d71a52a5; causal main CI 38836538305 passed.
- Prevention: every dependent native command must stop on a nonzero exit before the following mutation. Use checked subprocess calls or an explicit LASTEXITCODE guard.
- Resolution condition: a rejected prerequisite exits the command sequence before its following dependent action, and subsequent publication commands guard every prerequisite.
- Verification: the attempted binding reconciliation exited 2 and prevented the following run-list command from executing. The v0.1.0 publication sequence checked each preceding exit before tagging, pushing or publishing, and completed successfully.
- Next action: none; retain the incident and prevention evidence as learning history.
