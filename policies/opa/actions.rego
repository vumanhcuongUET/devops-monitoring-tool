package devops.actions

import future.keywords.contains
import future.keywords.if
import future.keywords.every

default allow = false

# Allow read-only actions without approval
allow if {
    input.action.risk_level == "safe"
    is_read_only_action(input.action.parsed_params)
}

# Allow approved actions in non-production environments
allow if {
    input.environment != "production"
    input.action.status == "approved"
    not forbidden_action(input.action)
}

# Allow safe operations in production with approval
allow if {
    input.environment == "production"
    input.action.status == "approved"
    input.action.risk_level in ["safe", "low"]
    not forbidden_action(input.action)
}

# Business hours restriction for production
deny[msg] if {
    input.environment == "production"
    is_business_hour(input.timestamp)
    input.action.risk_level in ["high", "critical"]
    not has_override(input.action)
    msg := sprintf("High-risk actions not allowed during business hours: %s", [input.action.title])
}

# Protect production databases
deny[msg] if {
    input.environment == "production"
    is_database_action(input.action)
    is_destructive_action(input.action)
    msg := "Production database destructive actions are forbidden"
}

# Protect namespace deletions
deny[msg] if {
    input.action.command_type == "kubectl"
    input.action.parsed_params.action == "delete"
    input.action.parsed_params.resource_type == "namespace"
    msg := "Namespace deletion is forbidden"
}

# Protect critical resources
deny[msg] if {
    is_critical_resource(input.action)
    is_destructive_action(input.action)
    not has_override(input.action)
    msg := sprintf("Action forbidden on critical resource: %s", [input.action.resource_name])
}

# Helper functions

is_read_only_action(params) if {
    params.action in ["get", "describe", "logs", "top", "list"]
}

is_business_hour(timestamp) if {
    hour := time.hour(timestamp)
    day := time.weekday(timestamp)
    hour >= 9
    hour <= 17
    day >= 1
    day <= 5
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
    action.resource_name
    contains(action.resource_name, "db")
}

is_database_action(action) if {
    action.resource_name
    contains(action.resource_name, "postgres")
}

is_database_action(action) if {
    action.resource_name
    contains(action.resource_name, "mysql")
}

is_critical_resource(action) if {
    action.environment == "production"
    action.labels["critical"] == "true"
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
