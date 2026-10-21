"""
tests/test_mockdriver.py -- step P4.2 done-criterion.

"The driver can play: success, refuse, confirmed failure, and
 timeout-then-really-done (needed for P4.3 and test P4)."
"""

import pytest

from gateway.mockdriver import MockDriver
from gateway.system_map import demo_map

H = "sha256:" + "9f2c" + "0" * 60


# ------------------------------------------------------- the four behaviors
class TestBehaviors:
    def test_success_changes_world_and_leaves_receipt(self):
        world = demo_map()
        v0 = world.version
        driver = MockDriver(world)
        receipt = driver.execute(H, "restart_pod", "web_frontend")
        assert receipt.action_hash == H
        assert world.version == v0 + 1                # the heartbeat bumped
        assert driver.reconcile(H) is receipt

    def test_refuse_changes_nothing(self):
        world = demo_map()
        v0 = world.version
        driver = MockDriver(world, behavior=["refuse"])
        with pytest.raises(PermissionError):
            driver.execute(H, "restart_pod", "web_frontend")
        assert world.version == v0                    # untouched
        assert driver.reconcile(H) is None

    def test_confirmed_failure_changes_nothing(self):
        world = demo_map()
        driver = MockDriver(world, behavior=["fail"])
        with pytest.raises(RuntimeError, match="confirmed"):
            driver.execute(H, "restart_pod", "web_frontend")
        assert driver.reconcile(H) is None

    def test_timeout_but_done_the_sneaky_one(self):
        """The radio cut out -- but the bus arrived. Only the receipt
        book knows; the caller sees just a TimeoutError."""
        world = demo_map()
        v0 = world.version
        driver = MockDriver(world, behavior=["timeout_but_done"])
        with pytest.raises(TimeoutError):
            driver.execute(H, "restart_pod", "web_frontend")
        assert world.version == v0 + 1                # it DID happen
        assert driver.reconcile(H) is not None        # the receipt proves it

    def test_timeout_not_done(self):
        world = demo_map()
        v0 = world.version
        driver = MockDriver(world, behavior=["timeout_not_done"])
        with pytest.raises(TimeoutError):
            driver.execute(H, "restart_pod", "web_frontend")
        assert world.version == v0                    # nothing happened
        assert driver.reconcile(H) is None

    def test_behavior_script_runs_in_order(self):
        world = demo_map()
        driver = MockDriver(world, behavior=["fail", "success"])
        with pytest.raises(RuntimeError):
            driver.execute(H, "restart_pod", "web_frontend")
        receipt = driver.execute(H, "restart_pod", "web_frontend")
        assert receipt is not None                    # second try succeeded


# --------------------------------------------------------- effects on the map
class TestEffects:
    def test_scale_out_adds_delta_nodes(self):
        world = demo_map()
        driver = MockDriver(world)
        driver.execute(H, "scale_out", "checkout", {"delta": 3})
        assert world.services["checkout"].nodes == 8   # 5 + 3


# ------------------------------------------------- one world, three views
class TestThreeViews:
    def test_gate1_view_grounds_names_and_kinds(self):
        snap = demo_map().snapshot_for_gate1()
        assert snap["web_frontend"]["kind"] == "pod"
        assert snap["checkout"]["revisions"] == ["v41", "v42"]

    def test_datalog_view_walks_the_same_world(self):
        from sentinel.checkers.datalog import dependents, sensitive_target
        topo = demo_map().topology_for_datalog()
        # master_db falls -> auth_service and checkout fall -> web_frontend
        assert dependents(topo, "master_db") == 3
        assert sensitive_target(topo, "master_db") is True

    def test_z3_view_carries_the_version(self):
        world = demo_map()
        photo = world.live_snapshot_for_z3("web_frontend")
        assert photo.version == world.version
        assert photo.active_nodes == 4
        assert photo.min_capacity == 3
        world.bump()
        assert world.live_snapshot_for_z3("web_frontend").version == photo.version + 1

    def test_prolog_view_knows_stateful_and_critical(self):
        facts = demo_map().snapshot_facts_for_prolog()
        assert "master_db" in facts["stateful"]
        assert ("auth_service", "production_critical") in facts["tier"]
