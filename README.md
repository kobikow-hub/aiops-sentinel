# AIOps Sentinel

An AI-driven incident-remediation system where an LLM is only ever allowed to
**propose** a fix — in a tiny, closed-vocabulary DSL — and a chain of
**independent, formal checkers** must each say yes before a Tool Gateway is
allowed to touch anything. Built as a mentored, step-by-step training project
(one step at a time: explain, build, prove with a real test run, then stop
for approval) covering 5 phases end to end, with **220 passing tests** plus
17 official policy tests.

The core idea: **the LLM never decides, it only drafts.** Every draft is
graded by a fixed pipeline of specialists that never trust each other's word
— they only trust facts passed forward and freshly re-checked state.

## Why this exists

Giving an LLM direct access to infrastructure is the fastest way to turn a
hallucination into an outage. This project is an exploration of the opposite
design: treat the LLM like a junior engineer who can *suggest* a fix in a
strict order form, while a panel of boring, deterministic, formally-verified
judges — a policy engine, a dependency analyzer, a logic prover, a temporal
rule-checker, and an SMT solver — each independently decide whether that
suggestion is safe enough to run, right now, on the real world as it
currently stands.

## Architecture at a glance

```
alert → mail slot → black-marker redaction → LLM drafts ONE sentence
                                                 │ (text only, zero power)
                                                 ▼
                                   GATE 1 (parse + typecheck + wax seal)
                                                 │ sealed program
        ┌────────────────────────────────────────┘
        ▼
  OPA (policy)  →  Datalog (blast radius)  →  Prolog (THE risk judge)  →  LTL (order of events)
        │ facts flow forward only; any NO → Blocked, nothing retried
        ▼
  risk LOW → proceeds alone        risk HIGH → one-time approval slip + 30s SLA timer
        │                                   │ silence ⇒ escalation, never consent
        ▼                                   ▼
  Z3 — LAST look, on a LIVE snapshot, pinned by version (refuses if the world moved)
        ▼
  Tool Gateway (the only component with credentials) — idempotent, reconciles on timeout
        ▼
  Health probe → bounded retry (max 2, brand-new fingerprint each time) → escalation if exhausted
        ▼
  Append-only diary (JSONL, closed vocabulary, authorized voices only)
        │ re-checks ALL time rules before closing — the ONLY door to "resolved"
        ▼
  Incident Resolved
```

A FastAPI dashboard (`web/`) drives three demo stories end-to-end through the
*real* engines (real OPA binary, real SWI-Prolog, real Z3, a mock
infrastructure driver) and renders the board's live state, the append-only
diary, and a click-through code atlas of every station.

## Design principles enforced by the code (not just documentation)

- **One authority per question.** Prolog is the *only* component that
  computes risk. OPA maps risk to a route but never recomputes it. Z3 runs
  physics checks last, on live data, never earlier. Nobody double-guesses
  another checker's job.
- **Fail closed.** A missing, broken, or slow checker is treated as a hard
  **NO** — never as "skip this check."
- **Grammar as a wall, not a filter.** The DSL's EBNF grammar makes unsafe
  sentences *unwritable* — there is no quoted-free-text rule anywhere, so a
  prompt-injection payload hidden in a log line has no grammar slot to land
  in. Evidence can only be cited by id.
- **One fingerprint, one action.** Every proposal is sealed with a SHA-256
  hash over the incident, the exact canonical program, and the proposal
  time. The Gateway refuses to execute the same fingerprint twice — doing a
  risky action twice is never "safer than once."
- **Silence is never consent.** An unanswered approval request expires into
  an escalation to a human owner, not into automatic action.
- **The diary is written in pen.** Append-only JSONL, a closed vocabulary of
  30 event names, one authorized "voice" per event (the LLM itself has none
  of its own), and a full re-check of every temporal rule before the diary
  is allowed to close. An incomplete or out-of-order diary cannot resolve.

## Engines used (the real thing, not simulated)

| Concern | Engine | Why |
|---|---|---|
| Policy / routing | **Open Policy Agent** (Rego) | Versioned, testable law instead of `if` statements buried in code |
| Blast-radius analysis | Datalog-style facts (pure Python, mirrors a Soufflé spec) | Deterministic "who breaks if this goes down" reasoning |
| Risk judgment | **SWI-Prolog** | One authoritative, provable risk verdict with a written proof trail |
| Event-order safety | Custom LTL-style rule engine | Catches "did this happen in a legal order," not just "is this content safe" |
| Pre-flight physics | **Z3 SMT solver** | Last-look constraint check against the live world, with named unsat cores |
| Orchestration | `python-statemachine` | An explicit, provably-reachable state machine — illegal transitions can't exist |

## Project layout

```
sentinel/   intake (alerts, redaction, mock LLM) + the DSL gate (parser, typecheck, fingerprint)
board/      the state machine every component moves on
rules/      the Datalog spec + the Prolog risk law (verbatim source-of-truth files)
policy/     the OPA/Rego policy + its official test suite
ltl/        the 15 temporal safety rules and their evaluator
constraints/ the Z3 deployment gate
gateway/    the mock infrastructure driver + the only component holding credentials
audit/      the append-only incident diary
web/        the FastAPI dashboard + its frontend
tests/      ~220 tests across every module
```

See **[CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md)** for a plain-words,
file-by-file explanation of how everything fits together, and
**[MEMENTO.md](MEMENTO.md)** for the full build history, every bug caught
along the way, and the design decisions made at each step.

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install z3-solver lark python-statemachine pytest fastapi uvicorn

# Run the full test suite
python -m pytest tests/

# Run the demo dashboard (from the project root)
python -m uvicorn web.app:app --port 8000
# then open http://localhost:8000
```

Two external engines are required for the full pipeline:
- **OPA** — download the single-file binary for your platform from the
  [official releases](https://github.com/open-policy-agent/opa/releases)
  into `tools/opa.exe` (or `tools/opa` on Linux/macOS).
- **SWI-Prolog** — install from the
  [official site](https://www.swi-prolog.org/download/stable); the adapter
  looks for it on `PATH` or at the standard Windows install location.

## Status

All 5 planned phases (Intake → Checking → Deciding → Deploying → Verify &
Close) plus the demo dashboard are complete. 220 tests passing, 17 official
OPA policy tests passing. Built as a learning project — the LLM is a
deterministic mock with scripted demo stories; swapping in a real LLM behind
the existing `LLMInterface` is a natural next step that requires zero
changes to any checker, since nothing downstream trusts the LLM's output
without re-verifying it from scratch.
