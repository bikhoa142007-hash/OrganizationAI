import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { RegisterForm } from '../components/auth/RegisterForm'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'

export function RegisterPage() {
  const { isAuthenticated, isLoading, register } = useAuth()
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit(username: string, contact: string, password: string) {
    setError('')
    setIsSubmitting(true)
    try {
      await register(username, contact, password)
      navigate('/login', {
        replace: true,
        state: { notice: 'Tạo tài khoản thành công. Đăng nhập bằng tên đăng nhập và mật khẩu của bạn.' },
      })
    } catch (requestError) {
      if (requestError instanceof AuthApiError && requestError.status === 0) {
        setError('Không thể kết nối đến dịch vụ đăng ký. Hãy kiểm tra kết nối rồi thử lại.')
      } else if (requestError instanceof AuthApiError && requestError.status === 409) {
        setError('Tên đăng nhập hoặc thông tin liên hệ đã được sử dụng.')
      } else if (requestError instanceof AuthApiError && requestError.status === 422) {
        setError('Vui lòng kiểm tra tên đăng nhập, email hoặc số điện thoại và mật khẩu.')
      } else if (requestError instanceof AuthApiError && requestError.status === 403) {
        setError('Hiện chưa thể tự đăng ký tài khoản. Vui lòng liên hệ quản trị viên.')
      } else if (requestError instanceof AuthApiError && requestError.status === 503) {
        setError('Dịch vụ đăng ký chưa được cấu hình. Vui lòng thử lại sau.')
      } else {
        setError('Tạo tài khoản chưa thành công. Hãy kiểm tra thông tin và thử lại.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) return <p role="status">Đang kiểm tra phiên đăng nhập…</p>
  if (isAuthenticated) return <Navigate to="/account" replace />

  return <main className="auth-page">
    <section className="auth-panel" aria-labelledby="register-heading">
      <h1 id="register-heading">Tạo tài khoản</h1>
      <p>Tài khoản tự đăng ký chỉ nhận quyền Maker. Đăng ký không tự đăng nhập.</p>
      <RegisterForm error={error} isLoading={isSubmitting} onSubmit={submit} />
      <p>Đã có tài khoản? <Link to="/login">Đăng nhập</Link></p>
    </section>
  </main>
}
