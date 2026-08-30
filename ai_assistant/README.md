# DevOps AI Monitoring Assistant

> **Phase 14 cleanup (2026-08-30):** the flag-off backend adapter layer
> (`services/`), Redis cache/single-flight, and the retry/circuit-breaker
> modules were removed — they had no production callers. The structure
> section below predates that cleanup and may still mention them.


Config-driven monitoring assistant for Claude CLI. Ask natural language questions about system status — Claude queries ELK, Prometheus, and APM automatically using Python scripts.

---

## Migration Notice

**`run_query.py` (v1) was removed on 2026-08-30.** Use `run_query_v2.py`:

### v2 Features
- ✅ Backend service integration with graceful fallback
- ✅ Retry logic with exponential backoff
- ✅ Circuit breaker for failing services
- ✅ Structured logging and metrics
- ✅ Result caching and query deduplication
- ✅ **Audit logging with tamper-evident chain hashing**
- ✅ **Enhanced input validation and security**
- ✅ **Rate limiting and DoS protection**

### Security Enhancements
- Command injection prevention
- URL/SSRF attack protection
- XSS and template injection prevention
- Resource exhaustion protection
- Comprehensive threat model

**See [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md) for details.**

**Quick start:**
```bash
# Old (deprecated)
python tools/run_query_v2.py --project meinvoice --section errors

# New (recommended)
python tools/run_query_v2.py --project meinvoice --section errors
```

---

## Project structure

```
ai_assistant/
├── CLAUDE.md                        # AI spec — Claude reads this first
├── requirements.txt                 # Python dependencies
├── CHANGELOG.md                     # Version history & changes
├── config/
│   ├── global.yaml                  # Default endpoints & settings
│   └── features.yaml               # Feature flags & optimization config
├── core/                            # Core infrastructure modules
│   ├── audit.py                    # Audit logging with tamper-evident chain hashing
│   ├── cache.py                     # Multi-layer caching (SimpleCache, RedisCache)
│   ├── redis_cache.py               # Redis distributed cache
│   ├── single_flight.py             # Query deduplication (local, Redis)
│   ├── redis_single_flight.py       # Redis-based distributed single-flight
│   ├── retry.py                     # Retry logic with circuit breaker
│   ├── security.py                  # Input validation, rate limiting, sanitization
│   ├── sync_bridge.py               # Async/sync bridge for backend adapters
│   ├── logging_config.py            # Structured logging & metrics
│   └── config_loader.py             # Configuration & template loading
├── services/                        # Backend service adapters
│   ├── elasticsearch_adapter.py     # Elasticsearch client with fallback
│   ├── prometheus_adapter.py        # Prometheus client with fallback
│   ├── apm_adapter.py               # APM client for error transactions
│   ├── kubernetes_adapter.py       # Kubernetes client for pod/status
│   └── optimizer_adapter.py        # Query optimizer client
├── docs/                            # Documentation
│   ├── SECURITY.md                  # Threat model & security documentation
│   ├── API.md                       # API documentation for adapters & utilities
│   └── MIGRATION_GUIDE.md           # v1 to v2 migration guide
├── templates/
│   └── system-status.yaml           # Report sections & display order
├── queries/
│   └── common/
│       ├── alerts.yaml              # Machine-readable query definition
│       ├── alerts.md                # Human-readable docs + display format
│       ├── errors.yaml / .md
│       ├── slow_endpoints.yaml / .md
│       ├── disk_usage.yaml / .md
│       ├── pod_status.yaml / .md
│       ├── apm_errors.yaml / .md
│       └── ... (14 query types)
├── tests/                           # Comprehensive test suite
│   ├── test_security.py             # Security tests (37 tests)
│   ├── test_audit.py                # Audit logging tests (15 tests)
│   ├── test_injection.py            # Injection-focused tests (18 tests)
│   ├── test_performance.py          # Performance regression tests (18 tests)
│   └── test_*.py                   # Unit tests for core modules
├── tools/
│   └── run_query_v2.py              # Query runner (CLI entrypoint)
└── projects/
    ├── _template/                   # Copy this for a new project
    │   └── config.yaml
    └── meinvoice/
        ├── config.yaml
        └── queries/
            └── errors.yaml          # Project-specific query override
```

---

## Prerequisites

- **Python 3.9+**
- **Node.js 18+** (required by Claude CLI)
- Network access to ELK / Prometheus endpoints
- **API key** from CSO/SRE Team

---

## Setup

### 1. Install Claude CLI

**Linux / macOS:**
```bash
npm install -g @anthropic-ai/claude-code
```

**Windows (PowerShell as Administrator):**
```powershell
npm install -g @anthropic-ai/claude-code
```

Verify:
```bash
claude --version
```

### 2. Configure the API key

Get your key from the **CSO/SRE Team** (shared via team password manager).

**Linux / macOS** — add to `~/.bashrc` or `~/.zshrc`:
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

**Windows PowerShell** — add to your profile (`$PROFILE`):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
```

Or set via Claude CLI (stored in `~/.claude/config.json`):
```bash
claude config set apiKey sk-ant-api03-...
```

> **Note:** Do not commit the API key to git. It is personal and tied to your CSO/SRE account.

### 3. Install Python dependencies

```bash
cd devops_ai_assistant
pip install -r requirements.txt
```

> On some systems use `pip3` or `python -m pip`.

### 4. Configure monitoring credentials

Credentials are passed as environment variables (never stored in config files).

Credentials are provided by the **SRE Team** alongside the API key.

| Env var | Dùng cho |
|---|---|
| `ELK_AUTH` | ELK / Elasticsearch (tất cả index) |
| `ELK_PROJECT_AUTH` | ELK riêng của project (nếu có) |
| `PROM_AUTH` | Tất cả Prometheus sub-servers (dùng chung 1 credential) |

> Nếu các sub-server Prometheus có credential khác nhau, tạo thêm biến riêng (vd `PROM_K8S_AUTH`) và cập nhật `auth_env` trong `config/global.yaml`.

**Linux / macOS** — thêm vào `~/.bashrc` hoặc `~/.zshrc`:
```bash
export ELK_AUTH=$(echo -n "elastic:your-elk-password" | base64)
export PROM_AUTH=$(echo -n "admin:your-prometheus-password" | base64)

# Optional: per-project ELK
export ELK_PROJECT_AUTH=$(echo -n "project_user:password" | base64)
```

**Windows PowerShell** — thêm vào `$PROFILE`:
```powershell
$env:ELK_AUTH = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes("elastic:your-elk-password"))
$env:PROM_AUTH = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes("admin:your-prometheus-password"))
```

### 5. (Optional) Verify Python tool works

```bash
# Should print JSON with "unreachable" status since this is test endpoints
python tools/run_query_v2.py --project meinvoice --section errors --output pretty
```

---

## Running the assistant

```bash
cd devops_ai_assistant
claude
```

Example questions:
```
Tình trạng hệ thống meinvoice
Tình trạng hệ thống meinvoice 30 phút qua
Show active alerts for meinvoice
Top slow endpoints meinvoice
Disk usage trên các server meinvoice
```

---

## Add a new project

1. Copy the template folder:
   ```bash
   cp -r projects/_template projects/your-project
   ```

2. Edit `projects/your-project/config.yaml`:
   - Set `project`, `namespace`, `node_job`
   - Configure source arrays (`elk_error`, `elk_apm`, etc.)
   - Set `project_filter` to scope ELK queries (e.g. `{"term": {"app.keyword": "your-project"}}`)

3. (Optional) Add project-specific query overrides:
   ```
   projects/your-project/queries/errors.yaml
   ```

4. Ask Claude: `"Tình trạng hệ thống your-project"`

---

## Query override logic

For each section, `run_query.py` resolves the query definition in this order:

```
projects/<project>/queries/<section>.yaml   ← project override (wins if exists)
queries/common/<section>.yaml               ← global fallback
```

## Source merging

In project `config.yaml`, each source type supports:

```yaml
sources:
  elk_error:
    inherit: true   # true = add to global sources, false = replace global
    extra:
      - name: My-Extra-ELK
        url: "http://..."
        index: "my-index-*"
        auth_env: ELK_AUTH
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ANTHROPIC_API_KEY not set` | Export the env var or run `claude config set apiKey ...` |
| `Missing dependency: requests` | Run `pip install -r requirements.txt` |
| All sources `unreachable` | Check VPN / network access to ELK/Prometheus; verify `url` in `config/global.yaml` |
| `http_401` from ELK/Prometheus | Check credential env vars (`ELK_AUTH`, `PROM_AUTH`) are set and correct |
| `template_error` | Query YAML body has a syntax issue — check `queries/common/<section>.yaml` |
| Project not found | Ensure `projects/<name>/config.yaml` exists |

---

## 🔒 Security

The AI Assistant implements comprehensive security measures:

### Input Validation
- **Project/Section names**: Only alphanumeric, hyphens, underscores allowed
- **Time ranges**: Strict format validation (`now` or `now-<duration>`)
- **URLs**: Protocol validation (http://, https:// only), credential detection
- **Templates**: Injection pattern detection (PHP, JSP, shell commands)
- **PromQL**: XSS and dangerous pattern detection

### Rate Limiting
- Token bucket algorithm with configurable rate and burst capacity
- Per-identifier rate limiting (IP, user, source name)
- Automatic retry-after responses

### Audit Logging
- Tamper-evident chain hashing (HMAC-SHA256)
- File rotation with configurable size limits
- Integrity verification to detect tampering
- Query by actor, event type, resource, time range

### Protection Against
- Command injection
- SQL/LDAP injection
- XSS attacks
- Template injection
- Path traversal
- SSRF attacks
- Resource exhaustion

### Documentation
- [Security Documentation](docs/SECURITY.md) - Threat model & security assumptions
- [API Documentation](docs/API.md) - Service adapter & utility APIs

### Running Security Tests
```bash
cd ai_assistant
python -m pytest tests/test_security.py tests/test_audit.py tests/test_injection.py -v
```

---

## 📊 Test Coverage

- **209 tests passing** ✅
- Security tests: 37 tests
- Audit logging tests: 15 tests  
- Injection tests: 18 tests
- Performance tests: 18 tests
- Core functionality tests: 121 tests

Run all tests:
```bash
python -m pytest tests/ -v
```

---

**Last Updated**: 2026-08-24  
**Version**: 2.0 (Production Ready)  
**Status**: ✅ Security Approved (Phase 3 Governance Complete)
