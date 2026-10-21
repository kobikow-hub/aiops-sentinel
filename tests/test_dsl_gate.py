"""
tests/test_dsl_gate.py -- step P1.4 done-criterion == test P15.

"All good/bad sentences from guide Part 5.3 behave exactly as the
 table says."  Each bad sentence comes from MockLLM's misbehave modes,
 so the exact strings the pretend AI can emit are the exact strings
 judged here.
"""

import pytest

from board.incident_machine import IncidentMachine
from sentinel.dsl.fingerprint import make_action_hash
from sentinel.dsl.gate import check_proposal
from sentinel.dsl.parser import DslParseError, parse
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import BAD_SCRIPTS, MockLLM

# The read-only system photo for Story 1's little world.
SNAPSHOT = {
    "web_frontend": {"kind": "pod", "revisions": []},
    "auth_service": {"kind": "service", "revisions": []},
    "checkout": {"kind": "deployment", "revisions": ["v41", "v42"]},
    "master_db": {"kind": "database", "revisions": []},
}
# The ids that really appeared in the alert + safe logs shown to the AI.
EVIDENCE_IDS = {"al_7f3", "lg_0192", "mem_web_p95"}

GOOD = ("propose restart_pod(web_frontend)\n"
        "  because alert(al_7f3), log(lg_0192), metric(mem_web_p95)\n"
        "  confidence [0.72, 0.88];")


def fresh_incident():
    incident = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-19T12:00:00Z",
    })
    incident.machine.logs_parsed()          # board to AI_Analysis
    return incident


def gate(text):
    return check_proposal(fresh_incident(), text, SNAPSHOT, EVIDENCE_IDS)


# --------------------------------------------------- the good sentence
class TestGoodSentence:
    def test_good_program_is_sealed_and_proposed(self):
        result = gate(GOOD)
        assert result.event == "llm_action_proposed"
        assert result.program.verb == "restart_pod"
        assert result.program.target == "web_frontend"
        assert result.program.confidence == (0.72, 0.88)
        assert result.action_hash.startswith("sha256:")
        assert len(result.action_hash) == len("sha256:") + 64

    def test_board_reaches_action_proposed(self):
        incident = fresh_incident()
        check_proposal(incident, GOOD, SNAPSHOT, EVIDENCE_IDS)
        assert incident.machine.current_state.name == "Action_Proposed"


# ------------------------------------- the §5.3 bad-sentence table (P15)
class TestBadSentencesP15:
    """One test per row; every bad string comes straight from MockLLM."""

    def flub(self, mode):
        return gate(MockLLM(misbehave=mode).propose("irrelevant"))

    def test_shell_command_grammar_error(self):
        result = self.flub("shell_command")
        assert result.event == "llm_output_invalid"
        assert "not a DSL sentence" in result.lesson

    def test_unknown_verb(self):
        result = self.flub("unknown_verb")
        assert result.event == "llm_output_invalid"
        assert "unknown action word 'reboot_cluster'" in result.lesson

    def test_made_up_target(self):
        result = self.flub("made_up_target")
        assert result.event == "llm_output_invalid"
        assert "'payments_v2' does not exist" in result.lesson

    def test_wrong_kind(self):
        result = self.flub("wrong_kind")
        assert result.event == "llm_output_invalid"
        assert "expects a Pod, got a Database" in result.lesson

    def test_delta_too_big(self):
        result = self.flub("delta_too_big")
        assert result.event == "llm_output_invalid"
        assert "delta must be a whole number 1..5, got 40" in result.lesson

    def test_quoted_text(self):
        result = self.flub("quoted_text")
        assert result.event == "llm_output_invalid"
        assert "quoted text has no place" in result.lesson

    def test_destructive_parses_but_flagged_as_trick(self):
        """'Known is not the same as allowed': recorded as dangerous."""
        result = self.flub("destructive")
        assert result.event == "llm_output_invalid"
        assert result.trick_flag is True
        assert "delete_volume" in result.lesson
        assert "never allowed" in result.lesson

    def test_every_flub_moves_board_to_recovery(self):
        for mode in BAD_SCRIPTS:
            incident = fresh_incident()
            check_proposal(incident, MockLLM(misbehave=mode).propose("x"),
                           SNAPSHOT, EVIDENCE_IDS)
            assert incident.machine.current_state.name == "Recovery", mode


# ------------------------------------------------- more type-rule edges
class TestTypeRuleEdges:
    def test_unshown_evidence_is_refused(self):
        result = gate("propose restart_pod(web_frontend) "
                      "because log(lg_9999) confidence [0.7, 0.8];")
        assert "log(lg_9999) was never shown" in result.lesson

    def test_bad_confidence_interval(self):
        result = gate("propose restart_pod(web_frontend) "
                      "because alert(al_7f3) confidence [0.9, 0.2];")
        assert "0 <= lo <= hi <= 1" in result.lesson

    def test_unreal_revision_is_refused(self):
        result = gate("propose rollback(checkout, revision=v99) "
                      "because alert(al_7f3) confidence [0.7, 0.8];")
        assert "revision 'v99' is not a real older version" in result.lesson

    def test_real_revision_is_accepted(self):
        result = gate("propose rollback(checkout, revision=v41) "
                      "because alert(al_7f3) confidence [0.7, 0.8];")
        assert result.event == "llm_action_proposed"


# ----------------------------------------------------- the wax seal
class TestFingerprint:
    def test_cosmetic_whitespace_does_not_change_the_seal(self):
        one = parse(GOOD)
        two = parse("propose  restart_pod( web_frontend )   because "
                    "alert(al_7f3),log(lg_0192),metric(mem_web_p95) "
                    "confidence [0.72,0.88];")
        t = "2026-09-19T12:00:00+00:00"
        assert (make_action_hash("inc_1", one, t)
                == make_action_hash("inc_1", two, t))

    def test_any_real_difference_changes_the_seal(self):
        one = parse(GOOD)
        other = parse(GOOD.replace("[0.72, 0.88]", "[0.72, 0.89]"))
        t = "2026-09-19T12:00:00+00:00"
        assert (make_action_hash("inc_1", one, t)
                != make_action_hash("inc_1", other, t))

    def test_same_program_different_incident_different_seal(self):
        program = parse(GOOD)
        t = "2026-09-19T12:00:00+00:00"
        assert (make_action_hash("inc_1", program, t)
                != make_action_hash("inc_2", program, t))
