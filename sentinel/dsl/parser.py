"""
sentinel/dsl/parser.py
======================
GATE 1, part one: the GRAMMAR READER (step P1.4, transitions T3/T4).

The restaurant-menu rule: the AI may only order dishes printed on the
menu. The menu is dsl/remediation.ebnf -- the official spec file copied
verbatim from the guide (Part 5.1). This module carries the SAME grammar
written in Lark's notation, because Lark is the engine that actually
reads sentences. If the two ever disagree, the .ebnf file wins and this
file is wrong (that pairing is recorded in VERSIONS.md).

What the grammar alone guarantees:
  * only the 11 known verbs can appear (5 fixing, 2 looking, 4 banned --
    banned verbs PARSE on purpose, so a trick is recognized and logged,
    never silently mangled);
  * evidence is ids only -- there is NO quoted-text rule anywhere, so
    hidden instructions from logs cannot even be written;
  * one proposal per program, always ending in ';'.

The 'recommendation' branch of the spec belongs to the AdvisorMachine
extension (T34) -- not part of the first version, so the parser reads
proposals only.
"""

import re
from dataclasses import dataclass, field

from lark import Lark, Transformer, UnexpectedInput

# The menu, in Lark notation -- mirrors sentinel/dsl/remediation.ebnf.
# (.2 = higher lexer priority, so verbs/evidence-kinds win over IDENT.)
GRAMMAR = r"""
start: proposal

proposal: "propose" VERB "(" IDENT ("," param)* ")" \
          "because" evidence ("," evidence)* \
          "confidence" interval ";"

param: "delta" "=" NUMBER      -> delta
     | "revision" "=" IDENT    -> revision

evidence: EVKIND "(" IDENT ")"

interval: "[" NUMBER "," NUMBER "]"

VERB.2: "restart_pod" | "restart_service" | "scale_out" | "rollback"
      | "restart_master_db"
      | "list_services" | "get_metrics"
      | "delete_volume" | "drop_database" | "disable_monitoring"
      | "exfiltrate"

EVKIND.2: "alert" | "log" | "metric"

IDENT: /[a-zA-Z][a-zA-Z0-9_]*/
NUMBER: /[0-9]+(\.[0-9]+)?/

%import common.WS
%ignore WS
"""

# The three word groups -- same lists as the grammar, OPA and Prolog
# (test P17 later checks none of the four ever drifts).
REMEDIATION_VERBS = {"restart_pod", "restart_service", "scale_out",
                     "rollback", "restart_master_db"}
READ_ONLY_VERBS = {"list_services", "get_metrics"}
DESTRUCTIVE_VERBS = {"delete_volume", "drop_database",
                     "disable_monitoring", "exfiltrate"}


ALL_VERBS = REMEDIATION_VERBS | READ_ONLY_VERBS | DESTRUCTIVE_VERBS


class DslParseError(Exception):
    """The sentence is not on the menu. str(e) is the exact lesson."""


@dataclass(frozen=True)
class Program:
    """One parsed proposal -- plain data, ready for the type checker."""

    verb: str
    target: str
    params: dict = field(default_factory=dict)
    evidence: tuple = ()          # of (kind, id) pairs
    confidence: tuple = (0.0, 0.0)  # (lo, hi)

    @property
    def verb_class(self) -> str:
        if self.verb in REMEDIATION_VERBS:
            return "remediation"
        if self.verb in READ_ONLY_VERBS:
            return "read_only"
        return "destructive"


class _BuildProgram(Transformer):
    """Turns Lark's parse tree into a Program."""

    def delta(self, children):
        return ("delta", float(children[0]))

    def revision(self, children):
        return ("revision", str(children[0]))

    def evidence(self, children):
        return (str(children[0]), str(children[1]))

    def interval(self, children):
        return (float(children[0]), float(children[1]))

    def proposal(self, children):
        verb, target = str(children[0]), str(children[1])
        params = dict(c for c in children[2:] if isinstance(c, tuple)
                      and c[0] in ("delta", "revision"))
        evidence = tuple(c for c in children[2:] if isinstance(c, tuple)
                         and c[0] in ("alert", "log", "metric"))
        confidence = children[-1]
        return Program(verb=verb, target=target, params=params,
                       evidence=evidence, confidence=confidence)

    def start(self, children):
        return children[0]


_parser = Lark(GRAMMAR, parser="earley")
_builder = _BuildProgram()


def parse(text: str) -> Program:
    """Read one sentence against the menu. Junk -> DslParseError(lesson)."""
    stripped = text.strip()

    # A command or free text is not a DSL sentence at all.
    if not stripped.startswith("propose"):
        raise DslParseError(
            "grammar error: a command is not a DSL sentence; "
            "every proposal starts with 'propose'"
        )

    if '"' in stripped or "'" in stripped:
        raise DslParseError(
            "grammar error: quoted text has no place in the DSL"
        )

    try:
        tree = _parser.parse(stripped)
    except UnexpectedInput as exc:
        raise DslParseError(_lesson_from(exc, stripped)) from exc

    return _builder.transform(tree)


def _lesson_from(exc: UnexpectedInput, text: str) -> str:
    """Turn Lark's complaint into the exact lesson for the retry prompt."""
    # "propose <word>(" with a word that is not on the menu: the most
    # important lesson to name exactly (guide §5.3: "Not on the menu").
    match = re.match(r"\s*propose\s+([a-zA-Z][a-zA-Z0-9_]*)\s*\(", text)
    if match and match.group(1) not in ALL_VERBS:
        return f"grammar error: unknown action word '{match.group(1)}'"

    where = getattr(exc, "column", "?")
    return f"grammar error: the sentence breaks the menu rules near column {where}"
