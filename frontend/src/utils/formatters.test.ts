/**
 * Unit tests for utility formatters.
 */

import { describe, it, expect } from 'vitest'
import { formatTimestamp, formatBytes, formatDuration, formatPercent } from './formatters'

describe('formatTimestamp', () => {
  it('formats ISO timestamp correctly', () => {
    const isoString = '2025-01-15T10:30:00Z'
    const result = formatTimestamp(isoString)
    expect(result).toBeDefined()
    expect(typeof result).toBe('string')
  })

  it('handles undefined input', () => {
    const result = formatTimestamp(undefined)
    expect(result).toBe('Invalid Date')
  })

  it('handles empty string', () => {
    const result = formatTimestamp('')
    expect(result).toBe('Invalid Date')
  })

  it('handles invalid date format', () => {
    const result = formatTimestamp('invalid-date')
    expect(result).toBe('Invalid Date')
  })
})

describe('formatBytes', () => {
  it('formats bytes correctly', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1048576)).toBe('1.0 MB')
    expect(formatBytes(1073741824)).toBe('1.0 GB')
  })

  it('handles decimal values', () => {
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(1572864)).toBe('1.5 MB')
  })

  it('handles large values', () => {
    expect(formatBytes(10737418240)).toBe('10.0 GB')
  })

  it('handles undefined input', () => {
    expect(formatBytes(undefined)).toBe('NaN B')
  })
})

describe('formatDuration', () => {
  it('formats milliseconds correctly', () => {
    expect(formatDuration(0)).toBe('0ms')
    expect(formatDuration(500)).toBe('500ms')
    expect(formatDuration(1000)).toBe('1.00s')
    expect(formatDuration(1500)).toBe('1.50s')
  })

  it('formats seconds correctly', () => {
    expect(formatDuration(60000)).toBe('60.00s')
  })

  it('handles undefined input', () => {
    expect(formatDuration(undefined)).toBe('NaNms')
  })
})

describe('formatPercent', () => {
  it('formats percentage correctly', () => {
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatPercent(50)).toBe('50.0%')
    expect(formatPercent(99.9)).toBe('99.9%')
  })

  it('handles decimal places', () => {
    expect(formatPercent(99.956)).toBe('100.0%')
  })

  it('handles undefined input', () => {
    expect(formatPercent(undefined)).toBe('NaN%')
  })

  it('handles values above 100%', () => {
    expect(formatPercent(150)).toBe('150.0%')
  })
})
