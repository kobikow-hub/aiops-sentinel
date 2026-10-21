"""
ltl/check.py
============
The LTL CHECKER -- the time-order guard (step P2.4, T11/T12).

Mirrors the scoped evaluator of guide Part 8.5: every rule is checked
ONLY on the diary pages it is about --

    "action"   pages of one fingerprint (an answer given to a different
               action never counts -- no borrowed approvals)
    "incident" the whole incident diary
    "episode"  restart memory across incidents (L12)

Used four ways (guide Part 8.6):
  1. look_ahead()  at Temporal_Check (T11/T12): diary + the PLANNED next
     steps -- would a rule break if we continued this way?
  2. live_guard()  on EVERY event: would accepting this event break a
     rule right now? A bad event is refused and written down (Story 3).
  3. timers        (Phase 3: the SLA timer sends approval_timeout -- L4)
  4. check_full_trace() at the end: a finished diary must satisfy ALL
     rules before audit_log_created is accepted (Phase 5).
"""

from dataclasses import dataclass, field

from ltl.rules import ALL_RULES, LIVE_RULES, LOOKAHEAD_RULES


@dataclass(frozen=True)
class Step:
    """One diary page: an event with its fingerprint and payload."""

    name: str
    action_hash: str | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class LtlVerdict:
    event: str                    # "validation_passed" | "temporal_violation"
    violated_rule: str | None = None
    simple: str | None = None     # the broken rule in simple words
    last_steps: list = field(default_factory=list)   # evidence for humans


def _scoped(rule, steps, action_hash, episode_memory):
    if rule.scope == "action":
        return [s for s in steps if s.action_hash == action_hash]
    if rule.scope == "incident":
        return steps
    return episode_memory or []          # "episode": L12's restart marks


def _check(rules, steps, action_hash, world, episode_memory):
    """Evaluate each rule on the part of history it is about (8.5)."""
    for rule in rules:
        scoped = _scoped(rule, steps, action_hash, episode_memory)
        if not rule.holds(scoped, world):
            return LtlVerdict(
                event="temporal_violation",
                violated_rule=rule.id, simple=rule.simple,
                last_steps=[s.name for s in steps[-3:]],
            )
    return LtlVerdict(event="validation_passed")


def look_ahead(steps, planned, action_hash, world=None, episode_memory=None):
    """T11/T12: check diary + planned next steps against the look-ahead
    rules. planned = e.g. ["risk_low", "z3_sat", "execute"]."""
    future = [Step(name=n, action_hash=action_hash) for n in planned]
    return _check(LOOKAHEAD_RULES, list(steps) + future, action_hash,
                  world or {}, episode_memory)


def live_guard(steps, proposed, world=None, episode_memory=None):
    """The guard on every event: may `proposed` (a Step) happen NOW?
    Checked BEFORE the board accepts it; a violation refuses the event."""
    verdict = _check(LIVE_RULES, list(steps) + [proposed],
                     proposed.action_hash, world or {}, episode_memory)
    if verdict.event == "temporal_violation":
        # The refused event never entered the diary -- the written-down
        # evidence is the diary as it STOOD (Story 3: "rule number +
        # last diary steps"), not the refused event itself.
        verdict.last_steps = [s.name for s in list(steps)[-3:]]
    return verdict


def check_full_trace(steps, action_hashes=None, world=None,
                     episode_memory=None):
    """The end-of-diary check: ALL rules, for EVERY fingerprint (Phase 5
    runs this before accepting audit_log_created)."""
    hashes = action_hashes or sorted(
        {s.action_hash for s in steps if s.action_hash})
    for action_hash in hashes or [None]:
        verdict = _check(ALL_RULES, list(steps), action_hash,
                         world or {}, episode_memory)
        if verdict.event == "temporal_violation":
            return verdict
    return LtlVerdict(event="validation_passed")


def check_temporal(incident, steps, planned, world=None,
                   episode_memory=None):
    """The full T11/T12 step for one incident sitting at Temporal_Check:
    look ahead, move the board, return the verdict."""
    verdict = look_ahead(steps, planned, incident.action_hash,
                         world, episode_memory)
    if verdict.event == "validation_passed":
        incident.machine.validation_passed()      # T11 -> Risk_Assessment
    else:
        incident.machine.temporal_violation()     # T12 -> Blocked
    return verdict
