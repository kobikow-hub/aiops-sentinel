"""
tests/test_gateway.py -- step P4.3 done-criterion (+ test P11's heart).

"Changed world version -> refused; duplicate slip -> refused (P11);
 timeout with no receipt -> reconcile first, then execution_failed only
 if truly not done."
"""

import pytest

from constraints.deployment_gate import check_constraints
from gateway.mockdriver import MockDriver
from gateway.system_map import demo_map
from gateway.tool_gateway import check_and_execute
from sentinel.decide.approval import issue_token
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM


def ready_incident(world, risk="low"):
    """Story 1 carried all the way to Ready_For_Execution, Z3-pinned."""
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-23T09:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(inc, MockLLM().propose("alert: al_7f3"),
                            world.snapshot_for_gate1(),
                            {"al_7f3", "lg_0192", "mem_web_p95"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = risk
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    if risk == "low":
        inc.machine.risk_low()
    else:
        inc.machine.risk_high()
        inc.machine.human_approved()
    verdict = check_constraints(inc, world.live_snapshot_for_z3("web_frontend"))
    assert verdict.event == "z3_sat"
    return inc


# ---------------------------------------------------------- the happy drive
class TestHappyDrive:
    def test_low_risk_executes_and_reaches_verification(self):
        world = demo_map()
        inc = ready_incident(world)
        result = check_and_execute(inc, MockDriver(world))
        assert result.event == "execution_succeeded"
        assert result.receipt.action_hash == inc.action_hash
        assert inc.machine.current_state.name == "Verification"

    def test_high_risk_with_the_right_slip_executes(self):
        world = demo_map()
        inc = ready_incident(world, risk="high")
        token = issue_token(inc, "dana", "sre")
        result = check_and_execute(inc, MockDriver(world), approval_token=token)
        assert result.event == "execution_succeeded"


# ------------------------------------------------- compare-and-execute (T22)
class TestStaleWorld:
    def test_changed_world_version_is_refused(self):
        """THE done-criterion row: the world moved after Z3's photo."""
        world = demo_map()
        inc = ready_incident(world)
        world.bump()                       # something ELSE changed the world
        result = check_and_execute(inc, MockDriver(world))
        assert result.event == "execution_failed"
        assert "stale_snapshot" in result.reason
        assert inc.machine.current_state.name == "Recovery"


# --------------------------------------------------------- idempotency (P11)
class TestFingerprintRules:
    def test_same_fingerprint_never_acts_twice(self):
        world = demo_map()
        driver = MockDriver(world)
        inc = ready_incident(world)
        first = check_and_execute(inc, driver)
        assert first.event == "execution_succeeded"
        # a second incident-object replaying the SAME sealed action:
        inc2 = ready_incident(world)
        inc2.action_hash = inc.action_hash          # the replay
        inc2.snapshot_version = world.version       # even with a fresh pin
        result = check_and_execute(inc2, driver)
        assert result.event == "execution_failed"
        assert "duplicate" in result.reason
        assert len([c for c in driver.calls]) == 1  # the driver drove ONCE

    def test_slip_for_another_action_is_refused(self):
        world = demo_map()
        inc = ready_incident(world, risk="high")
        token = issue_token(inc, "dana", "sre")
        token.action_hash = "sha256:" + "def4" + "0" * 60   # the pool slip
        result = check_and_execute(inc, MockDriver(world), approval_token=token)
        assert result.event == "execution_failed"
        assert "different action_hash" in result.reason

    def test_high_risk_with_no_slip_is_refused(self):
        world = demo_map()
        inc = ready_incident(world, risk="high")
        result = check_and_execute(inc, MockDriver(world))
        assert result.event == "execution_failed"
        assert "no approval token" in result.reason


# ------------------------------------------------- reconcile on timeout (T22)
class TestTimeouts:
    def test_timeout_but_done_reconciles_to_success(self):
        """The office calls the school: the bus DID arrive."""
        world = demo_map()
        driver = MockDriver(world, behavior=["timeout_but_done"])
        inc = ready_incident(world)
        result = check_and_execute(inc, driver)
        assert result.event == "execution_succeeded"
        assert result.reconciled is True
        assert inc.machine.current_state.name == "Verification"

    def test_timeout_not_done_reconciles_to_failure(self):
        """THE done-criterion row: reconcile first, fail only if truly
        not done."""
        world = demo_map()
        driver = MockDriver(world, behavior=["timeout_not_done"])
        inc = ready_incident(world)
        result = check_and_execute(inc, driver)
        assert result.event == "execution_failed"
        assert result.reconciled is True
        assert "found not done" in result.reason
        assert inc.machine.current_state.name == "Recovery"


# ----------------------------------------------------- ordinary failures
class TestOrdinaryFailures:
    def test_refusal_goes_to_recovery(self):
        world = demo_map()
        inc = ready_incident(world)
        result = check_and_execute(inc, MockDriver(world, behavior=["refuse"]))
        assert result.event == "execution_failed"
        assert "refused" in result.reason

    def test_confirmed_failure_goes_to_recovery(self):
        world = demo_map()
        inc = ready_incident(world)
        result = check_and_execute(inc, MockDriver(world, behavior=["fail"]))
        assert result.event == "execution_failed"
        assert "confirmed failure" in result.reason
        assert inc.machine.current_state.name == "Recovery"
