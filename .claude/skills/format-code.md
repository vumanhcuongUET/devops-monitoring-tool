---
name: format-code
description: Format and auto-fix code style issues in both backend and frontend
---

# Format Code

Format and auto-fix code style issues across the entire project.

## Usage

Run `/format-code` to format both backend and frontend code.

## Formatting

### Backend (Python)
```bash
cd backend

# Format with Black
black app/

# Auto-fix linting with Ruff
ruff check app/ --fix

# Sort imports (if needed)
ruff check app/ --select I --fix
```

### Frontend (TypeScript/React)
```bash
cd frontend

# Auto-fix ESLint issues
eslint . --fix

# Format with Prettier (if configured)
prettier --write "src/**/*.{ts,tsx}"
```

## Pre-commit Format (Recommended)

Configure pre-commit hooks to auto-format on commit:

```bash
# Backend pre-commit (if configured)
cd backend
pre-commit run --all-files

# Frontend husky (if configured)
cd frontend
npx lint-staged
```

## CI/CD Integration

Formatting is checked in CI:
- Backend: Runs `black --check` and `ruff check`
- Frontend: Runs `eslint` and `tsc -b`

## Configuration Files

- Backend: `backend/pyproject.toml` (Black, Ruff config)
- Frontend: `frontend/.eslintrc.cjs` (ESLint config)
