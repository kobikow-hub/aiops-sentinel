"""
tests/test_sla.py -- step P3.3 done-criterion.

"With no human answer inside the window, the board moves
 Human_Approval_Required -> Escalated."

Tests never sleep: the timer's clock is injectable.
"""

from datetime import datetime, timedelta, timezone

from sentinel.decide.approval import issue_token, submit_decision
from sentinel.decide.sla_timer import SlaTimer
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM

T0 = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)


def waiting_incident():
    """A high-risk case folder standing at Human_Approval_Required."""
    inc = receive_alert({
        "alert_id": "al_9c1", "source": "mock_monitor",
        "service": "master_db", "metric": "db_conn_errors",
        "severity": "critical", "timestamp": "2026-09-22T15:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(
        inc, MockLLM().propose("alert: al_9c1"),
        {"master_db": {"kind": "database", "revisions": []}},
        {"al_9c1", "db_conn_errors"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = "high"
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    inc.machine.risk_high()
    return inc


class TestTimeout:
    def test_no_answer_inside_window_escalates(self):
        """THE done-criterion."""
        inc = waiting_incident()
        timer = SlaTimer.start(inc, sla_minutes=30, now=T0)
        event = timer.check(now=T0 + timedelta(minutes=31))
        assert event == "approval_timeout"
        assert inc.machine.current_state.name == "Escalated"

    def test_inside_the_window_nothing_happens(self):
        inc = waiting_incident()
        timer = SlaTimer.start(inc, sla_minutes=30, now=T0)
        assert timer.check(now=T0 + timedelta(minutes=29)) is None
        assert inc.machine.current_state.name == "Human_Approval_Required"

    def test_fires_at_most_once(self):
        inc = waiting_incident()
        timer = SlaTimer.start(inc, sla_minutes=30, now=T0)
        assert timer.check(now=T0 + timedelta(minutes=31)) == "approval_timeout"
        assert timer.check(now=T0 + timedelta(minutes=32)) is None


class TestAnsweredInTime:
    def test_yes_in_time_means_timer_stands_down(self):
        inc = waiting_incident()
        timer = SlaTimer.start(inc, sla_minutes=30, now=T0)
        outcome = submit_decision(inc, issue_token(inc, "dana", "sre"),
                                  "approve")
        assert outcome.event == "human_approved"
        # the window closes later -- but nobody is waiting anymore:
        assert timer.check(now=T0 + timedelta(minutes=31)) is None
        assert inc.machine.current_state.name == "Constraint_Check"

    def test_no_in_time_means_timer_stands_down(self):
        inc = waiting_incident()
        timer = SlaTimer.start(inc, sla_minutes=30, now=T0)
        outcome = submit_decision(inc, issue_token(inc, "omar", "admin"),
                                  "reject")
        assert outcome.event == "human_rejected"
        assert timer.check(now=T0 + timedelta(minutes=31)) is None
        assert inc.machine.current_state.name == "Blocked"


class TestL4AlwaysEnds:
    def test_every_waiting_road_has_an_end(self):
        """Rule L4 in one test: yes, no, or time's up -- never forever.

        Three identical waiting incidents; each leaves the waiting square
        by a different one of the exactly-three exits.
        """
        exits = {}

        inc = waiting_incident()
        submit_decision(inc, issue_token(inc, "dana", "sre"), "approve")
        exits["yes"] = inc.machine.current_state.name

        inc = waiting_incident()
        submit_decision(inc, issue_token(inc, "dana", "sre"), "reject")
        exits["no"] = inc.machine.current_state.name

        inc = waiting_incident()
        SlaTimer.start(inc, sla_minutes=30, now=T0).check(
            now=T0 + timedelta(minutes=31))
        exits["timeout"] = inc.machine.current_state.name

        assert exits == {"yes": "Constraint_Check",
                         "no": "Blocked",
                         "timeout": "Escalated"}
