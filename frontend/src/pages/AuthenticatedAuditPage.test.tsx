import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowAuditEvent } from '../types/authWorkflow'
import { AuthenticatedAuditPage } from './AuthenticatedAuditPage'

function auditEvent(overrides: Partial<WorkflowAuditEvent> = {}): WorkflowAuditEvent {
  return {
    id: 'event-1', plan_id: 'plan-1', plan_code: 'MKT-1', actor_id: 'checker-1',
    actor_type: 'HUMAN', actor_name: 'Checker One', action: 'APPROVED',
    status_before: 'PENDING_APPROVAL', status_after: 'APPROVED', details: {},
    created_at: '2026-10-06T15:00:00Z', ...overrides,
  }
}

afterEach(() => vi.restoreAllMocks())

it('shows API decision and override reasons separately without inventing a missing override', async () => {
  vi.spyOn(authWorkflowService, 'listAuditEvents').mockResolvedValue({
    items: [
      auditEvent({ details: { reason: 'Đạt mục tiêu đã thống nhất.', override_reason: 'Checker xác nhận ngoại lệ theo brief.' } }),
      auditEvent({ id: 'event-2', plan_code: 'MKT-2', action: 'REJECTED', status_after: 'REJECTED', details: { reason: 'Thiếu KPI đo lường.' } }),
    ],
    offset: 0, limit: 50, total: 2,
  })

  render(<AuthenticatedAuditPage />)

  const rows = await screen.findAllByRole('row')
  expect(rows).toHaveLength(3)
  expect(rows[1]).toHaveTextContent('Lý do phê duyệt: Đạt mục tiêu đã thống nhất.')
  expect(rows[1]).toHaveTextContent('Lý do override AI: Checker xác nhận ngoại lệ theo brief.')
  expect(rows[2]).toHaveTextContent('Lý do từ chối: Thiếu KPI đo lường.')
  expect(rows[2]).not.toHaveTextContent('Lý do override AI')
  expect(screen.getByText('1–2 / 2')).toBeVisible()
  expect(within(screen.getByLabelText('Phân trang nhật ký')).getByRole('button', { name: 'Tiếp' })).toBeDisabled()
})
