"""
sentinel/decide/approval.py
===========================
The APPROVAL SERVICE -- one-time permission slips (step P3.2, T15/T16).

The principal signs a slip for ONE exact field trip, expiring at the end
of the day. A slip for the zoo does not work for the pool, a photocopy
does not count, and yesterday's slip is worthless.

How it works (guide Part 14):
  * The approval screen shows the CHECKERS' OWN reasons -- Datalog's
    paths, Prolog's proof, OPA's route. Honest explanations: the AI does
    not write the story afterwards.
  * A decision enters the board only as a standard event:
        human_approved (T15) -> Constraint_Check
        human_rejected (T16) -> Blocked  (+ remembered as rejected_before/2)
  * OPA checks the slip (approval_valid): right role (sre/admin), same
    fingerprint, not expired, never used before. A broken slip produces
    NO EVENT AT ALL -- the system keeps waiting (until P3.3's timer).
  * A human approves the IDEA, not the world: after human_approved the
    program STILL goes through Z3 on a live photo (rule L9, Phase 4).
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sentinel.checkers.opa_adapter import eval_opa

APPROVAL_TTL_MINUTES = 30       # a slip is good for one short while


@dataclass
class ApprovalToken:
    """One permission slip: one fingerprint, one expiry, one use."""

    token_id: str
    action_hash: str
    approver_id: str
    approver_role: str
    expires_at: str              # ISO text, UTC
    used: bool = False


@dataclass
class ApprovalOutcome:
    """What the approval desk did with one answer."""

    event: str | None            # "human_approved" | "human_rejected" | None
    reasons: list[str] = field(default_factory=list)   # why a slip was refused


def review_packet(incident, opa_verdict=None, datalog_verdict=None,
                  prolog_verdict=None, route_decision=None) -> dict:
    """
    Everything the approval screen shows -- the checkers' OWN words,
    collected; never a summary the AI wrote.
    """
    return {
        "incident_id": incident.incident_id,
        "action_hash": incident.action_hash,
        "program": {
            "verb": incident.program.verb,
            "target": incident.program.target,
            "confidence": list(incident.program.confidence),
        },
        "opa": {"deny": opa_verdict.deny if opa_verdict else []},
        "datalog": {
            "dependents": datalog_verdict.dependents if datalog_verdict else 0,
            "paths": datalog_verdict.paths if datalog_verdict else [],
        },
        "prolog": {
            "risk_level": getattr(incident, "risk_level", None),
            "proof": prolog_verdict.proof if prolog_verdict else [],
        },
        "route": route_decision.route if route_decision else "require_approval",
    }


def issue_token(incident, approver_id: str, approver_role: str,
                now: datetime | None = None) -> ApprovalToken:
    """Sign a fresh slip for THIS incident's exact fingerprint."""
    now = now or datetime.now(timezone.utc)
    return ApprovalToken(
        token_id=secrets.token_hex(8),
        action_hash=incident.action_hash,
        approver_id=approver_id,
        approver_role=approver_role,
        expires_at=(now + timedelta(minutes=APPROVAL_TTL_MINUTES))
        .isoformat().replace("+00:00", "Z"),
    )


def validate_token(token: ApprovalToken, action_hash: str) -> tuple[bool, list[str]]:
    """Ask OPA: is this slip real? (role, fingerprint, expiry, reuse)."""
    verdict, error = eval_opa("data.sentinel.authz", {
        "approver": {"id": token.approver_id, "role": token.approver_role},
        "approval": {
            "action_hash": token.action_hash,
            "expires_at": token.expires_at,
            "used": token.used,
        },
        "action_hash": action_hash,
    })
    if error is not None:
        # The desk cannot verify the slip -> the slip does not count.
        # No event; the system keeps waiting (the timer ends it, P3.3).
        return False, [f"could not verify the approval: {error}"]
    return bool(verdict.get("approval_valid")), sorted(
        verdict.get("approval_denied", []))


def submit_decision(incident, token: ApprovalToken, decision: str,
                    rejected_registry: list | None = None) -> ApprovalOutcome:
    """
    The full T15/T16 desk for one incident at Human_Approval_Required.

    decision: "approve" | "reject", coming from the screen's two buttons.
    Only a VALID slip produces an event; every broken slip produces
    nothing and the board keeps waiting.
    """
    valid, reasons = validate_token(token, incident.action_hash)
    if not valid:
        return ApprovalOutcome(event=None, reasons=reasons)

    token.used = True            # one slip, one use -- spent either way

    if decision == "approve":
        incident.machine.human_approved()        # T15 -> Constraint_Check
        return ApprovalOutcome(event="human_approved")

    # A rejection is remembered: the same action counts as high risk
    # forever after (Prolog's rejected_before/2, fed in at P2.3).
    if rejected_registry is not None:
        rejected_registry.append(
            (incident.program.verb, incident.program.target))
    incident.machine.human_rejected()            # T16 -> Blocked
    return ApprovalOutcome(event="human_rejected")
