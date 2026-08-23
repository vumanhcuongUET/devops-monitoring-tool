# ADR 001: Backend Integration via sys.path Manipulation

## Status

Accepted

## Context

AI Assistant (`ai_assistant/`) needs to reuse async backend service clients from the Backend (`backend/`) module. These clients provide:
- Connection pooling
- Proper error handling
- Authentication management
- Async/await patterns

The challenge: Both are separate top-level directories in the monorepo without a formal package relationship.

## Decision

Use `sys.path` manipulation to enable cross-directory imports from `backend/` in `ai_assistant/services/` adapters.

### Implementation Pattern

```python
# ai_assistant/services/elasticsearch_adapter.py
import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from app.services.elasticsearch_client import ElasticsearchClient
    from app.config import settings
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False
```

### Applied To

All service adapters in `ai_assistant/services/`:
- `elasticsearch_adapter.py`
- `prometheus_adapter.py`
- `apm_adapter.py`
- `k8s_adapter.py`
- `optimizer_adapter.py`

## Rationale

### Why This Approach?

1. **No Code Duplication**: Reuses production-tested backend clients
2. **Consistency**: Same authentication, pooling, error handling
3. **Fast Development**: No need to extract to shared package yet
4. **Monorepo Friendly**: Works within single repository structure

### Why Not Alternatives?

| Alternative | Rejected Because |
|-------------|------------------|
| **Shared package** | Too much refactoring for current stage |
| **Direct HTTP in ai_assistant** | Loses connection pooling, error handling |
| **Copy code** | Maintenance burden, inconsistency risk |
| **Import backend as installed package** | Backend not installed as editable package |

## Consequences

### Positive

- ✅ Zero code duplication for client logic
- ✅ Consistent behavior across both components
- ✅ Fast implementation path
- ✅ Graceful degradation when backend unavailable

### Negative

- ⚠️ **Fragile**: Breaks if `backend/` moves or structure changes
- ⚠️ **Implicit dependency**: Not visible from package requirements
- ⚠️ **Testing complexity**: Requires backend available for full tests
- ⚠️ **Not standard**: Violates normal Python package conventions

### Risks

1. **Directory structure changes**: Moving `backend/` breaks imports
2. **CI/CD assumptions**: Scripts must run from repository root
3. **IDE confusion**: Some IDEs don't resolve dynamic sys.path
4. **Deployment**: Both directories must coexist in production

### Mitigations

- Added `BACKEND_AVAILABLE` flag for graceful degradation
- Feature flag `backend_integration.enabled` controls usage
- Fallback to direct HTTP when backend unavailable
- Documented in this ADR for future reference

## Future Alternatives

When to replace this pattern:

1. **If backend becomes external package**: Install properly via pip
2. **If directory structure changes**: Update sys.path logic
3. **If multiple consumers**: Extract to shared package (e.g., `monitoring_clients`)
4. **If distributed deployment**: Backend as separate service with API

## References

- Implementation: `ai_assistant/services/` adapters
- Backend clients: `backend/app/services/`
- Feature flags: `ai_assistant/config/features.yaml`
