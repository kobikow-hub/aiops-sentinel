"""
web/app.py
==========
The DEMO STAGE (step P5.5): a FastAPI dashboard for the three stories.

THE GUI IS DUMB -- the same iron rule as everywhere: components (and
buttons!) only EMIT EVENTS; the board decides what may happen. This
backend contains no safety logic of its own: every station it calls is
the real, already-tested module (real OPA, real SWI-Prolog, real Z3,
real Gateway, real diary). The frontend only:

    POST /api/story/{n}   ring a doorbell: run demo story n
    POST /api/resolve     the human owner fixed it (Escalated only)
    POST /api/approve     the approval screen's two buttons
    POST /api/reject      (Human_Approval_Required only)
    GET  /api/state       poll: where does the piece stand NOW?
    GET  /api/diary       read the append-only minutes back

The three stories are the guide's locked scope (Part 13):
    1  it works       restart web_frontend, low risk, no human
    2  stopped        restart master_db, 40 dependents >= limit 10
    3  wrong order    'execute' right after the proposal -- the live
                      LTL guard refuses (rule L1); the refusal is shown
"""

import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from audit.audit_service import open_diary
from constraints.deployment_gate import check_constraints
from gateway.mockdriver import MockDriver
from gateway.system_map import demo_map
from gateway.tool_gateway import check_and_execute
from ltl.check import Step, check_temporal, live_guard
from sentinel.checkers.datalog import Topology, check_dependencies
from sentinel.checkers.opa_adapter import check_policy
from sentinel.checkers.prolog_adapter import check_rules
from sentinel.decide.approval import issue_token, submit_decision
from sentinel.decide.arbiter import decide_route
from sentinel.decide.sla_timer import SlaTimer
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM, build_prompt
from sentinel.intake.redactor import parse_logs
from sentinel.dsl.gate import check_proposal
from sentinel.verify.escalation import (ConsoleNotifier, escalate,
                                        notify_escalated,
                                        record_human_resolution)
from sentinel.verify.probe import probe_health

app = FastAPI(title="AIOps Sentinel — Demo Stage")

STORY_DELAY = 0.7          # seconds between stages (tests set this to 0)
APPROVAL_SLA_SECONDS = 30  # demo POC: 30s to answer, then escalation (L4)
_TEMPLATES = Path(__file__).parent / "templates"
_DIARY_DIR = Path(tempfile.mkdtemp(prefix="sentinel_diaries_"))

# The tracker's fixed stations: label + the exact engine file running,
# plus "refs" -- where each station is called and referenced across the
# repo. Clicking a tracker box in the UI opens this map and highlights
# the station's own lines in the diary. Static truth about the codebase
# (the GUI stays dumb: it renders this, it never derives it).
PIPELINE_STEPS = [
    {"key": "intake",  "label": "Intake",
     "engine": "sentinel/intake/alerts.py + redactor.py",
     "summary": "The mail slot + black marker: verify the alert's shape and sender, open the case folder, and strip every secret before any text can reach the AI.",
     "refs": {
         "called_by": ["web/app.py · _common_intake() — receive_alert(), parse_logs()"],
         "law": ["audit/trace.schema — alert_received: UUID born here",
                 "Rule L11 — secrets never reach the AI (redactor)"],
         "board_moves": "T1 (alert_received), T2 (logs_parsed)",
         "tests": ["tests/test_intake.py (11)", "tests/test_redactor.py (13)"],
         "diary_events": ["alert_received", "logs_parsed"],
     }},
    {"key": "ai",      "label": "AI Propose",
     "engine": "sentinel/intake/llm.py (MockLLM)",
     "summary": "The student actor fills the strict order form: ONE suggestion in the tiny DSL — plain text with zero power, zero credentials, zero events.",
     "refs": {
         "called_by": ["web/app.py · _common_intake() — build_prompt(), MockLLM.propose()"],
         "law": ["guide Part 5.4 — the sketch prompt (?? holes from checker lists)",
                 "THE AI SENDS NO EVENTS and has NO diary voice at all"],
         "board_moves": "none — text only; Gate 1 judges it",
         "tests": ["tests/test_llm.py (9)"],
         "diary_events": [],
     }},
    {"key": "gate1",   "label": "Gate 1",
     "engine": "sentinel/dsl/gate.py",
     "summary": "The menu check: parse the sentence, verify every name is real and every number in range, then press the wax seal (action_hash) — or send it back with the exact lesson.",
     "refs": {
         "called_by": ["web/app.py · _common_intake() — check_proposal()",
                       "parser.py + typecheck.py + fingerprint.py assembled here"],
         "law": ["sentinel/dsl/remediation.ebnf — the menu (verbatim spec)"],
         "board_moves": "T3 (llm_action_proposed), T4 (llm_output_invalid)",
         "tests": ["tests/test_dsl_gate.py (17) = official test P15"],
         "diary_events": ["llm_action_proposed", "llm_output_invalid"],
     }},
    {"key": "opa",     "label": "OPA",
     "engine": "sentinel/checkers/opa_adapter.py",
     "summary": "The school rule book: banned verbs, change freezes and closed windows get a flat NO — before anyone studies the details. Broken referee = NO (fail closed).",
     "refs": {
         "called_by": ["web/app.py · _run_story() — check_policy()",
                       "sentinel/decide/arbiter.py — eval_opa() for the route",
                       "sentinel/decide/approval.py — eval_opa() for the slip check"],
         "law": ["policy/sentinel/authz.rego — the rule book (verbatim spec)",
                 "runs the real tools/opa.exe (1.20.2) as a subprocess"],
         "board_moves": "T5 (opa_allowed), T6 (opa_denied), T30 (fail closed)",
         "tests": ["tests/test_opa_adapter.py (11)",
                   "policy/sentinel/authz_test.rego (17/17 via opa test)"],
         "diary_events": ["opa_allowed", "opa_denied"],
     }},
    {"key": "datalog", "label": "Datalog",
     "engine": "sentinel/checkers/datalog.py",
     "summary": "The domino expert: follows every dependency chain and counts who falls. 10+ victims or a secret-leak road = hard veto; two facts are handed forward to the judge.",
     "refs": {
         "called_by": ["web/app.py · _run_story() — check_dependencies()",
                       "sentinel/intake/redactor.py — alert_context fills allowed_services",
                       "hands facts forward to Prolog (sensitive_target, critical_in_blast)"],
         "law": ["rules/topology.dl — the official Soufflé spec this module mirrors"],
         "board_moves": "T7 (datalog_clear), T8 (datalog_sensitive_path)",
         "tests": ["tests/test_datalog.py (16)"],
         "diary_events": ["datalog_clear", "datalog_sensitive_path"],
     }},
    {"key": "prolog",  "label": "Prolog",
     "engine": "sentinel/checkers/prolog_adapter.py",
     "summary": "The logic judge: permitted or not, and low or high risk — the ONLY risk verdict in the whole system, always delivered with a written proof.",
     "refs": {
         "called_by": ["web/app.py · _run_story() — check_rules()",
                       "stores incident.risk_level — the Arbiter READS it, never recomputes"],
         "law": ["rules/remediation.pl — the judge's law (verbatim spec)",
                 "runs the real SWI-Prolog (swipl.exe) per case",
                 "checkpoint (b): the ONLY component that computes risk"],
         "board_moves": "T9 (prolog_allowed), T10 (prolog_forbidden)",
         "tests": ["tests/test_prolog.py (16)"],
         "diary_events": ["prolog_allowed", "prolog_forbidden"],
     }},
    {"key": "ltl",     "label": "LTL",
     "engine": "ltl/check.py",
     "summary": "The time-order guard: each step can look fine while the SEQUENCE is a crime. Rules L1–L15 check the diary as a story — 'always check BEFORE you act'.",
     "refs": {
         "called_by": ["web/app.py · _run_story() — check_temporal() (look-ahead)",
                       "web/app.py · story 3 — live_guard() refuses the bad event",
                       "audit/audit_service.py · close() — check_full_trace() before T29"],
         "law": ["ltl/rules.py — the time rules L1–L15 with scopes"],
         "board_moves": "T11 (validation_passed), T12 (temporal_violation)",
         "tests": ["tests/test_ltl.py (13)"],
         "diary_events": ["validation_passed", "temporal_violation"],
     }},
    {"key": "route",   "label": "Route",
     "engine": "sentinel/decide/arbiter.py",
     "summary": "The teacher at the fork: reads the judge's thermometer, looks up the policy, and sends exactly one event — go alone (low) or call a human (high/unsure).",
     "refs": {
         "called_by": ["web/app.py · _run_story() — decide_route()"],
         "law": ["reads incident.risk_level (Prolog's stored verdict)",
                 "asks OPA's one-line route rule — checkpoint (c): maps, never re-decides",
                 "unsure/broken ⇒ require_approval (a human, never 'go')"],
         "board_moves": "T13 (risk_low), T14 (risk_high)",
         "tests": ["tests/test_routing.py (7)"],
         "diary_events": ["risk_low", "risk_high"],
     }},
    {"key": "z3",      "label": "Z3",
     "engine": "constraints/deployment_gate.py",
     "summary": "The last look out the window: live photo, simple math (before → effect → after). Its unsat outranks even a human's YES — the human approved the idea, not the world.",
     "refs": {
         "called_by": ["web/app.py · _run_story() — check_constraints()",
                       "pins incident.snapshot_version — the Gateway compares it"],
         "law": ["EFFECTS table = the DSL rule book (guide 5.2) — never the AI's words",
                 "checkpoint (d): runs LAST, on a live photo, after all approvals"],
         "board_moves": "T18 (z3_sat), T19 (z3_unsat), T30 (fail closed)",
         "tests": ["tests/test_z3_gate.py (9)"],
         "diary_events": ["z3_sat", "z3_unsat"],
     }},
    {"key": "gateway", "label": "Gateway",
     "engine": "gateway/tool_gateway.py",
     "summary": "The bus driver with the only keys — and zero judgment: same world version? right papers? never acted before? Then drive exactly what was sealed; on silence, reconcile first.",
     "refs": {
         "called_by": ["web/app.py · _run_story() — check_and_execute()",
                       "drives gateway/mockdriver.py against gateway/system_map.py"],
         "law": ["the ONLY component with credentials — and zero judgment",
                 "compare-and-execute · idempotency by action_hash · reconcile-on-timeout"],
         "board_moves": "T20 (execute), T21 (execution_succeeded), T22 (execution_failed)",
         "tests": ["tests/test_gateway.py (10)", "tests/test_mockdriver.py (11)"],
         "diary_events": ["execute", "execution_succeeded", "execution_failed"],
     }},
    {"key": "probe",   "label": "Probe",
     "engine": "sentinel/verify/probe.py",
     "summary": "The doctor takes your temperature AGAIN after the pill: alert gone and numbers healthy, or back to Recovery with the failing numbers as the lesson.",
     "refs": {
         "called_by": ["web/app.py · _run_story() — probe_health()",
                       "a bad reading feeds sentinel/verify/recovery.py (lesson + retry ≤ 2)"],
         "law": ["reads the LIVE world, never the receipt — 'ran' ≠ 'well'"],
         "board_moves": "T23 (metrics_healthy), T24 (metrics_still_degraded)",
         "tests": ["tests/test_probe.py (6)"],
         "diary_events": ["metrics_healthy", "metrics_still_degraded"],
     }},
    {"key": "diary",   "label": "Diary",
     "engine": "audit/audit_service.py",
     "summary": "The minutes in pen: every event appended, never erased; the meeting only ends after the whole diary is read back against all time rules — the ONLY road to Incident_Resolved.",
     "refs": {
         "called_by": ["web/app.py — open_diary() at intake; every station appends its own line",
                       "web/app.py · /api/resolve — close() after human resolution"],
         "law": ["audit/trace.schema — 30-name vocabulary, authorized voices, phases",
                 "close() re-checks ALL of L1–L15 (rule L7: the only road to resolved)"],
         "board_moves": "T29 (audit_log_created) → Incident_Resolved",
         "tests": ["tests/test_audit.py (11) = official tests P5 + P12"],
         "diary_events": ["audit_log_created"],
     }},
]

STORY_ALERTS = {
    1: {"alert_id": "al_7f3", "service": "web_frontend",
        "metric": "mem_web_p95",
        "logs": ["web_frontend: OOMKilled, restarting (lg_0192)"]},
    2: {"alert_id": "al_9c1", "service": "master_db",
        "metric": "db_conn_errors",
        "logs": ["master_db: connection errors rising (lg_0201)"]},
    3: {"alert_id": "al_7f3", "service": "web_frontend",
        "metric": "mem_web_p95",
        "logs": ["web_frontend: OOMKilled, restarting (lg_0192)"]},
}

EVIDENCE = {"al_7f3", "lg_0192", "mem_web_p95", "al_9c1", "lg_0201",
            "db_conn_errors"}


def story1_topology() -> Topology:
    """Scenario 1's world (guide Part 10.3 I/O: "no Datalog facts
    derived for web_frontend") -- the pod is a clean leaf: nobody
    depends on it and it touches no sensitive chain. The backend's
    other services still exist, just not wired through the target."""
    return Topology.from_dict({
        "depends_on": [["auth_service", "master_db"],
                       ["checkout", "master_db"]],
        "sensitive": ["master_db"],
        "critical": ["auth_service"],
    })


def story2_topology() -> Topology:
    """Scenario 2's world: 40 services depend on master_db, limit 10."""
    return Topology.from_dict({
        "depends_on": [[f"svc_{i:02d}", "master_db"] for i in range(40)],
        "sensitive": ["master_db"],
        "blast_radius_limit": 10,
    })


class Run:
    """One demo run: the piece, its diary, and what the audience sees."""

    def __init__(self, story: int, high_risk: bool = False):
        self.story = story
        self.high_risk = high_risk    # Story-1 variant: stateful target
        self.status = "running"       # running | waiting_human | finished | error
        self.active_step: str | None = None
        self.engine: str | None = None
        self.timeline: list[dict] = []
        self.trace: list[dict] = []   # every board transition, in order
        self.refusal: dict | None = None
        self.escalation_packet: dict | None = None
        self.approval_packet: dict | None = None
        self.approval_deadline: float | None = None   # epoch secs (SLA)
        self.sla_timer: SlaTimer | None = None
        self.last_transition: str | None = None
        self.error: str | None = None
        self.incident = None
        self.diary = None
        self.world = None
        self.token = None
        self.lock = threading.Lock()

    def watch_board(self):
        """Record every transition the board makes (state + move), by
        listening to the machine -- the GUI renders this trace, it never
        derives it."""
        run = self

        class _Recorder:
            def on_transition(self, event, source, target, **kwargs):
                with run.lock:
                    run.trace.append({"event": event,
                                      "from": source.name,
                                      "to": target.name})
                    run.last_transition = f"{source.name} —{event}→ {target.name}"

        self.incident.machine.add_listener(_Recorder())

    # ------------------------------------------------ audience updates
    def stage(self, key: str, detail: str = ""):
        step = next(s for s in PIPELINE_STEPS if s["key"] == key)
        with self.lock:
            self.active_step = key
            self.engine = step["engine"]
            self.timeline.append({"step": key, "label": step["label"],
                                  "engine": step["engine"],
                                  "detail": detail})
        time.sleep(STORY_DELAY)

    def note(self, detail: str):
        with self.lock:
            if self.timeline:
                self.timeline[-1]["detail"] = detail

    def snapshot(self) -> dict:
        with self.lock:
            state = (self.incident.machine.current_state.name
                     if self.incident else None)
            seconds_left = None
            if self.approval_deadline is not None \
                    and self.status == "waiting_human":
                seconds_left = max(0, round(self.approval_deadline
                                            - time.time()))
            return {
                "story": self.story, "status": self.status,
                "current_state": state,
                "last_transition": self.last_transition,
                "trace": list(self.trace),
                "active_step": self.active_step, "engine": self.engine,
                "timeline": list(self.timeline),
                "refusal": self.refusal,
                "escalation_packet": self.escalation_packet,
                "approval_packet": self.approval_packet,
                "approval_seconds_left": seconds_left,
                "approval_sla_seconds": APPROVAL_SLA_SECONDS,
                "error": self.error,
                "steps": PIPELINE_STEPS,
            }


CURRENT: Run | None = None


# ---------------------------------------------------------------------------
# The story runners -- every station is the real module. The runner is a
# NARRATOR, not a decider: it calls each station and writes the diary
# line each component is authorized to claim.
# ---------------------------------------------------------------------------
def _common_intake(run: Run, story: int):
    spec = STORY_ALERTS[story]
    run.stage("intake", f"alert {spec['alert_id']} from mock_monitor")
    incident = receive_alert({
        "alert_id": spec["alert_id"], "source": "mock_monitor",
        "service": spec["service"], "metric": spec["metric"],
        "severity": "critical", "timestamp": "2026-09-26T12:00:00Z",
    })
    run.incident = incident
    run.watch_board()          # record every transition from here on
    run.trace.append({"event": "alert_received",
                      "from": "Awaiting_Alert", "to": "Alert_Parsed"})
    run.last_transition = "Awaiting_Alert —alert_received→ Alert_Parsed"
    run.diary = open_diary(incident, _DIARY_DIR)
    run.diary.append("alert_received", "intake",
                     payload={"alert_id": spec["alert_id"]})

    logs_event = parse_logs(incident, spec["logs"])
    run.diary.append("logs_parsed", "redactor",
                     payload=logs_event["payload"])
    run.note(f"redaction_applied={logs_event['payload']['Redaction_Applied']}")

    run.stage("ai", "MockLLM fills the sketch prompt")
    prompt = build_prompt(
        {"alert_id": spec["alert_id"], "service": spec["service"],
         "metric": spec["metric"]},
        incident.safe_logs,
        verbs=["restart_pod", "restart_service", "scale_out", "rollback",
               "restart_master_db", "list_services", "get_metrics"],
        targets=[spec["service"]])
    text = MockLLM().propose(prompt)
    run.note(text.replace("\n", " "))

    run.stage("gate1", "parse + typecheck + wax seal")
    gate = check_proposal(incident, text, run.world.snapshot_for_gate1(),
                          EVIDENCE)
    if gate.event != "llm_action_proposed":
        raise RuntimeError(f"gate refused the scripted story: {gate.lesson}")
    run.diary.append("llm_action_proposed", "gate1", incident.action_hash,
                     payload={"verb": gate.program.verb,
                              "target": gate.program.target,
                              "dsl_valid": True})
    run.note(f"sealed {incident.action_hash[:23]}…")


def _run_story(run: Run):
    try:
        run.world = demo_map()
        if run.high_risk:
            # The 1b demo lever: mark the target STATEFUL in the world's
            # photo. Prolog (the ONLY risk judge) reads the fact and rules
            # HIGH -- we never set the risk ourselves, we change the WORLD
            # and let the judge judge. Everything after (the alarm, the
            # 30s SLA countdown, timeout -> Escalated) is the real path.
            run.world.services[STORY_ALERTS[run.story]["service"]] \
                .stateful = True
        incident = None
        _common_intake(run, run.story)
        incident = run.incident

        if run.story == 3:
            # Story 3: something tries to EXECUTE right after the
            # proposal. The live guard refuses; the board never moves.
            run.stage("ltl", "live guard: may 'execute' happen NOW?")
            verdict = live_guard(run.diary.as_steps(),
                                 Step(name="execute",
                                      action_hash=incident.action_hash))
            # name exactly which of L1's five yes-flags are missing for
            # THIS fingerprint (guide 13.4: "none of them are there")
            from ltl.rules import CHECK_FLAGS
            present = {s.name for s in run.diary.as_steps()
                       if s.action_hash == incident.action_hash}
            run.refusal = {
                "violated_rule": verdict.violated_rule,
                "in_simple_words": verdict.simple,
                "last_diary_steps": verdict.last_steps,
                "required_approvals": list(CHECK_FLAGS),
                "missing_approvals": [f for f in CHECK_FLAGS
                                      if f not in present],
            }
            run.note(f"REFUSED by rule {verdict.violated_rule}")
            run.status = "finished"
            return

        run.stage("opa", "the rule book: banned? frozen? in window?")
        opa = check_policy(incident)
        run.diary.append(opa.event, "opa", incident.action_hash,
                         payload={"deny": opa.deny})
        if opa.event != "opa_allowed":
            raise RuntimeError(f"unexpected OPA verdict: {opa.event}")

        run.stage("datalog", "counting the dominoes")
        topo = (story2_topology() if run.story == 2
                else story1_topology())
        datalog = check_dependencies(incident, topo)
        run.diary.append(datalog.event, "datalog", incident.action_hash,
                         payload={"reason": datalog.reason,
                                  "dependents": datalog.dependents})

        if datalog.event == "datalog_sensitive_path":
            run.note(f"VETO: {datalog.dependents} dependents >= limit 10")
            notifier = ConsoleNotifier()
            record = escalate(incident, notifier, trigger="checker_no",
                              datalog_verdict=datalog)
            run.diary.append("escalation_notified", "notifier",
                             incident.action_hash,
                             payload={"trigger": "checker_no"})
            run.escalation_packet = record.packet
            run.status = "waiting_human"        # a person must own it
            return

        run.note(f"clear: {datalog.dependents} dependents")

        run.stage("prolog", "the judge: permitted? how risky? why?")
        prolog = check_rules(incident, run.world.snapshot_facts_for_prolog(),
                             datalog.facts_for_prolog)
        run.diary.append(prolog.event, "prolog", incident.action_hash,
                         payload={"risk_level": prolog.risk_level,
                                  "proof": prolog.proof})
        run.note(f"risk={prolog.risk_level}; proof: {'; '.join(prolog.proof)}")

        run.stage("ltl", "look-ahead: would the planned order break a rule?")
        ltl = check_temporal(incident, run.diary.as_steps(),
                             planned=["validation_passed", "risk_low",
                                      "z3_sat", "execute"])
        run.diary.append(ltl.event, "ltl", incident.action_hash)

        run.stage("route", "risk becomes a route (never recomputed)")
        route = decide_route(incident)
        run.diary.append(route.event, "arbiter", incident.action_hash,
                         payload={"route": route.route})

        if route.event == "risk_high":
            from sentinel.decide.approval import review_packet
            run.approval_packet = review_packet(
                incident, datalog_verdict=datalog, prolog_verdict=prolog,
                route_decision=route)
            run.status = "waiting_human"
            _start_sla_watchdog(run)      # 30s to answer, then L4
            return

        _deploy_and_close(run)

    except Exception as exc:                      # pragma: no cover
        run.error = f"{type(exc).__name__}: {exc}"
        run.status = "error"


def _deploy_and_close(run: Run, approval_token=None):
    """The pipeline's tail (Z3 -> Gateway -> probe -> diary). Runs for
    low-risk directly, and AGAIN after a human approval -- the yes is
    about the idea; Z3 still checks the world (rule L9). The approval
    slip (if any) travels along: the Gateway re-verifies the papers."""
    incident = run.incident
    try:
        run.stage("z3", "the last look, on the live photo")
        z3v = check_constraints(
            incident, run.world.live_snapshot_for_z3(
                incident.program.target))
        run.diary.append(z3v.event, "z3", incident.action_hash,
                         payload={"numbers": z3v.numbers,
                                  "snapshot_version": z3v.snapshot_version})
        run.note(f"{z3v.event}: {z3v.numbers}")

        run.stage("gateway", "papers → compare → idempotency → drive")
        run.diary.append("execute", "gateway", incident.action_hash)
        result = check_and_execute(incident, MockDriver(run.world),
                                   approval_token=approval_token)
        run.diary.append(result.event, "gateway", incident.action_hash,
                         payload={"reason": result.reason})
        if result.event != "execution_succeeded":
            raise RuntimeError(f"gateway: {result.reason}")

        run.stage("probe", "the doctor takes the temperature again")
        probe = probe_health(incident, run.world, alert_active=False)
        run.diary.append(probe.event, "probe", incident.action_hash,
                         payload={"checks": {k: list(v) for k, v
                                             in probe.checks.items()}})

        run.stage("diary", "reading the minutes back (L1–L15)")
        run.diary.close(incident,
                        world={"final_state": "Incident_Resolved"})
        run.status = "finished"

    except Exception as exc:                      # pragma: no cover
        run.error = f"{type(exc).__name__}: {exc}"
        run.status = "error"


def _start_sla_watchdog(run: Run):
    """The clock at the approval door: APPROVAL_SLA_SECONDS to answer.
    Unanswered -> approval_timeout (T17) -> Escalated + the doorbell
    (rule L4: silence is never consent -- and never ignored)."""
    run.sla_timer = SlaTimer.start(run.incident,
                                   sla_minutes=APPROVAL_SLA_SECONDS / 60)
    run.approval_deadline = time.time() + APPROVAL_SLA_SECONDS

    def watchdog():
        while True:
            time.sleep(0.25)
            with run.lock:
                if run.status != "waiting_human":
                    return                        # somebody answered
            if run.sla_timer.check() == "approval_timeout":
                run.diary.append("approval_timeout", "sla_timer",
                                 run.incident.action_hash,
                                 payload={"sla_seconds": APPROVAL_SLA_SECONDS})
                record = notify_escalated(
                    run.incident, ConsoleNotifier(),
                    trigger="approval_timeout")
                run.diary.append("escalation_notified", "notifier",
                                 run.incident.action_hash,
                                 payload={"trigger": "approval_timeout"})
                with run.lock:
                    run.approval_packet = None
                    run.approval_deadline = None
                    run.escalation_packet = record.packet
                return                            # still waiting_human:
                                                  # now for an OWNER (T28)

    threading.Thread(target=watchdog, daemon=True).start()


# ---------------------------------------------------------------------------
# The doorbells.
# ---------------------------------------------------------------------------
class Resolution(BaseModel):
    resolved_by: str
    note: str


class Decision(BaseModel):
    approver_id: str = "dana"
    approver_role: str = "sre"


@app.get("/")
def index():
    return FileResponse(_TEMPLATES / "index.html")


@app.post("/api/story/{story}")
def start_story(story: int, high_risk: bool = False):
    """high_risk=true is Story 1's HIGH-RISK VARIANT (not a 4th story):
    the same alert and sentence, but the target is stateful in the
    world's photo -- so Prolog rules HIGH and the pipeline pauses at
    the approval alarm (approve / reject / let the 30s SLA expire)."""
    global CURRENT
    if story not in (1, 2, 3):
        raise HTTPException(404, "only stories 1, 2 and 3 exist "
                                 "(scope locked by the teacher)")
    if high_risk and story != 1:
        raise HTTPException(400, "the high-risk variant exists only "
                                 "for story 1")
    if CURRENT is not None and CURRENT.status == "running":
        raise HTTPException(409, "a story is already running")
    CURRENT = Run(story, high_risk=high_risk)
    threading.Thread(target=_run_story, args=(CURRENT,), daemon=True).start()
    return {"started": story, "high_risk": high_risk}


@app.get("/api/state")
def state():
    if CURRENT is None:
        return {"status": "idle", "steps": PIPELINE_STEPS}
    return CURRENT.snapshot()


@app.get("/api/diary")
def diary():
    if CURRENT is None or CURRENT.diary is None:
        return JSONResponse([])
    return JSONResponse(CURRENT.diary.read_all())


# ------------------------------------------------------------------
# Read-only source viewer for the lightbox. STRICTLY read-only and
# allowlisted: only real project source files may be fetched -- never
# an absolute path, never a parent-directory escape, never secrets.
# ------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VIEWABLE_SUFFIXES = {".py", ".rego", ".dl", ".pl", ".ebnf", ".schema",
                      ".html", ".md"}


_TREE_SKIP = {"__pycache__", ".git", ".pytest_cache", ".venv", "tools"}

# One-line explanation per directory and per file (shown in the tree).
_TREE_NOTES = {
    # ---------------------------------------------------- directories
    "audit":     "the append-only diary: nothing closes without it",
    "board":     "the game board: 18 states, moves T1–T30 — the only boss",
    "constraints": "Z3, the last gate: live-photo math before acting",
    "gateway":   "the ONLY component with keys + the model railway",
    "ltl":       "the time rules L1–L15: the ORDER of steps is checked",
    "policy":    "OPA's law: the company rule book (Rego)",
    "rules":     "law books for Datalog (spec) and Prolog (the judge)",
    "sentinel":  "the main package: intake → DSL gate → checkers → decide → verify",
    "sentinel/checkers": "guards 1–3: OPA, Datalog, Prolog adapters",
    "sentinel/decide":   "phase 3: risk route, approval slips, SLA timer",
    "sentinel/dsl":      "GATE 1: grammar, types, wax seal",
    "sentinel/intake":   "phase 1: mail slot, redactor, the (mock) AI",
    "sentinel/verify":   "phase 5: probe, bounded retries, escalation",
    "tests":     "220 passing tests — every claim proven by a run",
    "web":       "this dashboard: dumb GUI, buttons only ring doorbells",
    # ---------------------------------------------------------- files
    "audit/audit_service.py": "the diary: append-only JSONL + the T29 close ritual",
    "audit/trace.schema": "the diary's law: format + 30-name vocabulary (verbatim spec)",
    "board/incident_machine.py": "IncidentMachine: every legal square and move",
    "constraints/deployment_gate.py": "Z3 gate: before → effect → after, named unsat cores",
    "gateway/mockdriver.py": "toy trains: success/refuse/fail/timeout on command",
    "gateway/system_map.py": "the pretend world with a version heartbeat",
    "gateway/tool_gateway.py": "compare-and-execute, idempotency, reconcile-on-timeout",
    "ltl/check.py": "the scoped evaluator: look-ahead, live guard, full-trace",
    "ltl/rules.py": "rules L1–L15 with scopes (action/incident/episode)",
    "policy/sentinel/authz.rego": "OPA law: permission, route, approval checks (verbatim spec)",
    "policy/sentinel/authz_test.rego": "17/17 official rule tests, run by opa test",
    "rules/remediation.pl": "the judge's law: permission + the ONLY risk rules (verbatim spec)",
    "rules/topology.dl": "the domino spec our Python Datalog mirrors (verbatim spec)",
    "sentinel/checkers/datalog.py": "who breaks? blast radius, secret flows, the veto",
    "sentinel/checkers/opa_adapter.py": "messenger to opa.exe — fail closed",
    "sentinel/checkers/prolog_adapter.py": "messenger to swipl — verdicts with proofs",
    "sentinel/decide/approval.py": "one-time slips bound to one exact fingerprint",
    "sentinel/decide/arbiter.py": "reads Prolog's risk, asks OPA the route — never recomputes",
    "sentinel/decide/sla_timer.py": "waiting always ends: yes, no, or timeout → escalate",
    "sentinel/dsl/fingerprint.py": "the wax seal: sha256 action_hash",
    "sentinel/dsl/gate.py": "GATE 1 assembled: sends T3/T4 — the AI never does",
    "sentinel/dsl/parser.py": "the menu reader (Lark) — no quoted text exists",
    "sentinel/dsl/remediation.ebnf": "the DSL grammar — the menu itself (verbatim spec)",
    "sentinel/dsl/typecheck.py": "grounded, right kind, limits, trick flag",
    "sentinel/intake/alerts.py": "the mail slot: envelope checks, case folder, T1",
    "sentinel/intake/llm.py": "the pretend AI: scripted stories + deliberate flubs",
    "sentinel/intake/redactor.py": "the black marker: secrets never reach the AI (L11)",
    "sentinel/verify/escalation.py": "the honest handover: checkers' own words to a human",
    "sentinel/verify/probe.py": "the doctor re-takes the temperature after the pill",
    "sentinel/verify/recovery.py": "MAX_RETRIES=2, lessons attached, NOs never retried",
    "web/app.py": "this backend: doorbell endpoints wired to the real pipeline",
    "web/templates/index.html": "the dumb frontend: renders state, rings doorbells",
    "CLAUDE.md": "the project guide for future sessions",
    "MEMENTO.md": "the progress log: what was built, broke, and decided",
    "CODE_WALKTHROUGH.md": "plain-words explanation of every file (study companion)",
    "VERSIONS.md": "provenance ledger: every law book's source and date",
    "generate_dev_plan.py": "builds the development-plan PDF (the machine-readable plan)",
}


@app.get("/api/tree")
def tree():
    """The project's file structure as an indented tree (source only)."""
    lines: list[str] = []

    def walk(folder: Path, prefix: str):
        entries = sorted(folder.iterdir(),
                         key=lambda e: (e.is_file(), e.name.lower()))
        entries = [e for e in entries if e.name not in _TREE_SKIP
                   and not e.name.startswith(".")
                   and (e.is_dir() or e.suffix in _VIEWABLE_SUFFIXES)]
        for i, entry in enumerate(entries):
            last = i == len(entries) - 1
            branch = "└── " if last else "├── "
            rel = str(entry.relative_to(_PROJECT_ROOT)).replace("\\", "/")
            note = _TREE_NOTES.get(rel, "")
            if entry.is_dir():
                lines.append(f"{prefix}{branch}{entry.name}/"
                             + (f"  ~· {note}" if note else ""))
                walk(entry, prefix + ("    " if last else "│   "))
            else:
                # name shown, full path carried for the lightbox link
                lines.append(f"{prefix}{branch}@[{entry.name}|{rel}]"
                             + (f"  ~· {note}" if note else ""))
    walk(_PROJECT_ROOT, "")
    return {"tree": "\n".join(lines)}


@app.get("/api/source")
def source(path: str):
    """Return one project file's text for the lightbox viewer."""
    candidate = (_PROJECT_ROOT / path).resolve()
    try:
        relative = candidate.relative_to(_PROJECT_ROOT)
    except ValueError:
        raise HTTPException(403, "only project files may be viewed")
    if candidate.suffix not in _VIEWABLE_SUFFIXES:
        raise HTTPException(403, f"'{candidate.suffix}' files are not viewable")
    if not candidate.is_file():
        raise HTTPException(404, f"no such file: {relative}")
    return {"path": str(relative).replace("\\", "/"),
            "content": candidate.read_text(encoding="utf-8")}


@app.post("/api/resolve")
def resolve(res: Resolution):
    """The human owner says the PROBLEM ITSELF is fixed (T28)."""
    run = CURRENT
    if run is None or run.status != "waiting_human" \
            or run.escalation_packet is None:
        raise HTTPException(409, "nothing is waiting for a human owner")
    record_human_resolution(run.incident, res.resolved_by, res.note)
    run.diary.append("human_resolution_recorded", "escalation_desk",
                     run.incident.action_hash,
                     payload={"resolved_by": res.resolved_by,
                              "note": res.note})
    run.stage("diary", "reading the minutes back (L1–L15)")
    run.diary.close(run.incident,
                    world={"final_state": "Incident_Resolved"})
    run.status = "finished"
    return {"state": run.incident.machine.current_state.name}


def _human_decision(decision: str, body: Decision):
    """Approve/Reject at Human_Approval_Required -- one shared desk.
    Returns (outcome, token): the spent slip still proves WHICH exact
    action was signed -- the Gateway re-checks its fingerprint."""
    run = CURRENT
    if run is None or run.status != "waiting_human" \
            or run.approval_packet is None:
        raise HTTPException(409, "nothing is waiting for approval")
    token = issue_token(run.incident, body.approver_id, body.approver_role)
    outcome = submit_decision(run.incident, token, decision)
    if outcome.event is None:
        raise HTTPException(403, "; ".join(outcome.reasons))
    run.diary.append(outcome.event, "approval_service",
                     run.incident.action_hash,
                     payload={"approver": body.approver_id})
    return outcome, token


@app.post("/api/approve")
def approve(body: Decision):
    """A valid YES: the idea may proceed -- and the pipeline CONTINUES
    (Z3 on the live photo, Gateway, probe, diary). The yes approved the
    idea, not the world; Z3 still checks (rule L9)."""
    run = CURRENT
    outcome, token = _human_decision("approve", body)
    with run.lock:
        run.approval_packet = None
        run.approval_deadline = None
        run.status = "running"
    threading.Thread(target=_deploy_and_close, args=(run, token),
                     daemon=True).start()
    return {"event": outcome.event}


@app.post("/api/reject")
def reject(body: Decision):
    """A valid NO: Blocked (remembered as rejected_before) -- and the
    doorbell rings so a human OWNER takes the incident (T27)."""
    run = CURRENT
    outcome, _token = _human_decision("reject", body)
    record = escalate(run.incident, ConsoleNotifier(),
                      trigger="checker_no")
    run.diary.append("escalation_notified", "notifier",
                     run.incident.action_hash,
                     payload={"trigger": "human_rejected"})
    with run.lock:
        run.approval_packet = None
        run.approval_deadline = None
        run.escalation_packet = record.packet   # stays waiting_human: T28
    return {"event": outcome.event}
