"""
sentinel/decide/arbiter.py
==========================
The ARBITER -- risk becomes a route (step P3.1, T13/T14).

The teacher reads the thermometer (Prolog's risk_level, stored on the
case folder at T9) and the school policy (OPA's route query) decides:
below the line you stay in class (go alone), above it your parents are
called (human approval). The teacher NEVER invents a new temperature:

  * the Arbiter READS incident.risk_level -- it never recomputes risk
    (instructor checkpoint (b));
  * OPA maps that risk to a route and nothing else -- its rule is one
    line: route := "autonomous" if input.risk_level == "low"
    (instructor checkpoint (c));
  * missing / unknown / broken anything => require_approval. When the
    router itself is unsure, the safe answer is not "stop" and not
    "go" -- it is "ask a human". (That is also why the board has no
    validation_failed road from Risk_Assessment.)

The Arbiter sends EXACTLY ONE event:
    risk_low  (T13) -> Constraint_Check          (Z3, then act)
    risk_high (T14) -> Human_Approval_Required   (the approval screen)
"""

from dataclasses import dataclass

from sentinel.checkers.opa_adapter import eval_opa


@dataclass
class RouteDecision:
    """What the routing station decided, and why."""

    event: str                   # "risk_low" | "risk_high"
    route: str                   # "autonomous" | "require_approval"
    risk_level: str | None       # the thermometer reading that was routed
    router_error: str | None = None   # set when OPA trouble forced the default


def ask_route(risk_level: str | None) -> tuple[str, str | None]:
    """
    The ROUTER's question (data.sentinel.authz.route) with the router's
    judgment: any trouble -> ("require_approval", why). Unsure = a human.
    """
    input_doc = {} if risk_level is None else {"risk_level": risk_level}
    route, error = eval_opa("data.sentinel.authz.route", input_doc)
    if error is not None:
        return "require_approval", error
    if route not in ("autonomous", "require_approval"):
        return "require_approval", f"opa answered an unknown route: {route!r}"
    return route, None


def decide_route(incident) -> RouteDecision:
    """
    The full T13/T14 step for one incident sitting at Risk_Assessment:
    read the stored risk (NEVER recompute it), ask OPA for the route,
    send exactly one event, return the decision.
    """
    risk_level = getattr(incident, "risk_level", None)
    route, error = ask_route(risk_level)

    if route == "autonomous":
        decision = RouteDecision(event="risk_low", route=route,
                                 risk_level=risk_level, router_error=error)
        incident.machine.risk_low()          # T13 -> Constraint_Check
    else:
        decision = RouteDecision(event="risk_high", route=route,
                                 risk_level=risk_level, router_error=error)
        incident.machine.risk_high()         # T14 -> Human_Approval_Required

    return decision
