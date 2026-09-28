import { afterEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from '../context/AuthContext'
import { RequireAuth } from '../components/auth/RequireAuth'
import { LoginPage } from './LoginPage'
import { RegisterPage } from './RegisterPage'
import { authService, AuthApiError } from '../services/auth'

const maker = {
  id: 'user-1', user_code: 'USR-000001', username: 'maker', email: 'maker@example.com',
  phone: null, display_name: 'Demo Maker', status: 'ACTIVE' as const, roles: ['MAKER'],
}

function AccountPage() {
  const { user, roles, logout } = useAuth()
  return <main>
    <h1>OrganizationAI</h1>
    <p>Logged in as: {user?.display_name}</p>
    <p>Roles: {roles.join(', ')}</p>
    <button onClick={() => void logout()}>Log out</button>
  </main>
}

function renderAuthApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/account" element={<RequireAuth><AccountPage /></RequireAuth>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

it('renders labeled login inputs and submits user code and password through the auth service', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
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

  expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeVisible()
  expect(screen.getByLabelText('Tên đăng nhập, mã người dùng hoặc email')).toBeVisible()
})

it('disables the form while the login request is pending', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
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
  const register = vi.spyOn(authService, 'register').mockResolvedValue(maker)
  renderAuthApp('/register')

  await user.type(await screen.findByLabelText('Tên đăng nhập'), 'new.maker')
  await user.type(screen.getByLabelText('Email hoặc số điện thoại quốc tế'), 'new@example.com')
  await user.type(screen.getByLabelText('Mật khẩu'), 'New-local-password-123')
  await user.type(screen.getByLabelText('Xác nhận mật khẩu'), 'New-local-password-123')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(register).toHaveBeenCalledWith('new.maker', 'new@example.com', 'New-local-password-123')
  expect(await screen.findByRole('heading', { name: 'Đăng nhập' })).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('Tạo tài khoản thành công')
})

it('rejects mismatched password confirmation before making a registration request', async () => {
  const user = userEvent.setup()
  vi.spyOn(authService, 'me').mockRejectedValue(new AuthApiError(401, 'Authentication is required.'))
  const register = vi.spyOn(authService, 'register')
  renderAuthApp('/register')

  await user.type(await screen.findByLabelText('Tên đăng nhập'), 'new.maker')
  await user.type(screen.getByLabelText('Email hoặc số điện thoại quốc tế'), 'new@example.com')
  await user.type(screen.getByLabelText('Mật khẩu'), 'New-local-password-123')
  await user.type(screen.getByLabelText('Xác nhận mật khẩu'), 'different-password')
  await user.click(screen.getByRole('button', { name: 'Đăng ký' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Mật khẩu xác nhận chưa khớp.')
  expect(register).not.toHaveBeenCalled()
})
