"""
gateway/system_map.py
=====================
The PRETEND SYSTEM MAP (step P4.2) -- the model railway's landscape.

One pretend world, three views, always consistent:
  * snapshot_for_gate1()   entity names + kinds + revisions (grounding)
  * topology_for_datalog() the domino field (depends_on, sensitive, ...)
  * live_snapshot_for_z3() the live photo with a VERSION number

The version number is the map's heartbeat: EVERY change to the world
(a restart, a scale-out, even a node dying on its own) bumps it. That
is what makes compare-and-execute possible in P4.3: Z3 pins a version,
and the Gateway refuses if the world moved past it.
"""

from dataclasses import dataclass, field

from constraints.deployment_gate import LiveSnapshot
from sentinel.checkers.datalog import Topology


@dataclass
class Service:
    """One place on the railway."""

    name: str
    kind: str                    # "pod" | "service" | "deployment" | "database"
    nodes: int = 1               # working machines right now
    min_capacity: int = 1
    max_nodes: int = 100
    stateful: bool = False
    critical: bool = False
    sensitive: bool = False
    revisions: tuple = ()        # older versions that really exist
    has_replica: bool = False
    healthy: bool = True


@dataclass
class SystemMap:
    """The whole pretend world, with its heartbeat version number."""

    services: dict = field(default_factory=dict)     # name -> Service
    depends_on: list = field(default_factory=list)   # [(x, y), ...]
    reads_from: list = field(default_factory=list)
    sends_to: list = field(default_factory=list)
    external: list = field(default_factory=list)
    version: int = 1
    cluster_node_budget: int = 1_000_000

    # ---------------------------------------------------------- three views
    def snapshot_for_gate1(self) -> dict:
        """What GATE 1's type checker grounds against."""
        return {name: {"kind": s.kind, "revisions": list(s.revisions)}
                for name, s in self.services.items()}

    def topology_for_datalog(self) -> Topology:
        """The domino field the 'who breaks?' finder walks."""
        return Topology.from_dict({
            "depends_on": [list(edge) for edge in self.depends_on],
            "sensitive": [n for n, s in self.services.items() if s.sensitive],
            "critical": [n for n, s in self.services.items() if s.critical],
            "reads_from": [list(edge) for edge in self.reads_from],
            "sends_to": [list(edge) for edge in self.sends_to],
            "external": list(self.external),
        })

    def snapshot_facts_for_prolog(self) -> dict:
        """The judge's snapshot facts (stateful / production-critical)."""
        return {
            "stateful": [n for n, s in self.services.items() if s.stateful],
            "tier": [(n, "production_critical")
                     for n, s in self.services.items() if s.critical],
            "change_frozen": [],
        }

    def live_snapshot_for_z3(self, target: str) -> LiveSnapshot:
        """The live photo, stamped with the current version."""
        s = self.services[target]
        cluster = sum(svc.nodes for svc in self.services.values())
        return LiveSnapshot(
            version=self.version,
            active_nodes=s.nodes,
            min_capacity=s.min_capacity,
            max_nodes=s.max_nodes,
            cluster_nodes=cluster,
            node_budget=self.cluster_node_budget,
            revisions=s.revisions,
            has_replica=s.has_replica,
        )

    # ------------------------------------------------------- world changes
    def bump(self) -> int:
        """The heartbeat: any change to the world bumps the version."""
        self.version += 1
        return self.version


def demo_map() -> SystemMap:
    """The three stories' little world (Story 1's pod, Story 2's db)."""
    return SystemMap(
        services={
            "web_frontend": Service("web_frontend", "pod",
                                    nodes=4, min_capacity=3),
            "auth_service": Service("auth_service", "service",
                                    nodes=3, min_capacity=2, critical=True),
            "checkout": Service("checkout", "deployment",
                                nodes=5, min_capacity=3,
                                revisions=("v41", "v42")),
            "master_db": Service("master_db", "database",
                                 nodes=2, min_capacity=1, stateful=True,
                                 sensitive=True, has_replica=True),
        },
        depends_on=[("web_frontend", "auth_service"),
                    ("auth_service", "master_db"),
                    ("checkout", "master_db")],
        external=["partner_api"],
    )
