"""
gateway/tool_gateway.py
=======================
The TOOL GATEWAY -- the ONLY component that acts (step P4.3, T20-T22).

The bus driver with the only keys. Everyone else -- the AI, the
checkers, the Arbiter, the approval desk -- only writes notes and moves
a game piece. THIS component touches machines. And precisely because it
holds the keys, it is the most paranoid piece of the whole system:

  COMPARE-AND-EXECUTE  the world must still be the version Z3
                       photographed (incident.snapshot_version). Moved
                       on? REFUSE -- an approval for world v318 means
                       nothing in world v319 (stale_snapshot).
  IDEMPOTENCY          one fingerprint acts ONCE. A receipt already in
                       the book means the duplicate is refused.
  THE RIGHT PAPERS     risk low, or an approval slip bound to THIS
                       exact action_hash. A slip for another action is
                       worthless here (test P11).
  RECONCILE ON TIMEOUT the radio cut out? Call the school before
                       sending a second bus: read the receipt book;
                       only a confirmed "not done" becomes a failure.

Events (the state Action_Executed means "an action was REQUESTED"):
    execute             T20  Ready_For_Execution -> Action_Executed
    execution_succeeded T21  -> Verification
    execution_failed    T22  -> Recovery (refused / confirmed / not-done)
"""

from dataclasses import dataclass

from gateway.mockdriver import Receipt


@dataclass
class GatewayResult:
    """What the driver did with the order, and why."""

    event: str                    # "execution_succeeded" | "execution_failed"
    reason: str | None = None     # set on every refusal/failure
    receipt: Receipt | None = None
    reconciled: bool = False      # True if a timeout was settled by receipt


def check_and_execute(incident, driver, approval_token=None) -> GatewayResult:
    """
    The full T20-T22 step for one incident at Ready_For_Execution.

    The board itself guards T20 (only Ready_For_Execution may execute);
    everything after that is the driver's own paranoia.
    """
    program = incident.program

    # ------------------------------------------------ the papers (P11)
    # Low risk drives alone; high risk needs a slip for THIS fingerprint.
    if getattr(incident, "risk_level", None) != "low":
        if approval_token is None:
            return _refuse(incident, "no approval token for a high-risk action")
        if approval_token.action_hash != incident.action_hash:
            return _refuse(incident,
                           "approval slip is bound to a different action_hash")

    incident.machine.execute()          # T20 -> Action_Executed (requested)

    # ------------------------------------------- compare-and-execute
    pinned = getattr(incident, "snapshot_version", None)
    if pinned is None or driver.world_version() != pinned:
        incident.machine.execution_failed()          # T22 -> Recovery
        return GatewayResult(
            event="execution_failed",
            reason=f"stale_snapshot: world is v{driver.world_version()}, "
                   f"Z3 checked v{pinned}")

    # ------------------------------------------------- idempotency
    if driver.reconcile(incident.action_hash) is not None:
        incident.machine.execution_failed()          # T22 -> Recovery
        return GatewayResult(
            event="execution_failed",
            reason="duplicate: this action_hash already has a receipt")

    # ------------------------------------------------- the drive itself
    try:
        receipt = driver.execute(incident.action_hash, program.verb,
                                 program.target, dict(program.params))
    except TimeoutError:
        # the radio cut out: reconcile BEFORE declaring anything
        receipt = driver.reconcile(incident.action_hash)
        if receipt is not None:
            incident.machine.execution_succeeded()   # T21 (it really ran)
            return GatewayResult(event="execution_succeeded",
                                 receipt=receipt, reconciled=True)
        incident.machine.execution_failed()          # T22 (truly not done)
        return GatewayResult(event="execution_failed",
                             reason="timeout: reconciled and found not done",
                             reconciled=True)
    except PermissionError as exc:
        incident.machine.execution_failed()          # T22
        return GatewayResult(event="execution_failed",
                             reason=f"target refused: {exc}")
    except RuntimeError as exc:
        incident.machine.execution_failed()          # T22
        return GatewayResult(event="execution_failed",
                             reason=f"confirmed failure: {exc}")

    incident.machine.execution_succeeded()           # T21 -> Verification
    return GatewayResult(event="execution_succeeded", receipt=receipt)


def _refuse(incident, reason: str) -> GatewayResult:
    """A paper problem: the piece has NOT executed -- it goes through
    T20+T22 so the refusal lands in Recovery with its reason on file."""
    incident.machine.execute()
    incident.machine.execution_failed()
    return GatewayResult(event="execution_failed", reason=reason)
