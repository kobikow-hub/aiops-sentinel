"""
sentinel/dsl/typecheck.py
=========================
GATE 1, part two: the TYPE CHECKER (step P1.4, guide Part 5.2).

The parser proved the sentence is on the menu. Now we check the ORDER
MAKES SENSE: you can't order "pod soup" from a table that has no pods.
A program counts as valid (Dsl_Valid) only if all four rules pass:

  Grounded  -- the target exists in the system photo, and every evidence
               id exists in the text the AI was given. No answer without
               a source.
  Right kind-- the target's kind matches the action (you can't
               restart_pod a database).
  Limits    -- delta is a whole number 1..5; revision must be a real
               older version of the target; 0 <= lo <= hi <= 1.
  Trick flag-- a destructive verb parses but is marked as a likely
               injection: recorded as a DANGEROUS REQUEST, not a
               spelling mistake. (OPA formally denies it at T6; the
               guide's §5.3 table: "Known is not the same as allowed.")

Every failure carries the exact lesson -- the counterexample that goes
back to the AI in the retry prompt (rule L10 / test P15).
"""

from dataclasses import dataclass, field

from sentinel.dsl.parser import Program

# What kind of thing each verb works on (guide Part 5.2's action table).
VERB_TARGET_KIND = {
    "restart_pod": "pod",
    "restart_service": "service",
    "scale_out": "deployment",
    "rollback": "deployment",
    "restart_master_db": "database",
    # read-only verbs accept any known entity ("scope")
    "list_services": None,
    "get_metrics": None,
}


@dataclass
class TypeCheckResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    trick_flag: bool = False   # destructive verb: dangerous request, not a typo

    @property
    def lesson(self) -> str:
        """The exact counterexample for the retry prompt."""
        return "; ".join(self.problems)


def typecheck(program: Program, snapshot: dict, evidence_ids: set[str]) -> TypeCheckResult:
    """
    The four rules, in order. `snapshot` is the read-only system photo:
      {entity_name: {"kind": "pod"|"service"|"deployment"|"database",
                     "revisions": [...older versions...]}}
    `evidence_ids` are the ids that really appeared in the alert + safe
    logs the AI was shown (alert ids, log-line ids, metric names).
    """
    problems: list[str] = []

    # --- trick flag first: a destructive verb is judged dangerous even
    #     if the rest of the order is tidy ----------------------------------
    if program.verb_class == "destructive":
        return TypeCheckResult(
            ok=False, trick_flag=True,
            problems=[f"destructive verb '{program.verb}' is recognized and "
                      f"recorded as a likely injection; it is never allowed"],
        )

    # --- Grounded: the target must exist in the photo ---------------------
    entity = snapshot.get(program.target)
    if entity is None:
        problems.append(
            f"type error: '{program.target}' does not exist in the system photo"
        )

    # --- Right kind: target's kind must match the action -------------------
    wanted = VERB_TARGET_KIND.get(program.verb)
    if entity is not None and wanted is not None and entity["kind"] != wanted:
        problems.append(
            f"type error: {program.verb} expects a {wanted.capitalize()}, "
            f"got a {entity['kind'].capitalize()}"
        )

    # --- Grounded: every evidence id must come from the shown text ---------
    for kind, ev_id in program.evidence:
        if ev_id not in evidence_ids:
            problems.append(
                f"type error: evidence {kind}({ev_id}) was never shown to the AI"
            )

    # --- Limits -------------------------------------------------------------
    if "delta" in program.params:
        delta = program.params["delta"]
        if delta != int(delta) or not (1 <= delta <= 5):
            problems.append(
                f"type error: delta must be a whole number 1..5, got {delta:g}"
            )

    if "revision" in program.params and entity is not None:
        rev = program.params["revision"]
        if rev not in entity.get("revisions", []):
            problems.append(
                f"type error: revision '{rev}' is not a real older version "
                f"of '{program.target}'"
            )

    lo, hi = program.confidence
    if not (0.0 <= lo <= hi <= 1.0):
        problems.append(
            f"type error: confidence must satisfy 0 <= lo <= hi <= 1, "
            f"got [{lo:g}, {hi:g}]"
        )

    return TypeCheckResult(ok=not problems, problems=problems)
