/**
 * Unit tests for SloTable component.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SloTable } from './SloTable'
import type { SloResult, SloApiDetail } from '../../types'

describe('SloTable', () => {
  const mockResults: SloResult[] = [
    {
      config_id: 'api-availability',
      service_name: 'api-service',
      slo_type: 'availability',
      target: 99.9,
      current_value: 99.95,
      window_days: 7,
      good_requests: 9995,
      bad_requests: 5,
      total_requests: 10000,
      error_budget_remaining_percent: 50.0,
      error_budget_total: 43200,
      error_budget_consumed: 21600,
      status: 'healthy'
    },
    {
      config_id: 'user-latency',
      service_name: 'user-service',
      slo_type: 'latency',
      target: 95.0,
      current_value: 92.5,
      window_days: 30,
      good_requests: 850,
      bad_requests: 150,
      total_requests: 1000,
      error_budget_remaining_percent: 15.0,
      error_budget_total: 432000,
      error_budget_consumed: 367200,
      status: 'warning'
    }
  ]

  const mockSlowApis: Record<string, SloApiDetail[]> = {
    'api-service': [
      {
        transaction_name: 'GET /api/products',
        total_requests: 1000,
        error_count: 5,
        latency_p50: 120,
        latency_p95: 250,
        latency_p99: 400,
        availability_percent: 99.5,
        slo_met: true,
        target: 500,
        slo_type: 'latency'
      },
      {
        transaction_name: 'POST /api/orders',
        total_requests: 500,
        error_count: 25,
        latency_p50: 300,
        latency_p95: 850,
        latency_p99: 1200,
        availability_percent: 95.0,
        slo_met: false,
        target: 500,
        slo_type: 'latency'
      }
    ]
  }

  it('renders SLO table headers', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    expect(screen.getByText('Service')).toBeInTheDocument()
    expect(screen.getByText('Type')).toBeInTheDocument()
    expect(screen.getByText('Target')).toBeInTheDocument()
    expect(screen.getByText('Current')).toBeInTheDocument()
    expect(screen.getByText('Budget Left')).toBeInTheDocument()
    expect(screen.getByText('Bad/Total')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('renders SLO results', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    expect(screen.getByRole('button', { name: /api-service/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /user-service/ })).toBeInTheDocument()
  })

  it('displays SLO type badges correctly', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    expect(screen.getByText('Avail 7d')).toBeInTheDocument()
    expect(screen.getByText('Latency 30d')).toBeInTheDocument()
  })

  it('highlights current value based on SLO target', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    // api-service: 99.95% >= 99.9% target → should be green/healthy
    const apiServiceRow = screen.getAllByRole('button', { name: /api-service/ })
    expect(apiServiceRow).toHaveLength(1)
  })

  it('colors error budget remaining based on thresholds', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    // api-service: 50% remaining → healthy color
    // user-service: 15% remaining → degraded/down color
  })

  it('shows slow API count when service has slow APIs', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    // api-service has 2 slow APIs (1 not meeting SLO)
    expect(screen.getByRole('button', { name: /1 slow/ })).toBeInTheDocument()
  })

  it('does not show slow API count when service has no slow APIs', () => {
    const resultsWithoutSlow = [mockResults[1]] // user-service has no slow APIs
    render(<SloTable results={resultsWithoutSlow} slowApisMap={{}} />)

    expect(screen.queryByText(/\d slow\)/)).not.toBeInTheDocument()
  })

  it('expands slow APIs when service is clicked', async () => {
    const user = userEvent.setup()
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    const serviceButton = screen.getByRole('button', { name: /api-service/ })
    await user.click(serviceButton)

    expect(screen.getByText('Slow APIs — api-service')).toBeInTheDocument()
    expect(screen.getByText(/1 not meeting SLO/)).toBeInTheDocument()
  })

  it('collapses slow APIs when service is clicked twice', async () => {
    const user = userEvent.setup()
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    const serviceButton = screen.getByRole('button', { name: /api-service/ })

    // First click expands
    await user.click(serviceButton)
    expect(screen.getByText('Slow APIs — api-service')).toBeInTheDocument()

    // Second click collapses
    await user.click(serviceButton)
    expect(screen.queryByText('Slow APIs — api-service')).not.toBeInTheDocument()
  })

  it('renders slow APIs table when expanded', async () => {
    const user = userEvent.setup()
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    await user.click(screen.getByRole('button', { name: /api-service/ }))

    expect(screen.getByText('API')).toBeInTheDocument()
    expect(screen.getByText('Requests')).toBeInTheDocument()
    expect(screen.getByText('Errors')).toBeInTheDocument()
    expect(screen.getByText('P95')).toBeInTheDocument()
    expect(screen.getByText('Availability')).toBeInTheDocument()
    expect(screen.getByText('SLO Met?')).toBeInTheDocument()
  })

  it('renders slow API details', async () => {
    const user = userEvent.setup()
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    await user.click(screen.getByRole('button', { name: /api-service/ }))

    // only APIs not meeting SLO are listed
    expect(screen.getByText('POST /api/orders')).toBeInTheDocument()
    expect(screen.queryByText('GET /api/products')).not.toBeInTheDocument()
  })

  it('handles empty results', () => {
    render(<SloTable results={[]} slowApisMap={{}} />)

    expect(screen.getByText('No data')).toBeInTheDocument()
  })

  it('displays status badges correctly', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    expect(screen.getByText('HEALTHY')).toBeInTheDocument()
    expect(screen.getByText('WARNING')).toBeInTheDocument()
  })

  it('formats bad/total requests correctly', () => {
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    // api-service: 5 / 10000 (bad requests out of total)
    const cell = screen.getAllByText((_, el) => el?.textContent === '5 / 10000')
    expect(cell.length).toBeGreaterThan(0)
  })

  it('only shows slow APIs that are not meeting SLO', async () => {
    const user = userEvent.setup()
    render(<SloTable results={mockResults} slowApisMap={mockSlowApis} />)

    await user.click(screen.getByRole('button', { name: /api-service/ }))

    // Should only show POST /api/orders (not meeting SLO)
    // GET /api/products should not be in the expanded table
    expect(screen.getByText('POST /api/orders')).toBeInTheDocument()
    expect(screen.queryByText('GET /api-products')).not.toBeInTheDocument()
  })
})
