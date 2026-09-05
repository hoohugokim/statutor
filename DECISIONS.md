<!-- writ: plane=log | policy=append_only (insertions only; supersede, never edit) | writer=orchestrator/human -->
# DECISIONS

## D-0001 — Four-plane typed ledger as the framework doctrine
**Status:** accepted
**Context:** Agent-facing repo docs rot when treated as prose; multi-agent sessions re-litigate settled questions and lose state across context windows.
**Decision:** Constitution/state/log/plan planes; one writer per file; mutation policy declared in each file header and machine-enforced.
**Consequences:** CHANGELOG.md and free-form ROADMAP demoted; DECISIONS.md and bounded HANDOFF.md become the load-bearing files.

## D-0002 — Name: "writ" (package `writ-ledger`, CLI `writ`)
**Status:** accepted
**Context:** Working name "Chunchugwan" was culturally specific; user wants culture-agnostic and lean. A writ is a written order whose authority comes from enforcement.
**Decision:** Rename framework to writ; keep governed filenames boring/standard (AGENTS.md et al.) for ecosystem interop.
**Consequences:** `.writ.yaml` policy file; PyPI-collision hedge via `writ-ledger`; T-0002 sweeps remaining collisions before publishing.

## D-0003 — Kernel/adapter split with a single-file, zero-dependency kernel
**Status:** accepted
**Context:** Multiple harnesses (Claude Code, OpenCode, Codex, custom) must share one policy implementation; per-harness reimplementation is drift-by-design.
**Decision:** One `validate()` in `core/writ_core.py` with four entry modes (hook/check/staged/init); templates embedded in the kernel as the single source of truth; adapters are thin shims.
**Consequences:** `writ init` works identically everywhere; no templates/ directory may ever exist; PyYAML optional-only.

## D-0004 — Enforcement pyramid: prose < in-loop hooks < git floor
**Status:** accepted
**Context:** Instructions decay; hook coverage varies by harness (Codex PreToolUse is Bash-only and opt-in; OpenCode has had subagent-bypass gaps).
**Decision:** In-loop hooks wherever the harness allows, plus a universal `writ staged` pre-commit/pre-receive floor that no harness can route around.
**Consequences:** Git floor is mandatory on Codex; archive semantics defined at the diff layer (arrival allowed, tamper/departure denied).

## D-0005 — Bash guard, strict by default
**Status:** accepted
**Context:** Agents can bypass Write/Edit hooks with `>> FILE`, `sed -i`, `tee` on any harness; on Codex, Bash is the only interceptable tool.
**Decision:** Deny write-ish shell commands touching governed basenames; accept false positives; per-repo opt-out via `bash_guard: false`.
**Consequences:** A false positive costs one rephrase; a false negative costs a corrupted ledger — asymmetry justifies strictness.

## D-0006 — No hand-maintained CHANGELOG.md
**Status:** accepted
**Context:** git log with conventional commits is a queryable superset that cannot drift from reality.
**Decision:** Generate any human-facing changelog from commits; agents read git log.
**Consequences:** Release tooling reads commits; a hand-edited CHANGELOG in a governed repo is a smell.

## D-0007 — Repo root doubles as the Claude Code plugin
**Status:** accepted
**Context:** Installing a plugin from a subdirectory would strand `core/` outside the installed payload.
**Decision:** `.claude-plugin/`, hooks/, commands/, skills/ live at root; core/ and adapters/ ride along inside the plugin harmlessly.
**Consequences:** Layout is asymmetric by design; other adapters are copied OUT from adapters/.

## D-0008 — Kernel language: Python; fish only for interactive wrappers
**Status:** accepted
**Context:** User's shell preference is fish, but hooks are JSON-on-stdin programs.
**Decision:** Deviate deliberately: Python for anything parsing hook JSON; fish for human-facing wrappers.
**Consequences:** Zero-dep stdlib-only kernel; fish snippets stay in docs/install paths.

## D-0009 — Rename the framework away from "writ" (supersedes D-0002's name choice)
**Status:** accepted
**Context:** T-0002 sweep (2026-08-23): github.com/infinri/Writ — an active, 187-star Claude Code governance framework — ships PyPI `claude-writ` whose install puts a `writ` console script on PATH; npm `writ` and crates.io `writ` also install `writ` binaries. Same word, same niche, same host tool; this project would be the third arrival, and pip silently clobbers competing console scripts.
**Decision:** Do not ship a CLI named `writ` and do not publish under the writ identity. Rename the framework (human decision, 2026-08-23); the replacement name is chosen from a fully-swept shortlist and recorded as D-0010.
**Consequences:** D-0002's name is superseded; its doctrine (culture-agnostic, lean, boring governed filenames for interop) stands and constrains the new name. T-0007 publishing rehearsal and any registry claims wait for D-0010; T-0014 executes the rename across pyproject, plugin.json, `.writ.yaml`, docs, and repo layout.

## D-0010 — New name: "statutor" (package `statutor`, CLI `statutor`)
**Status:** accepted
**Context:** Second sweep (2026-08-23) of the statute family: `statutor` — Latin agent noun of *statuere*, "the one who enacts" — is fully clear on every registry, OS channel, GitHub user/org, and domain (none even registered); `statuta` is blocked (statuta.com is a live MCP prompt-management SaaS; an active agentic compliance copilot holds the exact GitHub name); `statute`/`statutum` were clear but generic / less agentic. Human chose `statutor` 2026-08-23: an agent noun for an agent-governance framework.
**Decision:** Framework, PyPI distribution, and CLI are all `statutor`; doctor CLI `statutor-doctor`; policy file `.statutor.yaml`; plugin `statutor@hoo-plugins`; repo lives at ~/workbench/statutor (the old writ tree is retired unmodified as a pre-rename snapshot).
**Consequences:** The `writ-ledger` hedge is dropped — the short name is claimable. PyPI/npm/crates placeholders must be claimed the SAME DAY before any public announcement; the GitHub repo stays private until the PyPI claim lands. DECISIONS.md retains its original writ header marker (append-only forbids editing history). T-0014 executed 2026-08-23.

## D-0011 — Kernel parses apply_patch envelopes; unknown shapes fall through
**Status:** accepted
**Context:** T-0011: Codex PreToolUse delivers edits as tool_name `apply_patch` with `tool_input {"command": "<envelope>"}`, and opencode substitutes `apply_patch` for write/edit on GPT-5-class models — so name-based allowlists missed ledger mutations on both harnesses, leaving only the git floor.
**Decision:** `validate()` routes apply_patch to `guard_apply_patch()`, splitting the `*** Begin Patch` envelope into per-file ops with layer-consistent semantics: frozen paths untouchable except arrival INTO `plans/archive/` (matches the staged rename rule); Delete File denied wholesale for constitution/overwrite_bounded/append_only (records are superseded, never removed) while state files stay deletable (bash-guard parity); Add File gets the full cap + required-sections check; Update File denies append-only deleting/modifying hunks, estimates sized-policy line counts from disk plus adds-minus-dels, and skips section checks impossible on a partial diff.
**Consequences:** In-loop coverage closes on Codex (matcher widens to `^(Bash|apply_patch)$`) and opencode GPT-5-class sessions; residual blind spots (MCP tool ids, Update-File sections) stay with the mandatory git floor. Unknown payload shapes fall through silently — parsing must never be load-bearing where the floor also watches.

## D-0012 — Drop the Hermes adapter; four supported surfaces
**Status:** accepted
**Context:** T-0010 shipped a Hermes plugin adapter (`pre_tool_call` block directive) verified by source-reading only. The maintainer runs repo-coding work on Claude Code / OpenCode / Codex plus the git floor, not Hermes — so the adapter could never meet this project's verification bar (real-release verification, per T-0003/T-0004 practice) and would stay permanently un-exercised code posing as coverage.
**Decision:** Drop `adapters/hermes/` (plugin, middleware, README) and its tests. Supported surfaces are four: Claude Code, OpenCode, Codex, git. Custom harnesses remain first-class via kernel embedding (`import validate` / `statutor check TOOL JSON CWD`) without claiming an adapter.
**Consequences:** T-0010 stays closed as history — the hook-surface investigation stands and is documented in its README's git past. pytest baseline shrinks accordingly. Any future Hermes revival restarts from the D-0011-era kernel semantics plus a fresh real-release verification pass. ROADMAP's Hermes bullet trimmed by the human.

## D-0013 — No periodic checkpoint mechanism; staleness is the doctor's job
**Status:** accepted
**Context:** T-0006 asked for a "Clawd 5-hour HANDOFF checkpoint hook" that, on investigation (2026-08-24 sweep of settings.json, clawd-cleanup backups, app hooks, shell history), never existed on disk. Building a fresh time-based nudge was considered.
**Decision:** Close as obsolete without building. Checkpoints are event-driven (task closed, session ending) and the existing machinery already enforces them: stop_doctor warns on stale `last_verified` stamps (`stale_after_days`, policy-tunable per repo), and every HANDOFF write passes section/budget validation at the hook and floor. A 5-hour timer measures the usage window, not state change; doctrine builds enforcement only after a real failure — none occurred.
**Consequences:** T-0006 closed wontfix; the agent queue is empty. If staleness ever bites in practice, tune `stale_after_days` in `.statutor.yaml` before reconsidering any hook.

## D-0014 — Real registry artifacts: npm channel and conformance-gated Rust floor
**Status:** accepted
**Context:** The npm/crates placeholders (plans/registry-claims.md §T-0016/T-0017) were pure namespace defense; the human wants both registries to carry real code without forking the kernel. Drivers: OpenCode users want one-command plugin install, and a static server-side floor is the one genuine no-Python-runtime scenario.
**Decision:** Two bounded promotions. (1) npm `statutor` publishes the actual OpenCode adapter (`adapters/opencode/statutor.ts` + docs) — opencode.json's `plugin:` array consumes npm specs natively; every policy decision stays in the Python CLI via `statutor check`, making this a distribution channel with zero doctrine impact. (2) crates.io `statutor` ships a narrow staged-mode floor binary named **`statutor-staged`** — never plain `statutor`: the pipx CLI and the cargo binary must not collide on PATH (the D-0009 clobber lesson). Scope: frozen rename semantics, append-only `-U0` deletion scan, caps + required_sections on staged blobs, embedded-defaults policy fallback plus `.statutor.yaml` subset via yaml-rust2.
**Consequences:** Bounded exception to D-0003: the Rust duplicate exists only while CI conformance holds — `scripts/gen_staged_fixtures.py` materializes ~30 scenarios from the pytest battery and `tests/test_conformance_rust.py` asserts Python≡Rust verdicts per fixture (skips sans cargo); divergence fails the build. Kernel `_git()` first gains `-c color.ui=false` so the port inherits corrected behavior (pinned quirk test un-pinned). Python stays canonical (D-0008 stands); publishing remains human-tokened per the runbook.

## D-0015 — HEAD-anchored, non-self-amending trust roots
**Status:** accepted
**Context:** `statutor staged` reads worktree `.statutor.yaml`, so unstaged or co-staged weakening can choose the rules judging another staged mutation; neither the policy nor the init-created Claude→AGENTS bridge is protected independently of that mutable policy.
**Decision:** Floor mode defines baseline B as `HEAD:.statutor.yaml` (embedded defaults only when absent/unborn) and candidate C as index `:.statutor.yaml` (defaults when absent), never worktree bytes. B judges the complete staged transaction; an authorized changed C also judges candidate-governed records in the resulting index but cannot relax B inside that commit. Present malformed/unsupported policy, nondeterministic Python/Rust parsing, and Git read failures are floor errors, not fallback. In-loop modes use B when available and defaults before first commit; hook exceptions still fail open.
**Decision:** `.statutor.yaml` is human-owned after init and protected by non-configurable kernel meta-rules. The only Statutor-owned `CLAUDE.md` is the exact committed `@AGENTS.md\n` compatibility bridge created by init (legacy exact bridges are recognized when a tracked policy exists); its edit/delete/rename is likewise meta-protected. Init never overwrites or adopts any other `CLAUDE.md`, which remains human-owned and doctor-reported as unmanaged.
**Decision:** After bootstrap, every trust-root byte or lifecycle change requires interactive `statutor trust approve --decision D-NNNN`: it shows the policy diff and all staged paths, requires a typed tree-ID confirmation, and writes a mode-0600 Git-local receipt bound to repo identity, B's HEAD OID, the complete index-tree OID, policy blob IDs, approved reserved paths, decision, and reason. The receipt authorizes only those reserved paths, expires on any HEAD/index change, and is authorization evidence rather than human authentication; `--no-verify` remains an unverified break-glass escape.
**Decision:** The approval UI classifies a transition as non-weakening only when existing ordered pattern/policy pairs remain, caps only tighten, required sections only grow, `bash_guard` never changes true→false, and new rules append; removal, reordering, retyping, wider/missing caps, fewer sections, guard disablement, duplicates, or unknown semantics are weakening/incomparable. An approved weakening becomes authority only as the next HEAD; a B-forbidden ledger mutation therefore needs a later commit.
**Consequences:** T-0025/T-0026 implement the meta-rules, strict zero-dependency policy schema, receipt, dual-snapshot checks, legacy diagnostics, and expected-result Python/Rust cases. This narrows D-0005 opt-out and D-0014 fallback behavior without changing hook fail-open, Python canonicality, TASKS semantics (T-0027), or the later ref-range/global-layer decisions.
**Trust boundary:** Once a parse-valid candidate is committed it is B—even an explicitly approved `governed: []`; Statutor prevents unapproved transitions while its floor runs, but cannot authenticate the actor, prove historical hook use, or make `--no-verify`, hook installation, executable integrity, CI, or branch protection part of this local trust claim.

## D-0016 — State records preserve task identity, not task wording
**Status:** accepted
**Context:** TASKS was described as stable-ID state, but hooks allowed shell rewrites and the floor checked only its path lifecycle. A useful queue must remain editable without letting completed or delegated work silently disappear.
**Decision:** Every checkbox entry in a `state` file is one line shaped `- [ ] T-NNNN detail` or `- [x] T-NNNN detail`, with a unique four-or-more-digit ID. Existing IDs survive every candidate; checkbox, detail, and order may change. New IDs must be numerically greater than the committed maximum. Bash writes and record deletion/rename-out are denied; editor/apply_patch paths enforce what they can in-loop, and the HEAD/index floor judges the complete blob.
**Decision:** v0.3.1 has no pruning operation. Completed tasks remain as identity history. Any future compaction must first define an append-only or frozen archive that preserves the complete ID mapping and must supersede this decision.
**Consequences:** Doctor reports malformed/duplicate state entries; Python/Rust conformance carries allowed and denied transitions. This does not make task prose immutable or impose task ordering, dependency, assignment, or workflow semantics.

## D-0017 — Native staged twin is local-only, not a static server floor
**Status:** accepted; supersedes D-0014's static/pre-receive rationale only
**Context:** The published Rust binary reads a worktree index through `git diff --cached`. A bare pre-receive hook has neither that index nor the pushed old/new ref transaction, and ordinary Cargo builds do not guarantee static linkage.
**Decision:** `statutor-staged` remains the conformance-gated native implementation of local `staged` mode for pre-commit and CI. Public material must say native/no-Python, never static, and must not prescribe it for pre-receive. A server validator requires a new ref-range contract, decision, CLI mode, and conformance matrix.
**Consequences:** D-0014 still licenses the narrow Rust duplicate and its registry artifact. v0.3.1 retracts the false deployment claims rather than pretending staged-index semantics are portable to a server transaction.

## D-0018 — Bounded portable user layer for global instructions and Agent Skills
**Status:** accepted
**Context:** Claude Code, Codex, and OpenCode expose user-scoped instructions and Agent Skills, but at different paths and with different precedence. Current primary contracts are [Claude's user CLAUDE.md/skills](https://code.claude.com/docs/en/claude-directory), [Codex AGENTS discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [OpenCode v1 rules/skills](https://opencode.ai/docs/rules/), and the [Agent Skills specification](https://agentskills.io/specification). Copying global agreements and skill trees by hand produces divergent duplicates and unclear ownership.
**Decision:** Add an opt-in `statutor global` user layer. Humans own one common `AGENTS.md`, host overlays, canonical skill sources, and versioned JSON config. After explicit create/adopt, Statutor alone owns complete generated host instruction files, skill projections, receipts, journals, and backups. It never owns managed blocks inside another writer's file. Claude receives `CLAUDE.md`; Codex and stable OpenCode v1 receive native `AGENTS.md`; Codex overrides and OpenCode's Claude fallback are reported as precedence/shadowing facts, never rewritten.
**Decision:** Every mutation follows a displayed deterministic plan, backup, compare-and-swap precondition, same-directory atomic replacement, receipt update, and recoverable journal. Existing unmanaged targets conflict; identical skill trees need explicit adoption; modified managed targets are never overwritten or deleted. Foreign locks, admin/system/plugin/account-synced roots, host JSON/TOML, and the maintainer's real home remain read-only unless a later separately approved dogfood operation names exact targets.
**Decision:** Portable skills validate the open Agent Skills core while preserving host extensions. Canonical sources project to `$HOME/.agents/skills` and Claude's personal skills root; no third OpenCode-native copy is created by default. Source flow is one-way. Duplicate, foreign-managed, shadowed, invalid, escaping/cyclic-link, drift, and catalog-budget states are inventory, not guessed away.
**Scope:** Verification baselines are Claude Code 2.1.251, Codex CLI 0.151.0, and OpenCode 1.18.20 as of 2026-08-31. OpenCode v2, enterprise deployment, remote acquisition/update, plugin lifecycle, global hooks, daemon/watch mode, bidirectional merge, host-config editing, and automatic real-home migration are non-goals.
**Consequences:** T-0032–T-0036 implement the resolver and safety primitives, instruction and skill lifecycles, stable JSON diagnostics, fake-home matrix, and separately gated real-release probes. The global layer does not turn user instructions into enforcement and does not require any project to adopt Statutor.

## D-0019 — Automatic adapters enforce only explicitly marked ledgers
**Status:** accepted
**Context:** Real use in the Telltales repository exposed two cross-project false positives. The automatic PreToolUse path applied embedded ledger defaults even though the repository had no `.statutor.yaml`, so an unrelated nested `clawd/HANDOFF.md` operator manual was treated as bounded state. Separately, the strict bash scanner read a quoted `git commit -F -` heredoc body as shell syntax, so prose naming governed files plus words such as `cp` or a `>` glyph denied a normal commit. The Stop hook already treats `.statutor.yaml` as the explicit opt-in marker, while D-0015 requires embedded defaults only during the marked policy's pre-commit bootstrap.
**Decision:** Automatic Claude/Codex hooks and the OpenCode adapter first resolve the nearest ancestor carrying `.statutor.yaml`; outside one they stay silent. Inside one, relative tool paths remain relative to the host event CWD, but matching and policy loading use that ledger root. A worktree marker with no committed policy activates embedded defaults, preserving bootstrap; committed policy remains the in-loop authority. The public explicit `statutor check TOOL JSON [CWD]` contract retains its existing default-policy behavior for custom harnesses, while adapters use a new `--if-ledger` form. Denials that suggest policy changes must identify HEAD as the authority and explain the separate approval/commit transition.
**Decision:** D-0005's strict co-occurrence rule remains the default. One bounded lexical exception removes only the body and terminator of a complete, quoted heredoc whose owning simple command is exactly `git commit ... -F -`; the opener and every other command line remain scanned. Unquoted, incomplete, non-commit, piped, or chained mutation surfaces remain conservative. `git add` is not a worktree-content mutation and the staged floor remains responsible for the resulting candidate index.
**Scope:** Root-anchor syntax, exclusions, generalized match modes, and broad shell parsing are deferred. They change established basename semantics and require their own policy-schema decision plus Python/Rust conformance work.
**Consequences:** T-0037 adds automatic presence gating, nearest-ledger path semantics, accurate policy-source guidance, the narrow commit-message data exception, Telltales-derived regressions, and a separately approved real-home dogfood runbook before v0.4.0 publication.

## D-0020 — Hybrid worker provenance: local activity, portable completion
**Status:** accepted
**Context:** In a repository shared by Claude Code, Codex, and OpenCode, neither file timestamps nor commit authorship reliably answer which harness worked there most recently. "Latest" can mean mere activity, a successful mutation, or a completed shift, and harness hook surfaces prove different subsets of those events.
**Decision:** v0.5 records machine-local per-repository worker state under the Statutor XDG state root and adds explicit harness attribution to HANDOFF.md. The local registry reports activity, confirmed mutation, completion, and bounded active-session leases separately; a verified HANDOFF attribution is the portable authority for the last completed worker. Stable harness IDs are `claude`, `codex`, and `opencode`; role and invoking harness are recorded when known and remain unknown rather than inferred when a host cannot expose them.
**Decision:** Adapters may record only evidence their lifecycle surface proves. A pre-tool event is an attempt, never a confirmed mutation. State updates are atomic and keep prompts, tool payloads, and other conversation content out of the registry. Optional Git trailers may add history but are not required and are never the source of current-session truth.
**Consequences:** T-0038–T-0041 specify the schema and CLI, extend HANDOFF compatibly, integrate host capabilities, and verify concurrency, linked-worktree, privacy, and fake-root behavior. Existing v0.4 ledgers remain valid; missing attribution is introduced as a diagnostic rather than a floor-breaking migration.

## D-0021 — Random machine identity, portable completion, local-only presence
**Status:** accepted; refines D-0020
**Context:** Harness identity alone is ambiguous when the same agent tools operate from several machines. Hostnames, network addresses, MAC addresses, hardware serials, and OS machine identifiers are unstable or unnecessarily identifying, while a machine-local activity registry is not visible from another workstation.
**Decision:** Each Statutor user installation creates a random opaque `machine_id` in its mode-0600 XDG state, with an optional human-set label. Every worker record includes the ID and a label snapshot; HANDOFF completion carries `last_machine` alongside `last_worker`, making the last completed actor portable through Git. IDs are never derived from hardware, network, hostname, account, or repository data, and copied installations must explicitly rotate identity.
**Decision:** Active leases and uncommitted activity remain explicitly machine-local in v0.5. Statutor does not imply cross-machine presence, merge state files, or contact a service. Live fleet-wide coordination requires a later opt-in remote protocol and separate trust/privacy decision.
**Consequences:** T-0038–T-0041 cover machine initialization, display/label/rotation, attribution, cloned-state handling, and multi-machine fixtures. Queries expose their scope so portable completion cannot be confused with local activity.

## D-0022 — HANDOFF revision lineage as an offline collision guard
**Status:** accepted; refines D-0020/D-0021
**Context:** Machine-local leases cannot detect a simultaneous worker on another machine, but a live coordinator is unnecessary for Git-mediated workflows. Once both histories exist locally, Statutor can distinguish an ordinary successor from two handoffs independently produced from the same base.
**Decision:** Every attributed HANDOFF completion has a random `handoff_id` and one or more `supersedes` IDs. Session start records the baseline ID locally; completion validates compare-and-swap lineage. Concurrent machines starting from the same ID create distinct sibling revisions, and a reconciliation HANDOFF explicitly supersedes both. Missing lineage remains backward-compatible during v0.5 adoption.
**Decision:** Read-only comparison against a caller-supplied local Git ref reports base/ours/theirs worker and machine attribution plus the IDs a reconciliation must supersede. Statutor performs no fetch, pull, push, merge, automatic HANDOFF rewrite, or winner selection. Unique metadata lines intentionally make ordinary Git merging conservative when sibling handoffs collide.
**Consequences:** v0.5 provides collision detection and deterministic merge guidance after refs are locally available, while same-machine leases provide an earlier warning. Networked presence and remote coordination remain non-goals.

## D-0023 — No universal skill library; one routing skill only
**Status:** accepted
**Context:** Proposal to bundle Clawd/Codex/OpenCode-wide universal shared skills, including per-plane governance skills, as part of Statutor.
**Decision:** Decline the library. `skills/statutor` stays the sole bundled skill with a routing job (activation on ledger-related intent); per-trigger instruction lives in `commands/`, enforcement in the kernel hooks and git floor. Governance content duplicating enforced rules in unenforced prose recreates the instruction decay D-0001 was created to kill, and skill discovery is the least reliable layer (Claude exposes no offline personal-skill inventory, T-0036).
**Consequences:** Future skill proposals must show a non-duplicative job, pass three-host discovery verification, and keep general-purpose skills outside this repo.
