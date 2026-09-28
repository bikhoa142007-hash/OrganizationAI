import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { LoginForm } from '../components/auth/LoginForm'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'

function safeReturnPath(state: unknown): string {
  if (!state || typeof state !== 'object' || !('from' in state) || typeof state.from !== 'string') {
    return '/account'
  }
  return state.from.startsWith('/') && !state.from.startsWith('//') ? state.from : '/account'
}

export function LoginPage() {
  const { isAuthenticated, isLoading, login } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit(identifier: string, password: string, rememberMe: boolean) {
    setError('')
    setIsSubmitting(true)
    try {
      await login(identifier, password, rememberMe)
      navigate(safeReturnPath(location.state), { replace: true })
    } catch (requestError) {
      if (requestError instanceof AuthApiError && requestError.status === 0) {
        setError('Không thể kết nối đến dịch vụ đăng nhập. Hãy kiểm tra kết nối rồi thử lại.')
      } else if (requestError instanceof AuthApiError && requestError.status === 401) {
        setError('Thông tin đăng nhập không chính xác hoặc tài khoản đã bị vô hiệu hóa.')
      } else if (requestError instanceof AuthApiError && requestError.status === 503) {
        setError('Dịch vụ đăng nhập chưa được cấu hình. Vui lòng thử lại sau.')
      } else {
        setError('Đăng nhập chưa thành công. Hãy kiểm tra thông tin và thử lại.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) return <p role="status">Đang kiểm tra phiên đăng nhập…</p>
  if (isAuthenticated) return <Navigate to={safeReturnPath(location.state)} replace />

  return <main className="auth-page">
    <section className="auth-panel" aria-labelledby="login-heading">
      <h1 id="login-heading">Đăng nhập</h1>
      <p>Sử dụng tài khoản OrganizationAI của bạn.</p>
      {location.state && typeof location.state === 'object' && 'notice' in location.state
        && typeof location.state.notice === 'string'
        && <p role="status">{location.state.notice}</p>}
      <LoginForm error={error} isLoading={isSubmitting} onSubmit={submit} />
      <p>Chưa có tài khoản? <Link to="/register">Đăng ký tài khoản Maker</Link></p>
    </section>
  </main>
}
