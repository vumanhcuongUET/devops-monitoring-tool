"""
Configuration Validation Module

Provides schema-based validation for all configuration types.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """Result of configuration validation."""
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    config_type: str


class ConfigType(Enum):
    """Supported configuration types."""
    PROJECT = "project"
    ALERT = "alert"
    SLO_CONFIG = "slo_config"
    DEPLOYMENT_CONFIG = "deployment_config"
    MONITORING_CONFIG = "monitoring_config"
    PRIORITY_CONFIG = "priority_config"


class ConfigValidator:
    """Validate project configurations against schemas."""

    # Built-in validation schemas
    SCHEMAS = {
        ConfigType.PROJECT: {
            "type": "object",
            "required": ["project"],
            "properties": {
                "project": {
                    "type": "object",
                    "required": ["name", "environment"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "environment": {"type": "string", "enum": ["development", "staging", "production"]},
                        "description": {"type": "string"},
                        "owner": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "monitoring": {
                    "type": "object",
                    "properties": {
                        "elasticsearch": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "username": {"type": "string"},
                                "password": {"type": "string"},
                                "indices": {"type": "array", "items": {"type": "string"}}
                            }
                        },
                        "prometheus": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "username": {"type": "string"},
                                "password": {"type": "string"},
                                "queries": {"type": "object"}
                            }
                        },
                        "kubernetes": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "namespaces": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    }
                },
                "alerting": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "channels": {
                            "type": "object",
                            "properties": {
                                "slack": {"type": "object"},
                                "email": {"type": "object"},
                                "pagerduty": {"type": "object"}
                            }
                        }
                    }
                },
                "cache": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "ttl_seconds": {"type": "integer", "minimum": 0}
                    }
                }
            }
        },
        ConfigType.ALERT: {
            "type": "object",
            "required": ["name", "condition"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "enabled": {"type": "boolean"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                "condition": {
                    "type": "object",
                    "required": ["metric", "threshold"],
                    "properties": {
                        "metric": {"type": "string"},
                        "threshold": {"type": "number"},
                        "operator": {"type": "string", "enum": [">", "<", ">=", "<=", "==", "!="]},
                        "duration": {"type": "string"}
                    }
                },
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["slack", "email", "pagerduty", "webhook"]},
                            "target": {"type": "string"}
                        }
                    }
                }
            }
        },
        ConfigType.SLO_CONFIG: {
            "type": "object",
            "required": ["slo_name", "service", "objectives"],
            "properties": {
                "slo_name": {"type": "string"},
                "service": {"type": "string"},
                "description": {"type": "string"},
                "objectives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "target"],
                        "properties": {
                            "name": {"type": "string"},
                            "target": {"type": "number", "minimum": 0, "maximum": 100},
                            "window": {
                                "type": "object",
                                "properties": {
                                    "duration": {"type": "string"},
                                    "rolling": {"type": "boolean"}
                                }
                            }
                        }
                    }
                }
            }
        },
        ConfigType.DEPLOYMENT_CONFIG: {
            "type": "object",
            "properties": {
                "deployment": {
                    "type": "object",
                    "properties": {
                        "strategy": {"type": "string", "enum": ["rolling", "blue_green", "canary"]},
                        "replicas": {
                            "type": "object",
                            "properties": {
                                "min": {"type": "integer", "minimum": 0},
                                "max": {"type": "integer", "minimum": 0},
                                "default": {"type": "integer", "minimum": 0}
                            }
                        },
                        "resources": {
                            "type": "object",
                            "properties": {
                                "requests": {"type": "object"},
                                "limits": {"type": "object"}
                            }
                        }
                    }
                },
                "health_checks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "path": {"type": "string"},
                            "interval": {"type": "string"},
                            "threshold": {"type": "integer", "minimum": 1}
                        }
                    }
                }
            }
        },
        ConfigType.MONITORING_CONFIG: {
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "port": {"type": "integer", "minimum": 1024, "maximum": 65535},
                        "path": {"type": "string"}
                    }
                },
                "tracing": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "sample_rate": {"type": "number", "minimum": 0, "maximum": 1}
                    }
                },
                "logging": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                        "format": {"type": "string", "enum": ["json", "text"]}
                    }
                }
            }
        },
        ConfigType.PRIORITY_CONFIG: {
            "type": "object",
            "properties": {
                "priorities": {
                    "type": "object",
                    "patternProperties": {
                        ".*": {
                            "type": "object",
                            "properties": {
                                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                                "timeout_ms": {"type": "integer", "minimum": 0},
                                "retry_count": {"type": "integer", "minimum": 0},
                                "fallback_to_cache": {"type": "boolean"}
                            }
                        }
                    }
                }
            }
        }
    }

    def __init__(self, schema_path: str | None = None):
        """Initialize validator with optional external schema path."""
        self.schema_path = schema_path
        self.external_schemas: dict[str, dict] = {}

        if schema_path:
            self._load_external_schemas()

    def _load_external_schemas(self):
        """Load schemas from external directory."""
        schema_dir = Path(self.schema_path)
        if not schema_dir.exists():
            logger.warning(f"Schema path does not exist: {self.schema_path}")
            return

        for schema_file in schema_dir.glob("*.schema.yaml"):
            try:
                with open(schema_file) as f:
                    schema_name = schema_file.stem.replace(".schema", "")
                    self.external_schemas[schema_name] = yaml.safe_load(f)
                    logger.info(f"Loaded schema: {schema_name}")
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")

    def validate_config(
        self,
        config: dict[str, Any],
        config_type: ConfigType
    ) -> ValidationResult:
        """Validate configuration against schema."""
        errors = []
        warnings = []

        # Get schema
        schema = self.SCHEMAS.get(config_type, {})
        if config_type.value in self.external_schemas:
            schema = self.external_schemas[config_type.value]

        if not schema:
            return ValidationResult(
                is_valid=False,
                errors=[f"No schema found for {config_type.value}"],
                config_type=config_type.value
            )

        # Basic validation
        errors.extend(self._validate_schema(config, schema))

        # Custom business logic validations
        errors.extend(self._custom_validations(config_type, config, warnings))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            config_type=config_type.value
        )

    def _validate_schema(
        self,
        config: dict[str, Any],
        schema: dict[str, Any]
    ) -> list[str]:
        """Validate config against JSON schema."""
        errors = []

        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in config:
                errors.append(f"Required field missing: {field}")

        # Validate properties
        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key not in config:
                continue

            value = config[key]
            prop_type = prop_schema.get("type")

            # Type validation
            if prop_type == "object" and isinstance(value, dict):
                nested_errors = self._validate_schema(value, prop_schema)
                errors.extend([f"{key}.{e}" for e in nested_errors])

            elif prop_type == "array" and isinstance(value, list):
                if "items" in prop_schema:
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            nested_errors = self._validate_schema(item, prop_schema["items"])
                            errors.extend([f"{key}[{i}].{e}" for e in nested_errors])

            elif prop_type == "string":
                if not isinstance(value, str):
                    errors.append(f"{key} must be a string")
                else:
                    # Check enum
                    if "enum" in prop_schema and value not in prop_schema["enum"]:
                        errors.append(f"{key} must be one of: {prop_schema['enum']}")
                    # Check minLength
                    if "minLength" in prop_schema and len(value) < prop_schema["minLength"]:
                        errors.append(f"{key} must be at least {prop_schema['minLength']} characters")

            elif prop_type == "number":
                if not isinstance(value, (int, float)):
                    errors.append(f"{key} must be a number")
                else:
                    if "minimum" in prop_schema and value < prop_schema["minimum"]:
                        errors.append(f"{key} must be >= {prop_schema['minimum']}")
                    if "maximum" in prop_schema and value > prop_schema["maximum"]:
                        errors.append(f"{key} must be <= {prop_schema['maximum']}")

            elif prop_type == "integer":
                if not isinstance(value, int):
                    errors.append(f"{key} must be an integer")
                else:
                    if "minimum" in prop_schema and value < prop_schema["minimum"]:
                        errors.append(f"{key} must be >= {prop_schema['minimum']}")
                    if "maximum" in prop_schema and value > prop_schema["maximum"]:
                        errors.append(f"{key} must be <= {prop_schema['maximum']}")

            elif prop_type == "boolean":
                if not isinstance(value, bool):
                    errors.append(f"{key} must be a boolean")

        return errors

    def _custom_validations(
        self,
        config_type: ConfigType,
        config: dict[str, Any],
        warnings: list[str]
    ) -> list[str]:
        """Custom business logic validations."""
        errors = []

        if config_type == ConfigType.PROJECT:
            project = config.get("project", {})

            # Validate project name
            if not project.get("name"):
                errors.append("Project name is required")
            elif not project["name"].replace("-", "").replace("_", "").isalnum():
                errors.append("Project name must contain only alphanumeric characters, hyphens, and underscores")

            # Validate monitoring configuration
            monitoring = config.get("monitoring", {})
            if not monitoring.get("elasticsearch") and not monitoring.get("prometheus"):
                errors.append("At least one monitoring source must be configured")

            # Check for deprecated fields
            if config.get("legacy_mode"):
                warnings.append("legacy_mode is deprecated and will be removed in future version")

        elif config_type == ConfigType.SLO_CONFIG:
            objectives = config.get("objectives", [])
            for obj in objectives:
                target = obj.get("target", 0)
                if target <= 0 or target > 100:
                    errors.append(f"SLO target must be between 0 and 100: {obj.get('name')}")

        elif config_type == ConfigType.PRIORITY_CONFIG:
            priorities = config.get("priorities", {})
            for source_name, priority_config in priorities.items():
                timeout_ms = priority_config.get("timeout_ms", 0)
                if timeout_ms > 10000:
                    warnings.append(f"Priority timeout > 10s for {source_name} may cause slow responses")

        return errors

    def validate_yaml_file(
        self,
        file_path: str,
        config_type: ConfigType
    ) -> ValidationResult:
        """Validate configuration from YAML file."""
        try:
            with open(file_path) as f:
                config = yaml.safe_load(f)
            return self.validate_config(config, config_type)
        except FileNotFoundError:
            return ValidationResult(
                is_valid=False,
                errors=[f"Configuration file not found: {file_path}"],
                config_type=config_type.value
            )
        except yaml.YAMLError as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Invalid YAML: {e}"],
                config_type=config_type.value
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Error reading configuration: {e}"],
                config_type=config_type.value
            )
