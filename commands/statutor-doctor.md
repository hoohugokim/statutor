---
description: Lint the ledger for drift — stale handoff stamps, oversized constitution, unarchived consumed plans
---
Run `python3 ${CLAUDE_PLUGIN_ROOT}/core/statutor_doctor.py` from the repo root.

For each WARN/ERROR, fix it directly (respecting mutation policies) or explain in one line why it stands. Re-run until clean or every finding is accounted for.
