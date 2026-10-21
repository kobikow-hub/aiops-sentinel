"""
sentinel/verify/probe.py
========================
The HEALTH PROBE -- did the fix actually work? (step P5.1, T23/T24)

The doctor takes your temperature AGAIN after the medicine. "We gave
you the pill" (the Gateway's receipt) is not the same as "you are well"
(the alert is gone and the health numbers are OK).

The probe reads the LIVE world -- never the receipt, never the AI's
words, never what anyone hoped would happen:

    alert cleared AND metrics healthy -> metrics_healthy        (T23)
                                          -> Audit_Logging
    anything still wrong              -> metrics_still_degraded (T24)
                                          -> Recovery, with the numbers
                                             as the LESSON for the retry

Read-only, no credentials, no opinions about WHY it is still sick --
the numbers go into the lesson and the retry machinery (P5.2) decides
what happens next.
"""

from dataclasses import dataclass, field


@dataclass
class ProbeReport:
    """The doctor's chart: verdict + the numbers that decided it."""

    event: str                    # "metrics_healthy" | "metrics_still_degraded"
    checks: dict = field(default_factory=dict)   # name -> (value, threshold, ok)
    lesson: str | None = None     # set only when still degraded (for Recovery)


def read_health(world, target: str) -> dict:
    """
    One reading from the live world (the SystemMap view for the probe):
    which health checks does the target pass RIGHT NOW?
    """
    service = world.services[target]
    return {
        "service_healthy": (service.healthy, True,
                            service.healthy is True),
        "min_capacity": (service.nodes, service.min_capacity,
                         service.nodes >= service.min_capacity),
    }


def probe_health(incident, world, alert_active: bool) -> ProbeReport:
    """
    The full T23/T24 step for one incident at Verification.

    alert_active: is the original alert still firing? (In the pretend
    world the monitor is the caller; a real monitor plugs in later
    behind the same parameter.)
    """
    target = incident.program.target
    checks = dict(read_health(world, target))
    checks["alert_cleared"] = (not alert_active, True, not alert_active)

    all_ok = all(ok for (_value, _want, ok) in checks.values())

    if all_ok:
        incident.machine.metrics_healthy()            # T23 -> Audit_Logging
        return ProbeReport(event="metrics_healthy", checks=checks)

    failing = [f"{name}: got {value!r}, want {want!r}"
               for name, (value, want, ok) in checks.items() if not ok]
    lesson = ("health numbers still bad after the action -- "
              + "; ".join(failing))
    incident.machine.metrics_still_degraded()         # T24 -> Recovery
    return ProbeReport(event="metrics_still_degraded",
                       checks=checks, lesson=lesson)
