# MEMENTO.md — AIOps Sentinel progress log

Newest blocks at the top. Each block: what was built, what was decided, what broke and how it was fixed, and exactly where we parked.

---

## 2026-09-26 — Sessions 2–4: Phases 2, 3, 4, 5 COMPLETE — **ALL PHASES DONE**

**Parked at:** 🎉 the whole development plan is built. All 5 phases approved step by step, **220 tests passing** (`python -m pytest tests/`), plus 17 official Rego tests (`tools/opa.exe test policy/ -v`). The P5.5 web dashboard runs all three demo stories from the browser and ends in the guide's exact final states.
**Next when we resume:** no plan steps remain. Open ideas (not commitments): commit everything to git; swap MockLLM for a real OpenRouter LLM behind `LLMInterface`; modernize `current_state` → `configuration` (deprecation warnings); AdvisorMachine (T31–T43) stays parked spec.

### Test scoreboard (teacher's rule v5-9: only a test that RAN may be called passing)

| Official test | Where it ran | Status |
|---|---|---|
| **P1** (Story 1 happy road) | `tests/test_web.py` TestStory1 (real OPA+Prolog+Z3+Gateway via TestClient) | **PASSING** |
| **P2** (Story 2 blocked, nothing executed) | `tests/test_web.py` TestStory2 | **PASSING** |
| **P4** heart (bounded retry, checker-NO never retried) | `tests/test_recovery.py` | **PASSING** |
| **P5** (complete diary closes; incomplete refused) | `tests/test_audit.py` TestClosingP5 | **PASSING** |
| **P8** (one-time approval slips) | `tests/test_approval.py` | **PASSING** |
| **P10 + P14** core (Z3 last-look, snapshot pin) | `tests/test_z3_gate.py` | **PASSING** |
| **P11** heart (idempotency, reconcile-on-timeout) | `tests/test_gateway.py` | **PASSING** |
| **P12** (diary format: closed vocab, voices, phases) | `tests/test_audit.py` TestFormatP12 | **PASSING** |
| **P15** (the DSL gate) | `tests/test_dsl_gate.py` | **PASSING** |
| **P16** discipline (phase never backwards per fingerprint) | diary append check, `tests/test_audit.py` | **PASSING** |
| **P17** fixtures (checker goldens) | `tests/test_datalog.py`, `test_prolog.py`, `test_ltl.py` | **PASSING** |
| Local suite total | `python -m pytest tests/` | **220 passed** |

### Phase 2 — Checking (the four guards, all approved)

- **P2.1** `sentinel/checkers/opa_adapter.py` — runs the REAL `tools/opa.exe` as a subprocess against `policy/sentinel/authz.rego`. `eval_opa()` is the shared messenger (the arbiter and approval validator reuse it later); `check_policy()` moves T5/T6. Fail-closed: missing/broken/slow OPA = NO. Official `authz_test.rego`: 17/17. 11 tests.
- **P2.2** `sentinel/checkers/datalog.py` — plain Python mirroring `rules/topology.dl` (Soufflé has no Windows build; the `.dl` stays the law this code must match). `affected_by` (BFS), `alert_context` (finally plugging the redactor's `allowed_services` socket from P1.2), blast/dependents, sensitive-path veto. T7/T8. 16 tests.
- **P2.3** `sentinel/checkers/prolog_adapter.py` — the ONLY risk authority (checkpoint b). Writes a temp case file of `assertz` facts, runs the REAL swipl.exe against `rules/remediation.pl`, parses `ALLOWED:/RISK:/WHY:/PROOF:`. Stores `incident.risk_level`. T9/T10. 16 tests.
- **P2.4** `ltl/rules.py` + `ltl/check.py` — the 15 time rules L1–L15 as data, with per-action/incident/episode scoping; `look_ahead()` (Temporal_Check, T11/T12) vs `live_guard()` (always-on) vs `check_full_trace()` (the diary's close ritual). 13 tests.

### Phase 3 — Deciding (all approved)

- **P3.1** `sentinel/decide/arbiter.py` — reads Prolog's `incident.risk_level`, NEVER recomputes (checkpoint c); asks OPA for the route via the same `eval_opa` messenger. T13 (`risk_low`) / T14 (`risk_high`). 7 tests.
- **P3.2** `sentinel/decide/approval.py` — one-time tokens bound to the exact `action_hash`, validated by OPA (role, fingerprint, expiry, single-use); `review_packet()` = the honest screen. **Test P8 PASSING.** 9 tests.
- **P3.3** `sentinel/decide/sla_timer.py` — injectable clock, fires once, silence → escalation NEVER consent. 6 tests.

### Phase 4 — Deploying (all approved)

- **P4.1** `constraints/deployment_gate.py` — Z3 LAST-look on a LIVE snapshot (checkpoint d), `assert_and_track` for named unsat cores, `LiveSnapshot` version pin. 9 tests.
- **P4.2** `gateway/system_map.py` + `gateway/mockdriver.py` — the pretend infrastructure with a version heartbeat and scripted behaviors (success / refuse / fail / timeout_but_done / timeout_not_done) + receipt book. 11 tests.
- **P4.3** `gateway/tool_gateway.py` — the ONLY component with credentials. Papers check → compare-and-execute (refuses if world moved past Z3's pinned version) → `action_hash` idempotency → reconcile-on-timeout before declaring failure. 10 tests.

### Phase 5 — Verify & Close (all approved)

- **P5.1** `sentinel/verify/probe.py` — reads the LIVE world after execution: service healthy? capacity? alert cleared? T20/T21. 6 tests.
- **P5.2** `sentinel/verify/recovery.py` — MAX_RETRIES=2, only the 3 accident reasons may enter Recovery; a checker's NO structurally cannot be retried. Each retry = brand-new fingerprint through ALL checks. 9 tests.
- **P5.3** `sentinel/verify/escalation.py` — packet in the checkers' OWN words, notify-FIRST-then-move (T27), `record_human_resolution()` demands name+note (T28). 9 tests.
- **P5.4** `audit/audit_service.py` — the pen-not-pencil diary: 30-name closed vocabulary, authorized voices (the AI has NO voice), phase non-decreasing per fingerprint, append-only by construction (no eraser exists). `close()` re-reads the WHOLE diary against L1–L15 prospectively — the ONLY door into Incident_Resolved (L7, T29). **Tests P5 + P12 PASSING.** 11 tests.
- **P5.5** `web/app.py` + `web/templates/index.html` — the demo dashboard. **Tests P1 + P2 PASSING** through it. 25 tests.

### The dashboard (P5.5 + enhancement rounds, all user-requested)

The GUI is DUMB by design: buttons ring doorbells (POST), the page mirrors `/api/state` (GET, 600ms poll) — the board decides everything.

- **Three tabs:** ① annotated file-structure tree (`/api/tree`, one-line note per file AND per directory), ② architecture diagram (HTML box-and-arrow, 5 phase bands, every file name clickable), ③ runtime (the tracker).
- **12-station tracker**, click a station → refs panel (one-line summary, called_by, law, board_moves, tests, diary_events) + highlights the matching diary/timeline lines.
- **Lightbox source viewer** (`/api/source`) — read-only, project-root-jailed, suffix-allowlisted (`tools/opa.exe` → 403), Esc closes. Every file name anywhere in the UI opens it.
- **State + trace boxes** — current board square, last transition, full scrolling trace (a listener on the machine records every move).
- **High-risk approval alarm** — jumping/glowing panel with a **30s SLA countdown** (`APPROVAL_SLA_SECONDS`, demo POC value). Three endings, all tested: YES → token threads to the Gateway → Incident_Resolved; NO → Blocked + escalation packet; SILENCE → `sla_timer` fires `approval_timeout` → Escalated.
- **Story 1 ⚠ high-risk variant button** (added 2026-09-26, user request — none of the three locked stories reaches the approval alarm from the browser): `POST /api/story/1?high_risk=true` marks the target **stateful in the world's photo** before the run, so Prolog (still the only risk judge) rules HIGH and the pipeline pauses at the alarm. Lets the viewer WATCH the 30s countdown expire → `approval_timeout` → Escalated → owner form (T28) → lawful close. Not a 4th story — the same Story-1 alert/sentence in a different world; `high_risk=true` on stories 2/3 → 400. We change the WORLD, never the risk. 2 new tests (27 in test_web.py, suite total **220**).
- **Story 3 refusal detail** — shows `required_approvals` vs `missing_approvals` ("✗ opa_allowed (never happened)").
- Two-column layout: tracker left, Story-So-Far right (sticky) — one full screen, no scrolling.

### Bugs caught this stretch (the try-check-learn loop, again)

1. **Story 1 routed to human approval** — `demo_map()` wired `web_frontend` into the sensitive `master_db` chain, so Prolog said HIGH. Fix: `story1_topology()` — a clean leaf topology for Stories 1/3; Story 2 keeps the 40-dependent map. Lesson: the demo world is part of the spec.
2. **Gateway refused the approved high-risk action** ("no approval token") — `_deploy_and_close()` never received the token. Fix: `_human_decision()` returns `(outcome, token)`; `/api/approve` threads it through to `check_and_execute()`. The Gateway demanding papers it wasn't given is the SYSTEM WORKING — the plumbing was the bug.
3. **Typing in the escalation form got wiped** — the 600ms poll re-rendered the panel every tick. Fix: `ESC_SHOWN` flag renders the form once per appearance.
4. **`opa.exe` in the tree test** — the tree legitimately says "messenger to opa.exe" in `opa_adapter.py`'s note; the naive `"opa.exe" not in tree` assertion collided with it. Fix: assert the BINARY isn't listed (`@[opa.exe` / `tools/opa.exe` absent), not the substring.
5. **LTL violation evidence** (P2.4) — `live_guard`'s `last_steps` showed the refused event itself instead of the diary-as-it-stood; rebuilt from the pre-violation diary.

### Decisions recorded (do not relitigate)

- `story1_topology()` / `story2_topology()` are separate demo worlds on purpose — Story 2's blast radius must not contaminate Story 1's autonomy.
- `APPROVAL_SLA_SECONDS = 30` is a demo-POC value (user-set); production would be minutes.
- `eval_opa()` is the single OPA messenger for all three askers (checker T5/T6, arbiter route, approval validation) — one subprocess path, one fail-closed behavior.
- The dashboard tests drive the REAL engines (opa.exe, swipl, Z3) through FastAPI's TestClient — no mocking of the pipeline, only of the world (`demo_map`).

---

## 2026-09-19 — Session 1: Phase 0 + Phase 1 COMPLETE

**Parked at:** 🛑 STOP after P1.4 / end of Phase 1, approved through P1.4.
**Next step when we resume: `P2.1` — the OPA adapter** (wire `tools/opa.exe` + `policy/sentinel/authz.rego` into the pipeline; official `opa test policy/ -v` suite; fail-closed = missing/slow referee means NO; events `opa_allowed`/`opa_denied`, T5/T6).

### Test scoreboard (teacher's rule v5-9: only a test that RAN may be called passing)

| Test | Status |
|---|---|
| **P15** (the DSL gate works) | **PASSING** — 17 tests in `tests/test_dsl_gate.py`, full §5.3 bad-sentence table |
| P1–P14, P16–P18 | planned |
| Local suite total | **50 passed** (`python -m pytest tests/`) |

### Phase 0 — the workshop (all approved)

- **P0.1** skeleton: 16 folders per guide Part 17.1 (`sentinel/{dsl,intake,checkers,decide,verify}`, `policy/sentinel`, `rules`, `ltl`, `constraints`, `audit`, `gateway`, `board`, `web`, `tests`, `tools`).
- **P0.2** installed into parent `PYTON/.venv`: z3-solver 5.1.0, lark 1.3.1, python-statemachine 3.2.1, pytest 9.1.1.
- **P0.3** `tools/opa.exe` = OPA **1.20.2** (Rego v1) from official GitHub releases.
- **P0.4** SWI-Prolog **10.0.2** x64 via winget. NOTE: `swipl` needs a fresh terminal for PATH; full path `C:\Program Files\swipl\bin\swipl.exe` always works.
- **P0.5** five LAW BOOKS copied verbatim from the guide + `VERSIONS.md` (provenance ledger). Engine-verified: `opa check policy/` OK; `remediation.pl` loads in swipl and answered `risk_level(restart_master_db)=high`.

### Phase 1 — Intake (all approved)

- **P1.1** `sentinel/intake/alerts.py` (mail slot, T1) + `board/incident_machine.py` (game-board skeleton: 18 states, T1–T29 moves; plan says skeleton comes right after Phase 0). 11 tests.
- **P1.2** `sentinel/intake/redactor.py` (black marker, T2, rule L11): masks credentials/bearer/AWS-keys/emails, keeps labels; context filter socket for Datalog's `alert_context` (plug arrives P2.2). 13 tests.
- **P1.3** `sentinel/intake/llm.py`: `LLMInterface` (the costume), `SKETCH_PROMPT` (guide Part 5.4 fill-in form), `MockLLM` with `STORY_SCRIPTS` (Stories 1&2; Story 3 needs no script — its crime is the illegal execute jump, not the text) + 7 `BAD_SCRIPTS` misbehave modes (§5.3 table). 9 tests.
- **P1.4 GATE 1**: `sentinel/dsl/parser.py` (Lark grammar mirroring `remediation.ebnf`), `typecheck.py` (Grounded / Right-kind / Limits / trick-flag), `fingerprint.py` (action_hash = sha256(incident_id ‖ canonical(program) ‖ proposed_at)), `gate.py` (assembly; sends T3 `llm_action_proposed` or T4 `llm_output_invalid` — the AI NEVER sends events). 17 tests = **P15 PASSING**.

### Bugs caught by tests this session (the try-check-learn loop working on us)

1. **Board skeleton refused to load** — `python-statemachine` raised *"unreachable states: blocked, escalated, human_approval_required"*. Happy road alone isn't a legal board; added the NO-road/human-road/retry-road stubs (T6–T28). Lesson: the library proves every square reachable *before the program even runs* — exactly why we chose it.
2. **Bearer-token leak in the redactor** — pattern order was wrong: the general credential pattern masked the word "Bearer" and let the actual token through (`Authorization: ***REDACTED*** eyJhbGci…`). Fix: bearer pattern runs FIRST; comment in the pattern book marks the order as load-bearing.
3. **Vague unknown-verb lesson** — parser's first version returned "breaks the menu rules near column 9" instead of naming `reboot_cluster`. Fixed `_lesson_from` to name the unknown word; the exact lesson is the retry counterexample (rule L10).

### Decisions recorded (do not relitigate)

- Board skeleton built at P1.1 (plan: "right after Phase 0") because P1.1's done-criterion needs a board to move.
- Grammar file lives at `sentinel/dsl/remediation.ebnf` (Python package home); guide's file list says `dsl/remediation.ebnf` — same file, one home, noted at P0.1.
- Parser reads **proposals only**; the `recommendation` branch is AdvisorMachine (T34), not built — we build ONE workflow (IncidentMachine); Advisor exists as parked law only (user asked & understood 2026-09-19).
- `python-statemachine` deprecation warning: `current_state` → `configuration`. Cosmetic; modernize tests someday.

### Workflow protocol reminder (non-negotiable)

Explain with analogy FIRST → build → run done-criterion → 🛑 STOP → wait for "I understand and approve". One step at a time. Resume by step ID (e.g. "we are on P2.1").

---

## How to run everything (quick reference)

```bash
cd "C:\Users\fghw37\Desktop\PYTON\Final AI Archtect PRoj"
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m pytest tests/        # full suite (220)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m pytest tests/test_web.py -v        # P1+P2 (dashboard, real engines)
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m pytest tests/test_dsl_gate.py -v   # P15
./tools/opa.exe check policy/                                                  # Rego syntax
./tools/opa.exe test policy/ -v                                                # official Rego tests (17)
"/c/Program Files/swipl/bin/swipl.exe" -g "consult('rules/remediation.pl'), halt."  # Prolog loads

# The dashboard (run from the PROJECT ROOT, not from web/):
C:/Users/fghw37/Desktop/PYTON/.venv/Scripts/python.exe -m uvicorn web.app:app --port 8000
# then open http://localhost:8000
```
