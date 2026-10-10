import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { authService, AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPlan } from '../types/authWorkflow'
import { AuthenticatedPlansPage } from './AuthenticatedPlansPage'

const checker = {
  id: 'checker-1', user_code: 'USR-CHECKER', username: 'checker', email: 'checker@example.com',
  phone: null, display_name: 'Checker One', status: 'ACTIVE' as const, roles: ['CHECKER'],
}

function planFixture(index: number): WorkflowPlan {
  return {
    id: `plan-${index}`, code: `MKT-${index}`,
    payload: {
      title: `Campaign ${index}`, objective: '', summary: '', department: 'Marketing',
      start_date: '', end_date: '', budget_minor_units: '', currency: 'VND', target_audience: '',
      channels: [], kpi_expected: '', notes: '',
    },
    status: 'PENDING_APPROVAL', processing_stage: 'HUMAN_REVIEW_REQUIRED',
    maker_id: 'maker-1', maker_name: 'Maker One', checker_id: checker.id, checker_name: checker.display_name,
    current_version: 1, current_round: 1, revision: 1, decision_reason: null,
    attachments: [], versions: [], ai_evaluations: [], engine_decisions: [], history: [],
    created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
  }
}

function renderQueue() {
  return render(<MemoryRouter initialEntries={['/workflow/reviews']}>
    <AuthProvider><AuthenticatedPlansPage reviews /></AuthProvider>
  </MemoryRouter>)
}

afterEach(() => vi.restoreAllMocks())

it('shows the loading state and pages through only backend review results', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(checker)
  const listReviews = vi.spyOn(authWorkflowService, 'listReviews')
    .mockResolvedValueOnce(Array.from({ length: 100 }, (_, index) => planFixture(index)))
    .mockResolvedValueOnce([planFixture(100), planFixture(101)])

  renderQueue()

  expect(screen.getByRole('status')).toHaveTextContent('Đang tải danh sách')
  expect(await screen.findByRole('link', { name: 'Campaign 0 (MKT-0)' })).toBeVisible()
  expect(listReviews).toHaveBeenNthCalledWith(1, 0, 100)
  expect(screen.getByRole('button', { name: 'Tải thêm hồ sơ' })).toBeEnabled()

  fireEvent.click(screen.getByRole('button', { name: 'Tải thêm hồ sơ' }))
  expect(await screen.findByRole('link', { name: 'Campaign 101 (MKT-101)' })).toBeVisible()
  expect(listReviews).toHaveBeenNthCalledWith(2, 100, 100)
  expect(screen.getByRole('status')).toHaveTextContent('Đã tải hết hồ sơ được giao.')
  expect(screen.queryByRole('button', { name: 'Tải thêm hồ sơ' })).not.toBeInTheDocument()
})

it('keeps already loaded reviews when a later page fails and permits an explicit retry', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(checker)
  const listReviews = vi.spyOn(authWorkflowService, 'listReviews')
    .mockResolvedValueOnce(Array.from({ length: 100 }, (_, index) => planFixture(index)))
    .mockRejectedValueOnce(new AuthApiError(503, 'Service unavailable.', 'SERVICE_UNAVAILABLE', 'trace-page'))
    .mockResolvedValueOnce([planFixture(100)])
  renderQueue()

  expect(await screen.findByRole('link', { name: 'Campaign 0 (MKT-0)' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Tải thêm hồ sơ' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Dịch vụ workflow đang gặp sự cố')
  expect(screen.getByText('Mã tham chiếu: trace-page')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Campaign 99 (MKT-99)' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByRole('link', { name: 'Campaign 100 (MKT-100)' })).toBeVisible()
  expect(listReviews).toHaveBeenNthCalledWith(3, 100, 100)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('shows an empty queue and lets the user retry an initial service error', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(checker)
  vi.spyOn(authWorkflowService, 'listReviews')
    .mockRejectedValueOnce(new AuthApiError(503, 'Unavailable.', 'SERVICE_UNAVAILABLE', 'trace-initial'))
    .mockResolvedValueOnce([])
  renderQueue()

  expect(await screen.findByRole('alert')).toHaveTextContent('Dịch vụ workflow đang gặp sự cố')
  expect(screen.getByText('Mã tham chiếu: trace-initial')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

  expect(await screen.findByRole('heading', { name: 'Không có hồ sơ chờ duyệt được giao cho bạn.' })).toBeVisible()
})
