/**
 * Unit tests for health status utilities.
 */

import { describe, it, expect } from 'vitest'
import { getHealthColor, getHealthLabel } from './health'

describe('getHealthColor', () => {
  it('returns green for healthy status', () => {
    expect(getHealthColor('healthy')).toBe('green')
    expect(getHealthColor('Healthy')).toBe('green')
    expect(getHealthColor('HEALTHY')).toBe('green')
  })

  it('returns yellow for degraded status', () => {
    expect(getHealthColor('degraded')).toBe('yellow')
    expect(getHealthColor('Degraded')).toBe('yellow')
  })

  it('returns red for down status', () => {
    expect(getHealthColor('down')).toBe('red')
    expect(getHealthColor('Down')).toBe('red')
  })

  it('handles undefined input', () => {
    expect(getHealthColor(undefined)).toBe('gray')
  })

  it('handles unknown status', () => {
    expect(getHealthColor('unknown')).toBe('gray')
  })
})

describe('getHealthLabel', () => {
  it('returns formatted label for healthy', () => {
    expect(getHealthLabel('healthy')).toBe('Healthy')
    expect(getHealthLabel('Healthy')).toBe('Healthy')
  })

  it('returns formatted label for degraded', () => {
    expect(getHealthLabel('degraded')).toBe('Degraded')
  })

  it('returns formatted label for down', () => {
    expect(getHealthLabel('down')).toBe('Down')
  })

  it('handles undefined input', () => {
    expect(getHealthLabel(undefined)).toBe('Unknown')
  })

  it('capitalizes first letter', () => {
    expect(getHealthLabel('healthy')).toBe('Healthy')
    expect(getHealthLabel('degraded')).toBe('Degraded')
  })
})
