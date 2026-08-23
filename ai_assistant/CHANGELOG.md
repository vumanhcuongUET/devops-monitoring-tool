# Changelog

All notable changes to the AI Assistant module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **Redis distributed cache** - Alternative to in-memory cache for multi-process scenarios
- **Redis distributed single-flight** - Cross-process query deduplication via Redis
- **Retry logic with exponential backoff** - Resilient service calls with configurable retry
- **Circuit breaker pattern** - Automatic service protection after repeated failures
- **Structured logging** - JSON logs with credential sanitization
- **Metrics collection** - Comprehensive instrumentation for observability
- **Feature flags system** - Runtime configuration via `config/features.yaml`
- **Migration guide** - Documentation for v1 to v2 migration

### Changed
- **Backend import pattern documented** - Added ADR 001 explaining sys.path manipulation
- **Service adapters updated** - Added retry decorators to ElasticsearchAdapter
- **Enhanced test coverage** - Added tests for Redis cache, single-flight, and retry modules

### Deprecated
- **`run_query.py` (v1)** - Deprecated in favor of `run_query_v2.py`
  - Will be removed in v1.1.0 (estimated November 2026)
  - See [MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)

## [1.0.0] - 2026-08-15

### Added
- Initial release of AI Assistant module
- Cross-platform query runner (`run_query.py`)
- 14 query types (alerts, errors, APM, K8s, infrastructure)
- Project-specific configuration and query overrides
- Template-based query definitions
- YAML configuration management
- Integration with Claude CLI

### Features
- ELK/Elasticsearch queries with configurable sources
- Prometheus queries with PromQL support
- APM error and transaction analysis
- Kubernetes pod and deployment status
- Infrastructure metrics (disk, CPU, memory, network)
- Parallel query execution
- Graceful handling of unavailable sources
