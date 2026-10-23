# Worker provenance and handoffs

[Start here](../README.md) · [Ledger rules](policy.md) · [Global instructions](global.md)

Worker provenance records who attempted work locally and who completed a
shift. Automatic policy hooks record nothing by themselves. A pre-tool event
proves an attempt, not a successful mutation or completed handoff.

## Start a tracked shift

Run this from the intended ledger and worktree, using your actual agent ID:

```sh
statutor worker begin --harness codex --json
```

Keep the returned session ID, machine ID, and baseline handoff ID. Recording
and completion must use that session in its originating ledger and worktree.
After upgrading an old registry, begin a fresh session if its existing entry
lacks recorded ledger scope. Version-1 registries remain readable.

Custom wiring can record an attempted operation. Replace `SESSION_ID` with
the ID returned by `begin`:

```sh
statutor worker record --harness codex --event attempt --session SESSION_ID
```

Use `statutor worker capabilities --json` to inspect declared evidence and
verification baselines for each agent. Automatic agent integrations
(`claude`, `codex`, `opencode`, `antigravity`, `gemini`, `grok`, `cursor`)
cannot record `--event mutation`; only a human or a custom integration with
actual post-success evidence may do so. An `unknown` agent proves activity only.
Roles and origin agents stay `unknown` unless explicitly proved.

## Complete the handoff

First rewrite `HANDOFF.md` with the required sections and a current verification
stamp. For portability across time zones, use the UTC verification date.
Set `last_worker` to the session's agent and `last_machine` to its machine ID.
Generate a fresh handoff ID:

```sh
statutor worker new-id
```

Set `handoff_id` to the new value and `supersedes` to the baseline ID returned
by `begin`. Then record completion:

```sh
statutor worker complete --session SESSION_ID
```

Completion validates the HANDOFF attribution and revision lineage. It refuses
a stale or foreign session and detects a competing local completion. An active
lease is a machine-local presence hint, not proof that useful work occurred.
The registry retains at most 50 sessions per project and 20 leases per
worktree. Durable completion history lives in HANDOFF revisions committed to Git.

## Inspect and reconcile

```sh
statutor machine show --json
statutor worker show --basis completed --json
statutor worker active --json
statutor worker compare other-branch --json
```

The machine ID is random and stored in mode-0600 state. It is not derived from
hardware, network addresses, hostnames, or accounts. Copied installations must
rotate identity explicitly with `statutor machine rotate --confirm`.

The local registry omits prompts, tool payloads, and conversation content.
It is a bounded record of local evidence, not a cross-machine activity service.
The optional [global instruction layer](global.md) does not synchronize it.

`worker compare` reads a caller-supplied local Git ref. It explains sibling
handoffs and lists the IDs a reconciliation must supersede. It does not fetch,
merge, rewrite HANDOFF, or choose a winner. Once both histories are available,
write one reconciled HANDOFF with a fresh ID and all relevant IDs in
`supersedes`, then complete the session. See
[D-0020 through D-0022 and D-0029](../DECISIONS.md).
