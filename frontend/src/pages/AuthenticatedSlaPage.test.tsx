import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { SlaConfiguration } from '../types/authWorkflow'
import { authWorkflowService } from '../services/authWorkflow'
import { AuthenticatedSlaPage } from './AuthenticatedSlaPage'

const unconfigured: SlaConfiguration = {
  configured: false, revision: 0, enabled: false, duration_minutes: null,
  warning_before_minutes: null, changed_by_id: null, changed_by_name: null,
  change_reason: null, updated_at: null,
}

const emptyHistory = { items: [], offset: 0, limit: 25, total: 0 }

afterEach(() => vi.restoreAllMocks())

describe('Admin SLA page', () => {
  it('keeps the synthetic 24h/4h preview separate from saved configuration', async () => {
    vi.spyOn(authWorkflowService, 'getSlaConfiguration').mockResolvedValue(unconfigured)
    vi.spyOn(authWorkflowService, 'listSlaConfigurationHistory').mockResolvedValue(emptyHistory)
    render(<MemoryRouter><AuthenticatedSlaPage /></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: 'Cấu hình SLA duyệt' })).toBeVisible()
    expect(screen.getByText('24 giờ')).toBeVisible()
    expect(screen.getByText(/không được lưu/)).toBeVisible()
    expect(screen.getByText(/Chưa có cấu hình được lưu/)).toBeVisible()
    expect(authWorkflowService.getSlaConfiguration).toHaveBeenCalledOnce()
  })

  it('saves one explicit revision using the displayed expected revision', async () => {
    const user = userEvent.setup()
    const enabledRevision: SlaConfiguration = {
      ...unconfigured, configured: true, revision: 1, enabled: true,
      duration_minutes: 24 * 60, warning_before_minutes: 4 * 60,
      changed_by_id: 'admin-1', changed_by_name: 'Admin One',
      change_reason: 'Pilot', updated_at: '2026-10-11T00:00:00Z',
    }
    vi.spyOn(authWorkflowService, 'getSlaConfiguration')
      .mockResolvedValueOnce(unconfigured)
      .mockResolvedValue(enabledRevision)
    vi.spyOn(authWorkflowService, 'listSlaConfigurationHistory').mockResolvedValue(emptyHistory)
    const save = vi.spyOn(authWorkflowService, 'updateSlaConfiguration').mockResolvedValue(enabledRevision)
    render(<MemoryRouter><AuthenticatedSlaPage /></MemoryRouter>)

    await screen.findByRole('heading', { name: 'Cấu hình SLA duyệt' })
    const periodFieldsets = screen.getAllByRole('group')
    const durationInputs = within(periodFieldsets[0]).getAllByRole('spinbutton')
    const warningInputs = within(periodFieldsets[1]).getAllByRole('spinbutton')
    await user.clear(durationInputs[0]); await user.type(durationInputs[0], '24')
    await user.clear(durationInputs[1]); await user.type(durationInputs[1], '0')
    await user.clear(warningInputs[0]); await user.type(warningInputs[0], '4')
    await user.clear(warningInputs[1]); await user.type(warningInputs[1], '0')
    await user.click(screen.getByRole('checkbox', { name: /Bật SLA cho vòng duyệt mới/ }))
    await user.type(screen.getByLabelText('Lý do thay đổi'), 'Pilot')
    await user.click(screen.getByRole('button', { name: /Lưu revision/ }))

    await waitFor(() => expect(save).toHaveBeenCalledWith({
      enabled: true, duration_minutes: 1440, warning_before_minutes: 240,
      expected_revision: 0, change_reason: 'Pilot',
    }))
    expect(await screen.findByText(/Đã lưu cấu hình revision 1/)).toBeVisible()
  })
})