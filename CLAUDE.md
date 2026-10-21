# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Scope note:** This directory (`Final AI Archtect PRoj`) is the **AIOps Sentinel** project — it is NOT part of the Evergreen Brain RAG system described in the parent `PYTON/CLAUDE.md`. Nothing here touches GCP, Cloud Run, or the multi-tenant registry.

## What This Project Is

AIOps Sentinel is a mentored learning project for Danny & Kobi (AI Architects in training): an AI-driven incident-remediation system where an LLM proposes a fix in a strict DSL and a chain of formal checkers (OPA → Datalog → Prolog → LTL → Z3) must approve it before a Tool Gateway executes anything.

**Current state (2026-09-26): ALL PHASES (0–5) COMPLETE, including the P5.5 web dashboard.** See **MEMENTO.md** (newest blocks at top) for the full progress log, test scoreboard, bugs caught, and decisions recorded. The local suite is **220 passing tests** plus 17 official Rego tests; verified-by-run official tests: P1, P2, P5, P8, P12, P15 (+ the hearts of P4, P10, P11, P14, P16, P17). No plan steps remain — open follow-ups are listed in MEMENTO's top block (git commit, real-LLM swap, `current_state` deprecation).

- `AIOps_Sentinel_Simple_Guide.pdf` — the authoritative spec (v4 + v5 design). Rule files, state machine, tests P1–P18, and demo stories are all defined by guide part numbers referenced throughout the plan.
- `generate_dev_plan.py` — PDF generator whose CONTENT section (`PHASES`, `WORKFLOW_RULES`, `CHECKPOINTS`, etc.) is the machine-readable copy of the full development plan. Read it before doing anything else; it defines every step ID, file to create, and done-criterion.
- `MEMENTO.md` — session-by-session progress log (what was built/approved, what broke, where we parked). **Read the top block before resuming work.**
- `CODE_WALKTHROUGH.md` — plain-words explanation of every implementation file built so far (for Danny & Kobi's study).
- `VERSIONS.md` — provenance ledger for the five official rule files + engine versions (guide Part 15 requirement).

## Mandatory Workflow (non-negotiable teaching contract)

These rules come from the plan itself and override default behavior:

1. **Phase-based, in order.** Phases 0–5 (Intake, Checking, Deciding, Deploying, Verify & Close, plus Phase 0 setup). Never jump ahead.
2. **Explain first, code second.** Every step gets a plain-words explanation with a real-world analogy BEFORE any code appears (written for a 5th-grader level of clarity).
3. **One step, then STOP.** Present exactly one step, explain it, and stop. Nothing continues until the user says **"I understand and approve."**
4. **Step IDs are the resume mechanism.** Steps are numbered `P<phase>.<step>` (e.g. `P2.3` = Phase 2, step 3). If the user says "we are on P2.3", pick up exactly there using the step card in `generate_dev_plan.py`.
5. **A test is "passing" only after it actually ran.** All tests P1–P18 start as "planned" — never claim a pass without executing it.
6. **Exactly three demo stories** (scope locked): Story 1 — happy path (restart web_frontend, low risk); Story 2 — blocked (restart master_db, blast radius 40 > limit 10); Story 3 — wrong order (execute right after proposal, LTL rule L1 refuses). Everything else is a test, not a demo.

## Commands

```bash
# Regenerate the development-plan PDF (uses the parent PYTON .venv)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe generate_dev_plan.py

# Phase 0 installs (P0.2) — into the same .venv; fpdf2 and FastAPI already present
pip install z3-solver lark python-statemachine pytest

# Run tests (use the parent .venv's python; plain `python` may not be it)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m pytest tests/                  # full suite (220)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m pytest tests/test_web.py       # P1+P2 through the dashboard (real engines)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m pytest tests/test_dsl_gate.py  # one file (P15)

# Engine checks
tools/opa.exe check policy/             # Rego syntax check (OPA 1.20.2 lives in tools/)
tools/opa.exe test policy/ -v           # official OPA rule tests (17, written at P2.1)
"C:/Program Files/swipl/bin/swipl.exe" --version   # SWI-Prolog 10.0.2 (PATH needs a fresh terminal)

# Run the demo dashboard (MUST run from the project root, not from web/)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m uvicorn web.app:app --port 8000
```

## Target Architecture (what gets built)

**Pipeline order is fixed and never changes:**
AI suggests → GATE 1 (DSL parse + type check + `action_hash` fingerprint) → OPA (rule book, allow/deny) → Datalog (blast-radius / "who breaks?" finder, with veto) → Prolog (the ONLY risk authority) → LTL (event-order rules L1–L15) → risk route (low = autonomous, high/unknown = human approval with one-time token) → Z3 last-look on a live snapshot → Tool Gateway executes → health probe → append-only audit diary → close.

**Four architectural invariants (the instructor's checkpoints — verify at the end of every phase):**
- (a) The DSL parser/type checker is GATE 1: nothing the AI writes reaches any checker without passing it (P1.4).
- (b) **Prolog is the ONLY component that computes risk.** OPA, Datalog, Z3, and the Arbiter never compute their own risk level (P2.3).
- (c) OPA maps Prolog's risk to a route (autonomous vs. human approval) — it reads risk, never re-decides it (P3.1).
- (d) Z3 runs LAST, in Deploying, on a live snapshot taken after all decisions and approvals — never earlier (P4.1).

**Other load-bearing design decisions (already made — do not relitigate):**
- The state machine (`python-statemachine`, 18 states, transitions T1–T30) is the only boss: components send events, the board decides what may happen. Skeleton built right after Phase 0; each phase switches on its own transitions.
- Datalog is a plain, well-commented Python module mirroring the official `rules/topology.dl` spec (Soufflé has no native Windows build). The `.dl` file stays as the spec the code must match.
- The LLM starts as a **MockLLM** with fixed answers for the three stories, behind an interface a real AI (OpenRouter) can later replace.
- The Tool Gateway is the only component with credentials; it refuses on stale snapshot version, uses `action_hash` as idempotency key, and reconciles on timeout before declaring failure.
- Checkers fail closed (broken/slow checker = NO). A checker's NO is never retried; failures retry at most twice with the lesson in the prompt, then escalate.
- The audit diary is append-only JSONL; `Incident_Resolved` is reachable only through a complete diary that satisfies L1–L15 (rule L7).
- The five official rule files (`dsl/remediation.ebnf`, `policy/sentinel/authz.rego`, `rules/topology.dl`, `rules/remediation.pl`, `audit/trace.schema`) are copied verbatim from the guide in P0.5 and treated as law — code conforms to them, not the other way around.

**Directory layout** (created at P0.1): `sentinel/` with `dsl/`, `intake/`, `checkers/`, `decide/`, `verify/`; plus top-level `policy/sentinel/`, `rules/`, `ltl/`, `constraints/`, `audit/`, `gateway/`, `board/`, `web/`, `tests/`, `tools/`.

## What exists (ALL phases complete)

- **Law books (P0.5, verbatim from the guide, tracked in `VERSIONS.md`):** `sentinel/dsl/remediation.ebnf`, `policy/sentinel/authz.rego` (+ `authz_test.rego`, 17 official tests), `rules/topology.dl`, `rules/remediation.pl`, `audit/trace.schema`. The `.dl` file is a spec — the runtime Datalog is the Python module `sentinel/checkers/datalog.py`. Note: the grammar lives at `sentinel/dsl/remediation.ebnf` (package home), not top-level `dsl/`.
- **Board:** `board/incident_machine.py` — IncidentMachine, all 18 states + T1–T30 moves, all live. Only IncidentMachine is built; AdvisorMachine (T31–T43) stays parked spec.
- **Phase 1 — Intake:** `sentinel/intake/alerts.py` (mail slot, T1) → `sentinel/intake/redactor.py` (secret remover, T2; `allowed_services` plugged by Datalog's `alert_context`) → `sentinel/intake/llm.py` (`LLMInterface` + `MockLLM` with scripted stories and 7 deliberate bad outputs) → GATE 1 in `sentinel/dsl/`: `parser.py` (Lark, mirrors the .ebnf), `typecheck.py` (grounded/kind/limits/trick-flag), `fingerprint.py` (action_hash), `gate.py` (assembly; sends T3/T4 — the AI never sends events).
- **Phase 2 — Checking (the four guards, fixed order, facts forward only):** `sentinel/checkers/opa_adapter.py` (runs the real `tools/opa.exe`; `eval_opa()` is the shared messenger also used by the arbiter and approval validator; T5/T6) → `sentinel/checkers/datalog.py` (blast radius + sensitive-path veto, mirrors `topology.dl`; T7/T8) → `sentinel/checkers/prolog_adapter.py` (real swipl.exe against `remediation.pl`; the ONLY risk authority, stores `incident.risk_level`; T9/T10) → `ltl/rules.py` + `ltl/check.py` (rules L1–L15; `look_ahead` for Temporal_Check T11/T12, `live_guard` always-on, `check_full_trace` for the diary close).
- **Phase 3 — Deciding:** `sentinel/decide/arbiter.py` (reads Prolog's risk, never recomputes; OPA maps risk→route; T13/T14), `sentinel/decide/approval.py` (one-time tokens bound to `action_hash`, OPA-validated; `review_packet()` honest screen), `sentinel/decide/sla_timer.py` (silence → escalation, never consent).
- **Phase 4 — Deploying:** `constraints/deployment_gate.py` (Z3 last-look on a live snapshot, named unsat cores, version pin; T18/T19), `gateway/system_map.py` + `gateway/mockdriver.py` (pretend infrastructure with version heartbeat + scripted behaviors + receipt book), `gateway/tool_gateway.py` (the only credential holder: papers check, compare-and-execute, idempotency, reconcile-on-timeout).
- **Phase 5 — Verify & Close:** `sentinel/verify/probe.py` (health probe, T20/T21), `sentinel/verify/recovery.py` (MAX_RETRIES=2; checker NOs structurally unretryable), `sentinel/verify/escalation.py` (packet in the checkers' own words; notify-first T27; `record_human_resolution` T28), `audit/audit_service.py` (append-only JSONL diary: closed 30-name vocabulary, authorized voices, non-decreasing phases; `close()` re-checks L1–L15 — the only door into Incident_Resolved, T29).
- **P5.5 dashboard:** `web/app.py` (FastAPI; the GUI is dumb — buttons POST, the page mirrors `/api/state`) + `web/templates/index.html`. Three tabs (annotated file tree, architecture diagram, runtime tracker), clickable 12-station tracker with refs panel, lightbox source viewer (project-jailed, suffix-allowlisted), board state/trace boxes, and a jumping high-risk approval alarm with a 30s SLA countdown (approve/reject/silence-escalates, all tested). Demo worlds: `story1_topology()` (clean leaf → low risk) vs `story2_topology()` (40 dependents on master_db) — kept separate on purpose.
- **Tests (220 total):** intake 11, redactor 13, llm 9, dsl_gate 17 (**P15**), opa_adapter 11, datalog 16, prolog 16, ltl 13, routing 7, approval 9 (**P8**), sla 6, z3_gate 9, mockdriver 11, gateway 10, probe 6, recovery 9, escalation 9, audit 11 (**P5+P12**), web 27 (**P1+P2**, driving the real OPA/Prolog/Z3/Gateway through TestClient).
