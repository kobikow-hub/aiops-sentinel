"""
constraints/deployment_gate.py
==============================
Z3 -- THE LAST GATE, on live data (step P4.1, T18/T19; guide Part 11).

You got a yes at 5pm for a question asked at 2pm. Before leaving you
STILL look out the window -- maybe it started raining. Z3 is that last
look: it runs HERE, in Deploying, AFTER all decisions and approvals, on
a LIVE photo of the machines -- never earlier (instructor checkpoint (d),
time rule L9).

The three-step math (guide Part 11.2):
  BEFORE  is the system healthy enough to touch?
              nodes_before >= min_capacity
              (a rollback also needs the older version to exist)
  EFFECT  what the action does to the numbers -- taken from the DSL
          RULE BOOK (Part 5.2's action table), NEVER from the AI's words
  AFTER   do all safety rules still hold?
              nodes_after >= min_capacity
              nodes_after <= max_nodes
              cluster_nodes + (nodes_after - nodes_before) <= node_budget

sat   -> z3_sat  (T18) -> Ready_For_Execution, LOCKED to this photo's
         version number (the Gateway refuses if the world moved on)
unsat -> z3_unsat (T19) -> Blocked, with the UNSAT CORE -- the named
         rules that clash -- EVEN IF a human already approved.

Fail closed (T30): a broken/slow Z3 is a NO, never a shrug.
"""

from dataclasses import dataclass, field

import z3

Z3_TIMEOUT_MS = 5_000

# ---------------------------------------------------------------------------
# The EFFECT of each verb on the node count -- the DSL rule book's action
# table (guide Part 5.2), as pure data. The AI's text is never consulted.
#   delta_fn(params) -> the change in nodes_after relative to nodes_before
# ---------------------------------------------------------------------------
EFFECTS = {
    "restart_pod":       lambda p: -1,   # one pod away for a moment
    "restart_service":   lambda p: -1,
    "restart_master_db": lambda p: -1,   # (replica rule checked in BEFORE)
    "scale_out":         lambda p: int(p.get("delta", 1)),
    "rollback":          lambda p: 0,    # same size, older version
    "list_services":     lambda p: 0,    # read-only: touches nothing
    "get_metrics":       lambda p: 0,
}


@dataclass(frozen=True)
class LiveSnapshot:
    """The live photo, taken when entering Constraint_Check (11.1)."""

    version: int                  # the photo's serial number (compare-and-execute)
    active_nodes: int             # working machines of the target now
    min_capacity: int             # safety rule: at least this many must work
    max_nodes: int = 100
    cluster_nodes: int = 0        # machines used cluster-wide
    node_budget: int = 1_000_000  # cluster-wide ceiling
    revisions: tuple = ()         # older versions that really exist
    has_replica: bool = False     # for restart_master_db's BEFORE rule


@dataclass
class Z3Verdict:
    """The math checker's answer, with its work shown."""

    event: str                    # "z3_sat" | "z3_unsat" | "validation_failed"
    snapshot_version: int | None = None
    numbers: dict = field(default_factory=dict)
    unsat_core: list[str] = field(default_factory=list)  # the rules that clash
    checker_error: str | None = None


def deployment_gate(program, snapshot: LiveSnapshot) -> Z3Verdict:
    """
    The last look: BEFORE -> EFFECT -> AFTER on the live photo.
    Names every rule, so an unsat answer can say exactly which rules clash.
    """
    effect_fn = EFFECTS.get(program.verb)
    if effect_fn is None:
        return _fail_closed(f"no effect rule for verb '{program.verb}' "
                            f"in the DSL rule book")

    try:
        solver = z3.Solver()
        solver.set("timeout", Z3_TIMEOUT_MS)
        solver.set(unsat_core=True)

        nodes_before = z3.Int("nodes_before")
        nodes_after = z3.Int("nodes_after")

        # the photo's numbers (facts, tracked so cores can cite them)
        solver.assert_and_track(nodes_before == snapshot.active_nodes,
                                "world_nodes")
        # the EFFECT from the rule book
        delta = effect_fn(program.params)
        solver.assert_and_track(nodes_after == nodes_before + delta,
                                f"effect_{program.verb}")

        # BEFORE: healthy enough to touch?
        solver.assert_and_track(nodes_before >= snapshot.min_capacity,
                                "pre_min_capacity")
        if program.verb == "rollback":
            rev = program.params.get("revision")
            solver.assert_and_track(
                z3.BoolVal(rev in snapshot.revisions), "pre_revision_exists")
        if program.verb == "restart_master_db":
            solver.assert_and_track(
                z3.BoolVal(snapshot.has_replica), "pre_replica_exists")

        # AFTER: do all safety rules still hold?
        solver.assert_and_track(nodes_after >= snapshot.min_capacity,
                                "post_min_capacity")
        solver.assert_and_track(nodes_after <= snapshot.max_nodes,
                                "post_max_nodes")
        solver.assert_and_track(
            snapshot.cluster_nodes + (nodes_after - nodes_before)
            <= snapshot.node_budget, "post_node_budget")

        answer = solver.check()
    except z3.Z3Exception as exc:
        return _fail_closed(f"z3 crashed: {exc}")

    if answer == z3.sat:
        model = solver.model()
        return Z3Verdict(
            event="z3_sat", snapshot_version=snapshot.version,
            numbers={
                "nodes_before": model[nodes_before].as_long(),
                "nodes_after": model[nodes_after].as_long(),
                "min_capacity": snapshot.min_capacity,
            },
        )
    if answer == z3.unsat:
        core = sorted(str(name) for name in solver.unsat_core())
        return Z3Verdict(event="z3_unsat",
                         snapshot_version=snapshot.version,
                         numbers={
                             "nodes_before": snapshot.active_nodes,
                             "min_capacity": snapshot.min_capacity,
                         },
                         unsat_core=core)
    return _fail_closed("z3 answered 'unknown' (timeout?)")   # T30


def _fail_closed(reason: str) -> Z3Verdict:
    """T30: a broken or slow math checker is a NO, never a shrug."""
    return Z3Verdict(event="validation_failed", checker_error=reason)


def check_constraints(incident, snapshot: LiveSnapshot) -> Z3Verdict:
    """
    The full T18/T19 step for one incident at Constraint_Check: run the
    last look, move the board, and pin the photo version on the case
    folder -- the Gateway will refuse if the world moved past it (P4.3).
    """
    verdict = deployment_gate(incident.program, snapshot)

    if verdict.event == "z3_sat":
        incident.snapshot_version = snapshot.version   # the pin
        incident.machine.z3_sat()                      # T18 -> Ready_For_Execution
    elif verdict.event == "z3_unsat":
        incident.machine.z3_unsat()                    # T19 -> Blocked
    else:
        incident.machine.validation_failed()           # T30 -> Blocked

    return verdict
