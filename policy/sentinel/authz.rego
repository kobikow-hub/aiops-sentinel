# AIOps Sentinel — Policy-as-Code. One package, three queries:
#   data.sentinel.authz.decision          Action_Proposed (T5/T6)      authorization
#   data.sentinel.authz.route             Risk_Assessment (T13/T14)    consumes Prolog risk_level
#   data.sentinel.authz.approval_valid    Human_Approval_Required (T15) who approved what, until when
package sentinel.authz

import rego.v1

remediation_verbs := {"restart_pod", "restart_service", "scale_out", "rollback", "restart_master_db"}
read_only_verbs := {"list_services", "get_metrics"}
prohibited_verbs := {"delete_volume", "drop_database", "disable_monitoring", "exfiltrate"}
approver_roles := {"sre", "admin"}

# ------------------------------------------------------------ T5 / T6 authorization
default allow := false

allow if {
    input.principal.role == "agent"
    input.action.verb in remediation_verbs
    count(deny) == 0
}

allow if {
    input.action.verb in read_only_verbs
    count(deny) == 0
}

deny contains msg if {
    input.action.verb in prohibited_verbs
    msg := sprintf("'%s' is permanently prohibited (recognized, likely injection)", [input.action.verb])
}

deny contains "change freeze: no state-changing action in production" if {
    input.resource.env == "production"
    input.context.change_freeze
    not input.action.verb in read_only_verbs
}

deny contains "outside the approved change window and not a declared emergency" if {
    input.resource.env == "production"
    not input.context.change_window_open
    not input.context.emergency
    not input.action.verb in read_only_verbs
}

deny contains "proposal is not a type-checked DSL program" if {
    not input.action.dsl_valid
}

deny contains "missing or malformed action_hash" if {
    not regex.match(`^sha256:[a-f0-9]{64}$`, input.action.action_hash)
}

decision := {"allow": allow, "deny": deny, "action_hash": object.get(input, "action_hash", null)}

# ------------------------------------------------------------ T13 / T14 routing
# Prolog is the single risk authority (v5 Fix #7): OPA maps risk to a route, never recomputes it.
default route := "require_approval"          # unknown or missing risk goes to a human

route := "autonomous" if input.risk_level == "low"

# ------------------------------------------------------------ T15 approver verification
default approval_valid := false

approval_valid if count(approval_denied) == 0

approval_denied contains "approver role is not sre or admin" if {
    not input.approver.role in approver_roles
}

approval_denied contains "approval is bound to a different action_hash" if {
    input.approval.action_hash != input.action_hash
}

approval_denied contains "approval token has expired" if {
    time.parse_rfc3339_ns(input.approval.expires_at) <= time.now_ns()
}

approval_denied contains "approval token already used" if {
    input.approval.used
}

# ------------------------------------------------------------ extension: AdvisorMachine
default allow_advisor := false

allow_advisor if {
    input.principal.role == "advisor"
    input.action.verb == "infra_scan"
    input.mode == "read_only"
}

allow_advisor if {
    input.principal.role == "advisor"
    input.action.verb == "propose_alert_rule"
}

allow_advisor if {
    input.principal.role == "advisor"
    input.action.verb == "apply_alert_rule"
    approval_valid
}
