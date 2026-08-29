/**
 * Unit tests for DataTable component.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DataTable } from './DataTable'

interface TestRow {
  id: number
  name: string
  status: string
}

describe('DataTable', () => {
  const mockColumns = [
    { key: 'id', header: 'ID' },
    { key: 'name', header: 'Name' },
    { key: 'status', header: 'Status' }
  ]

  const mockData: TestRow[] = [
    { id: 1, name: 'Test 1', status: 'active' },
    { id: 2, name: 'Test 2', status: 'inactive' }
  ]

  it('renders table headers', () => {
    render(<DataTable columns={mockColumns} data={mockData} />)

    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('renders table data rows', () => {
    render(<DataTable columns={mockColumns} data={mockData} />)

    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('Test 1')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
  })

  it('renders all data rows', () => {
    render(<DataTable columns={mockColumns} data={mockData} />)

    expect(screen.getByText('Test 1')).toBeInTheDocument()
    expect(screen.getByText('Test 2')).toBeInTheDocument()
  })

  it('displays "No data" message when data is empty', () => {
    render(<DataTable columns={mockColumns} data={[]} />)

    expect(screen.getByText('No data')).toBeInTheDocument()
  })

  it('uses custom render function when provided', () => {
    const columnsWithRender = [
      { key: 'id', header: 'ID' },
      {
        key: 'status',
        header: 'Status',
        render: (row: TestRow) => (
          <span data-testid={`status-${row.id}`}>{row.status.toUpperCase()}</span>
        )
      }
    ]

    render(<DataTable columns={columnsWithRender} data={mockData} />)

    expect(screen.getByTestId('status-1')).toHaveTextContent('ACTIVE')
    expect(screen.getByTestId('status-2')).toHaveTextContent('INACTIVE')
  })

  it('handles missing row data gracefully', () => {
    const incompleteData = [{ id: 1, name: 'Test' }] as TestRow[]

    render(<DataTable columns={mockColumns} data={incompleteData} />)

    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('Test')).toBeInTheDocument()
    // Missing 'status' should render empty string
  })

  it('handles empty data with custom render', () => {
    const columnsWithRender = [
      { key: 'id', header: 'ID', render: () => <span>Custom ID</span> }
    ]

    render(<DataTable columns={columnsWithRender} data={[]} />)

    expect(screen.getByText('No data')).toBeInTheDocument()
  })
})
