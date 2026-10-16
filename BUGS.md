# Bugs

## B001 — sequential create retry duplicated the live pilot

Kind: bug. Observed: 2026-10-16. Source owner: work-items/manage GitHub transport.
Impact: a retry can duplicate remote work; P1 because retry safety is a promised acceptance condition.
State: resolved. Cause: unknown. An immediate second invocation created another issue for the same
persisted request. Current issue bodies and markers parse correctly and later lists contain both records;
the immediate response was not captured, so it cannot establish an upstream or reconciliation mechanism.
Evidence: original pilot issues #1 and #2 share request work-items-pilot-feature-20261016 and body
hash 0219a250ba4677c40f79e72244b6c02d27438e927a162ada5adcac6cd44036a1.
Repair: Feature/GitHubTransport, plans/work-items/PLAN.md. Owner: codex:01a1415f-6448-7123-8b17-c7fb67aee637.
Next action: none for this resolved defect; retain this record and the original pilot history.
Resolution condition: immediate repeat returns the same issue with one POST even when a list omits it;
uncertain submissions stay reconciliation-only and both failed pilot issues close with truthful evidence.
Verification: twenty-three tests pass, including stale-list, pending-intent and reconciliation-only cases.
Native repair review is complete at d7fe04f. Fresh pilot issue #4 reused the same issue on immediate create
retry, passed a hash-checked update, reused the same note, linked foundation PR #3 and closed with evidence.
Original failed pilot issues #1 and #2 closed with that truthful close-out, preserving original failure history.
Foundation PR #3 merged at 66aadc23819835469e72d8604d5a788da7b74211; causal main CI 38831521132 passed.
Transport PR #5 merged at 76c2640018326aa3f1ddd4c011c929c488f7d95a; causal main CI 38832601555
passed. The objective repair and live retry conditions are verified and delivered.
