"""
gateway/mockdriver.py
=====================
The MOCKDRIVER (step P4.2) -- the model railway's toy trains.

The driver is what the Tool Gateway (P4.3) will hold the keys to. This
pretend one runs actions against the SystemMap -- and, on command, can
play every failure the real world knows:

    "success"          the action works; the map changes; version bumps
    "refuse"           the target refuses (e.g. API said no); no change
    "fail"             CONFIRMED failure: tried, broke, world unchanged
    "timeout_but_done" the sneaky one: the radio cuts out (we get a
                       TimeoutError) but the action ACTUALLY HAPPENED --
                       exactly what reconcile-on-timeout must catch
    "timeout_not_done" the radio cuts out and nothing happened

Every completed action leaves a RECEIPT keyed by action_hash -- that is
what reconcile() reads to answer "did it really happen?", and what makes
idempotency checkable (the same fingerprint never acts twice).
"""

from dataclasses import dataclass, field

from gateway.system_map import SystemMap


@dataclass
class Receipt:
    """Proof one action really ran, keyed by its fingerprint."""

    action_hash: str
    verb: str
    target: str
    world_version_after: int


class MockDriver:
    """The toy trains. behavior is a script: one entry per call, in order."""

    def __init__(self, system_map: SystemMap, behavior: list[str] | None = None):
        self.map = system_map
        self.behavior = list(behavior or [])       # pop(0) per call
        self.receipts: dict[str, Receipt] = {}     # action_hash -> Receipt
        self.calls: list[tuple] = []               # everything ever asked

    # ------------------------------------------------------------ the work
    def _apply(self, verb: str, target: str, params: dict) -> None:
        """Actually change the pretend world (the EFFECT, for real now)."""
        s = self.map.services[target]
        if verb in ("restart_pod", "restart_service", "restart_master_db"):
            s.healthy = True                        # the fix worked
        elif verb == "scale_out":
            s.nodes += int(params.get("delta", 1))
        elif verb == "rollback":
            pass                                    # same size, older version
        self.map.bump()                             # the heartbeat

    def execute(self, action_hash: str, verb: str, target: str,
                params: dict | None = None) -> Receipt:
        """
        Run one action. Raises:
            PermissionError  on "refuse"
            RuntimeError     on "fail" (confirmed: nothing changed)
            TimeoutError     on both timeout flavors -- the caller cannot
                             tell them apart; only reconcile() can.
        """
        params = params or {}
        self.calls.append((action_hash, verb, target))
        mode = self.behavior.pop(0) if self.behavior else "success"

        if mode == "refuse":
            raise PermissionError(f"{target} refused {verb}")
        if mode == "fail":
            raise RuntimeError(f"{verb} on {target} failed (confirmed)")
        if mode == "timeout_but_done":
            # the sneaky one: do the work, write the receipt, THEN lose
            # the radio -- the caller sees only the TimeoutError
            self._apply(verb, target, params)
            self.receipts[action_hash] = Receipt(
                action_hash, verb, target, self.map.version)
            raise TimeoutError(f"{verb} on {target}: no answer")
        if mode == "timeout_not_done":
            raise TimeoutError(f"{verb} on {target}: no answer")

        self._apply(verb, target, params)
        receipt = Receipt(action_hash, verb, target, self.map.version)
        self.receipts[action_hash] = receipt
        return receipt

    # -------------------------------------------------------- the questions
    def reconcile(self, action_hash: str) -> Receipt | None:
        """'Did it really happen?' -- the office CALLS the school before
        sending a second bus. Reads the receipt book, changes nothing."""
        return self.receipts.get(action_hash)

    def world_version(self) -> int:
        """The world's current heartbeat (for compare-and-execute)."""
        return self.map.version
