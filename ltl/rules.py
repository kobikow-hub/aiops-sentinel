"""
ltl/rules.py
============
The TIME RULES L1-L15 (step P2.4, guide Part 8.3/8.4).

Some rules are not about one step but about the ORDER of steps:
"always wash your hands BEFORE eating". Each rule here is one law from
the guide's table, with:

    id     -- L1..L15
    scope  -- which diary pages it looks at (guide Part 8.5):
              "action"   only the pages of ONE fingerprint
              "incident" the whole incident's diary
              "episode"  restart memory ACROSS incidents (L12)
    kind   -- "safety" (bad never happens) | "liveness" (good eventually
              happens; only meaningful on a finished diary)
    holds(steps, world) -> True, or the index where it breaks

Scoping is the trick that stops one action from BORROWING another
action's approval: an answer given to a different fingerprint never
counts (guide Part 8.2, "flag" words).

The diary is finite (LTLf). Steps are plain dicts/Steps with .name
(event), .payload. World facts (e.g. "the target touches secret data")
come from Datalog and are passed in -- rules never compute them.
"""

from dataclasses import dataclass
from typing import Callable

# The five yes-flags L1 demands before acting (guide Part 8.2).
CHECK_FLAGS = ["opa_allowed", "datalog_clear", "prolog_allowed",
               "validation_passed", "z3_sat"]

# Any of these events means "some checker said NO or broke" (8.2).
VALIDATION_FAILED_EVENTS = {
    "opa_denied", "datalog_sensitive_path", "prolog_forbidden",
    "temporal_violation", "z3_unsat", "validation_failed",
}

# Events legal while the piece stands on Blocked / Recovery.
FROM_BLOCKED = {"escalation_notified"}
FROM_RECOVERY = {"retry_available", "retries_exhausted"}


@dataclass(frozen=True)
class Rule:
    id: str
    scope: str        # "action" | "incident" | "episode"
    kind: str         # "safety" | "liveness"
    simple: str       # the rule in simple words (for refusal messages)
    holds: Callable   # (steps, world) -> bool


def _names(steps):
    return [s.name for s in steps]


# --------------------------------------------------------------------- L1
def _l1(steps, world):
    """G(Execute -> all five checks said yes FOR THIS SAME ACTION)."""
    seen = set()
    for s in steps:
        if s.name == "execute" and not set(CHECK_FLAGS) <= seen:
            return False
        seen.add(s.name)
    return True


# --------------------------------------------------------------------- L2
def _l2(steps, world):
    """G(Validation_Failed -> X Blocked): after a NO, only Blocked roads."""
    for i, s in enumerate(steps):
        if s.name in VALIDATION_FAILED_EVENTS and i + 1 < len(steps):
            if steps[i + 1].name not in FROM_BLOCKED:
                return False
    return True


# --------------------------------------------------------------------- L3
def _l3(steps, world):
    """G(Risk_High -> (no Execute until a checked human says yes))."""
    waiting = False
    for s in steps:
        if s.name == "risk_high":
            waiting = True
        elif s.name == "human_approved":
            waiting = False
        elif s.name == "execute" and waiting:
            return False
    return True


# --------------------------------------------------------------------- L4
def _l4(steps, world):
    """Liveness: waiting for a human always ENDS (yes, no, or time up)."""
    names = _names(steps)
    for i, name in enumerate(names):
        if name == "risk_high":
            if not any(n in ("human_approved", "human_rejected",
                             "approval_timeout") for n in names[i + 1:]):
                return False
    return True


# --------------------------------------------------------------------- L5
def _l5(steps, world):
    """G(Tool_Failed -> X(Recovery or Escalated)): failure never ignored."""
    for i, s in enumerate(steps):
        if s.name in ("execution_failed", "config_apply_failed"):
            if i + 1 < len(steps) and steps[i + 1].name not in FROM_RECOVERY:
                return False
    return True


# --------------------------------------------------------------------- L6
def _l6(steps, world):
    """Liveness: every action is eventually written in the diary."""
    names = _names(steps)
    for i, name in enumerate(names):
        if name == "execute" and "audit_log_created" not in names[i + 1:]:
            return False
    return True


# --------------------------------------------------------------------- L7
def _l7(steps, world):
    """Never close before the diary exists (checked with final_state)."""
    if world.get("final_state") == "Incident_Resolved":
        names = _names(steps)
        return bool(names) and names[-1] == "audit_log_created"
    return True


# --------------------------------------------------------------------- L8
def _l8(steps, world):
    """Secret-data target: never Execute before Datalog checked it."""
    if not world.get("sensitive_data"):
        return True
    saw_datalog = False
    for s in steps:
        if s.name == "datalog_clear":
            saw_datalog = True
        elif s.name == "execute" and not saw_datalog:
            return False
    return True


# --------------------------------------------------------------------- L9
def _l9(steps, world):
    """FRESH CHECK: after 'go alone' or a human yes, no Execute until a
    Z3 yes that came AFTER that decision (a stale z3_sat never counts)."""
    fresh_z3 = False
    for s in steps:
        if s.name in ("risk_low", "human_approved"):
            fresh_z3 = False               # the decision resets the check
        elif s.name == "z3_sat":
            fresh_z3 = True
        elif s.name == "execute" and not fresh_z3:
            return False
    return True


# -------------------------------------------------------------------- L10
def _l10(steps, world):
    """G(Llm_Action_Proposed -> Dsl_Valid): only correct DSL gets in."""
    return all(s.payload.get("dsl_valid", True)
               for s in steps if s.name == "llm_action_proposed")


# -------------------------------------------------------------------- L11
def _l11(steps, world):
    """Secrets never go to the outside AI before they are removed."""
    if not world.get("sensitive_data_in_context"):
        return True
    redacted = False
    for s in steps:
        if s.name == "logs_parsed" and s.payload.get("Redaction_Applied"):
            redacted = True
        elif s.name == "external_llm_call" and not redacted:
            return False
    return True


# -------------------------------------------------------------------- L12
def _l12(episode_steps, world):
    """No restart loop: at most 2 restarts of the same target without it
    becoming healthy in between; the 3rd is refused. Steps here are the
    episode memory: 'restart' / 'healthy' marks across incidents."""
    unhealthy_restarts = 0
    for mark in episode_steps:
        if mark == "healthy":
            unhealthy_restarts = 0
        elif mark == "restart":
            unhealthy_restarts += 1
            if unhealthy_restarts >= 3:
                return False
    return True


# ------------------------------------------------- L13-L15 (Advisor, extra)
def _l13(steps, world):
    """The Advisor never changes alert settings without an approval."""
    approved = False
    for s in steps:
        if s.name == "rec_approved":
            approved = True
        elif s.name == "alert_config_applied" and not approved:
            return False
    return True


def _l14(steps, world):
    """While looking around, change nothing."""
    discovering = False
    for s in steps:
        if s.name == "infra_scan_triggered":
            discovering = True
        elif s.name == "infra_snapshot_ready":
            discovering = False
        elif s.name == "state_changing_tool_call" and discovering:
            return False
    return True


def _l15(steps, world):
    """Liveness: every suggestion gets an answer (or expires)."""
    names = _names(steps)
    for i, name in enumerate(names):
        if name == "rec_validation_passed":
            if not any(n in ("rec_approved", "rec_rejected",
                             "rec_review_timeout") for n in names[i + 1:]):
                return False
    return True


CATALOG = [
    Rule("L1", "action", "safety",
         "never act unless all 5 checkers said yes for this same action", _l1),
    Rule("L2", "incident", "safety",
         "if any checker says NO, the very next state is Blocked", _l2),
    Rule("L3", "action", "safety",
         "high-risk actions never run before a checked human says yes", _l3),
    Rule("L4", "incident", "liveness",
         "waiting for a human always ends: yes, no, or time is up", _l4),
    Rule("L5", "incident", "safety",
         "a tool failure is never ignored: next we retry or call a human", _l5),
    Rule("L6", "incident", "liveness",
         "every action is eventually written in the diary", _l6),
    Rule("L7", "incident", "safety",
         "never close before the diary exists", _l7),
    Rule("L8", "action", "safety",
         "never touch something with secret data before Datalog checked", _l8),
    Rule("L9", "action", "safety",
         "after the last decision, Z3 must check the live system again", _l9),
    Rule("L10", "action", "safety",
         "the AI can only speak correct DSL", _l10),
    Rule("L11", "incident", "safety",
         "secrets never go to the outside AI before they are removed", _l11),
    Rule("L12", "episode", "safety",
         "no restart loop: the 3rd restart without healthy is blocked", _l12),
    Rule("L13", "action", "safety",
         "the Advisor never changes alert settings by itself", _l13),
    Rule("L14", "incident", "safety",
         "while looking around, change nothing", _l14),
    Rule("L15", "incident", "liveness",
         "every suggestion gets an answer (or expires)", _l15),
]

# The four ways of checking use different rule sets (guide Part 8.6).
LOOKAHEAD_IDS = {"L1", "L3", "L8", "L9", "L10", "L12"}
LIVE_IDS = {"L1", "L2", "L3", "L5", "L7", "L9", "L10", "L11"}

LOOKAHEAD_RULES = [r for r in CATALOG if r.id in LOOKAHEAD_IDS]
LIVE_RULES = [r for r in CATALOG if r.id in LIVE_IDS]
ALL_RULES = CATALOG
