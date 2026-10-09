import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { AuthApiError, authService } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import { SessionProvider } from '../services/SessionProvider'
import type { WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'
import { AppRoutes } from './AppRoutes'

const maker = {
  id: 'maker-id', user_code: 'USR-1', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Maker One', status: 'ACTIVE' as const, roles: ['MAKER'],
}
const checker = { ...maker, id: 'checker-id', username: 'checker', roles: ['CHECKER'] }
const admin = { ...maker, id: 'admin-id', username: 'admin', roles: ['ADMIN'] }
const adminMaker = { ...admin, id: 'admin-maker-id', username: 'admin.maker', roles: ['ADMIN', 'MAKER'] }

function renderApplication(path = '/') {
  return render(<MemoryRouter initialEntries={[path]}><SessionProvider><AuthProvider><AppRoutes /></AuthProvider></SessionProvider></MemoryRouter>)
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
beforeEach(() => {
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: false })
})

describe('Auth-first route entry', () => {
  it('sends anonymous visitors from / to login', async () => {
    vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
    renderApplication('/')

    expect(await screen.findByRole('heading', { name: 'Chào mừng trở lại' })).toBeVisible()
  })

  it('keeps the unavailable-service error visible instead of redirecting to login', async () => {
    vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(503, 'Unavailable.'))
    renderApplication('/')

    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kết nối dịch vụ đăng nhập')
    expect(screen.queryByRole('heading', { name: 'Chào mừng trở lại' })).not.toBeInTheDocument()
  })

  it('sends Maker, Checker, and Admin users to their role home', async () => {
    for (const [user, heading] of [
      [maker, 'Kế hoạch của tôi'], [checker, 'Kế hoạch chờ tôi duyệt'],
    ] as const) {
      vi.restoreAllMocks()
      vi.spyOn(authService, 'me').mockResolvedValue(user)
      vi.spyOn(authWorkflowService, user.roles.includes('MAKER') ? 'listPlans' : 'listReviews').mockResolvedValue([])
      const view = renderApplication('/')
      expect(await screen.findByRole('heading', { name: heading })).toBeVisible()
      view.unmount()
    }

  vi.restoreAllMocks()
  vi.spyOn(authService, 'me').mockResolvedValue(admin)
  vi.spyOn(authWorkflowService, 'listPlans').mockResolvedValue([])
  renderApplication('/')
  expect(await screen.findByRole('heading', { name: 'Toàn bộ kế hoạch' })).toBeVisible()
  expect(screen.getByText('Chế độ chỉ đọc cho kế hoạch trong phạm vi marketing.')).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Mở workflow PostgreSQL của Maker' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Tạo kế hoạch' })).not.toBeInTheDocument()
  })

  it('keeps Maker and Checker navigation for a user with both roles', async () => {
    const dual = { ...maker, roles: ['MAKER', 'CHECKER'] }
    vi.spyOn(authService, 'me').mockResolvedValue(dual)
    vi.spyOn(authWorkflowService, 'listPlans').mockResolvedValue([])
    renderApplication('/')

    expect(await screen.findByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
    expect(screen.getByRole('link', { name: /Kế hoạch của tôi/ })).toBeVisible()
    expect(screen.getByRole('link', { name: /Hàng chờ duyệt/ })).toBeVisible()
  })

  it('adds Maker actions for ADMIN+MAKER without granting Checker navigation', async () => {
    const user = userEvent.setup()
    vi.spyOn(authService, 'me').mockResolvedValue(adminMaker)
    vi.spyOn(authWorkflowService, 'listPlans').mockResolvedValue([])
    const listCheckers = vi.spyOn(authWorkflowService, 'listCheckers').mockResolvedValue([])
    renderApplication('/')

    expect(await screen.findByRole('heading', { name: 'Toàn bộ kế hoạch' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Tạo kế hoạch' })).toBeVisible()
    expect(screen.queryByRole('link', { name: /Hàng chờ duyệt/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Tạo kế hoạch' }))

    expect(await screen.findByRole('heading', { name: 'Tạo kế hoạch marketing' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Lưu bản nháp' })).toBeEnabled()
    expect(listCheckers).toHaveBeenCalledOnce()
  })

  it('shows the read-only audit log to Admin and denies it to Maker', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(admin)
    const listAudit = vi.spyOn(authWorkflowService, 'listAuditEvents').mockResolvedValue({
      items: [{
        id: 'event-1', plan_id: 'plan-1', plan_code: 'MKT-1', actor_id: maker.id,
        actor_type: 'HUMAN', actor_name: 'Maker One', action: 'CREATED',
        status_before: null, status_after: 'DRAFT', details: {}, created_at: '2026-10-09T10:00:00Z',
      }],
      offset: 0, limit: 50, total: 1,
    })
    const adminView = renderApplication('/workflow/audit')

    expect(await screen.findByRole('heading', { name: 'Nhật ký kiểm toán' })).toBeVisible()
    expect(await screen.findByText('MKT-1')).toBeVisible()
    expect(listAudit).toHaveBeenCalledWith(0, 50)

    adminView.unmount()
    vi.restoreAllMocks()
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    const forbiddenAudit = vi.spyOn(authWorkflowService, 'listAuditEvents')
    renderApplication('/workflow/audit')
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(forbiddenAudit).not.toHaveBeenCalled()
  })

  it('does not render protected account content while the initial session check is pending', () => {
    vi.spyOn(authService, 'me').mockReturnValue(new Promise(() => {}))
    renderApplication('/account')

    expect(screen.getByRole('status')).toHaveTextContent('Đang khôi phục phiên đăng nhập')
    expect(screen.queryByRole('heading', { name: 'Tài khoản' })).not.toBeInTheDocument()
  })

  it('routes an authenticated user without the required role to access denied', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    renderApplication('/workflow/reviews')

    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Mở không gian làm việc' })).toHaveAttribute('href', '/workflow/plans')
    expect(screen.queryByRole('heading', { name: 'Kế hoạch chờ tôi duyệt' })).not.toBeInTheDocument()
  })

  it('allows a Maker to open the Request create form', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    vi.spyOn(authWorkflowService, 'listCheckers').mockResolvedValue([])
    renderApplication('/workflow/plans/new')

    expect(await screen.findByRole('heading', { name: 'Tạo kế hoạch marketing' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Lưu bản nháp' })).toBeEnabled()
  })

  it('does not load Maker edit resources for a Checker', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(checker)
    const getPlan = vi.spyOn(authWorkflowService, 'getPlan')
    renderApplication('/workflow/plans/plan-1/edit')

    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(getPlan).not.toHaveBeenCalled()
  })

  it('loads detail status from the backend and exposes edit only for the Maker owner', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    const payload: WorkflowPayload = {
      title: 'Plan from server', objective: '', summary: '', department: '', start_date: '', end_date: '',
      budget_minor_units: '', currency: 'VND', target_audience: '', channels: [], kpi_expected: '', notes: '',
    }
    const plan: WorkflowPlan = {
      id: 'plan-1', code: 'MKT-1', payload, status: 'DRAFT', processing_stage: 'DRAFT',
      maker_id: maker.id, maker_name: maker.display_name, checker_id: null, checker_name: null,
      current_version: 0, current_round: 0, revision: 2, decision_reason: null,
      attachments: [], versions: [], ai_evaluations: [], engine_decisions: [], history: [],
      created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
    }
    const getPlan = vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValue(plan)
    renderApplication('/workflow/plans/plan-1')

    expect(await screen.findByRole('heading', { name: 'Plan from server' })).toBeVisible()
    expect(getPlan).toHaveBeenCalledWith('plan-1')
    expect(screen.getByRole('link', { name: 'Chỉnh sửa và gửi lại' })).toHaveAttribute('href', '/workflow/plans/plan-1/edit')
    expect(screen.getByText('Bản nháp')).toBeVisible()
  })

  it('lets a Checker open an assigned review detail and exposes the decision form', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(checker)
    const payload: WorkflowPayload = {
      title: 'Assigned review', objective: 'Review the request', summary: '', department: 'Marketing',
      start_date: '2026-10-01', end_date: '2026-10-31', budget_minor_units: '250000', currency: 'VND',
      target_audience: '', channels: [], kpi_expected: '', notes: '',
    }
    const plan: WorkflowPlan = {
      id: 'review-1', code: 'MKT-REVIEW-1', payload, status: 'PENDING_APPROVAL',
      processing_stage: 'HUMAN_REVIEW_REQUIRED', maker_id: 'maker-id', maker_name: 'Maker One',
      checker_id: checker.id, checker_name: checker.display_name, current_version: 1, current_round: 1,
      revision: 3, decision_reason: 'Needs human review.', attachments: [], versions: [],
      ai_evaluations: [], engine_decisions: [], history: [],
      created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
    }
    const getPlan = vi.spyOn(authWorkflowService, 'getPlan').mockResolvedValue(plan)
    renderApplication('/workflow/plans/review-1')

    expect(await screen.findByRole('heading', { name: 'Assigned review' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Quyết định Checker' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Quay lại danh sách' })).toHaveAttribute('href', '/workflow/reviews')
    expect(getPlan).toHaveBeenCalledWith('review-1')
  })

  it('clears an expired session, shows the expiry notice, and returns to the original internal route after login', async () => {
    const user = userEvent.setup()
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    vi.spyOn(authService, 'login').mockResolvedValue(maker)
    const dispatchEvent = vi.spyOn(window, 'dispatchEvent')
    let planCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/auth/config')) {
        return new Response(JSON.stringify({ registration_enabled: true }), { status: 200 })
      }
      if (url.includes('/workflow/plans')) {
        planCalls += 1
        if (planCalls === 1) return new Response(JSON.stringify({
          code: 'UNAUTHENTICATED', message: 'Session expired.', correlation_id: 'trace-expired',
        }), { status: 401, headers: { 'Content-Type': 'application/json' } })
        return new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(null, { status: 404 })
    }))

    renderApplication('/workflow/plans?tab=assigned#latest')

    expect(await screen.findByText('Đang tải danh sách kế hoạch…')).toBeVisible()
    expect(await screen.findByText('Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.')).toBeVisible()
    expect(dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({ type: 'organizationai:auth-expired' }))
    await user.type(screen.getByLabelText('Tên đăng nhập, mã người dùng hoặc email'), 'maker')
    await user.type(screen.getByLabelText('Mật khẩu'), 'local-secret')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

    expect(await screen.findByRole('heading', { name: 'Kế hoạch của tôi' })).toBeVisible()
    expect(planCalls).toBe(2)
  })

  it('routes a backend 403 to access denied while keeping the current session', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      code: 'FORBIDDEN', message: 'Not permitted.', correlation_id: 'trace-forbidden',
    }), { status: 403, headers: { 'Content-Type': 'application/json' } })))

    renderApplication('/workflow/plans')

    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Chào mừng trở lại' })).not.toBeInTheDocument()
  })
})
