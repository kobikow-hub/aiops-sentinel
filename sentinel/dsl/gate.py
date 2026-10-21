"""
sentinel/dsl/gate.py
====================
GATE 1 assembled (step P1.4, transitions T3/T4).

The AI handed us a string. Nothing more. This gate decides what that
string becomes:

  parser OK + types OK  -> seal it (action_hash) and send
                           llm_action_proposed (T3):
                           AI_Analysis -> Action_Proposed
  anything wrong        -> send llm_output_invalid (T4):
                           AI_Analysis -> Recovery, carrying the EXACT
                           lesson (the counterexample for the retry)

Two iron rules live here:
  * The AI itself NEVER sends events -- this gate does. The AI's text
    is evidence, not authority.
  * NOTHING the AI writes reaches OPA, Datalog, Prolog or LTL without
    passing this gate first (instructor checkpoint (a)).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.dsl.fingerprint import make_action_hash
from sentinel.dsl.parser import DslParseError, Program, parse
from sentinel.dsl.typecheck import typecheck


@dataclass
class GateResult:
    """What came out of the gate: one of the two events, plus details."""

    event: str                    # "llm_action_proposed" | "llm_output_invalid"
    program: Program | None = None
    action_hash: str | None = None
    lesson: str | None = None     # the exact counterexample on failure
    trick_flag: bool = False      # destructive verb: dangerous, not a typo


def check_proposal(incident, raw_text: str, snapshot: dict,
                   evidence_ids: set[str]) -> GateResult:
    """
    Run one AI answer through GATE 1 and move the board accordingly.
    """
    # --- the menu (T3) ------------------------------------------------------
    try:
        program = parse(raw_text)
    except DslParseError as exc:
        incident.machine.llm_output_invalid()      # T4 -> Recovery
        return GateResult(event="llm_output_invalid", lesson=str(exc))

    # --- the order form (T4 checks) ----------------------------------------
    result = typecheck(program, snapshot, evidence_ids)
    if not result.ok:
        incident.machine.llm_output_invalid()      # T4 -> Recovery
        return GateResult(event="llm_output_invalid",
                          lesson=result.lesson,
                          trick_flag=result.trick_flag)

    # --- the wax seal, then T3 ----------------------------------------------
    proposed_at = datetime.now(timezone.utc).isoformat()
    action_hash = make_action_hash(incident.incident_id, program, proposed_at)

    incident.action_hash = action_hash
    incident.program = program
    incident.machine.llm_action_proposed()          # T3 -> Action_Proposed

    return GateResult(event="llm_action_proposed",
                      program=program, action_hash=action_hash)
