"""
sentinel/decide/sla_timer.py
============================
The SLA TIMER -- nobody waits forever (step P3.3, T17, time rule L4).

If you knock and nobody answers before dinner, you don't stand at the
door all night -- you go find an adult. Rule L4 (liveness): waiting for
a human always ENDS, one of exactly three ways:

    human_approved    (P3.2 -- the yes)
    human_rejected    (P3.2 -- the no)
    approval_timeout  (THIS module -- time's up)

On timeout the incident moves to Escalated: a person now OWNS it and
the system does nothing more alone.

Design notes:
  * The window length is configurable (the guide's numbers table says:
    "not fixed in the design -- choose it when building"). Default 30
    minutes -- the same length as the slip's own expiry, so a slip and
    its waiting window age together.
  * The clock is INJECTABLE: callers (and tests) may pass `now`. Tests
    never sleep; they hand the timer a pretend clock.
  * check() is idempotent and safe to poll: it fires at most once, and
    only while the board is actually still waiting.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_SLA_MINUTES = 30

WAITING_STATE = "Human_Approval_Required"


@dataclass
class SlaTimer:
    """One waiting window for one incident's approval."""

    incident: object
    deadline: datetime
    fired: bool = False

    @classmethod
    def start(cls, incident, sla_minutes: int = DEFAULT_SLA_MINUTES,
              now: datetime | None = None) -> "SlaTimer":
        """Open the window the moment the piece reaches the waiting square."""
        now = now or datetime.now(timezone.utc)
        return cls(incident=incident,
                   deadline=now + timedelta(minutes=sla_minutes))

    def check(self, now: datetime | None = None) -> str | None:
        """
        Poll the clock. Returns "approval_timeout" the one time it fires,
        else None. Fires ONLY if:
          * the window has closed, and
          * the board is still waiting (a yes/no already ended the wait
            -> the timer quietly stands down), and
          * it has not fired before.
        """
        now = now or datetime.now(timezone.utc)
        if self.fired:
            return None
        if self.incident.machine.current_state.name != WAITING_STATE:
            return None                      # somebody answered in time
        if now < self.deadline:
            return None                      # still within the window

        self.fired = True
        self.incident.machine.approval_timeout()   # T17 -> Escalated
        return "approval_timeout"
