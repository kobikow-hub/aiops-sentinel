"""
sentinel/dsl/fingerprint.py
===========================
GATE 1, part three: the WAX SEAL (step P1.4, guide Part 12.2).

Once a proposal passes the parser and the type checker, we press a wax
seal onto it: the action_hash. From this moment on, EVERY check, every
permission slip and every diary line carries this exact fingerprint --
so no later step can quietly judge (or approve!) a DIFFERENT suggestion
than the one that was checked.

The recipe (from the guide's §5.3 header):
    sha256( incident_id || canonical(program) || proposed_at )

canonical(program) means: the program re-printed in ONE standard way,
so cosmetic differences (extra spaces, line breaks) do not change the
seal, but ANY real difference (verb, target, param, evidence, numbers)
does.
"""

import hashlib

from sentinel.dsl.parser import Program


def canonical(program: Program) -> str:
    """Re-print the program in one standard form."""
    parts = [f"{program.verb}({program.target}"]
    for key in sorted(program.params):
        value = program.params[key]
        value = int(value) if isinstance(value, float) and value == int(value) else value
        parts.append(f",{key}={value}")
    parts.append(")")
    ev = ",".join(f"{kind}({ev_id})" for kind, ev_id in program.evidence)
    lo, hi = program.confidence
    return f"propose {''.join(parts)} because {ev} confidence [{lo:g},{hi:g}];"


def make_action_hash(incident_id: str, program: Program, proposed_at: str) -> str:
    """The wax seal. Format matches OPA's check: ^sha256:[a-f0-9]{64}$"""
    material = "‖".join([incident_id, canonical(program), proposed_at])
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
