"""
sentinel/intake/redactor.py
===========================
The SECRET REMOVER (step P1.2, transition T2, time rule L11).

Before ANY text is shown to the AI, we go over it with a black marker:
passwords, tokens, keys and personal data are replaced with a mask.
Rule L11 says: secrets NEVER leave our safe zone -- and the AI is
outside the safe zone.

Two jobs happen here:

  1. REDACT   -- black out secrets in every log line.
  2. FILTER   -- only logs of services connected to the problem may be
                 shown at all (the alert_context idea from
                 rules/topology.dl). Until the Datalog module arrives
                 in P2.2, the caller hands us the allowed list; the
                 hole is shaped now, Phase 2 plugs in the real answer.

When the marker work is done, the board moves Alert_Parsed ->
AI_Analysis (T2) and the logs_parsed event carries Redaction_Applied --
written proof the marker was used BEFORE the AI saw anything.

This module holds no passwords of its own and never calls the AI.
"""

import re
from dataclasses import dataclass

MASK = "***REDACTED***"

# The black marker's pattern book. Each entry: (name, compiled pattern).
# Patterns keep the label (e.g. "password=") and mask only the secret
# itself, so a human reading the log still understands what WAS there.
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Bearer eyJhbGciOi... (HTTP auth headers). MUST run before the
    # general credential pattern: in "Authorization: Bearer <token>" the
    # general pattern would mask the word "Bearer" and leave the real
    # token untouched (caught by test_bearer_header_is_masked).
    ("bearer_token", re.compile(r"(?i)\b(bearer)(\s+)(\S+)")),
    # password=..., pwd:..., secret=..., api_key=..., token=..., authorization=...
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?key"
            r"|token|authorization|auth)\b(\s*[=:]\s*)(\S+)"
        ),
    ),
    # AWS access key ids: AKIA followed by 16 uppercase letters/digits
    ("aws_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # personal data: email addresses
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
]


@dataclass
class RedactionResult:
    """What the marker did: the safe text + proof of the work."""

    lines: list[str]          # the text the AI may now see
    redaction_applied: bool   # did the marker touch anything?
    redaction_count: int      # how many secrets were masked
    lines_dropped: int        # log lines hidden by the context filter


def redact_line(line: str) -> tuple[str, int]:
    """Black out every secret in one line. Returns (safe_line, hits)."""
    hits = 0
    for _name, pattern in SECRET_PATTERNS:
        if pattern.groups >= 3:
            # keep the label and separator, mask only the secret value
            line, n = pattern.subn(r"\1\2" + MASK, line)
        else:
            line, n = pattern.subn(MASK, line)
        hits += n
    return line, hits


def redact_logs(
    raw_lines: list[str],
    allowed_services: set[str] | None = None,
) -> RedactionResult:
    """
    The full marker pass:
      FILTER -- if an allowed list is given, a line is kept only when it
                mentions an allowed service (Datalog's alert_context in
                Phase 2). No list = keep everything (redaction still runs).
      REDACT -- every kept line goes under the marker.
    """
    kept: list[str] = []
    dropped = 0
    if allowed_services is None:
        kept = list(raw_lines)
    else:
        for line in raw_lines:
            if any(service in line for service in allowed_services):
                kept.append(line)
            else:
                dropped += 1

    safe_lines: list[str] = []
    total_hits = 0
    for line in kept:
        safe, hits = redact_line(line)
        safe_lines.append(safe)
        total_hits += hits

    return RedactionResult(
        lines=safe_lines,
        redaction_applied=total_hits > 0,
        redaction_count=total_hits,
        lines_dropped=dropped,
    )


def parse_logs(incident, raw_lines, allowed_services=None) -> dict:
    """
    Step T2 for one incident: run the marker, move the board
    Alert_Parsed -> AI_Analysis, and return the logs_parsed event payload
    (carrying Redaction_Applied, as the done-criterion requires).

    The safe lines are stored on the incident -- from now on, ONLY these
    lines may ever be handed to the AI (P1.3).
    """
    result = redact_logs(raw_lines, allowed_services)

    incident.safe_logs = result.lines
    incident.machine.logs_parsed()  # T2: Alert_Parsed -> AI_Analysis

    return {
        "event": "logs_parsed",
        "payload": {
            "Redaction_Applied": result.redaction_applied,
            "redaction_count": result.redaction_count,
            "lines_kept": len(result.lines),
            "lines_dropped": result.lines_dropped,
        },
    }
