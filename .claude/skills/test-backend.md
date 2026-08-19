---
name: test-backend
description: Run backend tests for FastAPI application
---

# Test Backend

Run the backend test suite for the FastAPI application.

## Usage

Run `/test-backend` to execute all backend tests.

## Test Framework

Uses **pytest** for backend testing.

## Running Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/integration/test_api_overview.py

# Run with verbose output
pytest -v

# Run specific test
pytest tests/integration/test_api_overview.py::test_overview_success
```

## Test Structure

```
backend/tests/
├── unit/              # Unit tests for individual components
│   └── test_services/
├── integration/       # API endpoint tests
│   ├── test_api_overview.py
│   ├── test_api_analyze.py
│   └── test_api_alerts.py
└── conftest.py       # Shared fixtures
```

## Key Test Files

- `tests/unit/test_services/` - Service client unit tests
- `tests/integration/test_api_overview.py` - Overview endpoint tests
- `tests/integration/test_api_analyze.py` - Triage Card analysis tests
- `tests/integration/test_api_alerts.py` - Alert system tests

## Fixtures

Located in `tests/conftest.py`:
- `test_client` - FastAPI test client
- `mock_elasticsearch_client` - Mocked ES client
- `mock_prometheus_client` - Mocked Prometheus client
- `mock_kubernetes_client` - Mocked K8s client

## Running Specific Tests

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Test specific service
pytest tests/unit/test_services/test_elasticsearch_client.py
```

## Coverage Report

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html  # View coverage report
```
