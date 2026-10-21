"""
tests/test_redactor.py -- step P1.2 done-criterion.

"A log line containing a fake password comes out with the password
 masked; the event logs_parsed carries Redaction_Applied."

All secrets below are FAKE test values, invented for these tests.
"""

from sentinel.intake.alerts import receive_alert
from sentinel.intake.redactor import MASK, parse_logs, redact_line, redact_logs


def good_alert() -> dict:
    return {
        "alert_id": "al_7f3",
        "source": "mock_monitor",
        "service": "web_frontend",
        "metric": "mem_web_p95",
        "severity": "critical",
        "timestamp": "2026-09-19T12:00:00Z",
    }


# ---------------------------------------------------------------- the marker
class TestBlackMarker:
    def test_password_is_masked(self):
        safe, hits = redact_line("db connect failed: password=hunter2 host=db1")
        assert "hunter2" not in safe
        assert MASK in safe
        assert hits == 1

    def test_label_survives_only_secret_is_masked(self):
        safe, _ = redact_line("retry with password=hunter2")
        assert "password=" in safe          # a human still sees WHAT was there

    def test_api_key_and_token_are_masked(self):
        safe, hits = redact_line(
            "calling api_key=sk_test_abc123 with token: xyz789"
        )
        assert "sk_test_abc123" not in safe
        assert "xyz789" not in safe
        assert hits == 2

    def test_bearer_header_is_masked(self):
        safe, _ = redact_line("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.pay.load")
        assert "eyJhbGciOiJIUzI1NiJ9.pay.load" not in safe

    def test_aws_key_id_is_masked(self):
        safe, _ = redact_line("using key AKIAIOSFODNN7EXAMPLE for s3")
        assert "AKIAIOSFODNN7EXAMPLE" not in safe

    def test_email_is_masked(self):
        safe, _ = redact_line("user dana.sre@example.com reported the outage")
        assert "dana.sre@example.com" not in safe

    def test_clean_line_is_untouched(self):
        line = "web_frontend mem_p95=91% threshold=85% for 5m"
        safe, hits = redact_line(line)
        assert safe == line
        assert hits == 0


# ------------------------------------------------------------- context filter
class TestContextFilter:
    def test_only_allowed_services_survive(self):
        lines = [
            "web_frontend: OOMKilled, restarting",
            "billing: nightly invoice run started",     # unrelated service
        ]
        result = redact_logs(lines, allowed_services={"web_frontend"})
        assert len(result.lines) == 1
        assert "web_frontend" in result.lines[0]
        assert result.lines_dropped == 1

    def test_no_allowed_list_keeps_everything(self):
        result = redact_logs(["a: ok", "b: ok"])
        assert len(result.lines) == 2
        assert result.lines_dropped == 0


# ------------------------------------------------- T2: board + event payload
class TestParseLogsT2:
    def test_logs_parsed_event_carries_redaction_applied(self):
        incident = receive_alert(good_alert())
        event = parse_logs(
            incident, ["web_frontend restart: password=hunter2"]
        )
        assert event["event"] == "logs_parsed"
        assert event["payload"]["Redaction_Applied"] is True
        assert event["payload"]["redaction_count"] == 1

    def test_board_moves_to_ai_analysis(self):
        incident = receive_alert(good_alert())
        parse_logs(incident, ["web_frontend: OOMKilled"])
        assert incident.machine.current_state.name == "AI_Analysis"

    def test_incident_keeps_only_safe_logs(self):
        incident = receive_alert(good_alert())
        parse_logs(incident, ["web_frontend: password=hunter2"])
        assert all("hunter2" not in line for line in incident.safe_logs)

    def test_clean_logs_mean_redaction_applied_false(self):
        incident = receive_alert(good_alert())
        event = parse_logs(incident, ["web_frontend: mem 91%"])
        assert event["payload"]["Redaction_Applied"] is False
