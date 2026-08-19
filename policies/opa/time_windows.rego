package devops.time_windows

import future.keywords.if
import future.keywords.contains

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
    # Example: End of month closing (days 28-31)
    day := time.day(timestamp)
    day >= 28
    day <= 31
    month := time.month(timestamp)
    month in [3, 6, 9, 12]  # Quarter ends
}

is_maintenance_window(timestamp) if {
    # Default maintenance window: 10 PM - 6 AM daily
    hour := time.hour(timestamp)
    hour >= 22
    hour <= 6
}

is_maintenance_window(timestamp) if {
    # Weekend maintenance window
    day := time.weekday(timestamp)
    day in [6, 0]  # Saturday, Sunday
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
