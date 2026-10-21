# AIOps Sentinel — the official rule-book tests (guide Part 10.1 table).
# Run with the real referee:  tools/opa.exe test policy/ -v
# The law book is tested in its own language, by its own engine.
package sentinel.authz_test

import data.sentinel.authz
import rego.v1

good_hash := "sha256:9f2c000000000000000000000000000000000000000000000000000000000000"

base_input := {
	"principal": {"id": "sentinel-agent", "role": "agent"},
	"action": {
		"verb": "restart_pod", "target": "web_frontend", "params": {},
		"dsl_valid": true, "action_hash": good_hash,
	},
	"resource": {"kind": "pod", "env": "production"},
	"context": {"change_window_open": true, "change_freeze": false, "emergency": false},
	"action_hash": good_hash,
}

# --------------------------------------------------- T5/T6 authorization
test_restart_allowed_in_window if {
	authz.allow with input as base_input
}

test_prohibited_verb_denied if {
	inp := object.union(base_input, {"action": object.union(base_input.action, {"verb": "delete_volume"})})
	not authz.allow with input as inp
	some msg in authz.deny with input as inp
	contains(msg, "permanently prohibited")
}

test_change_freeze_denied if {
	inp := object.union(base_input, {"context": object.union(base_input.context, {"change_freeze": true})})
	not authz.allow with input as inp
}

test_outside_window_denied if {
	inp := object.union(base_input, {"context": object.union(base_input.context, {"change_window_open": false})})
	not authz.allow with input as inp
}

test_emergency_overrides_window if {
	inp := object.union(base_input, {"context": object.union(
		base_input.context,
		{"change_window_open": false, "emergency": true},
	)})
	authz.allow with input as inp
}

test_read_only_allowed_during_freeze if {
	inp := object.union(base_input, {
		"action": object.union(base_input.action, {"verb": "get_metrics"}),
		"context": object.union(base_input.context, {"change_freeze": true}),
	})
	authz.allow with input as inp
}

test_non_dsl_denied if {
	inp := object.union(base_input, {"action": object.union(base_input.action, {"dsl_valid": false})})
	not authz.allow with input as inp
}

test_bad_hash_denied if {
	inp := object.union(base_input, {"action": object.union(base_input.action, {"action_hash": "not-a-seal"})})
	not authz.allow with input as inp
}

# --------------------------------------------------- T13/T14 routing
test_route_low if {
	authz.route == "autonomous" with input as {"risk_level": "low", "action_hash": good_hash}
}

test_route_high if {
	authz.route == "require_approval" with input as {"risk_level": "high", "action_hash": good_hash}
}

test_route_missing if {
	authz.route == "require_approval" with input as {"action_hash": good_hash}
}

# --------------------------------------------------- T15 approver check
valid_approval := {
	"approver": {"id": "dana", "role": "sre"},
	"approval": {
		"action_hash": good_hash,
		"expires_at": "2099-01-01T00:00:00Z", "used": false,
	},
	"action_hash": good_hash,
}

test_approval_sre_valid if {
	authz.approval_valid with input as valid_approval
}

test_approval_viewer_refused if {
	inp := object.union(valid_approval, {"approver": {"id": "sam", "role": "viewer"}})
	not authz.approval_valid with input as inp
	some msg in authz.approval_denied with input as inp
	contains(msg, "role is not sre or admin")
}

test_approval_other_hash_refused if {
	inp := object.union(valid_approval, {"approval": object.union(
		valid_approval.approval,
		{"action_hash": "sha256:def4000000000000000000000000000000000000000000000000000000000000"},
	)})
	not authz.approval_valid with input as inp
}

test_approval_expired_refused if {
	inp := object.union(valid_approval, {"approval": object.union(
		valid_approval.approval,
		{"expires_at": "2020-01-01T00:00:00Z"},
	)})
	not authz.approval_valid with input as inp
}

test_approval_reused_refused if {
	inp := object.union(valid_approval, {"approval": object.union(
		valid_approval.approval,
		{"used": true},
	)})
	not authz.approval_valid with input as inp
}

# --------------------------------------------------- Advisor (extension)
test_advisor_apply_needs_approval if {
	not authz.allow_advisor with input as {
		"principal": {"role": "advisor"},
		"action": {"verb": "apply_alert_rule"},
		"approver": {"role": "viewer"},
		"approval": {"action_hash": "x", "expires_at": "2020-01-01T00:00:00Z", "used": true},
		"action_hash": "y",
	}
}
