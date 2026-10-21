"""
sentinel/verify/recovery.py
===========================
RECOVERY + the retry counter (step P5.2, T25/T26; guide Part 9).

A teacher returning homework with the mistake CIRCLED: you try again
fresh, at most twice; you don't erase-and-resubmit the same page. And
if the teacher said "this is against the rules" (a checker's NO), trying
again is not allowed at all -- Blocked has NO road back to AI_Analysis
on the board, and nothing in this module can create one.

The rules of the Recovery square:

  THE DOOR    entering requires a recovery_reason AND a counterexample
              (the exact lesson). Both go into the diary and into the
              next AI prompt. No reason, no entry -- an anonymous
              failure cannot be learned from.
  THE COUNTER MAX_RETRIES = 2 (guide Part 17.3, locked):
                  retry_count < 2  -> retry_available   (T25)
                  retry_count >= 2 -> retries_exhausted (T26)
  THE RESET   a retry is a BRAND-NEW suggestion: back to AI_Analysis
              with the lesson in the prompt; the new program gets a new
              action_hash and walks through ALL the checks again.
              Nothing old (approval, z3_sat, receipt) is reusable --
              the fingerprint changed.

Valid recovery reasons and where they come from (guide Part 9's table):
    llm_output_invalid      AI_Analysis (T4)   -- GATE 1's lesson
    tool_failed             Action_Executed (T22) -- the Gateway's reason
    metrics_still_degraded  Verification (T24) -- the probe's numbers
"""

from dataclasses import dataclass, field

MAX_RETRIES = 2          # guide Part 17.3: the locked number

VALID_REASONS = {"llm_output_invalid", "tool_failed",
                 "metrics_still_degraded"}


@dataclass
class RecoveryRecord:
    """One visit to the Recovery square, papers included."""

    reason: str
    counterexample: str          # the circled mistake, verbatim
    retry_number: int            # 1-based: which attempt this failure ended


@dataclass
class RecoveryOutcome:
    """What the counter decided."""

    event: str                   # "retry_available" | "retries_exhausted"
    lesson_for_prompt: str | None = None    # set on retry: goes to the AI
    history: list = field(default_factory=list)


def enter_recovery(incident, reason: str, counterexample: str) -> RecoveryRecord:
    """
    The DOOR. Called when a failure event has just moved the board into
    Recovery (T4 / T22 / T24). Refuses anonymous or reasonless failures.
    """
    if reason not in VALID_REASONS:
        raise ValueError(f"unknown recovery_reason {reason!r} -- "
                         f"must be one of {sorted(VALID_REASONS)}")
    if not counterexample or not counterexample.strip():
        raise ValueError("entering Recovery requires a counterexample "
                         "(the exact lesson) -- an anonymous failure "
                         "cannot be learned from")

    if not hasattr(incident, "recovery_history"):
        incident.recovery_history = []
    record = RecoveryRecord(
        reason=reason,
        counterexample=counterexample.strip(),
        retry_number=len(incident.recovery_history) + 1,
    )
    incident.recovery_history.append(record)
    return record


def decide_retry(incident) -> RecoveryOutcome:
    """
    The COUNTER. retry_count is how many retries were already SPENT
    (= failures beyond the first attempt). The exit rule, no exceptions:
        retry_count < MAX_RETRIES  -> retry_available   (T25)
        retry_count >= MAX_RETRIES -> retries_exhausted (T26)
    """
    history = getattr(incident, "recovery_history", [])
    if not history:
        raise RuntimeError("decide_retry called with no recovery record -- "
                           "the door (enter_recovery) comes first")

    retry_count = len(history) - 1        # failures AFTER the first attempt

    if retry_count < MAX_RETRIES:
        latest = history[-1]
        lesson = (f"Your previous attempt failed "
                  f"({latest.reason}): {latest.counterexample} -- "
                  f"write a NEW proposal that avoids this exact mistake.")
        incident.machine.retry_available()        # T25 -> AI_Analysis
        return RecoveryOutcome(event="retry_available",
                               lesson_for_prompt=lesson,
                               history=list(history))

    incident.machine.retries_exhausted()          # T26 -> Escalated
    return RecoveryOutcome(event="retries_exhausted",
                           history=list(history))
