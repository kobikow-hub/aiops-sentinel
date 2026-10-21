"""
sentinel/checkers/prolog_adapter.py
===================================
The PROLOG ADAPTER -- the logic judge takes the bench (step P2.3, T9/T10).

The judge answers three questions and always shows their work:
    allowed/3     may this agent run this verb on this target?
    risk_level/3  low or high -- THE ONLY PLACE RISK IS COMPUTED
                  (instructor checkpoint (b): OPA, Datalog, Z3 and the
                  Arbiter never compute a risk level of their own)
    why_refused/4 the written reasons for a NO

Courtroom procedure for one case:
  1. The adapter writes a small case file: consult the law book
     (rules/remediation.pl, verbatim from the guide), assert the case
     facts, ask the three questions, print the answers.
  2. The REAL SWI-Prolog engine (P0.4) runs it.
  3. The adapter parses the answers, gathers the proof, moves the board:
     prolog_allowed (T9 -> Temporal_Check) or prolog_forbidden
     (T10 -> Blocked).

The case facts and where they come from (the whole pipeline in a list):
    stateful/1, tier/2, change_frozen/1   -- the system photo
    sensitive_target/1, critical_in_blast/2 -- Datalog's notes (T7)
    proposal_confidence/2                 -- the AI's own DSL sentence
    rejected_before/2                     -- human history (T16)

Like every adapter: a MESSENGER with no opinions. All legal conclusions
come from the engine + the law book. Broken/slow judge = NO (T30).
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
RULES_FILE = _ROOT / "rules" / "remediation.pl"

SWIPL_CANDIDATES = [
    Path(r"C:\Program Files\swipl\bin\swipl.exe"),
    Path("swipl"),                       # PATH fallback (fresh terminals)
]

PROLOG_TIMEOUT_SECONDS = 10


@dataclass
class PrologVerdict:
    """The judge's ruling, with the written reasoning."""

    event: str                    # "prolog_allowed" | "prolog_forbidden" | "validation_failed"
    allowed: bool = False
    risk_level: str | None = None          # "low" | "high" | "none"
    why_refused: list[str] = field(default_factory=list)
    proof: list[str] = field(default_factory=list)
    checker_error: str | None = None


def _fact_lines(program, snapshot_facts: dict, datalog_facts: dict,
                rejected_before: list) -> list[str]:
    """Turn the case facts into assertz/1 lines for the case file."""
    lines = []
    for entity in snapshot_facts.get("stateful", []):
        lines.append(f"assertz(stateful({entity}))")
    for entity, tier in snapshot_facts.get("tier", []):
        lines.append(f"assertz(tier({entity}, {tier}))")
    for entity in snapshot_facts.get("change_frozen", []):
        lines.append(f"assertz(change_frozen({entity}))")
    for entity in datalog_facts.get("sensitive_target", []):
        lines.append(f"assertz(sensitive_target({entity}))")
    for crit in datalog_facts.get("critical_in_blast", []):
        lines.append(f"assertz(critical_in_blast({program.target}, {crit}))")
    lo, hi = program.confidence
    lines.append(f"assertz(proposal_confidence({lo}, {hi}))")
    for verb, target in rejected_before:
        lines.append(f"assertz(rejected_before({verb}, {target}))")
    return lines


_CASE_TEMPLATE = """:- consult('{rules}').
:- {facts}.

main :-
    ( allowed(sentinel_agent, {verb}, {target})
      -> format("ALLOWED:true~n")
      ;  format("ALLOWED:false~n") ),
    ( risk_level({verb}, {target}, Level)
      -> format("RISK:~w~n", [Level])
      ;  format("RISK:unknown~n") ),
    forall(why_refused(sentinel_agent, {verb}, {target}, Reason),
           format("WHY:~w~n", [Reason])),
    ( stateful({target}) -> format("PROOF:stateful({target})~n") ; true ),
    ( sensitive_target({target}) -> format("PROOF:sensitive_target({target})~n") ; true ),
    ( critical_in_blast({target}, C) -> format("PROOF:critical_in_blast({target},~w)~n", [C]) ; true ),
    ( proposal_confidence(Lo, _), Lo < 0.6 -> format("PROOF:low_confidence(~w)~n", [Lo]) ; true ),
    ( rejected_before({verb}, {target}) -> format("PROOF:rejected_before~n") ; true ),
    halt.

:- initialization(main).
"""


def _find_swipl() -> Path | None:
    import shutil
    for candidate in SWIPL_CANDIDATES:
        if candidate.is_absolute() and candidate.exists():
            return candidate
        found = shutil.which(str(candidate))
        if found:
            return Path(found)
    return None


def ask_prolog(program, snapshot_facts: dict, datalog_facts: dict,
               rejected_before: list | None = None) -> PrologVerdict:
    """Try the case before the real judge. Any trouble -> fail closed."""
    swipl = _find_swipl()
    if swipl is None:
        return _fail_closed("swipl not found -- the judge is missing")

    facts = _fact_lines(program, snapshot_facts, datalog_facts,
                        rejected_before or [])
    case = _CASE_TEMPLATE.format(
        rules=str(RULES_FILE).replace("\\", "/"),
        facts=",\n   ".join(facts) if facts else "true",
        verb=program.verb, target=program.target,
    )

    case_file = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pl", delete=False, encoding="utf-8") as fh:
            fh.write(case)
            case_file = Path(fh.name)
        completed = subprocess.run(
            [str(swipl), "-q", str(case_file)],
            capture_output=True, text=True,
            timeout=PROLOG_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            return _fail_closed(f"swipl exited {completed.returncode}: "
                                f"{completed.stderr.strip()[:200]}")
        return _parse_answers(completed.stdout)
    except subprocess.TimeoutExpired:
        return _fail_closed(f"swipl took longer than {PROLOG_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return _fail_closed(f"could not run the judge: {exc}")
    finally:
        if case_file is not None:
            case_file.unlink(missing_ok=True)


def _parse_answers(stdout: str) -> PrologVerdict:
    allowed, risk = None, None
    why, proof = [], []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("ALLOWED:"):
            allowed = line.removeprefix("ALLOWED:") == "true"
        elif line.startswith("RISK:"):
            risk = line.removeprefix("RISK:")
        elif line.startswith("WHY:"):
            why.append(line.removeprefix("WHY:"))
        elif line.startswith("PROOF:"):
            proof.append(line.removeprefix("PROOF:"))
    if allowed is None or risk is None:
        return _fail_closed(f"judge answered gibberish: {stdout[:200]!r}")
    if allowed and risk == "low" and not proof:
        proof = ["no high_risk/2 clause holds => risk_level low"]
    return PrologVerdict(
        event="prolog_allowed" if allowed else "prolog_forbidden",
        allowed=allowed, risk_level=risk, why_refused=why, proof=proof,
    )


def _fail_closed(reason: str) -> PrologVerdict:
    """T30: a broken or slow judge is a NO, never a shrug."""
    return PrologVerdict(event="validation_failed", allowed=False,
                         checker_error=reason)


def check_rules(incident, snapshot_facts: dict, datalog_facts: dict,
                rejected_before: list | None = None) -> PrologVerdict:
    """
    The full T9/T10 step for one incident sitting at Rule_Inference:
    try the case, move the board, remember the risk on the case folder
    (Phase 3's Arbiter reads it from there -- it never recomputes it).
    """
    verdict = ask_prolog(incident.program, snapshot_facts, datalog_facts,
                         rejected_before)

    if verdict.event == "validation_failed":
        incident.machine.validation_failed()         # T30 -> Blocked
    elif verdict.allowed:
        incident.risk_level = verdict.risk_level     # the official answer
        incident.machine.prolog_allowed()            # T9 -> Temporal_Check
    else:
        incident.machine.prolog_forbidden()          # T10 -> Blocked

    return verdict
