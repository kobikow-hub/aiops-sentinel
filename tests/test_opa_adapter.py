"""
tests/test_opa_adapter.py -- step P2.1 done-criterion.

"'opa test policy/ -v' passes all tests from the guide's table
 [17/17, run separately]; a banned verb yields opa_denied with the ban
 reason."  Plus the T30 fail-closed proofs.

These tests call the REAL opa.exe -- the same referee production uses.
"""

import pytest

from sentinel.checkers import opa_adapter
from sentinel.checkers.opa_adapter import build_input, check_policy
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM

SNAPSHOT = {
    "web_frontend": {"kind": "pod", "revisions": []},
    "master_db": {"kind": "database", "revisions": []},
}
EVIDENCE_IDS = {"al_7f3", "lg_0192", "mem_web_p95", "al_9c1", "db_conn_errors"}


def sealed_incident(alert_id="al_7f3", service="web_frontend",
                    metric="mem_web_p95"):
    """A Story-1 incident carried through Phase 1 to Action_Proposed."""
    incident = receive_alert({
        "alert_id": alert_id, "source": "mock_monitor", "service": service,
        "metric": metric, "severity": "critical",
        "timestamp": "2026-09-22T09:00:00Z",
    })
    incident.machine.logs_parsed()
    story = {"al_7f3": None}.get(alert_id)
    prompt = f"alert: {alert_id}"
    result = check_proposal(incident, MockLLM().propose(prompt),
                            SNAPSHOT, EVIDENCE_IDS)
    assert result.event == "llm_action_proposed", result.lesson
    return incident


# ------------------------------------------------------------- T5: allowed
class TestAllowed:
    def test_story1_is_allowed_and_board_advances(self):
        incident = sealed_incident()
        verdict = check_policy(incident)
        assert verdict.event == "opa_allowed"
        assert verdict.allow is True
        assert verdict.deny == []
        assert incident.machine.current_state.name == "Dependency_Check"

    def test_emergency_opens_a_closed_window(self):
        incident = sealed_incident()
        verdict = check_policy(incident, change_window_open=False,
                               emergency=True)
        assert verdict.event == "opa_allowed"


# -------------------------------------------------------------- T6: denied
class TestDenied:
    def test_change_freeze_denies_and_blocks(self):
        incident = sealed_incident()
        verdict = check_policy(incident, change_freeze=True)
        assert verdict.event == "opa_denied"
        assert any("change freeze" in reason for reason in verdict.deny)
        assert incident.machine.current_state.name == "Blocked"

    def test_closed_window_denies(self):
        incident = sealed_incident()
        verdict = check_policy(incident, change_window_open=False)
        assert verdict.event == "opa_denied"
        assert any("change window" in reason for reason in verdict.deny)

    def test_banned_verb_denied_with_ban_reason(self):
        """The §5.3 'known is not the same as allowed' case at OPA level.

        GATE 1 already flags delete_volume, but OPA is an INDEPENDENT
        wall: feed it the banned verb directly and it must name the ban.
        """
        incident = sealed_incident()
        form = build_input(incident)
        form["action"]["verb"] = "delete_volume"
        verdict = opa_adapter.ask_opa(form)
        assert verdict.allow is False
        assert any("permanently prohibited" in r for r in verdict.deny)

    def test_tampered_seal_is_denied(self):
        incident = sealed_incident()
        incident.action_hash = "sha256:tooshort"
        verdict = check_policy(incident)
        assert verdict.event == "opa_denied"
        assert any("action_hash" in r for r in verdict.deny)


# ------------------------------------------------------- T30: fail closed
class TestFailClosed:
    def test_missing_referee_means_no(self, monkeypatch):
        monkeypatch.setattr(opa_adapter, "OPA_EXE",
                            opa_adapter._ROOT / "tools" / "nonexistent.exe")
        incident = sealed_incident()
        verdict = check_policy(incident)
        assert verdict.event == "validation_failed"
        assert verdict.allow is False
        assert "missing" in verdict.checker_error
        assert incident.machine.current_state.name == "Blocked"

    def test_gibberish_answer_means_no(self, monkeypatch):
        import subprocess as sp

        def fake_run(*args, **kwargs):
            return sp.CompletedProcess(args, 0, stdout="not json at all",
                                       stderr="")
        monkeypatch.setattr(opa_adapter.subprocess, "run", fake_run)
        incident = sealed_incident()
        verdict = check_policy(incident)
        assert verdict.event == "validation_failed"
        assert "gibberish" in verdict.checker_error

    def test_referee_crash_means_no(self, monkeypatch):
        import subprocess as sp

        def fake_run(*args, **kwargs):
            return sp.CompletedProcess(args, 2, stdout="",
                                       stderr="rego panic")
        monkeypatch.setattr(opa_adapter.subprocess, "run", fake_run)
        incident = sealed_incident()
        verdict = check_policy(incident)
        assert verdict.event == "validation_failed"
        assert "exited 2" in verdict.checker_error

    def test_too_slow_means_no(self, monkeypatch):
        import subprocess as sp

        def fake_run(*args, **kwargs):
            raise sp.TimeoutExpired(cmd="opa", timeout=10)
        monkeypatch.setattr(opa_adapter.subprocess, "run", fake_run)
        incident = sealed_incident()
        verdict = check_policy(incident)
        assert verdict.event == "validation_failed"
        assert "longer than" in verdict.checker_error


# ----------------------------------------------------------- the form
class TestFormFilling:
    def test_form_carries_the_seal_and_gate1_stamp(self):
        incident = sealed_incident()
        form = build_input(incident)
        assert form["action"]["action_hash"] == incident.action_hash
        assert form["action_hash"] == incident.action_hash
        assert form["action"]["dsl_valid"] is True
        assert form["action"]["verb"] == "restart_pod"
        assert form["resource"]["env"] == "production"
