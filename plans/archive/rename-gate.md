<!-- writ: plane=plan | writer=human | decision-support for D-0010; archive when D-0010 is recorded -->
# Rename gate — choosing the successor to "writ"

Status: **CLOSED 2026-08-23 — the word is `statutor`.** Recorded as D-0010;
T-0014 (the mechanical rename) executed the same day. This file is archived as
the record of how the choice was made.

Sweep provenance: 2026-08-23, ~75 candidates, eight checks per name (PyPI incl.
PEP 503 variants, npm, crates.io, Homebrew formula+cask, GitHub exact-name repos,
Debian/Arch/AUR/nixpkgs binaries, product-name search, `<name>-doctor` on PyPI).
Three checks initially returned silent false negatives (Homebrew name list behind
an HTML challenge, Debian contents parser splitting paths, dead nixpkgs ES creds)
and were redone with positive controls. RubyGems checked as a bonus — all six
finalists 404 there too.

## Baseline: why "writ" is unusable
- github.com/infinri/Writ — 187 stars, pushed 2026-08-15: "Governance runtime for
  Claude Code. Enforces workflow gates at tool time... preserves decision
  provenance across sessions." Same niche, same host tool, same language.
- PyPI `claude-writ` 1.7.0 ships a `writ` console script (pip silently clobbers
  competing shims). npm `writ` and crates.io `writ` also install `writ` binaries.
- PyPI `writ` is an abandoned 2018 squat. We would be the third arrival on this
  word in the agent-governance niche.

## Finalists — fully clear on every check
1. **statute** (7) — codified, enacted written law; authority-from-enactment is
   the literal definition. Best typability; `.statute.yaml` / `statute doctor`
   read naturally. Cost: common word — crowded SEO, weak trademark.
2. **mandamus** (8) — the prerogative writ compelling a bound duty; literally a
   writ, the direct lineal successor. Near-zero web noise. Slightly litigious
   tone; mild `mandamas` typo risk.
3. **injunct** (7) — coinage from *injunction*: an order defined by punished
   breach — maps exactly onto hook-enforced mutation policies. The only finalist
   with ZERO exact-name GitHub repos. Weaker on the ledger/record half.
4. **decretal** (8) — a ruling letter that decides law and thereby becomes law;
   the Decretals are canon law's codified corpus. Captures both the single order
   and the accreting body (log hardening into constitution). Mildly ecclesiastic.
5. **placitum** (8) — a court's decision AND the written record of it. Deep fit,
   but obscure; reads as *placid*/*placebo* to most.
6. **probate** (7) — officially proving a document so it acquires force ("a hook
   proves the ledger"). Everyday sense is wills/estates; probate-tech is a
   crowded commercial vertical.

Also fully clear but dominated: `statutum`, `promulge`.

## Addendum — the statute family, swept deeper (2026-08-23, second sweep)
The human leans `statute` but wants a less generic, more agent-flavored identity.
Latin derivations swept with the same eight checks plus GitHub org, domains,
dotfile, and Claude-plugin-name probes:
- **statutor** (agent noun of *statuere*: "the one who enacts") — **FULLY CLEAR**
  everywhere; no domain even registered; GitHub user/org free; the lone
  exact-name repo is a dead one-day 0-star "StatTutor" (statistics tutor).
  Caveat: parses as "stat-tutor" before "one-who-enacts"; one character from
  `statutory` (autocomplete pressure); invites `statuter`/`statuor` misspells.
- **statutum** — already verified fully clear in the first sweep; under the new
  "distinctive over common" weighting it is no longer dominated by `statute`.
- **statuta** — **BLOCKED.** Registries are free, but statuta.com is a live,
  priced SaaS: "prompt management for AI clients" with MCP server integration,
  versioning, and team libraries (app.statuta.com login live; statuta.ai also
  registered). Plus an ACTIVE exact-name GitHub repo: an agentic EU-AI-Act
  compliance copilot pushed 2026-08-20 that ships a `.claude/` directory. The
  GitHub org `statuta` is taken. Typo note: one vowel from `statute`,
  indistinguishable by ear.
Statute-family choice set as of now: `statute`, `statutum`, `statutor` — all
claimable today.

## Near-misses (clear except one soft conflict)
- **regest** (6, shortest clean option) — every registry clear, zero repos; one
  keystroke from `regex` / `request` / `register`.
- **indenture** — excellent fit (duplicate-executed contract ~ single-writer
  files); 9 letters, over budget.
- **subpoena** — clear everywhere; notorious misspelling kills it as a CLI.
- **decretum** — clear, but an active 2-star Rust language project (2026-08).
- **syngraph** — clear, but a 34-star published bioinformatics toolkit owns it.

## Notable eliminations (why the register is a minefield)
- **edict** — 16,398-star OpenClaw multi-agent orchestration system (pushed
  2026-08-03), plus four more actives; kills `edictal`/`edictus` by adjacency.
- **diktat** — registries free, but a 572-star Kotlin code-standard ENFORCEMENT
  tool. Hard fail on identity.
- **muniment** — active crate in the exact storage/provenance domain, whose docs
  already name `codicil` as its sibling append-only log. Takes both words.
- **bylaw** (architecture-enforcement crate, 2026-08), **charter** (LLM-context
  crate + npm), **docket** (crate ships a binary, 32k downloads).
- Taken on a primary registry: decree, mandate, canon, seal, warrant, precept,
  verdict, sanction, attest, enact, notary, sigil, ledger, and ~50 more.

## Recommendation
`statute` for thesis fit + typability; `injunct` for a pristine, ownable
namespace; `mandamus` for explicit lineage from "writ".

## Urgency once decided
All clearances are as of 2026-08-23; PyPI is first-come with no reservation
mechanism. Claim the PyPI name (and npm/crates placeholders) the same day the
word is fixed, before announcing it anywhere.

## What executes on decision (T-0014 scope)
pyproject (name, scripts, modules), .claude-plugin/plugin.json + marketplace.json,
`.writ.yaml` → `.<name>.yaml` (kernel constant + templates + tests), hooks/,
commands/, skills/, adapter READMEs, root README, repo directory name. Full suite
must be green before and after; the live plugin needs one reinstall afterward.
