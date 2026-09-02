package devops.time_windows

import future.keywords

# Time-based policy enforcement

deny[msg] if {
    is_production(input.action)
    is_blackout_period(input.timestamp)
    not is_emergency(input.action)
    msg := "Actions are blocked during blackout period"
}

deny[msg] if {
    is_production(input.action)
    is_maintenance_window(input.timestamp) == false
    is_destructive_action(input.action)
    is_risky_action(input.action)
    not has_approval(input.action)
    msg := "High-risk destructive actions outside maintenance window require approval"
}

# Allow routine maintenance during maintenance window
allow if {
    is_production(input.action)
    is_maintenance_window(input.timestamp)
    is_maintenance_action(input.action)
    not is_destructive_action(input.action)
}

# Helper functions

is_blackout_period(timestamp) if {
    # Blackout during critical business periods
    # Example: End of month closing (days 28-31). OPA has no time.day /
    # time.month builtins — time.date(ns) returns [year, month, day] with
    # numeric month (Phase 16 P1-9: the old builtins don't exist, the module
    # could never compile).
    date := time.date(time.parse_rfc3339_ns(timestamp))
    day := date[2]
    month := date[1]
    day >= 28
    day <= 31
    month in [3, 6, 9, 12]  # Quarter ends
}

is_maintenance_window(timestamp) if {
    # Default maintenance window: 10 PM - 6 AM daily. Two rules because
    # "hour >= 22 AND hour <= 6" is unsatisfiable — the window crosses
    # midnight (Phase 16 P1-9).
    clock := time.clock(time.parse_rfc3339_ns(timestamp))
    hour := clock[0]
    hour >= 22
}

is_maintenance_window(timestamp) if {
    clock := time.clock(time.parse_rfc3339_ns(timestamp))
    hour := clock[0]
    hour < 6
}

is_maintenance_window(timestamp) if {
    # Weekend maintenance window. time.weekday() returns day NAMES, so the
    # old "day in [6, 0]" never matched (Phase 16 P1-9).
    day := time.weekday(timestamp)
    day in ["Saturday", "Sunday"]
}

is_production(action) if {
    action.environment == "production"
}

is_destructive_action(action) if {
    action.parsed_params.action in ["delete", "drain", "cordon", "uninstall"]
}

is_risky_action(action) if {
    action.risk_level in ["high", "critical"]
}

is_maintenance_action(action) if {
    action.command_type == "kubectl"
    action.parsed_params.action in ["scale", "rollout", "apply"]
}

is_emergency(action) if {
    action.context.emergency == true
}

has_approval(action) if {
    action.status == "approved"
    action.approved_by
}
