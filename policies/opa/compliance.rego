package devops.compliance

import future.keywords

# Phase 16 P1-9: opa_client.check_compliance queries
# /v1/data/devops/compliance/status — no rule defined it, so the call always
# returned {} and compliance reporting read as "unknown". This reports the
# time-window posture (blackout / maintenance window) for the environment
# being checked. Cross-package refs use the fully qualified data paths.

status := {
    "environment": input.environment,
    "project": input.project,
    "blackout_period": blackout,
    "maintenance_window": maintenance,
    "restricted": restricted,
    "checked_at": input.timestamp,
}

default blackout := false

blackout if {
    data.devops.time_windows.is_blackout_period(input.timestamp)
}

default maintenance := false

maintenance if {
    data.devops.time_windows.is_maintenance_window(input.timestamp)
}

# A blackout period restricts everything non-emergency, regardless of window.
restricted if blackout

default restricted := false
