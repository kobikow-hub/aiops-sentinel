"""
tests/test_probe.py -- step P5.1 done-criterion.

"Both outcomes drive the right board moves in a story-1 rehearsal."
"""

import pytest

from constraints.deployment_gate import check_constraints
from gateway.mockdriver import MockDriver
from gateway.system_map import demo_map
from gateway.tool_gateway import check_and_execute
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM
from sentinel.verify.probe import probe_health


def incident_at_verification(world):
    """Story 1 driven for real: the pretend pod was actually restarted."""
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-23T10:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(inc, MockLLM().propose("alert: al_7f3"),
                            world.snapshot_for_gate1(),
                            {"al_7f3", "lg_0192", "mem_web_p95"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = "low"
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    inc.machine.risk_low()
    assert check_constraints(
        inc, world.live_snapshot_for_z3("web_frontend")).event == "z3_sat"
    assert check_and_execute(
        inc, MockDriver(world)).event == "execution_succeeded"
    return inc


class TestHealthy:
    def test_alert_gone_and_numbers_ok_reaches_audit_logging(self):
        world = demo_map()
        inc = incident_at_verification(world)
        report = probe_health(inc, world, alert_active=False)
        assert report.event == "metrics_healthy"
        assert inc.machine.current_state.name == "Audit_Logging"

    def test_the_chart_shows_every_number(self):
        world = demo_map()
        inc = incident_at_verification(world)
        report = probe_health(inc, world, alert_active=False)
        assert report.checks["alert_cleared"] == (True, True, True)
        assert report.checks["min_capacity"] == (4, 3, True)
        assert report.lesson is None


class TestStillSick:
    def test_alert_still_firing_goes_to_recovery_with_lesson(self):
        world = demo_map()
        inc = incident_at_verification(world)
        report = probe_health(inc, world, alert_active=True)   # still screaming
        assert report.event == "metrics_still_degraded"
        assert "alert_cleared" in report.lesson
        assert inc.machine.current_state.name == "Recovery"

    def test_capacity_still_low_goes_to_recovery_with_the_numbers(self):
        world = demo_map()
        inc = incident_at_verification(world)
        world.services["web_frontend"].nodes = 1        # nodes kept dying
        report = probe_health(inc, world, alert_active=False)
        assert report.event == "metrics_still_degraded"
        assert "min_capacity: got 1, want 3" in report.lesson
        assert inc.machine.current_state.name == "Recovery"

    def test_unhealthy_service_flag_fails_the_probe(self):
        world = demo_map()
        inc = incident_at_verification(world)
        world.services["web_frontend"].healthy = False  # the pill didn't help
        report = probe_health(inc, world, alert_active=False)
        assert report.event == "metrics_still_degraded"
        assert "service_healthy" in report.lesson


class TestProbeReadsTheWorldNotTheReceipt:
    def test_probe_judges_now_not_what_the_gateway_did(self):
        """The receipt says 'ran'; the probe answers 'but are you well?'
        Same receipt, two different worlds, two different verdicts."""
        world = demo_map()
        inc = incident_at_verification(world)      # receipt: success
        sick = probe_health(inc, world, alert_active=True)
        assert sick.event == "metrics_still_degraded"

        world2 = demo_map()
        inc2 = incident_at_verification(world2)    # same kind of receipt
        well = probe_health(inc2, world2, alert_active=False)
        assert well.event == "metrics_healthy"
