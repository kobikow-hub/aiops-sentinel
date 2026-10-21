"""
tests/test_escalation.py -- step P5.3 done-criterion.

"Story 2's path (Blocked -> escalation_notified -> Escalated ->
 human_resolution_recorded) runs end to end."
"""

import pytest

from sentinel.checkers.datalog import Topology, check_dependencies
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM
from sentinel.verify.escalation import (ConsoleNotifier, escalate,
                                        notify_escalated,
                                        record_human_resolution)

# Scenario 2's world: 40 services depend on master_db, limit 10.
STORY2_TOPO = Topology.from_dict({
    "depends_on": [[f"svc_{i:02d}", "master_db"] for i in range(40)],
    "sensitive": ["master_db"],
    "blast_radius_limit": 10,
})


def story2_blocked_incident():
    """Story 2 driven for real up to Datalog's NO: board at Blocked."""
    inc = receive_alert({
        "alert_id": "al_9c1", "source": "mock_monitor",
        "service": "master_db", "metric": "db_conn_errors",
        "severity": "critical", "timestamp": "2026-09-26T09:00:00Z",
    })
    inc.machine.logs_parsed()
    gate = check_proposal(
        inc, MockLLM().propose("alert: al_9c1"),
        {"master_db": {"kind": "database", "revisions": []}},
        {"al_9c1", "db_conn_errors"})
    assert gate.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    verdict = check_dependencies(inc, STORY2_TOPO)     # the real veto
    assert verdict.event == "datalog_sensitive_path"
    return inc, verdict


# ------------------------------------------------ Story 2, end to end
class TestStory2EndToEnd:
    def test_blocked_to_resolved_through_the_human(self):
        """THE done-criterion, every station real."""
        inc, datalog_verdict = story2_blocked_incident()
        notifier = ConsoleNotifier()

        record = escalate(inc, notifier, trigger="checker_no",
                          datalog_verdict=datalog_verdict)   # T27
        assert inc.machine.current_state.name == "Escalated"
        assert len(notifier.delivered) == 1

        record = record_human_resolution(
            inc, resolved_by="dana",
            note="failed-over to replica, restarted master_db by hand")  # T28
        assert record.resolved is True
        assert inc.machine.current_state.name == "Audit_Logging"

    def test_notification_happens_before_the_board_moves(self):
        """T27 is one act: a dead doorbell means NO move to Escalated."""
        inc, datalog_verdict = story2_blocked_incident()

        class DeadDoorbell:
            def notify(self, packet):
                raise ConnectionError("doorbell unplugged")

        with pytest.raises(ConnectionError):
            escalate(inc, DeadDoorbell(), trigger="checker_no",
                     datalog_verdict=datalog_verdict)
        assert inc.machine.current_state.name == "Blocked"   # unmoved


# ------------------------------------------------ the honest packet
class TestHonestPacket:
    def test_packet_carries_the_checkers_own_words(self):
        inc, datalog_verdict = story2_blocked_incident()
        notifier = ConsoleNotifier()
        record = escalate(inc, notifier, trigger="checker_no",
                          datalog_verdict=datalog_verdict)
        packet = record.packet
        assert packet["trigger"] == "checker_no"
        assert packet["proposal"]["verb"] == "restart_master_db"
        assert packet["action_hash"] == inc.action_hash
        # Datalog's OWN voice: the count and the actual domino paths
        assert packet["checker_reasons"]["datalog"]["reason"] == "blast_radius"
        assert packet["checker_reasons"]["datalog"]["dependents"] == 40
        assert len(packet["checker_reasons"]["datalog"]["paths"]) == 40

    def test_retry_history_rides_along(self):
        inc, datalog_verdict = story2_blocked_incident()
        # pretend an earlier life left lessons on the case folder:
        class FakeRecord:
            reason, counterexample, retry_number = "tool_failed", "API 503", 1
        inc.recovery_history = [FakeRecord()]
        record = escalate(inc, ConsoleNotifier(), trigger="checker_no",
                          datalog_verdict=datalog_verdict)
        assert record.packet["retry_history"] == [
            {"reason": "tool_failed", "counterexample": "API 503",
             "attempt": 1}]


# ------------------------------------- the other two roads to Escalated
class TestOtherRoads:
    def waiting_incident(self):
        inc = receive_alert({
            "alert_id": "al_9c1", "source": "mock_monitor",
            "service": "master_db", "metric": "db_conn_errors",
            "severity": "critical", "timestamp": "2026-09-26T09:00:00Z",
        })
        inc.machine.logs_parsed()
        gate = check_proposal(
            inc, MockLLM().propose("alert: al_9c1"),
            {"master_db": {"kind": "database", "revisions": []}},
            {"al_9c1", "db_conn_errors"})
        assert gate.event == "llm_action_proposed"
        inc.machine.opa_allowed()
        inc.machine.datalog_clear()
        inc.risk_level = "high"
        inc.machine.prolog_allowed()
        inc.machine.validation_passed()
        inc.machine.risk_high()
        return inc

    def test_approval_timeout_road_gets_the_same_doorbell(self):
        inc = self.waiting_incident()
        inc.machine.approval_timeout()          # T17: already Escalated
        notifier = ConsoleNotifier()
        record = notify_escalated(inc, notifier, trigger="approval_timeout")
        assert notifier.delivered[0]["trigger"] == "approval_timeout"
        assert inc.machine.current_state.name == "Escalated"
        # and the human closes it the same way:
        record_human_resolution(inc, "omar", "approved by phone, ran fix")
        assert inc.machine.current_state.name == "Audit_Logging"


# ------------------------------------------------ resolution honesty
class TestResolutionRules:
    def escalated_incident(self):
        inc, datalog_verdict = story2_blocked_incident()
        escalate(inc, ConsoleNotifier(), trigger="checker_no",
                 datalog_verdict=datalog_verdict)
        return inc

    def test_no_name_no_resolution(self):
        inc = self.escalated_incident()
        with pytest.raises(ValueError, match="resolver's name"):
            record_human_resolution(inc, "  ", "fixed it")

    def test_no_note_no_resolution(self):
        inc = self.escalated_incident()
        with pytest.raises(ValueError, match="needs a note"):
            record_human_resolution(inc, "dana", "")

    def test_no_handover_no_resolution(self):
        """T28 without a recorded escalation is refused."""
        inc, _ = story2_blocked_incident()
        with pytest.raises(RuntimeError, match="handover"):
            record_human_resolution(inc, "dana", "fixed")

    def test_resolution_does_not_skip_the_diary(self):
        """Escalation is a handover, never a shortcut: after T28 the
        board is at Audit_Logging, NOT Incident_Resolved (rule L7)."""
        inc = self.escalated_incident()
        record_human_resolution(inc, "dana", "fixed by hand")
        assert inc.machine.current_state.name == "Audit_Logging"
