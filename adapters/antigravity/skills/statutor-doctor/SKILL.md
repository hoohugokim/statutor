---
name: statutor-doctor
description: Lint the ledger for drift — stale handoff stamps, oversized constitution, unarchived consumed plans, missing status fields. Use when checking ledger health or diagnosing drift.
---

# statutor-doctor

Lint the Statutor ledger for drift.

## Procedure

1. Run `statutor-doctor .` from the repository root.
2. Review findings:
   - `WARN`: soft-limit violations (e.g. constitution > 120 lines, HANDOFF stamp > 3 days old, consumed plans not archived, missing status fields).
   - `ERROR`: policy violations (e.g. missing required sections in HANDOFF, constitution > 200 lines, duplicate or disappearing task IDs).
3. For each finding, fix it directly (respecting mutation policies) or explain in one line why it stands.
4. Re-run `statutor-doctor .` until clean or every finding is accounted for.
