import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
  await user.type(screen.getByLabelText('Email hoặc số điện thoại quốc tế'), 'new@example.com')
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
  await user.type(screen.getByLabelText('Email hoặc số điện thoại quốc tế'), 'new@example.com')
  await user.type(screen.getByLabelText('Mật khẩu'), 'New-local-password-123')
  await user.type(screen.getByLabelText('Nhập lại mật khẩu'), 'different-password')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(await screen.findByText('Mật khẩu nhập lại chưa khớp.')).toBeVisible()
  expect(screen.getByLabelText('Nhập lại mật khẩu')).toHaveAttribute('aria-invalid', 'true')
  expect(register).not.toHaveBeenCalled()
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
    <Route path="/account" element={<AuthenticatedAccountPage />} />
    <Route path="/login" element={<p>Login page</p>} />
  </Routes></AuthProvider></MemoryRouter>)

  expect(await screen.findByText('Tên hiển thị: Demo Maker')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Đăng xuất' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Phiên hiện tại vẫn được giữ')
  expect(screen.getByText('Tên hiển thị: Demo Maker')).toBeVisible()
})
