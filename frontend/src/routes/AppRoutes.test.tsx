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
    renderApplication('/')
    expect(await screen.findByRole('heading', { name: 'Tài khoản đã đăng nhập' })).toBeVisible()
    expect(screen.queryByRole('link', { name: 'Mở workflow PostgreSQL của Maker' })).not.toBeInTheDocument()
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
})
