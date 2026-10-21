"""
tests/test_intake.py -- step P1.1 done-criterion.

"A good alert moves the board Awaiting_Alert -> Alert_Parsed;
 a malformed one is rejected and logged."
"""

import logging

import pytest

from board.incident_machine import IncidentMachine
from sentinel.intake.alerts import AlertRejected, receive_alert, validate_alert


def good_alert(**overrides) -> dict:
    """The Story-1 style letter: web_frontend is out of memory."""
    alert = {
        "alert_id": "al_7f3",
        "source": "mock_monitor",
        "service": "web_frontend",
        "metric": "mem_web_p95",
        "severity": "critical",
        "timestamp": "2026-09-19T12:00:00Z",
    }
    alert.update(overrides)
    return alert


# ---------------------------------------------------------------- good mail
class TestGoodAlert:
    def test_good_alert_moves_board_to_alert_parsed(self):
        incident = receive_alert(good_alert())
        assert incident.machine.current_state.name == "Alert_Parsed"

    def test_good_alert_gets_unique_incident_ids(self):
        a = receive_alert(good_alert())
        b = receive_alert(good_alert())
        assert a.incident_id != b.incident_id

    def test_validate_returns_no_problems_for_good_alert(self):
        assert validate_alert(good_alert()) == []


# ---------------------------------------------------------------- junk mail
class TestJunkMail:
    def test_missing_field_is_rejected(self):
        letter = good_alert()
        del letter["service"]
        with pytest.raises(AlertRejected, match="missing required field 'service'"):
            receive_alert(letter)

    def test_wrong_kind_is_rejected(self):
        with pytest.raises(AlertRejected, match="'severity' must be str"):
            receive_alert(good_alert(severity=5))

    def test_unknown_monitor_is_rejected(self):
        with pytest.raises(AlertRejected, match="unknown monitor 'stranger'"):
            receive_alert(good_alert(source="stranger"))

    def test_unknown_severity_is_rejected(self):
        with pytest.raises(AlertRejected, match="unknown severity"):
            receive_alert(good_alert(severity="apocalyptic"))

    def test_non_dict_is_rejected(self):
        with pytest.raises(AlertRejected, match="must be a mapping"):
            receive_alert("web_frontend is down!!")

    def test_rejection_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="sentinel.intake"):
            with pytest.raises(AlertRejected):
                receive_alert(good_alert(source="stranger"))
        assert any("alert rejected" in r.message for r in caplog.records)


# ------------------------------------------------------------- board safety
class TestBoardRules:
    def test_board_starts_at_awaiting_alert(self):
        assert IncidentMachine().current_state.name == "Awaiting_Alert"

    def test_alert_received_cannot_fire_twice(self):
        """T1 exists only FROM Awaiting_Alert -- the board forbids a replay."""
        incident = receive_alert(good_alert())
        with pytest.raises(Exception):
            incident.machine.alert_received()
