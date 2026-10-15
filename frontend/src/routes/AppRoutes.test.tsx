import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { AuthApiError, authService } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import {
  approvalConfigurationService,
  type ConfigurationCurrent,
  type ConfigurationHistory,
  type ConfigurationRevision,
} from '../services/approvalConfiguration'
import { SessionProvider } from '../services/SessionProvider'
import { ServicesProvider } from '../services/ServiceProvider'
import { createApiServices } from '../services/api'
import { isPublicJudgeOnly } from '../services/apiBaseUrl'
import type { WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'
import { AppRoutes } from './AppRoutes'

const maker = {
  id: 'maker-id', user_code: 'USR-1', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Maker One', status: 'ACTIVE' as const, roles: ['MAKER'],
}
const checker = { ...maker, id: 'checker-id', username: 'checker', roles: ['CHECKER'] }
const admin = {
  ...maker,
  id: 'admin-id',
  username: 'admin',
  roles: ['ADMIN'],
  effective_permissions: [
    'MARKETING_PLAN_READ', 'MARKETING_PLAN_VIEW_ALL', 'MARKETING_HISTORY_READ',
    'ADMIN_EMPLOYEE_MANAGE', 'ADMIN_ROLE_MANAGE', 'ADMIN_APPROVER_MANAGE',
    'ADMIN_SLA_MANAGE', 'ADMIN_AUDIT_READ',
  ],
}
const adminMaker = { ...admin, id: 'admin-maker-id', username: 'admin.maker', roles: ['ADMIN', 'MAKER'] }

function renderApplication(path = '/') {
  const routes = isPublicJudgeOnly()
    ? <AppRoutes />
    : <SessionProvider><AuthProvider><AppRoutes /></AuthProvider></SessionProvider>
  return render(<MemoryRouter initialEntries={[path]}><ServicesProvider services={createApiServices()}>{routes}</ServicesProvider></MemoryRouter>)
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })
beforeEach(() => {
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: false })
})

describe('Auth-first route entry', () => {
  it('limits a Public Judge-only build to Judge routes without loading Auth', async () => {
    vi.stubEnv('VITE_PUBLIC_JUDGE_ONLY', 'true')
    vi.stubEnv('VITE_DEMO_ENABLED', 'true')
    const loadPrincipal = vi.spyOn(authService, 'me')

    renderApplication('/workflow/plans/new')

    expect(await screen.findByRole('heading', { name: 'Verify workflow' })).toBeVisible()
    expect(screen.getByText('Judge công khai, không cần tạo tài khoản')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Đăng nhập' })).not.toBeInTheDocument()
    expect(loadPrincipal).not.toHaveBeenCalled()
  })

  it('exposes the public Challenge A Judge without Auth when Demo is enabled', async () => {
    vi.stubEnv('VITE_DEMO_ENABLED', 'true')
    const loadPrincipal = vi.spyOn(authService, 'me')

    renderApplication('/challenge-a')

    expect(await screen.findByRole('heading', { name: 'Verify workflow' })).toBeVisible()
    expect(screen.getByText('Judge công khai, không cần tạo tài khoản')).toBeVisible()
    expect(loadPrincipal).not.toHaveBeenCalled()
  })

  it('does not expose the public Challenge A route when Demo is disabled', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('VITE_DEMO_ENABLED', 'false')
    vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))

    renderApplication('/challenge-a')

    expect(await screen.findByRole('heading', { name: 'Chào mừng trở lại' })).toBeVisible()
    expect(screen.queryByText('Judge công khai, không cần tạo tài khoản')).not.toBeInTheDocument()
  })

  it('protects approval configuration with the Admin role', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    const deniedLoad = vi.spyOn(approvalConfigurationService, 'current')
    const denied = renderApplication('/workflow/configuration')
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(deniedLoad).not.toHaveBeenCalled()

    denied.unmount()
    vi.restoreAllMocks()
    vi.spyOn(authService, 'me').mockResolvedValue(admin)
    vi.spyOn(approvalConfigurationService, 'current').mockResolvedValue({ as_of: '2026-10-12T00:00:00Z', items: [] })
    vi.spyOn(approvalConfigurationService, 'history').mockResolvedValue({
      kind: 'approval_policy', as_of: '2026-10-12T00:00:00Z', items: [], offset: 0, limit: 50, total: 0,
    })
    renderApplication('/workflow/configuration')
    expect(await screen.findByRole('heading', { name: 'Cấu hình phê duyệt' })).toBeVisible()
  })
  it('warns that valid custom Strategy weights are not supported by the evaluator', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(admin)
    vi.spyOn(approvalConfigurationService, 'current').mockResolvedValue({ as_of: '2026-10-12T00:00:00Z', items: [] })
    vi.spyOn(approvalConfigurationService, 'history').mockImplementation(async kind => ({
      kind, as_of: '2026-10-12T00:00:00Z', items: [], offset: 0, limit: 50, total: 0,
    }))
    const user = userEvent.setup()
    renderApplication('/workflow/configuration')

    await screen.findByRole('heading', { name: 'Cấu hình phê duyệt' })
    await user.selectOptions(screen.getByLabelText('Loại cấu hình'), 'strategy_rubric')

    expect(await screen.findByRole('note')).toHaveTextContent('evaluator hiện chỉ hỗ trợ bộ trọng số baseline 15/15/15/15/15/15/10')
    expect(screen.getByRole('note')).toHaveTextContent('EVALUATOR_RUBRIC_UNSUPPORTED')
  })
  it('does not apply an older configuration history response after switching kinds', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(admin)
    const current: ConfigurationCurrent = { as_of: '2026-10-14T00:00:00Z', items: [] }
    vi.spyOn(approvalConfigurationService, 'current').mockResolvedValue(current)

    let resolvePolicyHistory!: (history: ConfigurationHistory) => void
    const policyHistory = new Promise<ConfigurationHistory>(resolve => { resolvePolicyHistory = resolve })
    const emptyCheckerHistory: ConfigurationHistory = {
      kind: 'checker_assignment', as_of: '2026-10-14T00:00:00Z', items: [], offset: 0, limit: 50, total: 0,
    }
    const loadHistory = vi.spyOn(approvalConfigurationService, 'history').mockImplementation(async kind => {
      if (kind === 'approval_policy') return policyHistory
      return { ...emptyCheckerHistory, kind }
    })
    const stalePolicyRevision: ConfigurationRevision = {
      revision_id: 'policy-revision-2',
      kind: 'approval_policy',
      revision: 2,
      status: 'EFFECTIVE',
      effective_at: '2026-10-13T00:00:00Z',
      change_reason: 'Synthetic policy revision for stale-response regression.',
      value: {},
      configuration_hash: 'a'.repeat(64),
      changed_by: 'admin-id',
      created_at: '2026-10-13T00:00:00Z',
    }
    const checkerRevision: ConfigurationRevision = {
      ...stalePolicyRevision,
      revision_id: 'checker-revision-1',
      kind: 'checker_assignment',
      revision: 1,
      value: { maker_may_select_other: false, defaults: [] },
    }
    const createRevision = vi.spyOn(approvalConfigurationService, 'createRevision').mockResolvedValue(checkerRevision)
    const user = userEvent.setup()
    renderApplication('/workflow/configuration')

    await waitFor(() => expect(loadHistory).toHaveBeenCalledWith('approval_policy'))
    await user.selectOptions(screen.getByLabelText('Loại cấu hình'), 'checker_assignment')
    await waitFor(() => expect(loadHistory).toHaveBeenCalledWith('checker_assignment'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Tạo revision bất biến' })).toBeEnabled())

    await act(async () => {
      resolvePolicyHistory({
        kind: 'approval_policy',
        as_of: '2026-10-14T00:00:00Z',
        items: [stalePolicyRevision],
        offset: 0,
        limit: 50,
        total: 1,
      })
      await policyHistory
    })

    expect(screen.queryByText('Revision 2 · Đang hiệu lực')).not.toBeInTheDocument()
    await user.clear(screen.getByLabelText('Giá trị JSON'))
    fireEvent.change(screen.getByLabelText('Giá trị JSON'), { target: { value: '{"maker_may_select_other":false,"defaults":[{"department":"Marketing","checker_id":"b7a90116-e0fa-4a91-8658-572eb86a4d37"}]}' } })
    await user.clear(screen.getByLabelText(/Hiệu lực từ thời điểm/))
    await user.type(screen.getByLabelText(/Hiệu lực từ thời điểm/), '2026-10-14T16:30')
    await user.type(screen.getByLabelText('Lý do thay đổi'), 'Synthetic stale configuration response regression.')
    await user.click(screen.getByRole('button', { name: 'Tạo revision bất biến' }))

    expect(await screen.findByText(/Đã tạo revision 1/)).toBeVisible()
    expect(createRevision).toHaveBeenCalledWith('checker_assignment', expect.objectContaining({ expected_revision: null }))
  })

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

  it('shows the employee directory only to Admin users', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(admin)
    const listEmployees = vi.spyOn(authWorkflowService, 'listEmployees').mockResolvedValue({
      items: [{
        id: 'employee-1', account_id: 'user-1', user_code: 'USR-1', username: 'maker', display_name: 'Maker One',
        email: 'maker@example.com', phone: null, department: null, job_title: null,
        employment_start_date: null, employment_status: 'ACTIVE', status: 'ACTIVE', account_status: 'ACTIVE', roles: ['MAKER'], effective_permissions: [],
      }],
      offset: 0, limit: 25, total: 1,
    })
    vi.spyOn(authWorkflowService, 'listRoles').mockResolvedValue({ items: [], permission_catalog: [] })
    const adminView = renderApplication('/workflow/employees')

    expect(await screen.findByRole('heading', { name: 'Danh sách nhân viên' })).toBeVisible()
    const directoryTable = await screen.findByRole('table')
    expect(within(directoryTable).getByText('Maker One')).toBeVisible()
    expect(listEmployees).toHaveBeenCalledWith({
      query: '', role: '', status: undefined, department: '', job_title: '',
      employment_status: undefined, offset: 0, limit: 25,
    })

    adminView.unmount()
    vi.restoreAllMocks()
    vi.spyOn(authService, 'me').mockResolvedValue(maker)
    const deniedList = vi.spyOn(authWorkflowService, 'listEmployees')
    renderApplication('/workflow/employees')
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(deniedList).not.toHaveBeenCalled()
  })

  it('shows SLA configuration only to Admin with the existing management permission', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue({
      ...admin, effective_permissions: ['ADMIN_AUDIT_READ', 'ADMIN_EMPLOYEE_MANAGE', 'ADMIN_ROLE_MANAGE'],
    })
    const deniedLoad = vi.spyOn(authWorkflowService, 'getSlaConfiguration')
    const denied = renderApplication('/workflow/sla')
    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(deniedLoad).not.toHaveBeenCalled()

    denied.unmount()
    vi.restoreAllMocks()
    vi.spyOn(authService, 'me').mockResolvedValue({
      ...admin, effective_permissions: ['ADMIN_SLA_MANAGE'],
    })
    vi.spyOn(authWorkflowService, 'getSlaConfiguration').mockResolvedValue({
      configured: false, revision: 0, enabled: false, duration_minutes: null,
      warning_before_minutes: null, changed_by_id: null, changed_by_name: null,
      change_reason: null, updated_at: null,
    })
    vi.spyOn(authWorkflowService, 'listSlaConfigurationHistory').mockResolvedValue({
      items: [], offset: 0, limit: 25, total: 0,
    })
    renderApplication('/workflow/sla')
    expect(await screen.findByRole('heading', { name: 'Cấu hình SLA duyệt' })).toBeVisible()
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

  it('does not load the audit page for an Admin missing ADMIN_AUDIT_READ', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue({
      ...admin,
      effective_permissions: ['ADMIN_EMPLOYEE_MANAGE'],
    })
    const listAudit = vi.spyOn(authWorkflowService, 'listAuditEvents')

    renderApplication('/workflow/audit')

    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(listAudit).not.toHaveBeenCalled()
  })

  it('does not load employee administration for an Admin missing ADMIN_EMPLOYEE_MANAGE', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue({
      ...admin,
      effective_permissions: ['ADMIN_AUDIT_READ'],
    })
    const listEmployees = vi.spyOn(authWorkflowService, 'listEmployees')

    renderApplication('/workflow/employees')

    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(listEmployees).not.toHaveBeenCalled()
  })

  it('does not load role administration for an Admin missing ADMIN_ROLE_MANAGE', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue({
      ...admin,
      effective_permissions: ['ADMIN_AUDIT_READ'],
    })
    const listRoles = vi.spyOn(authWorkflowService, 'listRoles')

    renderApplication('/workflow/roles')

    expect(await screen.findByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
    expect(listRoles).not.toHaveBeenCalled()
  })
})
