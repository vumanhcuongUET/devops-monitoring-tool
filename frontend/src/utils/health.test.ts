/**
 * Unit tests for health status utilities.
 * getHealthColor/getHealthLabel map HealthStatus to design tokens / labels.
 */

import { describe, it, expect } from 'vitest'
import { getHealthColor, getHealthLabel } from './health'

describe('getHealthColor', () => {
  it('returns healthy token for healthy status', () => {
    expect(getHealthColor('healthy')).toBe('var(--color-healthy)')
  })

  it('returns degraded token for degraded status', () => {
    expect(getHealthColor('degraded')).toBe('var(--color-degraded)')
  })

  it('returns down token for down status', () => {
    expect(getHealthColor('down')).toBe('var(--color-down)')
  })

  it('returns unknown token for unknown status', () => {
    expect(getHealthColor('unknown')).toBe('var(--color-unknown)')
  })
})

describe('getHealthLabel', () => {
  it('returns label for healthy', () => {
    expect(getHealthLabel('healthy')).toBe('Healthy')
  })

  it('returns label for degraded', () => {
    expect(getHealthLabel('degraded')).toBe('Degraded')
  })

  it('returns label for down', () => {
    expect(getHealthLabel('down')).toBe('Down')
  })

  it('returns Unknown for unknown status', () => {
    expect(getHealthLabel('unknown')).toBe('Unknown')
  })
})
