"""
tests/test_recovery.py -- step P5.2 done-criterion (test P4's heart +
rule L12's no-restart-loop cousin at the counter level).

"tool_failed retries at most twice then escalates; a Blocked incident
 never re-enters the pipeline."
"""

import pytest

from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM
from sentinel.verify.recovery import (MAX_RETRIES, decide_retry,
                                      enter_recovery)


def incident_in_recovery(reason="tool_failed", lesson="the pod refused"):
    """A Story-1 incident whose execution just failed (T22 -> Recovery)."""
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-23T11:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(inc, MockLLM().propose("alert: al_7f3"),
                            {"web_frontend": {"kind": "pod", "revisions": []}},
                            {"al_7f3", "lg_0192", "mem_web_p95"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = "low"
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    inc.machine.risk_low()
    inc.machine.z3_sat()
    inc.machine.execute()
    inc.machine.execution_failed()          # T22 -> Recovery
    enter_recovery(inc, reason, lesson)
    return inc


def fail_again(inc, n=1):
    """Retry -> walk back to a failure -> Recovery again, n times."""
    for i in range(n):
        outcome = decide_retry(inc)
        assert outcome.event == "retry_available"
        # the brand-new attempt walks the pipeline and fails again:
        inc.machine.llm_action_proposed()
        inc.machine.opa_allowed()
        inc.machine.datalog_clear()
        inc.machine.prolog_allowed()
        inc.machine.validation_passed()
        inc.machine.risk_low()
        inc.machine.z3_sat()
        inc.machine.execute()
        inc.machine.execution_failed()
        enter_recovery(inc, "tool_failed", f"failed again (attempt {i + 2})")
    return inc


# ------------------------------------------------------------------ the door
class TestTheDoor:
    def test_no_reason_no_entry(self):
        inc = incident_in_recovery()
        with pytest.raises(ValueError, match="unknown recovery_reason"):
            enter_recovery(inc, "felt_like_it", "whatever")

    def test_no_counterexample_no_entry(self):
        inc = incident_in_recovery()
        with pytest.raises(ValueError, match="requires a counterexample"):
            enter_recovery(inc, "tool_failed", "   ")

    def test_the_record_keeps_the_circled_mistake(self):
        inc = incident_in_recovery(lesson="the pod refused: API 503")
        record = inc.recovery_history[-1]
        assert record.reason == "tool_failed"
        assert record.counterexample == "the pod refused: API 503"
        assert record.retry_number == 1


# ------------------------------------------------------------- the counter
class TestTheCounter:
    def test_first_failure_gets_a_retry_with_the_lesson(self):
        inc = incident_in_recovery(lesson="the pod refused: API 503")
        outcome = decide_retry(inc)
        assert outcome.event == "retry_available"
        assert "API 503" in outcome.lesson_for_prompt
        assert "NEW proposal" in outcome.lesson_for_prompt
        assert inc.machine.current_state.name == "AI_Analysis"

    def test_the_locked_number_is_two(self):
        assert MAX_RETRIES == 2          # guide Part 17.3

    def test_two_retries_then_escalated(self):
        """THE done-criterion: at most twice, then a human owns it."""
        inc = incident_in_recovery()     # attempt 1 failed
        fail_again(inc, n=2)             # retries 1 and 2 spent, both failed
        outcome = decide_retry(inc)      # asking for a THIRD retry
        assert outcome.event == "retries_exhausted"
        assert inc.machine.current_state.name == "Escalated"
        assert len(outcome.history) == 3          # the whole sad story kept

    def test_counter_asks_the_door_first(self):
        inc = incident_in_recovery()
        inc.recovery_history = []
        with pytest.raises(RuntimeError, match="door"):
            decide_retry(inc)


# ------------------------------------------- a NO is never retried (board)
class TestBlockedIsFinal:
    def test_blocked_has_no_road_back_to_the_pipeline(self):
        """A checker's NO: the board itself forbids re-entry -- the only
        road out of Blocked is escalation to a human."""
        inc = receive_alert({
            "alert_id": "al_9c1", "source": "mock_monitor",
            "service": "master_db", "metric": "db_conn_errors",
            "severity": "critical", "timestamp": "2026-09-23T11:00:00Z",
        })
        inc.machine.logs_parsed()
        result = check_proposal(
            inc, MockLLM().propose("alert: al_9c1"),
            {"master_db": {"kind": "database", "revisions": []}},
            {"al_9c1", "db_conn_errors"})
        assert result.event == "llm_action_proposed"
        inc.machine.opa_allowed()
        inc.machine.datalog_sensitive_path()      # Datalog's NO -> Blocked

        for illegal in ("retry_available", "llm_action_proposed", "execute"):
            with pytest.raises(Exception):
                getattr(inc.machine, illegal)()
        assert inc.machine.current_state.name == "Blocked"

    def test_recovery_reasons_do_not_include_checker_nos(self):
        """opa_denied / prolog_forbidden / z3_unsat are NOT valid
        recovery reasons -- a NO cannot even enter the Recovery door."""
        inc = incident_in_recovery()
        for no in ("opa_denied", "datalog_sensitive_path",
                   "prolog_forbidden", "temporal_violation", "z3_unsat"):
            with pytest.raises(ValueError):
                enter_recovery(inc, no, "trying to sneak a NO into retry")
