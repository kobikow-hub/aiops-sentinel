"""
tests/test_routing.py -- step P3.1 done-criterion.

"risk low / high / missing route to autonomous / require_approval /
 require_approval (OPA tests test_route_low, test_route_high,
 test_route_missing)."  The three Rego tests already pass (P2.1, 17/17);
 here we prove the Python station end-to-end, against the real referee.
"""

import pytest

from sentinel.checkers.datalog import Topology, check_dependencies
from sentinel.checkers.prolog_adapter import check_rules
from sentinel.decide import arbiter
from sentinel.decide.arbiter import ask_route, decide_route
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM
from ltl.check import Step, check_temporal


def incident_with_risk(risk_level):
    """A case folder standing at Risk_Assessment with a stored reading."""
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-22T13:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(
        inc, MockLLM().propose("alert: al_7f3"),
        {"web_frontend": {"kind": "pod", "revisions": []}},
        {"al_7f3", "lg_0192", "mem_web_p95"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    if risk_level is not None:
        inc.risk_level = risk_level
    return inc


# --------------------------------------------------- the three routes
class TestThreeRoutes:
    def test_low_routes_autonomous(self):
        inc = incident_with_risk("low")
        decision = decide_route(inc)
        assert decision.event == "risk_low"
        assert decision.route == "autonomous"
        assert inc.machine.current_state.name == "Constraint_Check"

    def test_high_routes_to_a_human(self):
        inc = incident_with_risk("high")
        decision = decide_route(inc)
        assert decision.event == "risk_high"
        assert decision.route == "require_approval"
        assert inc.machine.current_state.name == "Human_Approval_Required"

    def test_missing_risk_routes_to_a_human(self):
        inc = incident_with_risk(None)          # nobody stored a reading
        decision = decide_route(inc)
        assert decision.event == "risk_high"
        assert decision.route == "require_approval"
        assert inc.machine.current_state.name == "Human_Approval_Required"

    def test_unknown_reading_routes_to_a_human(self):
        route, _ = ask_route("apocalyptic")
        assert route == "require_approval"


# ------------------------------------------- unsure => human, never "go"
class TestRouterTrouble:
    def test_missing_referee_routes_to_a_human(self, monkeypatch):
        from sentinel.checkers import opa_adapter
        monkeypatch.setattr(opa_adapter, "OPA_EXE",
                            opa_adapter.OPA_EXE.parent / "nonexistent.exe")
        inc = incident_with_risk("low")          # even a LOW reading!
        decision = decide_route(inc)
        assert decision.event == "risk_high"
        assert "not found" in decision.router_error
        assert inc.machine.current_state.name == "Human_Approval_Required"

    def test_gibberish_routes_to_a_human(self, monkeypatch):
        import subprocess as sp
        from sentinel.checkers import opa_adapter

        def fake_run(*args, **kwargs):
            return sp.CompletedProcess(args, 0, stdout="cats", stderr="")
        monkeypatch.setattr(opa_adapter.subprocess, "run", fake_run)
        route, error = ask_route("low")
        assert route == "require_approval"
        assert "gibberish" in error


# ------------------------------------ the full corridor, wired end-to-end
class TestFullPipelineToRoute:
    """Story 1 from the letter to the route, every station real."""

    def test_story1_low_risk_reaches_constraint_check(self):
        inc = receive_alert({
            "alert_id": "al_7f3", "source": "mock_monitor",
            "service": "web_frontend", "metric": "mem_web_p95",
            "severity": "critical", "timestamp": "2026-09-22T13:00:00Z",
        })
        inc.machine.logs_parsed()                                  # T2
        gate = check_proposal(                                      # T3
            inc, MockLLM().propose("alert: al_7f3"),
            {"web_frontend": {"kind": "pod", "revisions": []}},
            {"al_7f3", "lg_0192", "mem_web_p95"})
        assert gate.event == "llm_action_proposed"

        from sentinel.checkers.opa_adapter import check_policy
        assert check_policy(inc).event == "opa_allowed"             # T5

        topo = Topology.from_dict({
            "depends_on": [], "sensitive": [], "critical": []})
        datalog = check_dependencies(inc, topo)                     # T7
        assert datalog.event == "datalog_clear"

        prolog = check_rules(inc, {}, datalog.facts_for_prolog)     # T9
        assert prolog.event == "prolog_allowed"
        assert inc.risk_level == "low"

        diary = [Step(name=n, action_hash=inc.action_hash)
                 for n in ("llm_action_proposed", "opa_allowed",
                           "datalog_clear", "prolog_allowed")]
        ltl = check_temporal(                                       # T11
            inc, diary,
            planned=["validation_passed", "risk_low", "z3_sat", "execute"])
        assert ltl.event == "validation_passed"

        decision = decide_route(inc)                                # T13
        assert decision.event == "risk_low"
        assert inc.machine.current_state.name == "Constraint_Check"
