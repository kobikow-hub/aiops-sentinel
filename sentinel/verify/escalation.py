"""
sentinel/verify/escalation.py
=============================
ESCALATION + the notifier (step P5.3, T27/T28; guide Part 9 + Part 14).

When a guard says NO, or the retries ran dry, or nobody answered the
door -- a grown-up takes over. Two rules make this module:

  HONEST HANDOVER  the SRE receives the checkers' OWN explanations --
                   OPA deny reasons, Datalog domino paths, Prolog's
                   written proof, Z3's unsat core, the LTL rule number,
                   the retry history with every lesson. Never a summary
                   the AI wrote afterwards.
  REAL RESOLUTION  the incident is "done" only when the human says the
                   PROBLEM ITSELF is fixed (human_resolution_recorded,
                   T28) -- and even then it closes through the diary
                   like every other incident (rule L7). Escalation is
                   a handover, never a shortcut.

Three roads lead here (all already live on the board):
    Blocked   -> escalation_notified (T27)  a checker's NO
    Recovery  -> retries_exhausted   (T26)  out of tries      (P5.2)
    Waiting   -> approval_timeout    (T17)  nobody answered   (P3.3)
T27 is sent by THIS module -- notification and the move are one act,
so an incident can never sit in Escalated with nobody told.

The notifier itself is an interface (like LLMInterface): today a
console/list notifier for the demo; Slack/email plug in later behind
the same one-method costume.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


# ---------------------------------------------------------------------------
# The handover file: the checkers' own words, collected -- never rewritten.
# ---------------------------------------------------------------------------
def build_escalation_packet(incident, *, trigger,
                            opa_verdict=None, datalog_verdict=None,
                            prolog_verdict=None, ltl_verdict=None,
                            z3_verdict=None, gateway_result=None) -> dict:
    """
    Everything the SRE needs to OWN the incident, in the original
    voices. `trigger` names which road brought us here:
    "checker_no" | "retries_exhausted" | "approval_timeout".
    """
    program = getattr(incident, "program", None)
    packet = {
        "incident_id": incident.incident_id,
        "action_hash": getattr(incident, "action_hash", None),
        "trigger": trigger,
        "alert": incident.alert,
        "proposal": None if program is None else {
            "verb": program.verb,
            "target": program.target,
            "params": dict(program.params),
            "confidence": list(program.confidence),
        },
        "checker_reasons": {},
        "retry_history": [
            {"reason": r.reason, "counterexample": r.counterexample,
             "attempt": r.retry_number}
            for r in getattr(incident, "recovery_history", [])
        ],
    }

    reasons = packet["checker_reasons"]
    if opa_verdict is not None:
        reasons["opa_deny"] = list(opa_verdict.deny)
        if opa_verdict.checker_error:
            reasons["opa_error"] = opa_verdict.checker_error
    if datalog_verdict is not None:
        reasons["datalog"] = {
            "reason": datalog_verdict.reason,
            "dependents": datalog_verdict.dependents,
            "paths": list(datalog_verdict.paths),
        }
    if prolog_verdict is not None:
        reasons["prolog"] = {
            "risk_level": prolog_verdict.risk_level,
            "why_refused": list(prolog_verdict.why_refused),
            "proof": list(prolog_verdict.proof),
        }
    if ltl_verdict is not None:
        reasons["ltl"] = {
            "violated_rule": ltl_verdict.violated_rule,
            "in_simple_words": ltl_verdict.simple,
            "last_diary_steps": list(ltl_verdict.last_steps),
        }
    if z3_verdict is not None:
        reasons["z3"] = {
            "unsat_core": list(z3_verdict.unsat_core),
            "numbers": dict(z3_verdict.numbers),
        }
    if gateway_result is not None:
        reasons["gateway"] = {"reason": gateway_result.reason}

    return packet


# ---------------------------------------------------------------------------
# The notifier costume + the demo actor wearing it.
# ---------------------------------------------------------------------------
class NotifierInterface(Protocol):
    """Any doorbell that can deliver one escalation packet fits."""

    def notify(self, packet: dict) -> None: ...


class ConsoleNotifier:
    """The demo doorbell: prints and remembers. Slack comes later."""

    def __init__(self):
        self.delivered: list[dict] = []

    def notify(self, packet: dict) -> None:
        self.delivered.append(packet)
        reasons = ", ".join(packet["checker_reasons"]) or "none recorded"
        print(f"[ESCALATION] incident={packet['incident_id']} "
              f"trigger={packet['trigger']} checker_reasons=[{reasons}]")


# ---------------------------------------------------------------------------
# T27 + T28.
# ---------------------------------------------------------------------------
@dataclass
class EscalationRecord:
    """Proof of the handover (T27) and, later, the resolution (T28)."""

    packet: dict
    notified_at: str
    resolved: bool = False
    resolved_by: str | None = None
    resolution_note: str | None = None
    resolved_at: str | None = None


def escalate(incident, notifier, *, trigger, **verdicts) -> EscalationRecord:
    """
    The full T27 step for one incident at Blocked: build the honest
    packet, DELIVER it, and only then move Blocked -> Escalated.
    (For the T17/T26 roads the board is already at Escalated; this
    function is the Blocked-road entry -- see notify_escalated below.)
    """
    packet = build_escalation_packet(incident, trigger=trigger, **verdicts)
    notifier.notify(packet)                       # tell a human FIRST
    incident.machine.escalation_notified()        # T27 -> Escalated
    record = EscalationRecord(
        packet=packet,
        notified_at=datetime.now(timezone.utc).isoformat(),
    )
    incident.escalation = record
    return record


def notify_escalated(incident, notifier, *, trigger, **verdicts) -> EscalationRecord:
    """
    The doorbell for incidents ALREADY standing at Escalated (via
    approval_timeout T17 or retries_exhausted T26): same honest packet,
    no board move needed.
    """
    packet = build_escalation_packet(incident, trigger=trigger, **verdicts)
    notifier.notify(packet)
    record = EscalationRecord(
        packet=packet,
        notified_at=datetime.now(timezone.utc).isoformat(),
    )
    incident.escalation = record
    return record


def record_human_resolution(incident, resolved_by: str, note: str) -> EscalationRecord:
    """
    The full T28 step: a person says the PROBLEM ITSELF is fixed.
    Moves Escalated -> Audit_Logging -- the diary still comes before
    any closing (rule L7). Requires a name and a real note: an
    anonymous or empty resolution is no resolution.
    """
    if not resolved_by or not resolved_by.strip():
        raise ValueError("a human resolution needs the resolver's name")
    if not note or not note.strip():
        raise ValueError("a human resolution needs a note saying what "
                         "was actually done")

    record = getattr(incident, "escalation", None)
    if record is None:
        raise RuntimeError("no escalation record -- the handover (T27 "
                           "or the timeout/exhaustion roads) comes first")

    record.resolved = True
    record.resolved_by = resolved_by.strip()
    record.resolution_note = note.strip()
    record.resolved_at = datetime.now(timezone.utc).isoformat()

    incident.machine.human_resolution_recorded()   # T28 -> Audit_Logging
    return record
