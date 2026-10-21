"""
tests/test_audit.py -- step P5.4 done-criterion == tests P5 + P12.

"A complete story-1 diary is accepted; a diary with
 execution_succeeded jumping straight to Incident_Resolved is refused
 (L6/L7)."
"""

import json

import pytest

from audit.audit_service import DiaryRefused, open_diary
from sentinel.dsl.gate import check_proposal
from sentinel.intake.alerts import receive_alert
from sentinel.intake.llm import MockLLM

H = "sha256:" + "9f2c" + "0" * 60

# (event, actor) pairs of a complete Story-1 diary, in order.
STORY1_LINES = [
    ("alert_received", "intake", None),
    ("logs_parsed", "redactor", None),
    ("llm_action_proposed", "gate1", H),
    ("opa_allowed", "opa", H),
    ("datalog_clear", "datalog", H),
    ("prolog_allowed", "prolog", H),
    ("validation_passed", "ltl", H),
    ("risk_low", "arbiter", H),
    ("z3_sat", "z3", H),
    ("execute", "gateway", H),
    ("execution_succeeded", "gateway", H),
    ("metrics_healthy", "probe", H),
]


def incident_at_audit_logging():
    """A real incident carried to Audit_Logging (board-wise)."""
    inc = receive_alert({
        "alert_id": "al_7f3", "source": "mock_monitor",
        "service": "web_frontend", "metric": "mem_web_p95",
        "severity": "critical", "timestamp": "2026-09-26T10:00:00Z",
    })
    inc.machine.logs_parsed()
    gate = check_proposal(
        inc, MockLLM().propose("alert: al_7f3"),
        {"web_frontend": {"kind": "pod", "revisions": []}},
        {"al_7f3", "lg_0192", "mem_web_p95"})
    assert gate.event == "llm_action_proposed"
    inc.machine.opa_allowed()
    inc.machine.datalog_clear()
    inc.risk_level = "low"
    inc.machine.prolog_allowed()
    inc.machine.validation_passed()
    inc.machine.risk_low()
    inc.machine.z3_sat()
    inc.machine.execute()
    inc.machine.execution_succeeded()
    inc.machine.metrics_healthy()          # board now at Audit_Logging
    return inc


def written_story1_diary(inc, tmp_path):
    diary = open_diary(inc, tmp_path)
    for name, actor, action_hash in STORY1_LINES:
        diary.append(name, actor,
                     inc.action_hash if action_hash else None)
    return diary


# ------------------------------------------------------------- P5: closing
class TestClosingP5:
    def test_complete_story1_diary_is_accepted(self, tmp_path):
        """THE done-criterion, half one: the happy diary closes."""
        inc = incident_at_audit_logging()
        diary = written_story1_diary(inc, tmp_path)
        event = diary.close(inc)
        assert event["name"] == "audit_log_created"
        assert inc.machine.current_state.name == "Incident_Resolved"

    def test_diary_missing_the_checks_is_refused(self, tmp_path):
        """Half two: execution_succeeded jumping toward closing without
        the checker pages breaks L1 -- the diary refuses to close."""
        inc = incident_at_audit_logging()
        diary = open_diary(inc, tmp_path)
        diary.append("alert_received", "intake")
        diary.append("logs_parsed", "redactor")
        diary.append("llm_action_proposed", "gate1", inc.action_hash)
        diary.append("execute", "gateway", inc.action_hash)
        diary.append("execution_succeeded", "gateway", inc.action_hash)
        with pytest.raises(DiaryRefused, match="rule L1"):
            diary.close(inc)
        # and the board never moved:
        assert inc.machine.current_state.name == "Audit_Logging"

    def test_closing_writes_the_final_line(self, tmp_path):
        inc = incident_at_audit_logging()
        diary = written_story1_diary(inc, tmp_path)
        diary.close(inc)
        names = [e["name"] for e in diary.read_all()]
        assert names[-1] == "audit_log_created"


# ------------------------------------------------------------ P12: format
class TestFormatP12:
    def test_every_line_matches_trace_schema(self, tmp_path):
        inc = incident_at_audit_logging()
        diary = written_story1_diary(inc, tmp_path)
        for event in diary.read_all():
            assert set(event) == {"name", "timestamp", "phase",
                                  "action_hash", "actor", "payload"}
            assert 1 <= event["phase"] <= 5

    def test_unknown_event_name_is_refused(self, tmp_path):
        inc = incident_at_audit_logging()
        diary = open_diary(inc, tmp_path)
        with pytest.raises(DiaryRefused, match="vocabulary is closed"):
            diary.append("incident_fixed_trust_me", "gateway", H)

    def test_unauthorized_voice_is_refused(self, tmp_path):
        """The probe may not claim the Gateway's line -- and the AI has
        no voice at all (no event maps to an 'llm' actor)."""
        inc = incident_at_audit_logging()
        diary = open_diary(inc, tmp_path)
        with pytest.raises(DiaryRefused, match="belongs to 'gateway'"):
            diary.append("execute", "probe", H)
        from audit.audit_service import AUTHORIZED_ACTOR
        assert "llm" not in AUTHORIZED_ACTOR.values()

    def test_fingerprint_required_after_proposal(self, tmp_path):
        inc = incident_at_audit_logging()
        diary = open_diary(inc, tmp_path)
        with pytest.raises(DiaryRefused, match="requires an action_hash"):
            diary.append("opa_allowed", "opa", None)

    def test_phase_never_goes_backwards_for_one_fingerprint(self, tmp_path):
        """P16's discipline at the diary door."""
        inc = incident_at_audit_logging()
        diary = open_diary(inc, tmp_path)
        diary.append("llm_action_proposed", "gate1", H)
        diary.append("z3_sat", "z3", H)                    # phase 4
        with pytest.raises(DiaryRefused, match="backwards"):
            diary.append("opa_allowed", "opa", H)          # phase 2 again


# ------------------------------------------------------ pen, not pencil
class TestAppendOnly:
    def test_lines_accumulate_and_survive_reopening(self, tmp_path):
        inc = incident_at_audit_logging()
        diary = written_story1_diary(inc, tmp_path)
        reopened = open_diary(inc, tmp_path)      # a fresh handle
        assert len(reopened.read_all()) == len(STORY1_LINES)

    def test_the_module_offers_no_eraser(self):
        """Append-only by construction: no edit/delete exists at all."""
        from audit import audit_service
        from audit.audit_service import Diary
        forbidden = [name for name in dir(Diary) + dir(audit_service)
                     if any(word in name.lower()
                            for word in ("delete", "remove", "edit",
                                         "update", "rewrite", "truncate"))]
        assert forbidden == []

    def test_file_is_valid_jsonl(self, tmp_path):
        inc = incident_at_audit_logging()
        diary = written_story1_diary(inc, tmp_path)
        with diary.path.open() as fh:
            for line in fh:
                json.loads(line)          # every line parses alone
