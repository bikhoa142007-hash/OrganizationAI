import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { workflowCompletionService } from '../services/workflowCompletion'
import type { WorkflowDashboard } from '../services/workflowCompletion'
import { AuthenticatedDashboardPage } from './AuthenticatedDashboardPage'

const emptyDashboard: WorkflowDashboard = {
  as_of: '2026-10-12T08:30:00+00:00',
  principal_scope: 'MAKER_OWN',
  counts: { draft: 0, pending_ai: 0, human_review: 0, approved: 0, rejected: 0 },
  active_assignments: 0,
}

afterEach(() => vi.restoreAllMocks())

it('renders zero-state counts from the server aggregate without loading plan rows', async () => {
  const getDashboard = vi.spyOn(workflowCompletionService, 'getDashboard').mockResolvedValue(emptyDashboard)

  render(<AuthenticatedDashboardPage />)

  expect(await screen.findByText('Chưa có kế hoạch trong phạm vi bạn được xem.')).toBeVisible()
  expect(screen.getByText('Bản nháp')).toBeVisible()
  expect(screen.getAllByText('0')).toHaveLength(6)
  expect(getDashboard).toHaveBeenCalledOnce()
})

it('renders the server counts and UTC as-of timestamp', async () => {
  vi.spyOn(workflowCompletionService, 'getDashboard').mockResolvedValue({
    ...emptyDashboard,
    principal_scope: 'CHECKER_ASSIGNED',
    counts: { draft: 5, pending_ai: 2, human_review: 3, approved: 7, rejected: 1 },
    active_assignments: 5,
  })

  render(<AuthenticatedDashboardPage />)

  expect(await screen.findByText('Tổng quan kế hoạch marketing')).toBeVisible()
  expect(screen.getByText('Đang xử lý AI')).toBeVisible()
  expect(screen.getByText('Chờ Checker')).toBeVisible()
  expect(screen.getByText('7')).toBeVisible()
  expect(screen.getByText('Phân công đang hoạt động')).toBeVisible()
  expect(screen.getByText(/Số liệu chỉ gồm các kế hoạch được giao/)).toHaveTextContent(/UTC\./)
})
