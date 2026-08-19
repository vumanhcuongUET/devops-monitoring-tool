package devops.resources

import future.keywords.contains
import future.keywords.if
import future.keywords.every

# Resource protection policies

deny[msg] if {
    is_production(input.action)
    is_statefulset_action(input.action)
    is_destructive(input.action)
    not has_approval(input.action)
    msg := "StatefulSet destructive actions require explicit approval in production"
}

deny[msg] if {
    is_production(input.action)
    is_pvc_action(input.action)
    input.action.parsed_params.action == "delete"
    msg := "PVC deletion is forbidden in production"
}

deny[msg] if {
    is_production(input.action)
    is_configmap_action(input.action)
    input.action.resource_name == "core-config"
    is_destructive(input.action)
    msg := "Core configmap modification requires additional approval"
}

deny[msg] if {
    is_production(input.action)
    is_secret_action(input.action)
    not has_approval(input.action)
    msg := "Secret actions in production require approval"
}

deny[msg] if {
    is_production(input.action)
    is_ingress_action(input.action)
    input.action.resource_name == "main-ingress"
    is_destructive(input.action)
    msg := "Main ingress modification is restricted in production"
}

# Helper functions

is_production(action) if {
    action.environment == "production"
}

is_statefulset_action(action) if {
    action.resource_type == "statefulset"
}

is_statefulset_action(action) if {
    action.resource_type == "statefulsets"
}

is_pvc_action(action) if {
    action.resource_type == "persistentvolumeclaim"
}

is_pvc_action(action) if {
    action.resource_type == "pvc"
}

is_configmap_action(action) if {
    action.resource_type == "configmap"
}

is_secret_action(action) if {
    action.resource_type == "secret"
}

is_ingress_action(action) if {
    action.resource_type == "ingress"
}

is_destructive(action) if {
    action.parsed_params.action in ["delete", "remove", "uninstall"]
}

has_approval(action) if {
    action.status == "approved"
    action.approved_by
    not action.auto_approved
}
