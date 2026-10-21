"""
tests/test_prolog.py -- step P2.3 done-criterion + P17 Prolog fixtures.

"Scenario 1 from guide Part 10.3 returns prolog_allowed with risk low
 and a proof; the frozen checkout example returns prolog_forbidden with
 why_refused = change_frozen(checkout)."

These tests call the REAL SWI-Prolog engine with the REAL law book.
"""

import pytest

from sentinel.checkers import prolog_adapter
from sentinel.checkers.prolog_adapter import ask_prolog, check_rules
from sentinel.dsl.gate import check_proposal
from sentinel.dsl.parser import parse
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM

NO_FACTS: dict = {}


def program(text):
    return parse(text)


def sealed_incident_at_rule_inference():
    """Story 1 carried through GATE 1, OPA and Datalog to Rule_Inference."""
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-22T11:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(
        inc, MockLLM().propose("alert: al_7f3"),
        {"web_frontend": {"kind": "pod", "revisions": []}},
        {"al_7f3", "lg_0192", "mem_web_p95"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    return inc


# --------------------------------------------- Scenario 1: allowed, low risk
class TestScenario1:
    def test_allowed_low_risk_with_proof(self):
        """Guide 10.3 I/O: confidence [0.72, 0.88], no Datalog facts."""
        prog = program("propose restart_pod(web_frontend) "
                       "because alert(al_7f3) confidence [0.72, 0.88];")
        verdict = ask_prolog(prog, NO_FACTS, NO_FACTS)
        assert verdict.event == "prolog_allowed"
        assert verdict.risk_level == "low"
        assert verdict.proof == ["no high_risk/2 clause holds => risk_level low"]
        assert verdict.why_refused == []

    def test_full_step_moves_board_and_stores_risk(self):
        inc = sealed_incident_at_rule_inference()
        verdict = check_rules(inc, NO_FACTS, NO_FACTS)
        assert verdict.event == "prolog_allowed"
        assert inc.machine.current_state.name == "Temporal_Check"
        assert inc.risk_level == "low"       # the Arbiter reads THIS in P3.1


# ------------------------------------------ the frozen checkout: forbidden
class TestFrozenCheckout:
    def test_forbidden_with_written_reason(self):
        """Guide 10.3 I/O: change_frozen(checkout) -> why_refused names it."""
        prog = program("propose restart_service(checkout) "
                       "because alert(al_frz) confidence [0.8, 0.9];")
        verdict = ask_prolog(
            prog, {"change_frozen": ["checkout"]}, NO_FACTS)
        assert verdict.event == "prolog_forbidden"
        assert verdict.allowed is False
        assert "change_frozen(checkout)" in verdict.why_refused


# ----------------------------------------- the 8 high-risk reasons, one each
class TestHighRiskReasons:
    GOOD = ("propose restart_pod(web_frontend) "
            "because alert(al_7f3) confidence [0.72, 0.88];")

    def risk_of(self, text=GOOD, snapshot=None, datalog=None, rejected=None):
        verdict = ask_prolog(program(text), snapshot or {}, datalog or {},
                             rejected or [])
        assert verdict.event == "prolog_allowed"
        return verdict

    def test_stateful_target(self):
        v = self.risk_of(snapshot={"stateful": ["web_frontend"]})
        assert v.risk_level == "high"
        assert "stateful(web_frontend)" in v.proof

    def test_production_critical_tier(self):
        v = self.risk_of(snapshot={"tier": [("web_frontend",
                                             "production_critical")]})
        assert v.risk_level == "high"

    def test_sensitive_target_from_datalog(self):
        v = self.risk_of(datalog={"sensitive_target": ["web_frontend"]})
        assert v.risk_level == "high"
        assert "sensitive_target(web_frontend)" in v.proof

    def test_critical_in_blast_from_datalog(self):
        v = self.risk_of(datalog={"critical_in_blast": ["auth_service"]})
        assert v.risk_level == "high"
        assert "critical_in_blast(web_frontend,auth_service)" in v.proof

    def test_rollback_is_always_high(self):
        v = self.risk_of("propose rollback(web_frontend, revision=v1) "
                         "because alert(al_7f3) confidence [0.9, 0.95];")
        assert v.risk_level == "high"

    def test_restart_master_db_is_always_high(self):
        v = self.risk_of("propose restart_master_db(web_frontend) "
                         "because alert(al_7f3) confidence [0.9, 0.95];")
        assert v.risk_level == "high"

    def test_low_confidence_lower_bound(self):
        v = self.risk_of("propose restart_pod(web_frontend) "
                         "because alert(al_7f3) confidence [0.55, 0.95];")
        assert v.risk_level == "high"
        assert "low_confidence(0.55)" in v.proof

    def test_rejected_before(self):
        v = self.risk_of(rejected=[("restart_pod", "web_frontend")])
        assert v.risk_level == "high"
        assert "rejected_before" in v.proof


# --------------------------------------------------- destructive + read-only
class TestVerbClasses:
    def test_destructive_verb_forbidden_by_the_judge(self):
        prog = program("propose delete_volume(pv_orders) "
                       "because log(lg_0666) confidence [0.9, 0.99];")
        verdict = ask_prolog(prog, NO_FACTS, NO_FACTS)
        assert verdict.event == "prolog_forbidden"
        assert "destructive(delete_volume)" in verdict.why_refused

    def test_read_only_verb_has_no_risk(self):
        prog = program("propose get_metrics(web_frontend) "
                       "because alert(al_7f3) confidence [0.5, 0.6];")
        verdict = ask_prolog(prog, NO_FACTS, NO_FACTS)
        assert verdict.event == "prolog_allowed"
        assert verdict.risk_level == "none"


# ------------------------------------------------------- T30: fail closed
class TestFailClosed:
    def test_missing_judge_means_no(self, monkeypatch):
        monkeypatch.setattr(prolog_adapter, "_find_swipl", lambda: None)
        inc = sealed_incident_at_rule_inference()
        verdict = check_rules(inc, NO_FACTS, NO_FACTS)
        assert verdict.event == "validation_failed"
        assert "missing" in verdict.checker_error
        assert inc.machine.current_state.name == "Blocked"

    def test_too_slow_means_no(self, monkeypatch):
        import subprocess as sp

        def fake_run(*args, **kwargs):
            raise sp.TimeoutExpired(cmd="swipl", timeout=10)
        monkeypatch.setattr(prolog_adapter.subprocess, "run", fake_run)
        verdict = ask_prolog(program(TestHighRiskReasons.GOOD),
                             NO_FACTS, NO_FACTS)
        assert verdict.event == "validation_failed"
        assert "longer than" in verdict.checker_error

    def test_gibberish_means_no(self, monkeypatch):
        import subprocess as sp

        def fake_run(*args, **kwargs):
            return sp.CompletedProcess(args, 0, stdout="cats", stderr="")
        monkeypatch.setattr(prolog_adapter.subprocess, "run", fake_run)
        verdict = ask_prolog(program(TestHighRiskReasons.GOOD),
                             NO_FACTS, NO_FACTS)
        assert verdict.event == "validation_failed"
        assert "gibberish" in verdict.checker_error
