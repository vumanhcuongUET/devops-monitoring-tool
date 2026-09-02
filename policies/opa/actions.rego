package devops.actions

import future.keywords

# Phase 16 P1-9: the engine's OPA input now sends the full action shape
# (risk_level, status, parsed_params, command_type, resource_type/name,
# labels, context, title) — every rule below used to be undefined against
# the old {"command", "id"} input, so allow defaulted to false and turning
# on OPA_ENFORCE denied everything.
#
# Structure:
#   violations  — every reason the action must not run (consumed by
#                 opa_client via /v1/data/devops/actions/violations)
#   allow       — the decision: base preconditions AND no violations.
#                 (The old deny[msg] sets were dead letters: nothing read
#                 them and they never influenced `allow`.)

default allow := false

# Base preconditions (independent of deny rules)
preconditions_allow if {
    input.action.risk_level == "safe"
    is_read_only_action(input.action.parsed_params)
}

preconditions_allow if {
    input.environment != "production"
    input.action.status == "approved"
}

preconditions_allow if {
    input.environment == "production"
    input.action.status == "approved"
    input.action.risk_level in ["safe", "low"]
}

# The decision: preconditions hold AND no policy violation applies.
allow if {
    preconditions_allow
    count(violations) == 0
}

# Business hours restriction for production
violations contains violation if {
    input.environment == "production"
    is_business_hour(input.timestamp)
    input.action.risk_level in ["high", "critical"]
    not has_override(input.action)
    violation := {
        "policy_id": "production-business-hours",
        "description": sprintf("High-risk actions not allowed during business hours: %s", [object.get(input.action, "title", "action")]),
        "severity": "high",
    }
}

# Protect production databases
violations contains violation if {
    input.environment == "production"
    is_database_action(input.action)
    is_destructive_action(input.action)
    violation := {
        "policy_id": "production-database",
        "description": "Production database destructive actions are forbidden",
        "severity": "critical",
    }
}

# Protect namespace deletions
violations contains violation if {
    input.action.command_type == "kubectl"
    input.action.parsed_params.action == "delete"
    input.action.parsed_params.resource_type == "namespace"
    violation := {
        "policy_id": "namespace-deletion",
        "description": "Namespace deletion is forbidden",
        "severity": "critical",
    }
}

# Protect critical resources
violations contains violation if {
    is_critical_resource(input.action)
    is_destructive_action(input.action)
    not has_override(input.action)
    violation := {
        "policy_id": "critical-resource",
        "description": sprintf("Action forbidden on critical resource: %s", [object.get(input.action, "resource_name", "unknown")]),
        "severity": "high",
    }
}

# Helper functions

is_read_only_action(params) if {
    params.action in ["get", "describe", "logs", "top", "list"]
}

is_business_hour(timestamp) if {
    # OPA has no time.hour builtin — time.clock(ns) returns [h, m, s].
    ns := time.parse_rfc3339_ns(timestamp)
    clock := time.clock(ns)
    hour := clock[0]
    day := time.weekday(ns)
    hour >= 9
    hour <= 17
    # time.weekday() returns day NAMES ("Monday"..), never numbers.
    day != "Saturday"
    day != "Sunday"
}

forbidden_action(action) if {
    is_destructive_action(action)
    action.risk_level == "critical"
}

is_destructive_action(action) if {
    action.command_type == "kubectl"
    action.parsed_params.action in ["delete", "drain", "cordon"]
}

is_destructive_action(action) if {
    action.command_type == "helm"
    action.parsed_params.action == "uninstall"
}

is_database_action(action) if {
    action.resource_type == "database"
}

is_database_action(action) if {
    name := object.get(action, "resource_name", "")
    is_string(name)
    contains(name, "db")
}

is_database_action(action) if {
    name := object.get(action, "resource_name", "")
    is_string(name)
    contains(name, "postgres")
}

is_database_action(action) if {
    name := object.get(action, "resource_name", "")
    is_string(name)
    contains(name, "mysql")
}

is_critical_resource(action) if {
    action.environment == "production"
    object.get(action, "labels", {})["critical"] == "true"
}

is_critical_resource(action) if {
    action.environment == "production"
    action.resource_type in ["database", "storage", "statefulset"]
}

has_override(action) if {
    action.context.override_reason
}

has_override(action) if {
    action.context.emergency_override == true
}
