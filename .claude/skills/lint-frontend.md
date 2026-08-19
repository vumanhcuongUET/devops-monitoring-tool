---
name: lint-frontend
description: Lint and type-check frontend TypeScript code
---

# Lint Frontend

Lint and type-check the frontend TypeScript + React code.

## Usage

Run `/lint-frontend` to lint and type-check frontend code.

## Tools

- **ESLint** - JavaScript/TypeScript linter
- **TypeScript** - Type checking via `tsc`

## Running

```bash
cd frontend

# Lint (check only)
npm run lint

# Type check (included in lint)
npm run lint  # Runs: tsc -b && eslint .
```

## Manual Commands

```bash
# TypeScript check only
tsc -b

# ESLint check only
eslint .

# ESLint auto-fix
eslint . --fix

# Type check specific file
tsc --noEmit src/pages/OverviewPage.tsx
```

## Configuration

- ESLint: `frontend/.eslintrc.cjs`
- TypeScript: `frontend/tsconfig.json`
- TypeScript app: `frontend/tsconfig.app.json`

## Common Issues

- **Type errors:** Check type definitions in `src/types/index.ts`
- **Missing imports:** ESLint will flag unused imports
- **React hooks:** ESLint rules enforce hooks rules
- **Import order:** Use `eslint --fix` to auto-sort

## Type Definitions

Common types in `src/types/index.ts`:
- `HealthStatus` - Service health status
- `Alert` - Alert data structure
- `SLO` - SLO data structure
- `TriageCard` - AI analysis result

## Pre-commit Hook (if configured)

```bash
# Install pre-commit hooks
npm install -g husky
npx husky install
```
