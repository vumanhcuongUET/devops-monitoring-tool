/**
 * Unit tests for StatusBadge component.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders healthy status', () => {
    render(<StatusBadge status="healthy" />)
    const badge = screen.getByText('Healthy')
    expect(badge).toBeInTheDocument()
  })

  it('renders degraded status', () => {
    render(<StatusBadge status="degraded" />)
    const badge = screen.getByText('Degraded')
    expect(badge).toBeInTheDocument()
  })

  it('renders down status', () => {
    render(<StatusBadge status="down" />)
    const badge = screen.getByText('Down')
    expect(badge).toBeInTheDocument()
  })

  it('renders unknown status', () => {
    render(<StatusBadge status="unknown" />)
    const badge = screen.getByText('Unknown')
    expect(badge).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<StatusBadge status="healthy" className="custom-class" />)
    expect(container.querySelector('.custom-class')).toBeInTheDocument()
  })

  it('renders colored indicator', () => {
    const { container } = render(<StatusBadge status="healthy" />)
    const indicator = container.querySelector('.rounded-full')
    expect(indicator).toBeInTheDocument()
    expect(indicator).toHaveStyle({ backgroundColor: 'var(--color-healthy)' })
  })
})
