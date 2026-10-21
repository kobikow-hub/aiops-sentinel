"""
sentinel/checkers/datalog.py
============================
The DATALOG MODULE -- the "who breaks?" finder (step P2.2, T7/T8).

The domino expert: services are dominoes, depends_on(x, y) means x falls
if y falls. Before anything is touched, this guard follows the chains
and counts. Two hard NOs (the veto): 10+ services would break, or secret
data could reach the outside. It also hands two facts forward to Prolog.

THE LAW THIS FILE OBEYS: rules/topology.dl (the official Soufflé spec,
copied verbatim from guide Part 10.2). Soufflé has no native Windows
build, so this plain Python module MIRRORS the spec rule for rule --
each function quotes the .dl lines it implements. If the two ever
disagree, the .dl file wins and this file is wrong (VERSIONS.md).

Like every checker: read-only, no credentials, no risk opinions.
It reports WHO breaks; how risky that is remains Prolog's job alone.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topology:
    """The read-only system photo -- the .dl file's .input facts.

    depends_on: {(x, y)} meaning x needs y (x falls if y falls)
    """

    depends_on: frozenset = frozenset()
    sensitive: frozenset = frozenset()
    critical: frozenset = frozenset()
    reads_from: frozenset = frozenset()
    sends_to: frozenset = frozenset()
    external: frozenset = frozenset()
    blast_radius_limit: int = 10          # guide Part 17.3: the magic number

    @staticmethod
    def from_dict(doc: dict) -> "Topology":
        return Topology(
            depends_on=frozenset(map(tuple, doc.get("depends_on", []))),
            sensitive=frozenset(doc.get("sensitive", [])),
            critical=frozenset(doc.get("critical", [])),
            reads_from=frozenset(map(tuple, doc.get("reads_from", []))),
            sends_to=frozenset(map(tuple, doc.get("sends_to", []))),
            external=frozenset(doc.get("external", [])),
            blast_radius_limit=doc.get("blast_radius_limit", 10),
        )


# ---------------------------------------------------------------------------
# The chain-follower -- the heart of the file.
#
#   .dl:  affected_by(x, t) :- depends_on(x, t).
#         affected_by(x, t) :- depends_on(x, y), affected_by(y, t).
# ---------------------------------------------------------------------------
def affected_by(topo: Topology, t: str) -> set[str]:
    """Everyone hurt if t stops: direct dependents, then chains of them."""
    hurt: set[str] = set()
    frontier = {t}
    while frontier:
        step = {x for (x, y) in topo.depends_on if y in frontier and x not in hurt}
        hurt |= step
        frontier = step
    return hurt


# ---------------------------------------------------------------------------
# T2: the context the model may use (plugs the redactor's socket).
#
#   .dl:  alert_context(s) :- alerting(s).
#         alert_context(x) :- alerting(s), depends_on(s, x).
#         alert_context(x) :- alerting(s), affected_by(x, s).
# ---------------------------------------------------------------------------
def alert_context(topo: Topology, alerting: str) -> set[str]:
    """The screamer, what it needs, and who needs it -- nothing else."""
    context = {alerting}
    context |= {y for (x, y) in topo.depends_on if x == alerting}
    context |= affected_by(topo, alerting)
    return context


# ---------------------------------------------------------------------------
# Blast radius of acting on the target.
#
#   .dl:  blast(t, x)      :- target(t), affected_by(x, t).
#         dependents(t, n) :- target(t), n = count : { blast(t, _) }.
#         critical_in_blast(t, x) :- blast(t, x), critical(x).
# ---------------------------------------------------------------------------
def blast(topo: Topology, target: str) -> set[str]:
    return affected_by(topo, target)


def dependents(topo: Topology, target: str) -> int:
    return len(blast(topo, target))


def critical_in_blast(topo: Topology, target: str) -> set[str]:
    return blast(topo, target) & topo.critical


# ---------------------------------------------------------------------------
# Sensitive data: exposure and forbidden flows.
#
#   .dl:  exposed_to_sensitive(x) :- depends_on(x, y), sensitive(y).
#         exposed_to_sensitive(x) :- reads_from(x, y), sensitive(y).
#         exposed_to_sensitive(x) :- depends_on(x, y), exposed_to_sensitive(y).
# ---------------------------------------------------------------------------
def exposed_to_sensitive(topo: Topology) -> set[str]:
    """Everyone who touches secret data, directly or through a chain."""
    exposed = {x for (x, y) in topo.depends_on if y in topo.sensitive}
    exposed |= {x for (x, y) in topo.reads_from if y in topo.sensitive}
    changed = True
    while changed:                      # bottom-up, like the Soufflé engine
        step = {x for (x, y) in topo.depends_on if y in exposed} - exposed
        exposed |= step
        changed = bool(step)
    return exposed


#   .dl:  sensitive_target(t) :- target(t), sensitive(t).
#         sensitive_target(t) :- target(t), exposed_to_sensitive(t).
def sensitive_target(topo: Topology, target: str) -> bool:
    return target in topo.sensitive or target in exposed_to_sensitive(topo)


#   .dl:  sensitive_flow(s, e) :- exposed_to_sensitive(s), sends_to(s, e), external(e).
def sensitive_flow(topo: Topology, s: str) -> set[str]:
    """Outside places s could leak secrets to (empty = no leak road)."""
    if s not in exposed_to_sensitive(topo) and s not in topo.sensitive:
        return set()
    return {e for (x, e) in topo.sends_to if x == s and e in topo.external}


# ---------------------------------------------------------------------------
# The Dependency_Check verdict.
#
#   .dl:  veto(t, "blast_radius")   :- dependents(t, n), blast_radius_limit(k), n >= k.
#         veto(t, "sensitive_flow") :- target(t), sensitive_flow(t, _).
# ---------------------------------------------------------------------------
@dataclass
class DatalogVerdict:
    """The domino expert's report: verdict + everything it counted."""

    event: str                       # "datalog_clear" | "datalog_sensitive_path"
    reason: str | None = None        # "blast_radius" | "sensitive_flow"
    dependents: int = 0
    paths: list = field(default_factory=list)      # the broken chains, for humans
    facts_for_prolog: dict = field(default_factory=dict)


def _paths_to(topo: Topology, target: str, hurt: set[str]) -> list[list[str]]:
    """Human-readable domino chains [victim, ..., target] for the report."""
    parents = {}
    frontier, seen = {target}, {target}
    while frontier:
        step = set()
        for (x, y) in topo.depends_on:
            if y in frontier and x not in seen:
                parents[x] = y
                step.add(x)
        seen |= step
        frontier = step
    paths = []
    for victim in sorted(hurt):
        chain, node = [victim], victim
        while node != target:
            node = parents[node]
            chain.append(node)
        paths.append(chain)
    return paths


def check_dependencies(incident, topo: Topology) -> DatalogVerdict:
    """
    The full T7/T8 step for one incident sitting at Dependency_Check:
    count the dominoes, check the leak roads, move the board, and write
    the two facts Prolog will read (sensitive_target, critical_in_blast).
    """
    target = incident.program.target
    hurt = blast(topo, target)
    n = len(hurt)

    facts = {
        "sensitive_target": [target] if sensitive_target(topo, target) else [],
        "critical_in_blast": sorted(critical_in_blast(topo, target)),
    }

    leak_roads = sensitive_flow(topo, target)

    if n >= topo.blast_radius_limit:
        verdict = DatalogVerdict(
            event="datalog_sensitive_path", reason="blast_radius",
            dependents=n, paths=_paths_to(topo, target, hurt),
            facts_for_prolog=facts,
        )
    elif leak_roads:
        verdict = DatalogVerdict(
            event="datalog_sensitive_path", reason="sensitive_flow",
            dependents=n,
            paths=[[target, e] for e in sorted(leak_roads)],
            facts_for_prolog=facts,
        )
    else:
        verdict = DatalogVerdict(event="datalog_clear", dependents=n,
                                 facts_for_prolog=facts)

    if verdict.event == "datalog_clear":
        incident.machine.datalog_clear()             # T7 -> Rule_Inference
    else:
        incident.machine.datalog_sensitive_path()    # T8 -> Blocked

    return verdict
