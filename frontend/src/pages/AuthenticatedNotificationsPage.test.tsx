import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowNotification } from '../types/authWorkflow'
import { AuthenticatedNotificationsPage } from './AuthenticatedNotificationsPage'

const notice: WorkflowNotification = {
  id: 'notice-1', event_type: 'PLAN_SUBMITTED', plan_id: 'plan-1', plan_code: 'MKT-1',
  title: 'Kế hoạch cần được duyệt', message: 'Kế hoạch MKT-1 đã được gửi duyệt.',
  version_number: 1, round_number: 1, created_at: '2026-10-11T08:00:00Z', read_at: null,
}

afterEach(() => vi.restoreAllMocks())

it('shows the recipient inbox and marks a notice read', async () => {
  vi.spyOn(authWorkflowService, 'listNotifications').mockResolvedValue({
    items: [notice], offset: 0, limit: 20, total: 1, unread_count: 1,
  })
  vi.spyOn(authWorkflowService, 'markNotificationRead').mockResolvedValue({
    ...notice, read_at: '2026-10-11T08:01:00Z',
  })

  render(<MemoryRouter><AuthenticatedNotificationsPage /></MemoryRouter>)

  expect(await screen.findByText('Kế hoạch MKT-1 đã được gửi duyệt.')).toBeVisible()
  expect(screen.getByText('1 chưa đọc')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Mở kế hoạch' })).toHaveAttribute('href', '/workflow/plans/plan-1')

  fireEvent.click(screen.getByRole('button', { name: 'Đánh dấu đã đọc' }))

  expect(await screen.findByText('0 chưa đọc')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Đánh dấu đã đọc' })).not.toBeInTheDocument()
  expect(authWorkflowService.markNotificationRead).toHaveBeenCalledWith('notice-1')
})
