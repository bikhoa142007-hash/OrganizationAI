import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { AuthApiError, authService } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPlan } from '../types/authWorkflow'
import { AuthenticatedPlansPage } from './AuthenticatedPlansPage'

const maker = {
  id: 'maker-1', user_code: 'USR-MAKER', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Maker One', status: 'ACTIVE' as const, roles: ['MAKER'],
}
const checker = {
  id: 'checker-1', user_code: 'USR-CHECKER', username: 'checker', email: 'checker@example.com',
  phone: null, display_name: 'Checker One', status: 'ACTIVE' as const, roles: ['CHECKER'],
}

function planFixture(index: number, overrides: Partial<WorkflowPlan> = {}): WorkflowPlan {
  return {
    id: `plan-${index}`, code: `MKT-${index}`,
    payload: {
      title: `Campaign ${index}`, objective: '', summary: '', department: 'Marketing',
      start_date: '', end_date: '', budget_minor_units: '', currency: 'VND', target_audience: '',
      channels: [], kpi_expected: '', notes: '',
    },
    status: 'DRAFT', processing_stage: 'PENDING',
    maker_id: maker.id, maker_name: 'Maker One', checker_id: null, checker_name: null,
    current_version: 1, current_round: 0, revision: 1, decision_reason: null,
    attachments: [], versions: [], ai_evaluations: [], engine_decisions: [], history: [],
    created_at: `2026-10-${String(index % 28 + 1).padStart(2, '0')}T10:00:00Z`,
    updated_at: `2026-10-${String(index % 28 + 1).padStart(2, '0')}T11:00:00Z`,
    ...overrides,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="current-search">{location.search}</output>
}

function renderList(path = '/workflow/plans') {
  return render(<MemoryRouter initialEntries={[path]}>
    <LocationProbe />
    <AuthProvider><Routes>
      <Route path="/workflow/plans" element={<AuthenticatedPlansPage />} />
      <Route path="/workflow/reviews" element={<AuthenticatedPlansPage reviews />} />
    </Routes></AuthProvider>
  </MemoryRouter>)
}

afterEach(() => vi.restoreAllMocks())

it('loads Maker pages, combines live client filters and writes only frontend URL state', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  const spring = planFixture(1, {
    code: 'REQ-SPRING', payload: { ...planFixture(1).payload, title: 'Spring launch', department: 'Marketing' },
    status: 'PENDING_APPROVAL', maker_name: 'Linh Nguyen',
    created_at: '2026-10-02T00:30:00+07:00',
  })
  const summerSales = planFixture(2, {
    code: 'REQ-SUMMER-2', payload: { ...planFixture(2).payload, title: 'Summer event', department: 'Sales' },
    status: 'APPROVED', maker_name: 'An Tran', created_at: '2026-10-02T11:00:00Z',
  })
  const summerMarketing = planFixture(3, {
    code: 'REQ-SUMMER-3', payload: { ...planFixture(3).payload, title: 'Summer launch', department: 'Marketing' },
    status: 'PENDING_APPROVAL', maker_name: 'An Tran',
    created_at: '2026-10-02T23:30:00-07:00',
  })
  const listPlans = vi.spyOn(authWorkflowService, 'listPlans').mockResolvedValue([spring, summerSales, summerMarketing])
  const listReviews = vi.spyOn(authWorkflowService, 'listReviews')

  renderList()

  expect(await screen.findByRole('link', { name: 'Spring launch (REQ-SPRING)' })).toBeVisible()
  expect(listPlans).toHaveBeenCalledExactlyOnceWith(0, 100)
  expect(listReviews).not.toHaveBeenCalled()
  expect(screen.getByText('3 kết quả trong 3 yêu cầu đã tải')).toBeVisible()

  fireEvent.change(screen.getByLabelText('Tìm trong các yêu cầu đã tải'), { target: { value: '  sUmMeR ' } })
  expect(screen.getByRole('link', { name: 'Summer event (REQ-SUMMER-2)' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Summer launch (REQ-SUMMER-3)' })).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Spring launch (REQ-SPRING)' })).not.toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('Trạng thái'), { target: { value: 'PENDING_APPROVAL' } })
  fireEvent.change(screen.getByLabelText('Bộ phận'), { target: { value: 'Marketing' } })
  fireEvent.change(screen.getByLabelText('Ngày tạo từ'), { target: { value: '2026-10-02' } })
  fireEvent.change(screen.getByLabelText('Ngày tạo đến'), { target: { value: '2026-10-02' } })

  expect(screen.getByRole('link', { name: 'Summer launch (REQ-SUMMER-3)' })).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Summer event (REQ-SUMMER-2)' })).not.toBeInTheDocument()
  expect(screen.getByText('1 kết quả trong 3 yêu cầu đã tải')).toBeVisible()
  expect(screen.getByTestId('current-search').textContent).toContain('q=sUmMeR')
  expect(screen.getByTestId('current-search').textContent).toContain('status=PENDING_APPROVAL')
  expect(screen.getByTestId('current-search').textContent).toContain('department=Marketing')
  expect(screen.getByTestId('current-search').textContent).toContain('created_from=2026-10-02')
  expect(screen.getByTestId('current-search').textContent).toContain('created_to=2026-10-02')
  expect(listPlans).toHaveBeenCalledTimes(1)

  fireEvent.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }))
  await waitFor(() => expect(screen.getByTestId('current-search').textContent).toBe(''))
  expect(screen.getByLabelText('Tìm trong các yêu cầu đã tải')).toHaveValue('')
  expect(screen.getByLabelText('Trạng thái')).toHaveValue('')
  expect(screen.getByLabelText('Bộ phận')).toHaveValue('')
  expect(screen.getByLabelText('Ngày tạo từ')).toHaveValue('')
  expect(screen.getByLabelText('Ngày tạo đến')).toHaveValue('')
  expect(screen.getByRole('link', { name: 'Spring launch (REQ-SPRING)' })).toBeVisible()
  expect(listPlans).toHaveBeenCalledTimes(1)
})

it('restores valid URL filters, normalizes invalid values, and does not call list APIs while filtering', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  const matching = planFixture(4, {
    code: 'REQ-DEEP-LINK', payload: { ...planFixture(4).payload, title: 'Deep linked campaign', department: 'Operations' },
    status: 'APPROVED', created_at: '2026-10-04T08:00:00Z',
  })
  const listPlans = vi.spyOn(authWorkflowService, 'listPlans').mockResolvedValue([matching])
  const validView = renderList('/workflow/plans?q=deep&status=APPROVED&department=Operations&created_from=2026-10-04')

  expect(await screen.findByRole('link', { name: 'Deep linked campaign (REQ-DEEP-LINK)' })).toBeVisible()
  expect(screen.getByLabelText('Tìm trong các yêu cầu đã tải')).toHaveValue('deep')
  expect(screen.getByLabelText('Trạng thái')).toHaveValue('APPROVED')
  expect(screen.getByLabelText('Bộ phận')).toHaveValue('Operations')
  expect(listPlans).toHaveBeenCalledExactlyOnceWith(0, 100)

  validView.unmount()
  const invalidView = renderList('/workflow/plans?status=UNKNOWN&created_from=2026-02-30')
  expect(await screen.findByText(/một số bộ lọc.*không hợp lệ/i)).toBeVisible()
  await waitFor(() => expect(screen.getByTestId('current-search').textContent).toBe(''))
  expect(screen.getByLabelText('Trạng thái')).toHaveValue('')
  invalidView.unmount()
})

it('offers load more when current-page filters have no match and merges duplicate IDs safely', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  const firstPage = Array.from({ length: 100 }, (_, index) => planFixture(index))
  const duplicateUpdated = planFixture(99, {
    payload: { ...planFixture(99).payload, title: 'Updated duplicate' },
  })
  const matchingNextPage = planFixture(100, {
    code: 'REQ-FINAL', payload: { ...planFixture(100).payload, title: 'Needle found', department: 'Research' },
  })
  const listPlans = vi.spyOn(authWorkflowService, 'listPlans')
    .mockResolvedValueOnce(firstPage)
    .mockResolvedValueOnce([duplicateUpdated, matchingNextPage])

  renderList()
  expect(await screen.findByRole('link', { name: 'Campaign 0 (MKT-0)' })).toBeVisible()
  fireEvent.change(screen.getByLabelText('Tìm trong các yêu cầu đã tải'), { target: { value: 'needle' } })
  expect(screen.getByText(/chưa có kết quả phù hợp trong dữ liệu đã tải/i)).toBeVisible()
  expect(screen.getByText('0 kết quả trong 100 yêu cầu đã tải')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Tải thêm hồ sơ' })).toBeEnabled()
  expect(listPlans).toHaveBeenCalledTimes(1)

  fireEvent.click(screen.getByRole('button', { name: 'Tải thêm hồ sơ' }))
  expect(await screen.findByRole('link', { name: 'Needle found (REQ-FINAL)' })).toBeVisible()
  expect(screen.getByText('1 kết quả trong 101 yêu cầu đã tải')).toBeVisible()
  fireEvent.change(screen.getByLabelText('Tìm trong các yêu cầu đã tải'), { target: { value: 'updated duplicate' } })
  expect(screen.getByRole('link', { name: 'Updated duplicate (MKT-99)' })).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: 'Updated duplicate (MKT-99)' })).toHaveLength(1)
  expect(listPlans).toHaveBeenNthCalledWith(1, 0, 100)
  expect(listPlans).toHaveBeenNthCalledWith(2, 100, 100)
})

it('keeps loaded rows and retries the same page after a temporary Maker list error', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  const firstPage = Array.from({ length: 100 }, (_, index) => planFixture(index))
  const listPlans = vi.spyOn(authWorkflowService, 'listPlans')
    .mockResolvedValueOnce(firstPage)
    .mockRejectedValueOnce(new AuthApiError(503, 'Unavailable.', 'SERVICE_UNAVAILABLE', 'maker-page-trace'))
    .mockResolvedValueOnce([planFixture(100)])
  renderList()

  expect(await screen.findByRole('link', { name: 'Campaign 0 (MKT-0)' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: /Tải lại/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Dịch vụ workflow đang gặp sự cố')
  expect(screen.getByRole('link', { name: 'Campaign 0 (MKT-0)' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Thử tải lại' }))
  expect(await screen.findByRole('link', { name: 'Campaign 100 (MKT-100)' })).toBeVisible()
  expect(listPlans).toHaveBeenNthCalledWith(1, 0, 100)
  expect(listPlans).toHaveBeenNthCalledWith(2, 0, 100)
  expect(listPlans).toHaveBeenNthCalledWith(3, 0, 100)
})

it('uses only the Checker review endpoint for the Checker list mode', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(checker)
  const listReviews = vi.spyOn(authWorkflowService, 'listReviews').mockResolvedValue([planFixture(9)])
  const listPlans = vi.spyOn(authWorkflowService, 'listPlans')
  renderList('/workflow/reviews')

  expect(await screen.findByRole('link', { name: 'Campaign 9 (MKT-9)' })).toBeVisible()
  expect(listReviews).toHaveBeenCalledExactlyOnceWith(0, 100)
  expect(listPlans).not.toHaveBeenCalled()
})
