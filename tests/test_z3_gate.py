"""
tests/test_z3_gate.py -- step P4.1 done-criterion (tests P10 + P14 core).

"Example A (4 machines) gives z3_sat; Example B (3 machines, after human
 approval) gives z3_unsat with post_min_capacity in the reasons."
 (guide Part 11.3's table, with its real numbers)
"""

from constraints.deployment_gate import (LiveSnapshot, check_constraints,
                                         deployment_gate)
from sentinel.dsl.gate import check_proposal
from sentinel.dsl.parser import parse
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM

RESTART = parse("propose restart_pod(web_frontend) "
                "because alert(al_7f3) confidence [0.72, 0.88];")


def incident_at_constraint_check(via_human=False):
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-22T16:00:00Z",
    })
    inc.machine.logs_parsed()
    result = check_proposal(
        inc, MockLLM().propose("alert: al_7f3"),
        {"web_frontend": {"kind": "pod", "revisions": []}},
        {"al_7f3", "lg_0192", "mem_web_p95"})
    assert result.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = "high" if via_human else "low"
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    if via_human:
        inc.machine.risk_high()
        inc.machine.human_approved()      # the 5pm yes...
    else:
        inc.machine.risk_low()
    return inc


# ------------------------------------------- guide 11.3, the two examples
class TestGuideExamples:
    def test_example_A_four_machines_sat(self):
        """T13 risk_low -> T18, live photo v318: 4-1=3, 3>=3 -> sat."""
        inc = incident_at_constraint_check()
        verdict = check_constraints(inc, LiveSnapshot(
            version=318, active_nodes=4, min_capacity=3))
        assert verdict.event == "z3_sat"
        assert verdict.numbers == {"nodes_before": 4, "nodes_after": 3,
                                   "min_capacity": 3}
        assert inc.machine.current_state.name == "Ready_For_Execution"
        assert inc.snapshot_version == 318          # locked to the photo

    def test_example_B_three_machines_unsat_even_after_human_yes(self):
        """T15 human_approved -> T18, photo v512: 3-1=2, 2<3 -> unsat.
        The human approved the IDEA; the world stopped cooperating."""
        inc = incident_at_constraint_check(via_human=True)
        verdict = check_constraints(inc, LiveSnapshot(
            version=512, active_nodes=3, min_capacity=3))
        assert verdict.event == "z3_unsat"
        assert "post_min_capacity" in verdict.unsat_core
        assert inc.machine.current_state.name == "Blocked"


# --------------------------------------------------- rules named in cores
class TestNamedRules:
    def test_sick_system_fails_the_before_rule(self):
        # only 2 working, rule says 3: too sick to even touch
        verdict = deployment_gate(RESTART, LiveSnapshot(
            version=1, active_nodes=2, min_capacity=3))
        assert verdict.event == "z3_unsat"
        assert "pre_min_capacity" in verdict.unsat_core

    def test_scale_out_bumps_into_max_nodes(self):
        prog = parse("propose scale_out(checkout, delta=5) "
                     "because alert(al_7f3) confidence [0.8, 0.9];")
        verdict = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=8, min_capacity=3, max_nodes=10))
        assert verdict.event == "z3_unsat"
        assert "post_max_nodes" in verdict.unsat_core

    def test_scale_out_bumps_into_the_budget(self):
        prog = parse("propose scale_out(checkout, delta=4) "
                     "because alert(al_7f3) confidence [0.8, 0.9];")
        verdict = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=5, min_capacity=3, max_nodes=100,
            cluster_nodes=98, node_budget=100))
        assert verdict.event == "z3_unsat"
        assert "post_node_budget" in verdict.unsat_core

    def test_rollback_needs_a_real_older_version(self):
        prog = parse("propose rollback(checkout, revision=v41) "
                     "because alert(al_7f3) confidence [0.8, 0.9];")
        bad = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=4, min_capacity=3, revisions=()))
        assert bad.event == "z3_unsat"
        assert "pre_revision_exists" in bad.unsat_core
        good = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=4, min_capacity=3, revisions=("v41",)))
        assert good.event == "z3_sat"

    def test_db_restart_needs_a_replica(self):
        prog = parse("propose restart_master_db(master_db) "
                     "because alert(al_9c1) confidence [0.8, 0.9];")
        bad = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=4, min_capacity=3, has_replica=False))
        assert bad.event == "z3_unsat"
        assert "pre_replica_exists" in bad.unsat_core

    def test_scale_out_effect_comes_from_params_not_ai_prose(self):
        prog = parse("propose scale_out(checkout, delta=3) "
                     "because alert(al_7f3) confidence [0.8, 0.9];")
        verdict = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=4, min_capacity=3))
        assert verdict.event == "z3_sat"
        assert verdict.numbers["nodes_after"] == 7        # 4 + delta(3)

    def test_read_only_touches_nothing(self):
        prog = parse("propose get_metrics(web_frontend) "
                     "because alert(al_7f3) confidence [0.5, 0.6];")
        verdict = deployment_gate(prog, LiveSnapshot(
            version=1, active_nodes=3, min_capacity=3))
        assert verdict.event == "z3_sat"
        assert verdict.numbers["nodes_after"] == 3
