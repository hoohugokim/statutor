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
