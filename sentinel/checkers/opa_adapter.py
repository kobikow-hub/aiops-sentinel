"""
sentinel/checkers/opa_adapter.py
================================
The OPA ADAPTER (step P2.1, transitions T5/T6, fail-closed rule T30).

OPA is the school rule book: flat company rules ("no running in the
halls") -- banned actions, change freezes, closed change windows. It is
a referee we hired from outside (tools/opa.exe, P0.3); its law book is
policy/sentinel/authz.rego (P0.5).

This adapter is a MESSENGER, deliberately thin:

    * it carries the sealed proposal to the referee (one 'opa eval'
      subprocess call with a JSON input form),
    * brings back the ruling: allow yes/no + the exact deny reasons,
    * and sends the board event -- opa_allowed (T5) or opa_denied (T6).

It contains NO rules of its own. If you want to change policy, edit the
law book (and its tests), never this file.

FAIL CLOSED (T30): if the referee is missing, crashes, answers gibberish
or is too slow, the answer is NO -- validation_failed -> Blocked. A
broken rule book never waves anyone through.
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Project root: this file lives at <root>/sentinel/checkers/.
_ROOT = Path(__file__).resolve().parents[2]
OPA_EXE = _ROOT / "tools" / "opa.exe"
POLICY_DIR = _ROOT / "policy"

# The referee must answer within this many seconds, or it's a NO (T30).
OPA_TIMEOUT_SECONDS = 10


@dataclass
class OpaVerdict:
    """The referee's ruling, plus how we obtained it."""

    allow: bool
    deny: list[str] = field(default_factory=list)
    event: str = ""            # "opa_allowed" | "opa_denied" | "validation_failed"
    checker_error: str | None = None   # set only on the fail-closed path


def build_input(incident, *, env: str = "production",
                change_window_open: bool = True,
                change_freeze: bool = False,
                emergency: bool = False) -> dict:
    """
    Fill OPA's form (the shape from guide Part 10.1's I/O example).
    Everything comes from the sealed case folder GATE 1 stamped --
    the adapter never re-parses the AI's text.
    """
    program = incident.program
    return {
        "principal": {"id": "sentinel-agent", "role": "agent"},
        "action": {
            "verb": program.verb,
            "target": program.target,
            "params": dict(program.params),
            "dsl_valid": True,               # only GATE-1-passed programs get here
            "action_hash": incident.action_hash,
        },
        "resource": {"kind": program.verb_class, "env": env},
        "context": {
            "change_window_open": change_window_open,
            "change_freeze": change_freeze,
            "emergency": emergency,
        },
        "action_hash": incident.action_hash,
    }


def eval_opa(query: str, input_doc: dict) -> tuple[object, str | None]:
    """
    The shared MESSENGER'S LEGS: one question to the real referee, one
    answer back. Returns (value, None) or (None, what-went-wrong).

    NO POLICY LIVES HERE. What a failure MEANS is each station's own
    judgment: the checker fails closed (Blocked), the router defaults to
    require_approval (a human), the approval check keeps waiting.
    """
    try:
        completed = subprocess.run(
            [str(OPA_EXE), "eval",
             "--data", str(POLICY_DIR),
             "--stdin-input",
             "--format", "json",
             query],
            input=json.dumps(input_doc),
            capture_output=True, text=True,
            timeout=OPA_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            return None, (f"opa exited {completed.returncode}: "
                          f"{completed.stderr.strip()[:200]}")
        payload = json.loads(completed.stdout)
        return payload["result"][0]["expressions"][0]["value"], None
    except FileNotFoundError:
        return None, "opa.exe not found -- the referee is missing"
    except subprocess.TimeoutExpired:
        return None, f"opa took longer than {OPA_TIMEOUT_SECONDS}s"
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        return None, f"opa answered gibberish: {exc}"


def ask_opa(input_doc: dict) -> OpaVerdict:
    """
    The CHECKER's question (data.sentinel.authz.decision) with the
    checker's judgment: any trouble -> fail closed (T30).
    """
    decision, error = eval_opa("data.sentinel.authz.decision", input_doc)
    if error is not None:
        return _fail_closed(error)
    try:
        return OpaVerdict(allow=bool(decision["allow"]),
                          deny=sorted(decision["deny"]))
    except (KeyError, TypeError) as exc:
        return _fail_closed(f"opa answered gibberish: {exc}")


def _fail_closed(reason: str) -> OpaVerdict:
    """T30: a broken or slow checker is a NO, never a shrug."""
    return OpaVerdict(allow=False, deny=[], checker_error=reason)


def check_policy(incident, **context) -> OpaVerdict:
    """
    The full T5/T6 step for one incident sitting at Action_Proposed:
    fill the form, ask the referee, move the board, return the verdict.
    """
    verdict = ask_opa(build_input(incident, **context))

    if verdict.checker_error is not None:
        verdict.event = "validation_failed"          # T30 -> Blocked
        incident.machine.validation_failed()
    elif verdict.allow:
        verdict.event = "opa_allowed"                # T5 -> Dependency_Check
        incident.machine.opa_allowed()
    else:
        verdict.event = "opa_denied"                 # T6 -> Blocked
        incident.machine.opa_denied()

    return verdict
