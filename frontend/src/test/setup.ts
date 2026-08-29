/**
 * Vitest setup file for DevOps AI Agentics 2026 frontend tests.
 *
 * This file runs before each test file and sets up the test environment.
 */

import { expect, afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import * as matchers from '@testing-library/jest-dom/matchers'

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers)

// Cleanup after each test
afterEach(() => {
  cleanup()
})

// Mock window.matchMedia for components that use responsive design
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  }),
})

// Mock IntersectionObserver
globalThis.IntersectionObserver = class {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return []
  }
} as unknown as typeof IntersectionObserver

// Mock ResizeObserver
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
  unobserve() {}
} as unknown as typeof ResizeObserver
