# AIOps Sentinel: Architectural Guidelines
### Speed Without Catastrophe

## Slide 1: Executive Thesis
* Structure Over Intelligence: AI intelligence cannot evaluate its own safety.
* Core Spec Files: `dsl/remediation.ebnf` and `audit/trace.schema`.

## Slide 2: The Sentinel Pipeline
* Forward Assembly Line: Intake -> Gate 1 -> OPA -> Datalog -> Prolog -> LTL -> Arbiter -> Z3 -> Gateway -> Verify -> Audit.
* Central State Machine: `board/` (18 states, T1-T30).

## Slide 3: Phase 1 — Intake & Gate 1
* AI Only Suggests: Zero credentials, tiny DSL only.
* Gate 1: Lark parser (`parser.py`) and typecheck (`typecheck.py`) ground entities.
* Fingerprint: Cryptographic `action_hash` (`fingerprint.py`).

## Slide 4: Phase 2 — The Four Checkers
* OPA: Policy guard (`policy/sentinel/authz.rego`).
* Datalog: Blast radius guard (`rules/topology.dl`).
* Prolog: Sole risk authority (`rules/remediation.pl`).
* LTL: Temporal timeline guard (`ltl/rules.py`).

## Slide 5: Prolog — Sole Risk Authority
* One Boss Per Topic: Only Prolog computes risk.
* Written proofs: `why_refused` predicate chains.

## Slide 6: Phase 3 — Deciding & Approvals
* Arbiter: Routes based on Prolog risk (`arbiter.py`).
* Approvals: One-time token bound to `action_hash` (`approval.py`).
* SLA Watchdog: Silence is never consent (`sla_timer.py`).

## Slide 7: Phase 4 — Deploying & Live Math
* Z3 Solver: Evaluates invariants on live snapshot (`constraints/deployment_gate.py`). Math overrides human approval.
* Tool Gateway: Only credentialed actor (`gateway/tool_gateway.py`). Compare-and-execute & idempotency.

## Slide 8: Phase 5 — Verify, Recovery & Audit
* Health Probes: Verify SLIs post-execution (`probe.py`).
* Bounded Recovery: Max 2 retries with lessons (`recovery.py`). Checker NOs never retried.
* Diary: Immutable JSONL ledger (`audit/audit_service.py`).

## Slide 9: State Machine Governance
* 18 states, 30 transitions. Illegal shortcuts are impossible to express (`board/state_machine.py`).

## Slide 10: Checkpoints & Demo Stories
* Checkpoints: Gate 1 first, one risk judge, OPA routes, Z3 on live data.
* Stories: Story 1 (Happy Path), Story 2 (Datalog Veto), Story 3 (Out-of-order LTL Block).