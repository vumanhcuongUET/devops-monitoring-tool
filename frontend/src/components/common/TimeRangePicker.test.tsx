/**
 * Unit tests for TimeRangePicker component.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TimeRangePicker } from './TimeRangePicker'

describe('TimeRangePicker', () => {
  it('renders all time range presets', () => {
    const mockOnChange = vi.fn()
    render(<TimeRangePicker value={{ start: 'now-1h', end: 'now', label: '1h' }} onChange={mockOnChange} />)

    expect(screen.getByText('5m')).toBeInTheDocument()
    expect(screen.getByText('15m')).toBeInTheDocument()
    expect(screen.getByText('1h')).toBeInTheDocument()
    expect(screen.getByText('6h')).toBeInTheDocument()
    expect(screen.getByText('24h')).toBeInTheDocument()
  })

  it('highlights selected time range', () => {
    const mockOnChange = vi.fn()
    render(<TimeRangePicker value={{ start: 'now-1h', end: 'now', label: '1h' }} onChange={mockOnChange} />)

    const selectedButton = screen.getByText('1h')
    expect(selectedButton).toHaveClass('bg-[var(--color-accent)]')
  })

  it('calls onChange when preset is clicked', async () => {
    const user = userEvent.setup()
    const mockOnChange = vi.fn()
    render(<TimeRangePicker value={{ start: 'now-1h', end: 'now', label: '1h' }} onChange={mockOnChange} />)

    await user.click(screen.getByText('15m'))

    expect(mockOnChange).toHaveBeenCalledTimes(1)
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({ label: '15m', start: 'now-15m', end: 'now' })
    )
  })

  it('switches between different time ranges', async () => {
    const user = userEvent.setup()
    const mockOnChange = vi.fn()
    render(<TimeRangePicker value={{ start: 'now-5m', end: 'now', label: '5m' }} onChange={mockOnChange} />)

    await user.click(screen.getByText('6h'))
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({ label: '6h' })
    )

    await user.click(screen.getByText('24h'))
    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({ label: '24h' })
    )
  })

  it('handles rapid clicks on different presets', async () => {
    const user = userEvent.setup()
    const mockOnChange = vi.fn()
    render(<TimeRangePicker value={{ start: 'now-5m', end: 'now', label: '5m' }} onChange={mockOnChange} />)

    await user.click(screen.getByText('15m'))
    await user.click(screen.getByText('1h'))
    await user.click(screen.getByText('6h'))

    expect(mockOnChange).toHaveBeenCalledTimes(3)
  })
})
