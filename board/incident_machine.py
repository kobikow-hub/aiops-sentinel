"""
board/incident_machine.py
=========================
The GAME BOARD (guide Part 7): the state machine that rules them all.

Think of a board game: states are squares, events are dice rolls, and the
transitions T1..T30 say which roll may move the piece from which square.
Anything not printed on the board CANNOT HAPPEN -- that is what makes
illegal shortcuts impossible by design.

This file is the SKELETON built right after Phase 0 (see the development
plan, section 8): all 18 squares exist now, and the happy-road moves are
laid down as stubs. Each phase then "switches on" its own moves as its
checkers come alive:

    Phase 1 -> T1-T4      (intake, redaction, the AI, GATE 1)
    Phase 2 -> T5-T12+T30 (OPA, Datalog, Prolog, LTL)
    Phase 3 -> T13-T17    (risk route, human approval, SLA timer)
    Phase 4 -> T18-T22    (Z3 last look, Tool Gateway)
    Phase 5 -> T23-T29    (probe, recovery, escalation, audit)

The board is the only boss: components SEND EVENTS, the board decides
what may happen next. No component ever changes state directly.
"""

from statemachine import State, StateMachine


class IncidentMachine(StateMachine):
    """One incident = one piece moving across this board (guide Part 7.1)."""

    # ------------------------------------------------------------------
    # The 18 squares (states)
    # ------------------------------------------------------------------
    # Phase 1 -- intake & analysis
    awaiting_alert = State("Awaiting_Alert", initial=True)
    alert_parsed = State("Alert_Parsed")
    ai_analysis = State("AI_Analysis")
    action_proposed = State("Action_Proposed")

    # Phase 2 -- governance validation (the four checkers)
    dependency_check = State("Dependency_Check")
    rule_inference = State("Rule_Inference")
    temporal_check = State("Temporal_Check")

    # Phase 3 -- decision & approval
    risk_assessment = State("Risk_Assessment")
    human_approval_required = State("Human_Approval_Required")

    # Phase 4 -- deployment
    constraint_check = State("Constraint_Check")
    ready_for_execution = State("Ready_For_Execution")
    action_executed = State("Action_Executed")

    # Phase 5 -- verify & close
    verification = State("Verification")
    audit_logging = State("Audit_Logging")
    incident_resolved = State("Incident_Resolved", final=True)

    # The "something went wrong" squares
    blocked = State("Blocked")      # a checker said NO; nothing changed
    recovery = State("Recovery")    # a normal failure; retry with a lesson
    escalated = State("Escalated")  # a human owns it now

    # ------------------------------------------------------------------
    # The moves (events). Phase 1 activates T1-T4; the rest of the happy
    # road is laid down as stubs so later phases only have to switch
    # their guards on, never redraw the board.
    # ------------------------------------------------------------------
    # --- Phase 1 moves (ACTIVE in this phase) ---
    alert_received = awaiting_alert.to(alert_parsed)            # T1
    logs_parsed = alert_parsed.to(ai_analysis)                  # T2
    llm_action_proposed = ai_analysis.to(action_proposed)       # T3
    llm_output_invalid = ai_analysis.to(recovery)               # T4

    # --- happy-road stubs for later phases (switched on in Phases 2-5) ---
    opa_allowed = action_proposed.to(dependency_check)          # T5
    datalog_clear = dependency_check.to(rule_inference)         # T7
    prolog_allowed = rule_inference.to(temporal_check)          # T9
    validation_passed = temporal_check.to(risk_assessment)      # T11
    risk_low = risk_assessment.to(constraint_check)             # T13
    z3_sat = constraint_check.to(ready_for_execution)           # T18
    execute = ready_for_execution.to(action_executed)           # T20
    execution_succeeded = action_executed.to(verification)      # T21
    metrics_healthy = verification.to(audit_logging)            # T23 (probe OK)
    audit_log_created = audit_logging.to(incident_resolved)     # T29

    # --- NO-road and human-road stubs (guide Part 7; activated in
    #     Phases 2-5). Every square must be reachable -- the library
    #     refuses a board with squares no road leads to, and it is right:
    #     a square nothing can reach is a drawing, not a game square. ---
    opa_denied = action_proposed.to(blocked)                    # T6
    datalog_sensitive_path = dependency_check.to(blocked)       # T8
    prolog_forbidden = rule_inference.to(blocked)               # T10
    temporal_violation = temporal_check.to(blocked)             # T12
    risk_high = risk_assessment.to(human_approval_required)     # T14
    human_approved = human_approval_required.to(constraint_check)   # T15
    human_rejected = human_approval_required.to(blocked)        # T16
    approval_timeout = human_approval_required.to(escalated)    # T17 (rule L4)
    z3_unsat = constraint_check.to(blocked)                     # T19
    execution_failed = action_executed.to(recovery)             # T22
    metrics_still_degraded = verification.to(recovery)          # T24 -> Recovery
    retry_available = recovery.to(ai_analysis)                  # T25 (with lesson)
    retries_exhausted = recovery.to(escalated)                  # T26 (>= 2 tries)
    escalation_notified = blocked.to(escalated)                 # T27
    human_resolution_recorded = escalated.to(audit_logging)     # T28

    # T30 -- fail closed: a BROKEN or too-slow checker is a NO, from any
    # checking square. Activated in Phase 2 with the first real checker;
    # per guide Part 7.5, T30 also covers Constraint_Check (Z3, Phase 4).
    validation_failed = (
        action_proposed.to(blocked)
        | dependency_check.to(blocked)
        | rule_inference.to(blocked)
        | temporal_check.to(blocked)
        | constraint_check.to(blocked)
    )
