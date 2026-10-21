"""
audit/audit_service.py
======================
The APPEND-ONLY DIARY (step P5.4, T29; guide Part 13.1 + rule L7).

The class secretary writes minutes IN PEN: you may add lines, never
tear pages out. And the meeting is not over until the minutes are read
back and complete.

The law this file obeys: audit/trace.schema (verbatim from the guide,
P0.5). Three disciplines per line:

  CLOSED VOCABULARY   only the 30 official event names exist. A made-up
                      event is refused (P12).
  AUTHORIZED VOICES   only the component allowed to claim an event may
                      write that line (schema §7.2). The Gateway says
                      'execute'; the probe says 'metrics_healthy'; the
                      AI says NOTHING -- it has no voice here at all.
  PHASE NEVER GOES    within one fingerprint's pages the phase number
  BACKWARDS           is non-decreasing (P16).

Append-only BY CONSTRUCTION: the file opens in "a" mode only, and this
module simply has no edit or delete function. The close ritual (T29):
read the WHOLE diary back, check it against ALL time rules L1-L15
(ltl.check_full_trace), and only then accept audit_log_created --
the ONLY road into Incident_Resolved (rule L7).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ltl.check import Step, check_full_trace

# ---------------------------------------------------------------------------
# The law, restated as data (trace.schema, verbatim vocabulary).
# ---------------------------------------------------------------------------
VALID_EVENT_NAMES = {
    "alert_received", "logs_parsed", "llm_action_proposed", "llm_output_invalid",
    "opa_allowed", "opa_denied", "datalog_clear", "datalog_sensitive_path",
    "prolog_allowed", "prolog_forbidden",
    "validation_passed", "temporal_violation", "validation_failed",
    "risk_low", "risk_high",
    "human_approved", "human_rejected", "approval_timeout",
    "z3_sat", "z3_unsat", "execute",
    "execution_succeeded", "execution_failed",
    "metrics_healthy", "metrics_still_degraded",
    "retry_available", "retries_exhausted",
    "escalation_notified", "human_resolution_recorded", "audit_log_created",
}

# §7.2 -- who may claim each event. One event, one authorized voice.
AUTHORIZED_ACTOR = {
    "alert_received": "intake", "logs_parsed": "redactor",
    "llm_action_proposed": "gate1", "llm_output_invalid": "gate1",
    "opa_allowed": "opa", "opa_denied": "opa",
    "datalog_clear": "datalog", "datalog_sensitive_path": "datalog",
    "prolog_allowed": "prolog", "prolog_forbidden": "prolog",
    "validation_passed": "ltl", "temporal_violation": "ltl",
    "validation_failed": "checker_supervisor",
    "risk_low": "arbiter", "risk_high": "arbiter",
    "human_approved": "approval_service", "human_rejected": "approval_service",
    "approval_timeout": "sla_timer",
    "z3_sat": "z3", "z3_unsat": "z3",
    "execute": "gateway",
    "execution_succeeded": "gateway", "execution_failed": "gateway",
    "metrics_healthy": "probe", "metrics_still_degraded": "probe",
    "retry_available": "recovery", "retries_exhausted": "recovery",
    "escalation_notified": "notifier",
    "human_resolution_recorded": "escalation_desk",
    "audit_log_created": "audit_service",
}

# Which phase (1-5) each event belongs to (guide Part 4 / trace.schema).
EVENT_PHASE = {
    "alert_received": 1, "logs_parsed": 1, "llm_action_proposed": 1,
    "llm_output_invalid": 1,
    "opa_allowed": 2, "opa_denied": 2, "datalog_clear": 2,
    "datalog_sensitive_path": 2, "prolog_allowed": 2, "prolog_forbidden": 2,
    "validation_passed": 2, "temporal_violation": 2, "validation_failed": 2,
    "risk_low": 3, "risk_high": 3, "human_approved": 3, "human_rejected": 3,
    "approval_timeout": 3,
    "z3_sat": 4, "z3_unsat": 4, "execute": 4,
    "execution_succeeded": 4, "execution_failed": 4,
    "metrics_healthy": 5, "metrics_still_degraded": 5,
    "retry_available": 5, "retries_exhausted": 5, "escalation_notified": 5,
    "human_resolution_recorded": 5, "audit_log_created": 5,
}

# Before this event, action_hash may legitimately be null (trace.schema).
PRE_FINGERPRINT_EVENTS = {"alert_received", "logs_parsed",
                          "llm_output_invalid"}


class DiaryRefused(Exception):
    """The secretary refused a line (or the closing). str(e) says why."""


@dataclass
class Diary:
    """One incident's minutes: an append-only JSONL file + its reading."""

    incident_id: str
    path: Path
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # -------------------------------------------------------- writing
    def append(self, name: str, actor: str, action_hash: str | None = None,
               payload: dict | None = None) -> dict:
        """
        Write ONE line, in pen. Refuses: unknown events, unauthorized
        voices, a missing fingerprint after llm_action_proposed, and a
        phase running backwards within one fingerprint (P16).
        """
        if name not in VALID_EVENT_NAMES:
            raise DiaryRefused(f"unknown event name '{name}' -- the "
                               f"vocabulary is closed (P12)")
        if AUTHORIZED_ACTOR[name] != actor:
            raise DiaryRefused(
                f"actor '{actor}' may not claim '{name}' -- that line "
                f"belongs to '{AUTHORIZED_ACTOR[name]}' (schema §7.2)")
        if action_hash is None and name not in PRE_FINGERPRINT_EVENTS:
            raise DiaryRefused(
                f"'{name}' requires an action_hash -- only pre-proposal "
                f"events may be unfingerprinted")

        phase = EVENT_PHASE[name]
        if action_hash is not None:
            for line in self.read_all():
                if (line["action_hash"] == action_hash
                        and line["phase"] > phase):
                    raise DiaryRefused(
                        f"phase would go backwards for this fingerprint: "
                        f"{line['phase']} -> {phase} (P16)")

        event = {
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "action_hash": action_hash,
            "actor": actor,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as fh:   # pen: append only
            fh.write(json.dumps(event) + "\n")
        return event

    # -------------------------------------------------------- reading
    def read_all(self) -> list[dict]:
        """Read the minutes back, in order."""
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def as_steps(self) -> list[Step]:
        """The diary as LTL steps, for the time-rule reading."""
        return [Step(name=e["name"], action_hash=e["action_hash"],
                     payload=e["payload"]) for e in self.read_all()]

    # -------------------------------------------------------- closing
    def close(self, incident, world: dict | None = None,
              episode_memory: list | None = None) -> dict:
        """
        The T29 ritual: read the WHOLE diary back, check ALL time rules
        L1-L15 for EVERY fingerprint, and only if the minutes are
        complete write audit_log_created and move the board
        Audit_Logging -> Incident_Resolved. Rule L7: the only way in.

        The reading asks: "would the minutes be complete ONCE the
        closing line is written?" -- so the prospective
        audit_log_created step is included in the check (L6/L7 demand
        that very line), exactly like Temporal_Check's look-ahead.
        """
        closing_hash = getattr(incident, "action_hash", None)
        prospective = self.as_steps() + [
            Step(name="audit_log_created", action_hash=closing_hash)]
        verdict = check_full_trace(prospective, world=world,
                                   episode_memory=episode_memory)
        if verdict.event == "temporal_violation":
            raise DiaryRefused(
                f"diary incomplete -- rule {verdict.violated_rule} "
                f"({verdict.simple}); last steps: {verdict.last_steps}")

        event = self.append("audit_log_created", actor="audit_service",
                            action_hash=getattr(incident, "action_hash", None),
                            payload={"events_in_diary": len(self.read_all())})
        incident.machine.audit_log_created()     # T29 -> Incident_Resolved
        return event


def open_diary(incident, directory: Path) -> Diary:
    """One incident, one book, named by its id."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return Diary(incident_id=incident.incident_id,
                 path=directory / f"{incident.incident_id}.jsonl")
