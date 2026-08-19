---
name: test-frontend
description: Run frontend tests for React application
---

# Test Frontend

Run the frontend test suite for the React + TypeScript application.

## Usage

Run `/test-frontend` to execute all frontend tests.

## Test Framework

Uses **Vitest** for unit testing and **Playwright** for E2E testing.

## Running Tests

```bash
cd frontend

# Run all tests
npm test

# Run in watch mode
npm test -- --watch

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test src/hooks/usePolling.test.ts

# Run specific test
npm test -- src/hooks/usePolling.test.ts -t "polling stops when component unmounts"
```

## Test Structure

```
frontend/src/
├── test/              # Test utilities
│   └── setup.ts       # Test setup
├── api/*.test.ts      # API client tests
├── hooks/*.test.ts    # Custom hook tests
└── utils/*.test.ts    # Utility function tests
```

## Key Test Files

- `src/api/client.test.ts` - API client tests
- `src/hooks/usePolling.test.ts` - Polling hook tests
- `src/hooks/useWebSocket.test.ts` - WebSocket hook tests
- `src/hooks/useAlertNotifications.test.ts` - Alert notification tests
- `src/utils/health.test.ts` - Health status utility tests
- `src/utils/formatters.test.ts` - Formatter utility tests

## Running Specific Tests

```bash
# Test hooks only
npm test -- src/hooks/

# Test utilities only
npm test -- src/utils/

# Test specific file
npm test -- src/hooks/useWebSocket.test.ts
```

## Coverage Report

```bash
npm test -- --coverage
# Report generated in coverage/
```

## E2E Tests (if Playwright is configured)

```bash
# Run E2E tests
npx playwright test

# Run with UI
npx playwright test --ui
```
