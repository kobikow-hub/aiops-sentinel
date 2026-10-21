"""
tests/test_datalog.py -- step P2.2 done-criterion + P17 Datalog fixtures.

"The Scenario 2 input from guide Part 10.2 (40 services depend on
 master_db, limit 10) returns datalog_sensitive_path with reason
 blast_radius."

Every rule tested here mirrors a rule in rules/topology.dl -- if a test
disagrees with the .dl file, the .dl file wins.
"""

from sentinel.checkers.datalog import (
    Topology, alert_context, affected_by, check_dependencies,
    critical_in_blast, dependents, exposed_to_sensitive, sensitive_flow,
    sensitive_target,
)
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM
from sentinel.intake.redactor import redact_logs

# ---------------------------------------------------------------- fixtures
# Story 1's little world: web_frontend is a leaf -- nobody depends on it.
STORY1 = Topology.from_dict({
    "depends_on": [["web_frontend", "auth_service"],
                   ["auth_service", "user_db"]],
    "sensitive": ["user_db"],
    "critical": ["auth_service"],
})

# Scenario 2 (guide Part 10.2 I/O): 40 services depend on master_db.
STORY2 = Topology.from_dict({
    "depends_on": [[f"svc_{i:02d}", "master_db"] for i in range(40)],
    "sensitive": ["master_db"],
    "blast_radius_limit": 10,
})

# A leak world: reporting reads secrets and sends to an outside place.
LEAKY = Topology.from_dict({
    "depends_on": [],
    "reads_from": [["reporting", "user_db"]],
    "sends_to": [["reporting", "partner_api"]],
    "sensitive": ["user_db"],
    "external": ["partner_api"],
})


def incident_for(alert_id, service, metric, snapshot, evidence):
    inc = receive_alert({
        "alert_id": alert_id, "source": "mock_monitor", "service": service,
        "metric": metric, "severity": "critical",
        "timestamp": "2026-09-22T10:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(inc, MockLLM().propose(f"alert: {alert_id}"),
                            snapshot, evidence)
    assert result.event == "llm_action_proposed", result.lesson
    inc.machine.opa_allowed()          # OPA said yes; now at Dependency_Check
    return inc


# ------------------------------------------------------- the chain-follower
class TestChains:
    def test_direct_and_transitive_dominoes(self):
        # user_db falls -> auth_service falls -> web_frontend falls
        assert affected_by(STORY1, "user_db") == {"auth_service", "web_frontend"}

    def test_leaf_hurts_nobody(self):
        assert affected_by(STORY1, "web_frontend") == set()

    def test_cycles_do_not_loop_forever(self):
        loopy = Topology.from_dict({"depends_on": [["a", "b"], ["b", "a"]]})
        assert affected_by(loopy, "a") == {"a", "b"}


# ------------------------------------------- alert_context (T2, the socket)
class TestAlertContext:
    def test_context_is_the_neighborhood(self):
        # auth_service screams: itself + what it needs + who needs it.
        assert alert_context(STORY1, "auth_service") == {
            "auth_service", "user_db", "web_frontend"}

    def test_context_plugs_into_the_redactor(self):
        """The P1.2 socket finally gets its plug."""
        allowed = alert_context(STORY1, "auth_service")
        result = redact_logs(
            ["auth_service: token refresh failing",
             "billing: nightly invoice run started"],   # not in the neighborhood
            allowed_services=allowed,
        )
        assert result.lines_dropped == 1
        assert "auth_service" in result.lines[0]


# --------------------------------------------------- counting and the veto
class TestBlastRadius:
    def test_scenario2_counts_40_dependents(self):
        assert dependents(STORY2, "master_db") == 40

    def test_story1_target_counts_zero(self):
        assert dependents(STORY1, "web_frontend") == 0

    def test_critical_in_blast_found(self):
        assert critical_in_blast(STORY1, "user_db") == {"auth_service"}


# ------------------------------------------------------- secrets and leaks
class TestSensitive:
    def test_exposure_follows_chains(self):
        assert exposed_to_sensitive(STORY1) == {"auth_service", "web_frontend"}

    def test_sensitive_target_direct_and_via_exposure(self):
        assert sensitive_target(STORY2, "master_db") is True     # is secret
        assert sensitive_target(STORY1, "auth_service") is True  # touches secrets
        assert sensitive_target(STORY1, "web_frontend") is True  # chain
        assert sensitive_target(LEAKY, "partner_api") is False

    def test_leak_road_found(self):
        assert sensitive_flow(LEAKY, "reporting") == {"partner_api"}

    def test_no_leak_road_in_story1(self):
        assert sensitive_flow(STORY1, "auth_service") == set()


# --------------------------------------------------- the full T7/T8 verdict
class TestVerdict:
    SNAP1 = {"web_frontend": {"kind": "pod", "revisions": []}}
    SNAP2 = {"master_db": {"kind": "database", "revisions": []}}
    EVIDENCE = {"al_7f3", "lg_0192", "mem_web_p95", "al_9c1", "db_conn_errors"}

    def test_story1_is_clear_and_board_advances(self):
        inc = incident_for("al_7f3", "web_frontend", "mem_web_p95",
                           self.SNAP1, self.EVIDENCE)
        verdict = check_dependencies(inc, STORY1)
        assert verdict.event == "datalog_clear"
        assert verdict.dependents == 0
        assert inc.machine.current_state.name == "Rule_Inference"

    def test_scenario2_blast_radius_veto(self):
        """THE done-criterion: 40 >= 10 -> datalog_sensitive_path."""
        inc = incident_for("al_9c1", "master_db", "db_conn_errors",
                           self.SNAP2, self.EVIDENCE)
        verdict = check_dependencies(inc, STORY2)
        assert verdict.event == "datalog_sensitive_path"
        assert verdict.reason == "blast_radius"
        assert verdict.dependents == 40
        assert len(verdict.paths) == 40          # every chain shown to humans
        assert inc.machine.current_state.name == "Blocked"

    def test_facts_for_prolog_are_handed_forward(self):
        inc = incident_for("al_9c1", "master_db", "db_conn_errors",
                           self.SNAP2, self.EVIDENCE)
        verdict = check_dependencies(inc, STORY2)
        assert verdict.facts_for_prolog["sensitive_target"] == ["master_db"]

    def test_sensitive_flow_veto(self):
        snap = {"reporting": {"kind": "service", "revisions": []}}
        inc = receive_alert({
            "alert_id": "al_xyz", "source": "mock_monitor",
            "service": "reporting", "metric": "latency",
            "severity": "warning", "timestamp": "2026-09-22T10:00:00Z",
        })
        inc.machine.logs_parsed()
        gate = check_proposal(
            inc,
            "propose restart_service(reporting) because alert(al_xyz) "
            "confidence [0.7, 0.8];",
            snap, {"al_xyz"})
        assert gate.event == "llm_action_proposed"
        inc.machine.opa_allowed()
        verdict = check_dependencies(inc, LEAKY)
        assert verdict.event == "datalog_sensitive_path"
        assert verdict.reason == "sensitive_flow"
        assert ["reporting", "partner_api"] in verdict.paths
