/**
 * Unit tests for AlertRuleForm component.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import toast from 'react-hot-toast'
import { AlertRuleForm } from './AlertRuleForm'
import * as alertsApi from '../../api/alerts'
import type { AlertRule } from '../../types'

// Mock the API
vi.mock('../../api/alerts', () => ({
  createAlertRule: vi.fn(),
  updateAlertRule: vi.fn()
}))

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn()
  },
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}))

describe('AlertRuleForm', () => {
const fullAlertRule: AlertRule = {
  id: 'rule-001',
  name: 'Test Rule',
  source: 'prometheus',
  metric: 'cpu_usage',
  condition: 'gt',
  threshold: 80,
  duration_seconds: 60,
  severity: 'warning',
  enabled: true,
  notify_slack: true,
  notify_email: false,
  notify_webhook: false,
  labels: {}
}


  const mockOnClose = vi.fn()
  const mockOnSaved = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders form for creating new rule', () => {
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByDisplayValue('prometheus')).toBeInTheDocument() // default source
    expect(screen.getByText('Create')).toBeInTheDocument()
  })

  it('renders form for editing existing rule', () => {
    const existingRule = {
      id: 'test-001',
      name: 'Test Rule',
      source: 'elasticsearch' as const,
      metric: 'error_count',
      condition: 'gt' as const,
      threshold: 100,
      duration_seconds: 300,
      severity: 'warning' as const,
      enabled: true,
      notify_slack: true,
      notify_email: false,
      notify_webhook: false,
      labels: {}
    }

    render(<AlertRuleForm rule={existingRule} onClose={mockOnClose} onSaved={mockOnSaved} />)

    expect(screen.getByDisplayValue('Test Rule')).toBeInTheDocument()
    expect(screen.getByDisplayValue('elasticsearch')).toBeInTheDocument()
    expect(screen.getByText('Update')).toBeInTheDocument()
  })

  it('renders all source options', () => {
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    expect(screen.getByDisplayValue('prometheus')).toBeInTheDocument()
    expect(screen.getByText('elasticsearch')).toBeInTheDocument()
    expect(screen.getByText('apm')).toBeInTheDocument()
    expect(screen.getByText('kubernetes')).toBeInTheDocument()
  })

  it('updates form state on input change', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    const nameInput = screen.getByLabelText('Name')
    await user.clear(nameInput)
    await user.type(nameInput, 'New Test Rule')

    expect(screen.getByDisplayValue('New Test Rule')).toBeInTheDocument()
  })

  it('handles source selection', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    const sourceSelect = screen.getByDisplayValue('prometheus')
    await user.selectOptions(sourceSelect, 'elasticsearch')

    expect(screen.getByDisplayValue('elasticsearch')).toBeInTheDocument()
  })

  it('handles condition selection', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    const conditionSelect = screen.getByDisplayValue('gt')
    await user.selectOptions(conditionSelect, 'lte')

    expect(screen.getByDisplayValue('lte')).toBeInTheDocument()
  })

  it('handles severity selection', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    const severitySelect = screen.getByDisplayValue('warning')
    await user.selectOptions(severitySelect, 'critical')

    expect(screen.getByDisplayValue('critical')).toBeInTheDocument()
  })

  it('handles threshold input', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    const thresholdInput = screen.getByDisplayValue('0')
    await user.clear(thresholdInput)
    await user.type(thresholdInput, '85')

    expect(screen.getByDisplayValue('85')).toBeInTheDocument()
  })

  it('handles checkbox toggles', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    const slackCheckbox = screen.getAllByRole('checkbox')[0] // Slack checkbox

    // Slack should be checked by default
    expect(slackCheckbox).toBeChecked()

    await user.click(slackCheckbox)
    expect(slackCheckbox).not.toBeChecked()

    await user.click(slackCheckbox)
    expect(slackCheckbox).toBeChecked()
  })

  it('calls onClose when cancel button clicked', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    await user.click(screen.getByText('Cancel'))
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('submits new rule and shows success toast', async () => {
    const user = userEvent.setup()
    vi.mocked(alertsApi.createAlertRule).mockResolvedValueOnce({ ...fullAlertRule, id: 'new-001' })

    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    // Fill required fields
    await user.type(screen.getByLabelText('Name'), 'Test Rule')
    await user.type(screen.getByPlaceholderText('e.g. cpu_percent'), 'cpu_usage')
    await user.click(screen.getByText('Create'))

    await waitFor(() => {
      expect(alertsApi.createAlertRule).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('Rule created')
      expect(mockOnSaved).toHaveBeenCalled()
    })
  })

  it('submits updated rule and shows success toast', async () => {
    const user = userEvent.setup()
    const existingRule = {
      id: 'test-001',
      name: 'Test Rule',
      source: 'prometheus' as const,
      metric: 'cpu_usage',
      condition: 'gt' as const,
      threshold: 80,
      duration_seconds: 60,
      severity: 'warning' as const,
      enabled: true,
      notify_slack: true,
      notify_email: false,
      notify_webhook: false,
      labels: {}
    }

    vi.mocked(alertsApi.updateAlertRule).mockResolvedValueOnce(fullAlertRule)

    render(<AlertRuleForm rule={existingRule} onClose={mockOnClose} onSaved={mockOnSaved} />)

    await user.click(screen.getByText('Update'))

    await waitFor(() => {
      expect(alertsApi.updateAlertRule).toHaveBeenCalledWith('test-001', expect.any(Object))
      expect(toast.success).toHaveBeenCalledWith('Rule updated')
      expect(mockOnSaved).toHaveBeenCalled()
    })
  })

  it('shows error toast when API call fails', async () => {
    const user = userEvent.setup()
    vi.mocked(alertsApi.createAlertRule).mockRejectedValueOnce(new Error('API Error'))

    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    // Fill required fields
    await user.type(screen.getByLabelText('Name'), 'Test Rule')
    await user.type(screen.getByPlaceholderText('e.g. cpu_percent'), 'cpu_usage')
    await user.click(screen.getByText('Create'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to save rule')
    })
  })

  it('prevents submission with empty required fields', async () => {
    const user = userEvent.setup()
    render(<AlertRuleForm rule={null} onClose={mockOnClose} onSaved={mockOnSaved} />)

    // Don't fill required fields, just click submit
    const submitButton = screen.getByText('Create')
    await user.click(submitButton)

    // Form should not submit (HTML5 validation)
    expect(alertsApi.createAlertRule).not.toHaveBeenCalled()
  })
})
