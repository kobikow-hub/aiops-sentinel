"""
sentinel/intake/alerts.py
=========================
The MAIL SLOT (step P1.1, transition T1).

An alert is a letter saying "something is broken!". Before anyone opens
it, this module checks the ENVELOPE:

  1. Is it shaped like real mail?  (all required fields, right kinds)
  2. Does it come from a monitor we know?  (not a stranger)

Badly-shaped mail is thrown away and logged -- NEVER opened, never shown
to the AI. Good mail opens a case: an Incident with a unique id (the
diary format says: "UUID, generated at alert_received") and the board
moves Awaiting_Alert -> Alert_Parsed (T1).

This module holds NO passwords and changes NO computers. It only reads
the envelope and sends one event to the board.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from board.incident_machine import IncidentMachine

logger = logging.getLogger("sentinel.intake")

# The monitors we trust -- mail from anyone else is junk. (In the first
# version this is a simple set; a real monitor registry can replace it
# later behind the same check.)
KNOWN_MONITORS = {"prometheus", "grafana", "cloudwatch", "mock_monitor"}

# The envelope shape: field name -> the Python kind it must be.
REQUIRED_FIELDS = {
    "alert_id": str,      # e.g. "al_7f3" -- the id evidence will cite
    "source": str,        # which monitor sent it (must be known)
    "service": str,       # which service is complaining
    "metric": str,        # what is wrong, e.g. "mem_web_p95"
    "severity": str,      # "info" | "warning" | "critical"
    "timestamp": str,     # when the monitor saw it (ISO text)
}

VALID_SEVERITIES = {"info", "warning", "critical"}


class AlertRejected(Exception):
    """Raised for junk mail. The reason says exactly which check failed."""


@dataclass
class Incident:
    """One case folder: the alert that started it, the unique id, the board."""

    alert: dict
    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    machine: IncidentMachine = field(default_factory=IncidentMachine)


def validate_alert(alert: object) -> list[str]:
    """Check the envelope. Returns a list of problems (empty = good mail)."""
    problems: list[str] = []

    if not isinstance(alert, dict):
        return [f"alert must be a mapping, got {type(alert).__name__}"]

    for name, kind in REQUIRED_FIELDS.items():
        if name not in alert:
            problems.append(f"missing required field '{name}'")
        elif not isinstance(alert[name], kind):
            problems.append(
                f"field '{name}' must be {kind.__name__}, "
                f"got {type(alert[name]).__name__}"
            )

    # Only meaningful if the fields above exist and are strings:
    if not problems:
        if alert["source"] not in KNOWN_MONITORS:
            problems.append(f"unknown monitor '{alert['source']}'")
        if alert["severity"] not in VALID_SEVERITIES:
            problems.append(f"unknown severity '{alert['severity']}'")

    return problems


def receive_alert(alert: object) -> Incident:
    """
    The mail slot. Good mail -> a new Incident whose board just moved
    Awaiting_Alert -> Alert_Parsed (T1). Junk mail -> logged + AlertRejected;
    no incident is created and nothing reaches the AI.
    """
    problems = validate_alert(alert)
    if problems:
        logger.warning("[INTAKE] alert rejected: %s", "; ".join(problems))
        raise AlertRejected("; ".join(problems))

    incident = Incident(alert=alert)
    incident.machine.alert_received()  # T1: Awaiting_Alert -> Alert_Parsed
    logger.info(
        "[INTAKE] incident %s opened for alert %s from %s",
        incident.incident_id, alert["alert_id"], alert["source"],
    )
    return incident
