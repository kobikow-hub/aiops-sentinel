"""
tests/test_web.py -- step P5.5 done-criterion (+ tests P1 and P2's heart).

"All three demo stories run from the browser and end in the exact
 final states the guide's Part 13 shows."

The TestClient drives the REAL app: real OPA, real SWI-Prolog, real Z3,
real Gateway, real diary. Stories run in a background thread; tests
poll /api/state exactly like the browser does.
"""

import time

import pytest
from fastapi.testclient import TestClient

import web.app as webapp

client = TestClient(webapp.app)


@pytest.fixture(autouse=True)
def fast_and_fresh(monkeypatch):
    """No stage delays in tests; every test starts with an empty stage."""
    monkeypatch.setattr(webapp, "STORY_DELAY", 0)
    webapp.CURRENT = None


def wait_until(predicate, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get("/api/state").json()
        if predicate(state):
            return state
        time.sleep(0.1)
    raise AssertionError(f"timed out; last state: {state}")


def run_story(n, until="finished"):
    assert client.post(f"/api/story/{n}").status_code == 200
    return wait_until(lambda s: s["status"] in (until, "error"))


# ---------------------------------------------------- Story 1 (test P1)
class TestStory1:
    def test_happy_road_reaches_incident_resolved(self):
        state = run_story(1)
        assert state["status"] == "finished", state["error"]
        assert state["current_state"] == "Incident_Resolved"

    def test_diary_tells_the_whole_story_in_order(self):
        run_story(1)
        names = [e["name"] for e in client.get("/api/diary").json()]
        assert names == [
            "alert_received", "logs_parsed", "llm_action_proposed",
            "opa_allowed", "datalog_clear", "prolog_allowed",
            "validation_passed", "risk_low", "z3_sat", "execute",
            "execution_succeeded", "metrics_healthy", "audit_log_created"]

    def test_tracker_lit_every_station(self):
        state = run_story(1)
        visited = [t["step"] for t in state["timeline"]]
        assert visited == ["intake", "ai", "gate1", "opa", "datalog",
                           "prolog", "ltl", "route", "z3", "gateway",
                           "probe", "diary"]

    def test_every_stage_names_its_engine_file(self):
        state = run_story(1)
        assert all(t["engine"] for t in state["timeline"])
        prolog_stage = next(t for t in state["timeline"]
                            if t["step"] == "prolog")
        assert "prolog_adapter.py" in prolog_stage["engine"]


# ---------------------------------------------------- Story 2 (test P2)
class TestStory2:
    def test_blocked_then_human_resolution_closes_lawfully(self):
        state = run_story(2, until="waiting_human")
        assert state["status"] == "waiting_human"
        assert state["current_state"] == "Escalated"
        # the escalation screen shows Datalog's OWN words:
        datalog = state["escalation_packet"]["checker_reasons"]["datalog"]
        assert datalog["reason"] == "blast_radius"
        assert datalog["dependents"] == 40

        # the human owner records the fix (T28):
        response = client.post("/api/resolve", json={
            "resolved_by": "dana", "note": "failed over to replica"})
        assert response.status_code == 200
        state = wait_until(lambda s: s["status"] == "finished")
        assert state["current_state"] == "Incident_Resolved"

        names = [e["name"] for e in client.get("/api/diary").json()]
        assert "datalog_sensitive_path" in names
        assert "escalation_notified" in names
        assert "human_resolution_recorded" in names
        assert names[-1] == "audit_log_created"
        # P2's heart: nothing was executed -- no gateway lines at all
        assert "execute" not in names

    def test_resolution_needs_a_waiting_incident(self):
        response = client.post("/api/resolve", json={
            "resolved_by": "dana", "note": "nothing to fix"})
        assert response.status_code == 409


# ---------------------------------------------------- Story 3 (L1 live)
class TestStory3:
    def test_wrong_order_is_refused_by_rule_L1(self):
        state = run_story(3)
        assert state["status"] == "finished"
        assert state["refusal"]["violated_rule"] == "L1"
        assert "never act unless" in state["refusal"]["in_simple_words"]
        assert state["refusal"]["last_diary_steps"][-1] == "llm_action_proposed"

    def test_board_never_left_action_proposed(self):
        state = run_story(3)
        assert state["current_state"] == "Action_Proposed"
        names = [e["name"] for e in client.get("/api/diary").json()]
        assert "execute" not in names          # the crime never happened


# ------------------------------------------- the refs map + source viewer
class TestTrackerRefs:
    def test_every_station_carries_its_reference_map(self):
        steps = client.get("/api/state").json()["steps"]
        for step in steps:
            refs = step["refs"]
            assert refs["called_by"], step["key"]
            assert refs["tests"], step["key"]
            assert "board_moves" in refs, step["key"]

    def test_the_ai_station_has_no_diary_voice(self):
        steps = client.get("/api/state").json()["steps"]
        ai = next(s for s in steps if s["key"] == "ai")
        assert ai["refs"]["diary_events"] == []

    def test_every_station_carries_a_one_line_summary(self):
        steps = client.get("/api/state").json()["steps"]
        for step in steps:
            assert step.get("summary"), step["key"]
            assert "\n" not in step["summary"]        # one line, really


class TestHighRiskApproval:
    """The approval alarm: high-risk pauses, YES continues to the end,
    NO blocks and summons an owner, silence escalates (30s SLA)."""

    def start_high_risk_story1(self, monkeypatch):
        """Make Story 1 high-risk by making its target stateful."""
        original = webapp.demo_map

        def stateful_world():
            world = original()
            world.services["web_frontend"].stateful = True
            return world
        monkeypatch.setattr(webapp, "demo_map", stateful_world)
        return run_story(1, until="waiting_human")

    def test_approval_pauses_with_countdown(self, monkeypatch):
        state = self.start_high_risk_story1(monkeypatch)
        assert state["current_state"] == "Human_Approval_Required"
        assert state["approval_packet"]["prolog"]["risk_level"] == "high"
        assert 0 < state["approval_seconds_left"] <= 30
        assert state["approval_sla_seconds"] == 30

    def test_approve_continues_to_incident_resolved(self, monkeypatch):
        self.start_high_risk_story1(monkeypatch)
        response = client.post("/api/approve", json={
            "approver_id": "dana", "approver_role": "sre"})
        assert response.status_code == 200
        state = wait_until(lambda s: s["status"] == "finished")
        assert state["current_state"] == "Incident_Resolved"
        names = [e["name"] for e in client.get("/api/diary").json()]
        assert "human_approved" in names
        assert "z3_sat" in names                  # L9: fresh check ran
        assert names[-1] == "audit_log_created"

    def test_reject_blocks_and_summons_an_owner(self, monkeypatch):
        self.start_high_risk_story1(monkeypatch)
        response = client.post("/api/reject", json={
            "approver_id": "dana", "approver_role": "sre"})
        assert response.status_code == 200
        state = client.get("/api/state").json()
        assert state["status"] == "waiting_human"
        assert state["escalation_packet"] is not None
        # the owner closes it:
        client.post("/api/resolve", json={
            "resolved_by": "dana", "note": "handled manually"})
        state = wait_until(lambda s: s["status"] == "finished")
        assert state["current_state"] == "Incident_Resolved"
        names = [e["name"] for e in client.get("/api/diary").json()]
        assert "human_rejected" in names
        assert "execute" not in names             # the NO changed nothing

    def test_silence_escalates_via_the_sla_timer(self, monkeypatch):
        monkeypatch.setattr(webapp, "APPROVAL_SLA_SECONDS", 0.5)
        self.start_high_risk_story1(monkeypatch)
        state = wait_until(lambda s: s.get("escalation_packet") is not None,
                           timeout=10)
        assert state["current_state"] == "Escalated"
        assert state["approval_packet"] is None   # the slip window closed
        names = [e["name"] for e in client.get("/api/diary").json()]
        assert "approval_timeout" in names
        assert "escalation_notified" in names

    def test_the_launchpad_variant_reaches_the_alarm(self):
        """The Story-1b button (?high_risk=true): no monkeypatching --
        the endpoint itself makes the target stateful, Prolog rules
        HIGH, and the pipeline pauses at the approval alarm."""
        r = client.post("/api/story/1", params={"high_risk": "true"})
        assert r.status_code == 200 and r.json()["high_risk"] is True
        state = wait_until(lambda s: s["status"] in
                           ("waiting_human", "error"))
        assert state["status"] == "waiting_human", state["error"]
        assert state["current_state"] == "Human_Approval_Required"
        assert state["approval_packet"]["prolog"]["risk_level"] == "high"
        assert 0 < state["approval_seconds_left"] <= 30

    def test_the_variant_exists_only_for_story_1(self):
        r = client.post("/api/story/2", params={"high_risk": "true"})
        assert r.status_code == 400


class TestTraceAndTree:
    def test_state_carries_the_board_trace(self):
        state = run_story(1)
        trace = state["trace"]
        assert trace[0] == {"event": "alert_received",
                            "from": "Awaiting_Alert", "to": "Alert_Parsed"}
        assert trace[-1]["to"] == "Incident_Resolved"
        assert state["last_transition"].endswith("Incident_Resolved")

    def test_tree_lists_annotated_project_files(self):
        tree = client.get("/api/tree").json()["tree"]
        assert "@[incident_machine.py|board/incident_machine.py]" in tree
        assert "the only boss" in tree            # a directory note
        assert "tools/opa.exe" not in tree        # tools/ excluded
        assert "@[opa.exe" not in tree            # the binary is not listed


class TestSourceViewer:
    def test_project_file_is_served(self):
        response = client.get("/api/source",
                              params={"path": "ltl/rules.py"})
        assert response.status_code == 200
        body = response.json()
        assert body["path"] == "ltl/rules.py"
        assert "L1" in body["content"]

    def test_escape_outside_the_project_is_refused(self):
        response = client.get("/api/source",
                              params={"path": "../../secrets.txt"})
        assert response.status_code == 403

    def test_absolute_path_is_refused(self):
        response = client.get("/api/source",
                              params={"path": "C:/Windows/win.ini"})
        assert response.status_code == 403

    def test_non_source_suffix_is_refused(self):
        response = client.get("/api/source",
                              params={"path": "tools/opa.exe"})
        assert response.status_code == 403

    def test_missing_file_is_404(self):
        response = client.get("/api/source",
                              params={"path": "sentinel/ghost.py"})
        assert response.status_code == 404


# ---------------------------------------------------- the dumb-GUI rules
class TestStageRules:
    def test_only_three_stories_exist(self):
        assert client.post("/api/story/4").status_code == 404

    def test_no_double_booking_while_running(self, monkeypatch):
        monkeypatch.setattr(webapp, "STORY_DELAY", 0.3)
        client.post("/api/story/1")
        assert client.post("/api/story/1").status_code == 409
        wait_until(lambda s: s["status"] == "finished")

    def test_approve_endpoint_refuses_when_nobody_waits(self):
        response = client.post("/api/approve", json={})
        assert response.status_code == 409
