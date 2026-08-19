---
name: lint-backend
description: Lint and format backend Python code with ruff and black
---

# Lint Backend

Lint and format the backend Python code.

## Usage

Run `/lint-backend` to lint and format backend code.

## Tools

- **ruff** - Fast Python linter (replaces flake8, pylint, isort)
- **black** - Python code formatter

## Running

```bash
cd backend

# Lint (check only)
ruff check app/

# Format code
black app/

# Lint and auto-fix
ruff check app/ --fix

# Format and lint together
black app/ && ruff check app/ --fix
```

## Configuration

Configuration in `backend/pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.black]
line-length = 100
target-version = ['py311']
```

## Common Issues

- **Import sorting:** Use `ruff check --fix` to auto-sort imports
- **Line too long:** Black will format long lines
- **Unused imports:** Ruff will flag these, remove manually
- **Missing docstrings:** Add docstrings for public functions/classes

## Pre-commit Hook (if configured)

The pre-commit hook runs both formatters automatically:

```bash
# Install pre-commit hooks (if configured)
pip install pre-commit
pre-commit install
```
