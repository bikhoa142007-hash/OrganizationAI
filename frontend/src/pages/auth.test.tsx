import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from '../context/AuthContext'
import { RequireAuth } from '../components/auth/RequireAuth'
import { LoginPage } from './LoginPage'
import { RegisterPage } from './RegisterPage'
import { AuthenticatedAccountPage } from './AuthenticatedAccountPage'
import { authService, AuthApiError } from '../services/auth'

const maker = {
  id: 'user-1', user_code: 'USR-000001', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Demo Maker', status: 'ACTIVE' as const, roles: ['MAKER'],
}

function AccountPage() {
  const { user, roles, logout } = useAuth()
  const location = useLocation()
  return <main>
    <h1>OrganizationAI</h1>
    <p>Logged in as: {user?.display_name}</p>
    <p>Roles: {roles.join(', ')}</p>
    <p>Location: {`${location.pathname}${location.search}${location.hash}`}</p>
    <button onClick={() => void logout()}>Log out</button>
  </main>
}

function renderAuthApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<p>Auth entry</p>} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/account" element={<RequireAuth><AccountPage /></RequireAuth>} />
          <Route path="/workflow/plans" element={<RequireAuth><AccountPage /></RequireAuth>} />
          <Route path="/workflow/reviews" element={<RequireAuth><AccountPage /></RequireAuth>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())
beforeEach(() => {
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: false })
})

it('renders labeled login inputs and submits user code and password through the auth service', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me')
    .mockRejectedValueOnce(new AuthApiError(401, 'Authentication is required.'))
    .mockResolvedValue(maker)
  const login = vi.spyOn(authService, 'login').mockResolvedValue(maker)
  renderAuthApp('/login')

  await user.type(await screen.findByLabelText('Tên đăng nhập, mã người dùng hoặc email'), 'USR-000001')
  await user.type(screen.getByLabelText('Mật khẩu'), 'local-secret')
  await user.click(screen.getByLabelText('Ghi nhớ trên thiết bị này'))
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

  expect(login).toHaveBeenCalledWith('USR-000001', 'local-secret', true)
  expect(await screen.findByText('Logged in as: Demo Maker')).toBeVisible()
})

it('shows the registration link only when the server enables registration', async () => {
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: true })
  renderAuthApp('/login')

  expect(await screen.findByRole('link', { name: 'Đăng ký' })).toHaveAttribute('href', '/register')
})

it('shows a generic error when login fails', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'login').mockRejectedValue(
    new AuthApiError(401, 'Invalid user code/email or password.'),
  )
  renderAuthApp('/login')

  await user.type(await screen.findByLabelText('Tên đăng nhập, mã người dùng hoặc email'), 'nobody')
  await user.type(screen.getByLabelText('Mật khẩu'), 'bad-password')
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Thông tin đăng nhập không chính xác')
  expect(screen.getByLabelText('Tên đăng nhập, mã người dùng hoặc email')).toHaveValue('nobody')
  expect(screen.getByLabelText('Mật khẩu')).toHaveValue('bad-password')
})

it('shows and retries a non-401 session restoration error without blocking login', async () => {
  const user = userEvent.setup()
  const me = vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(503, 'Unavailable.'))
  renderAuthApp('/login')

  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kiểm tra phiên đăng nhập')
  expect(screen.getByRole('button', { name: 'Đăng nhập' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: 'Thử kiểm tra phiên lại' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kiểm tra phiên đăng nhập')
  expect(me).toHaveBeenCalledTimes(2)
})

it('trims the identifier while preserving whitespace in a non-empty password', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  const login = vi.spyOn(authService, 'login').mockResolvedValue(maker)
  renderAuthApp('/login')

  await user.type(await screen.findByLabelText('Tên đăng nhập, mã người dùng hoặc email'), ' maker ')
  await user.type(screen.getByLabelText('Mật khẩu'), '  ')
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

  expect(login).toHaveBeenCalledWith('maker', '  ', false)
})

it('enforces the 320-character login identifier contract before calling the API', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  const login = vi.spyOn(authService, 'login')
  renderAuthApp('/login')

  const identifier = await screen.findByLabelText('Tên đăng nhập, mã người dùng hoặc email')
  fireEvent.change(identifier, { target: { value: 'a'.repeat(321) } })
  await user.type(screen.getByLabelText('Mật khẩu'), 'p')
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

  expect(await screen.findByText('Thông tin đăng nhập không được vượt quá 320 ký tự.')).toBeVisible()
  expect(login).not.toHaveBeenCalled()
})

it('redirects unauthenticated visitors from the protected account page to login', async () => {
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  renderAuthApp('/account')

  expect(await screen.findByRole('heading', { name: 'Chào mừng trở lại' })).toBeVisible()
  expect(screen.getByLabelText('Tên đăng nhập, mã người dùng hoặc email')).toBeVisible()
})

it('disables the form while the login request is pending', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me')
    .mockRejectedValueOnce(new AuthApiError(401, 'Authentication is required.'))
    .mockResolvedValue(maker)
  let finishLogin!: (value: typeof maker) => void
  vi.spyOn(authService, 'login').mockImplementation(
    () => new Promise(resolve => { finishLogin = resolve }),
  )
  renderAuthApp('/login')

  await user.type(await screen.findByLabelText('Tên đăng nhập, mã người dùng hoặc email'), 'USR-000001')
  await user.type(screen.getByLabelText('Mật khẩu'), 'local-secret')
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

  expect(screen.getByRole('button', { name: 'Đang đăng nhập…' })).toBeDisabled()
  finishLogin(maker)
  expect(await screen.findByText('Logged in as: Demo Maker')).toBeVisible()
})

it('registers an account through the backend and directs the new Maker to login', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: true })
  const register = vi.spyOn(authService, 'register').mockResolvedValue(maker)
  renderAuthApp('/register')

  await user.type(await screen.findByLabelText('Tên đăng nhập'), 'new.maker')
  await user.type(screen.getByLabelText('Email hoặc số điện thoại'), 'new@example.com')
  await user.type(screen.getByLabelText('Mật khẩu'), 'New-local-password-123')
  await user.type(screen.getByLabelText('Nhập lại mật khẩu'), 'New-local-password-123')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(register).toHaveBeenCalledWith('new.maker', 'new@example.com', 'New-local-password-123')
  expect(await screen.findByRole('heading', { name: 'Chào mừng trở lại' })).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('Tạo tài khoản thành công')
})

it('rejects mismatched password confirmation before making a registration request', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: true })
  const register = vi.spyOn(authService, 'register')
  renderAuthApp('/register')

  await user.type(await screen.findByLabelText('Tên đăng nhập'), 'new.maker')
  await user.type(screen.getByLabelText('Email hoặc số điện thoại'), 'new@example.com')
  await user.type(screen.getByLabelText('Mật khẩu'), 'New-local-password-123')
  await user.type(screen.getByLabelText('Nhập lại mật khẩu'), 'different-password')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(await screen.findByText('Mật khẩu nhập lại chưa khớp.')).toBeVisible()
  expect(screen.getByLabelText('Nhập lại mật khẩu')).toHaveAttribute('aria-invalid', 'true')
  expect(register).not.toHaveBeenCalled()
})

it.each([
  [409, 'Tên đăng nhập hoặc thông tin liên hệ đã được sử dụng.'],
  [422, 'Vui lòng kiểm tra tên đăng nhập, thông tin liên hệ và mật khẩu.'],
] as const)('keeps registration inputs and reports HTTP %i', async (status, expectedMessage) => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: true })
  vi.spyOn(authService, 'register').mockRejectedValue(new AuthApiError(status, 'API detail', 'REQUEST_ERROR', 'trace-123'))
  renderAuthApp('/register')

  await user.type(await screen.findByLabelText('Tên đăng nhập'), 'new.maker')
  await user.type(screen.getByLabelText('Email hoặc số điện thoại'), 'contact value')
  await user.type(screen.getByLabelText('Mật khẩu'), 'New-local-password-123')
  await user.type(screen.getByLabelText('Nhập lại mật khẩu'), 'New-local-password-123')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(expectedMessage)
  expect(screen.getByRole('alert')).toHaveTextContent('trace-123')
  expect(screen.getByLabelText('Tên đăng nhập')).toHaveValue('new.maker')
  expect(screen.getByLabelText('Email hoặc số điện thoại')).toHaveValue('contact value')
})

it('validates register contract lengths but lets the backend validate contact format', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: true })
  const register = vi.spyOn(authService, 'register').mockResolvedValue(maker)
  renderAuthApp('/register')

  await user.type(await screen.findByLabelText('Tên đăng nhập'), 'abc')
  await user.type(screen.getByLabelText('Email hoặc số điện thoại'), 'x')
  await user.type(screen.getByLabelText('Mật khẩu'), '123456789012')
  await user.type(screen.getByLabelText('Nhập lại mật khẩu'), '123456789012')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(register).toHaveBeenCalledWith('abc', 'x', '123456789012')
})

it('returns to an internal protected deep link including query and hash after login', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me')
    .mockRejectedValueOnce(new AuthApiError(401, 'Authentication is required.'))
    .mockRejectedValueOnce(new AuthApiError(401, 'Authentication is required.'))
    .mockResolvedValue(maker)
  vi.spyOn(authService, 'login').mockResolvedValue(maker)
  renderAuthApp('/account?tab=history#round-2')

  await user.type(await screen.findByLabelText('Tên đăng nhập, mã người dùng hoặc email'), 'maker')
  await user.type(screen.getByLabelText('Mật khẩu'), 'local-secret')
  await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))

  expect(await screen.findByText('Location: /account?tab=history#round-2')).toBeVisible()
})

it('explains when Maker self-registration is disabled by server policy', async () => {
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  vi.spyOn(authService, 'getRegistrationConfig').mockResolvedValue({ registration_enabled: false })
  renderAuthApp('/register')

  expect(await screen.findByText(/Tự đăng ký hiện đang tắt/)).toBeVisible()
  expect(screen.queryByLabelText('Tên đăng nhập')).not.toBeInTheDocument()
})

it('keeps the current account session when logout cannot reach the server', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  vi.spyOn(authService, 'logout').mockRejectedValue(new AuthApiError(0, 'network error'))
  render(<MemoryRouter initialEntries={['/account']}><AuthProvider><Routes>
    <Route path="/account" element={<RequireAuth><AuthenticatedAccountPage /></RequireAuth>} />
    <Route path="/login" element={<p>Login page</p>} />
  </Routes></AuthProvider></MemoryRouter>)

  expect(await screen.findByText('Demo Maker')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Đăng xuất' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Phiên hiện tại vẫn được giữ')
  expect(screen.getByText('Demo Maker')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Thử đăng xuất lại' })).toBeEnabled()
})

it('shows separate contact fields, the empty phone state, and granted roles on the account page', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  render(<MemoryRouter initialEntries={['/account']}><AuthProvider><Routes>
    <Route path="/account" element={<RequireAuth><AuthenticatedAccountPage /></RequireAuth>} />
  </Routes></AuthProvider></MemoryRouter>)

  expect(await screen.findByText('Demo Maker')).toBeVisible()
  expect(screen.getByText('maker@example.com')).toBeVisible()
  expect(screen.getAllByText('Chưa cung cấp')).toHaveLength(1)
  expect(screen.getByText('Maker')).toBeVisible()
  expect(screen.queryByRole('link', { name: /Judge Demo|Demo/ })).not.toBeInTheDocument()
})

it('shows the account empty states when no contact details or roles are returned', async () => {
  vi.spyOn(authService, 'me').mockResolvedValue({ ...maker, email: null, phone: null, roles: [] })
  render(<MemoryRouter initialEntries={['/account']}><AuthProvider><Routes>
    <Route path="/account" element={<RequireAuth><AuthenticatedAccountPage /></RequireAuth>} />
  </Routes></AuthProvider></MemoryRouter>)

  expect(await screen.findAllByText('Chưa cung cấp')).toHaveLength(2)
  expect(screen.getByText('Chưa có vai trò được cấp')).toBeVisible()
})

it('clears the account session only after logout confirms HTTP 204', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockResolvedValue(maker)
  vi.spyOn(authService, 'logout').mockResolvedValue(undefined)
  render(<MemoryRouter initialEntries={['/account']}><AuthProvider><Routes>
    <Route path="/account" element={<RequireAuth><AuthenticatedAccountPage /></RequireAuth>} />
    <Route path="/login" element={<p>Login page</p>} />
  </Routes></AuthProvider></MemoryRouter>)

  expect(await screen.findByText('Demo Maker')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Đăng xuất' }))

  expect(await screen.findByText('Login page')).toBeVisible()
})
