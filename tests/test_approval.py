"""
tests/test_approval.py -- step P3.2 done-criterion == test P8.

"Only a valid slip produces human_approved; every broken slip produces
 nothing and the system keeps waiting."

Slip checks run through the REAL opa.exe with the REAL law book.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sentinel.decide.approval import (issue_token, review_packet,
                                      submit_decision, validate_token)
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM


def incident_waiting_for_a_human():
    """A high-risk case folder standing at Human_Approval_Required."""
    inc = receive_alert({
        "alert_id": "al_9c1", "source": "mock_monitor",
        "service": "master_db", "metric": "db_conn_errors",
        "severity": "critical", "timestamp": "2026-09-22T14:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(
        inc, MockLLM().propose("alert: al_9c1"),
        {"master_db": {"kind": "database", "revisions": []}},
        {"al_9c1", "db_conn_errors"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = "high"                  # Prolog's stored reading
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    inc.machine.risk_high()                  # T14 -> Human_Approval_Required
    return inc


WAITING = "Human_Approval_Required"


# ----------------------------------------------------------- the valid slip
class TestValidSlip:
    def test_sre_approval_produces_human_approved(self):
        inc = incident_waiting_for_a_human()
        token = issue_token(inc, "dana", "sre")
        outcome = submit_decision(inc, token, "approve")
        assert outcome.event == "human_approved"
        assert inc.machine.current_state.name == "Constraint_Check"

    def test_admin_may_also_sign(self):
        inc = incident_waiting_for_a_human()
        outcome = submit_decision(inc, issue_token(inc, "omar", "admin"),
                                  "approve")
        assert outcome.event == "human_approved"

    def test_rejection_blocks_and_is_remembered(self):
        inc = incident_waiting_for_a_human()
        rejected: list = []
        outcome = submit_decision(inc, issue_token(inc, "dana", "sre"),
                                  "reject", rejected_registry=rejected)
        assert outcome.event == "human_rejected"
        assert inc.machine.current_state.name == "Blocked"
        assert ("restart_master_db", "master_db") in rejected


# ---------------------------------------------- test P8: broken slips
class TestBrokenSlipsP8:
    """Viewer / other-hash / expired / reused: refused, NO event,
    the board keeps waiting."""

    def test_viewer_slip_refused(self):
        inc = incident_waiting_for_a_human()
        token = issue_token(inc, "sam", "viewer")
        outcome = submit_decision(inc, token, "approve")
        assert outcome.event is None
        assert any("role is not sre or admin" in r for r in outcome.reasons)
        assert inc.machine.current_state.name == WAITING

    def test_other_actions_slip_refused(self):
        inc = incident_waiting_for_a_human()
        token = issue_token(inc, "dana", "sre")
        token.action_hash = ("sha256:"
                             + "def4" + "0" * 60)   # a slip for the POOL
        outcome = submit_decision(inc, token, "approve")
        assert outcome.event is None
        assert any("different action_hash" in r for r in outcome.reasons)
        assert inc.machine.current_state.name == WAITING

    def test_expired_slip_refused(self):
        inc = incident_waiting_for_a_human()
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        token = issue_token(inc, "dana", "sre", now=old)   # signed 2h ago
        outcome = submit_decision(inc, token, "approve")
        assert outcome.event is None
        assert any("expired" in r for r in outcome.reasons)
        assert inc.machine.current_state.name == WAITING

    def test_reused_slip_refused(self):
        inc = incident_waiting_for_a_human()
        token = issue_token(inc, "dana", "sre")
        first = submit_decision(inc, token, "approve")
        assert first.event == "human_approved"
        # the photocopy: same slip again (board already moved on; what
        # matters is the desk refuses it, not where the piece stands)
        valid, reasons = validate_token(token, inc.action_hash)
        assert valid is False
        assert any("already used" in r for r in reasons)

    def test_desk_trouble_means_no_event(self, monkeypatch):
        """Cannot verify the slip -> the slip does not count -> wait."""
        from sentinel.checkers import opa_adapter
        monkeypatch.setattr(opa_adapter, "OPA_EXE",
                            opa_adapter.OPA_EXE.parent / "nonexistent.exe")
        inc = incident_waiting_for_a_human()
        outcome = submit_decision(inc, issue_token(inc, "dana", "sre"),
                                  "approve")
        assert outcome.event is None
        assert any("could not verify" in r for r in outcome.reasons)
        assert inc.machine.current_state.name == WAITING


# ------------------------------------------------------ the honest screen
class TestReviewPacket:
    def test_packet_carries_the_checkers_own_words(self):
        inc = incident_waiting_for_a_human()

        class FakeDatalog:      # stand-ins with the checkers' real fields
            dependents = 40
            paths = [["checkout", "master_db"]]

        class FakeProlog:
            proof = ["stateful(master_db)"]

        packet = review_packet(inc, datalog_verdict=FakeDatalog(),
                               prolog_verdict=FakeProlog())
        assert packet["action_hash"] == inc.action_hash
        assert packet["datalog"]["dependents"] == 40
        assert packet["prolog"]["risk_level"] == "high"
        assert packet["prolog"]["proof"] == ["stateful(master_db)"]
        assert packet["program"]["verb"] == "restart_master_db"
