import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { AuthApiError, authService } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import { SessionProvider } from '../services/SessionProvider'
import { AppRoutes } from './AppRoutes'

const maker = {
  id: 'maker-id', user_code: 'USR-1', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Maker One', status: 'ACTIVE' as const, roles: ['MAKER'],
}
const checker = { ...maker, id: 'checker-id', username: 'checker', roles: ['CHECKER'] }
const admin = { ...maker, id: 'admin-id', username: 'admin', roles: ['ADMIN'] }

function renderApplication(path = '/') {
  return render(<MemoryRouter initialEntries={[path]}><SessionProvider><AuthProvider><AppRoutes /></AuthProvider></SessionProvider></MemoryRouter>)
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

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
})
