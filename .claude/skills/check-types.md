---
name: check-types
description: Type check backend Python and frontend TypeScript code
---

# Check Types

Run type checking on both backend and frontend code.

## Usage

Run `/check-types` to type-check both codebases.

## Backend (Python)

Uses **mypy** for static type checking.

```bash
cd backend

# Run type check
mypy app/

# Check specific module
mypy app/services/elasticsearch_client.py

# Strict mode (more checks)
mypy app/ --strict
```

### Configuration
`backend/pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
```

## Frontend (TypeScript)

Uses **tsc** (TypeScript compiler).

```bash
cd frontend

# Type check (included in npm run lint)
npm run lint

# Type check only
tsc -b

# Check specific file
tsc --noEmit src/pages/OverviewPage.tsx
```

### Configuration
- `frontend/tsconfig.json` - Base TypeScript config
- `frontend/tsconfig.app.json` - App-specific config

## Type Definitions

### Backend Types
Located in `backend/app/models/`:
- `common.py` - Common base models
- `alerts.py` - Alert data models
- `triage_card.py` - Triage Card models
- `actions.py` - Action models
- `registry.py` - Registry config models

### Frontend Types
Located in `frontend/src/types/index.ts`:
- `HealthStatus` - Service health status
- `Alert` - Alert data structure
- `SLO` - SLO data structure
- `TriageCard` - AI analysis result
- `Action` - Action data structure

## Common Issues

### Backend
- **Missing imports:** Add `from typing import ...`
- **Optional types:** Use `Optional[T]` for nullable values
- **Any types:** Replace `Any` with specific types when possible

### Frontend
- **Missing types:** Define interfaces in `types/index.ts`
- **Assertion types:** Use type assertions sparingly
- **Unknown types:** Use `unknown` instead of `any` for untyped data

## CI/CD

Type checking runs in CI pipeline:
- Backend: `mypy app/`
- Frontend: `tsc -b` (via `npm run lint`)
