"""
tests/test_ltl.py -- step P2.4 done-criterion + P17 LTL fixtures.

"The allowed/forbidden order table from guide Part 8.7 is reproduced
 exactly: story-1's order passes, llm_action_proposed -> execute is a
 violation of L1."
"""

from ltl.check import Step, check_full_trace, check_temporal, live_guard, look_ahead
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM

H = "sha256:9f2c"          # story fingerprint (abbreviated, tests only)
H2 = "sha256:def4"         # a DIFFERENT action's fingerprint


def trace(*names, action_hash=H, payloads=None):
    payloads = payloads or {}
    return [Step(name=n, action_hash=action_hash,
                 payload=payloads.get(n, {})) for n in names]


STORY1_ORDER = ["llm_action_proposed", "opa_allowed", "datalog_clear",
                "prolog_allowed", "validation_passed", "risk_low",
                "z3_sat", "execute", "execution_succeeded",
                "metrics_healthy", "audit_log_created"]


# ---------------------------------------------- the 8.7 table: allowed rows
class TestAllowedOrders:
    def test_story1_full_order_passes_all_rules(self):
        verdict = check_full_trace(trace(*STORY1_ORDER),
                                   world={"final_state": "Incident_Resolved"})
        assert verdict.event == "validation_passed"

    def test_high_risk_with_approval_then_fresh_z3_passes(self):
        # ... risk_high -> human_approved -> z3_sat -> execute ...  (L3, L9 OK)
        steps = trace("llm_action_proposed", "opa_allowed", "datalog_clear",
                      "prolog_allowed", "validation_passed", "risk_high",
                      "human_approved", "z3_sat", "execute")
        verdict = live_guard(steps[:-1], steps[-1])
        assert verdict.event == "validation_passed"


# --------------------------------------------- the 8.7 table: forbidden rows
class TestForbiddenOrders:
    def test_story3_execute_right_after_proposal_violates_L1(self):
        """THE done-criterion row -- Story 3's crime."""
        steps = trace("alert_received", "logs_parsed", "llm_action_proposed")
        verdict = live_guard(steps, Step(name="execute", action_hash=H))
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L1"
        assert verdict.last_steps[-1] == "llm_action_proposed"

    def test_risk_high_then_execute_without_approval_violates_L3(self):
        steps = trace("llm_action_proposed", "opa_allowed", "datalog_clear",
                      "prolog_allowed", "validation_passed", "risk_high",
                      "z3_sat")
        verdict = live_guard(steps, Step(name="execute", action_hash=H))
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule in ("L1", "L3")   # both watch this
        # L3 specifically: remove z3 gap by checking the L3-only story
        steps_l3 = trace("llm_action_proposed", "opa_allowed",
                         "datalog_clear", "prolog_allowed",
                         "validation_passed", "z3_sat", "risk_high")
        verdict = live_guard(steps_l3, Step(name="execute", action_hash=H))
        assert verdict.event == "temporal_violation"

    def test_z3_before_the_decision_violates_L9(self):
        # z3_sat -> risk_low -> execute: the yes is STALE (took the photo
        # before the decision). L9 demands a fresh z3 AFTER risk_low.
        steps = trace("llm_action_proposed", "opa_allowed", "datalog_clear",
                      "prolog_allowed", "validation_passed", "z3_sat",
                      "risk_low")
        verdict = live_guard(steps, Step(name="execute", action_hash=H))
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L9"

    def test_close_without_diary_violates_L7(self):
        steps = trace(*STORY1_ORDER[:-1])       # no audit_log_created
        verdict = check_full_trace(
            steps, world={"final_state": "Incident_Resolved"})
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule in ("L6", "L7")

    def test_checker_no_then_anything_but_blocked_violates_L2(self):
        steps = trace("llm_action_proposed", "opa_denied", "risk_low")
        verdict = check_full_trace(steps)
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L2"

    def test_tool_failure_ignored_violates_L5(self):
        steps = trace("llm_action_proposed", "opa_allowed", "datalog_clear",
                      "prolog_allowed", "validation_passed", "risk_low",
                      "z3_sat", "execute", "execution_failed",
                      "metrics_healthy")          # pretending nothing happened
        verdict = check_full_trace(steps)
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L5"

    def test_third_restart_without_healthy_violates_L12(self):
        verdict = check_full_trace(
            trace(*STORY1_ORDER),
            world={"final_state": "Incident_Resolved"},
            episode_memory=["restart", "restart", "restart"])
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L12"

    def test_two_restarts_with_healthy_between_is_fine(self):
        verdict = check_full_trace(
            trace(*STORY1_ORDER),
            world={"final_state": "Incident_Resolved"},
            episode_memory=["restart", "healthy", "restart", "restart"])
        assert verdict.event == "validation_passed"


# ------------------------------------------------ scoping: no borrowed slips
class TestScoping:
    def test_action_A_approval_cannot_help_action_B(self):
        """Guide 8.5's example: A got approved; B must not borrow it."""
        steps = (trace("llm_action_proposed", "opa_allowed", "datalog_clear",
                       "prolog_allowed", "validation_passed", "risk_high",
                       "human_approved", "z3_sat", "execute", action_hash=H)
                 + trace("llm_action_proposed", action_hash=H2))
        # B tries to execute with only its proposal on file:
        verdict = live_guard(steps, Step(name="execute", action_hash=H2))
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L1"


# ------------------------------------------------------- T11/T12 on the board
class TestTemporalCheckStep:
    def incident_at_temporal_check(self):
        inc = receive_alert({
            "alert_id": "al_7f3", "source": "mock_monitor",
            "service": "web_frontend", "metric": "mem_web_p95",
            "severity": "critical", "timestamp": "2026-09-22T12:00:00Z",
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
        return inc

    def diary_so_far(self, inc):
        return trace("llm_action_proposed", "opa_allowed", "datalog_clear",
                     "prolog_allowed", action_hash=inc.action_hash)

    def test_good_plan_passes_and_board_advances(self):
        inc = self.incident_at_temporal_check()
        verdict = check_temporal(
            inc, self.diary_so_far(inc),
            planned=["validation_passed", "risk_low", "z3_sat", "execute"])
        assert verdict.event == "validation_passed"
        assert inc.machine.current_state.name == "Risk_Assessment"

    def test_bad_plan_blocks_with_rule_number_and_evidence(self):
        inc = self.incident_at_temporal_check()
        verdict = check_temporal(
            inc, self.diary_so_far(inc),
            planned=["execute"])                 # skipping the rest
        assert verdict.event == "temporal_violation"
        assert verdict.violated_rule == "L1"
        assert verdict.simple.startswith("never act unless")
        assert verdict.last_steps                # the last diary steps attached
        assert inc.machine.current_state.name == "Blocked"
