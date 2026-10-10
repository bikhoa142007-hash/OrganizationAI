import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { authService } from '../services/auth'

export function AccountHandoverPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [complete, setComplete] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (token && window.location.hash) {
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`)
    }
  }, [token])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!token) { setError('Liên kết không có token hợp lệ. Hãy yêu cầu Admin gửi liên kết mới.'); return }
    if (password.length < 12) { setError('Mật khẩu cần có ít nhất 12 ký tự.'); return }
    if (password !== confirmation) { setError('Hai mật khẩu chưa khớp.'); return }
    setSaving(true)
    try {
      await authService.completeAccountHandover(token, password)
      setComplete(true)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không thể cập nhật mật khẩu.')
    } finally {
      setSaving(false)
    }
  }

  return <main className="auth-account" aria-labelledby="handover-title">
    <p className="login-card-kicker">OrganizationAI</p>
    <h1 id="handover-title">{complete ? 'Mật khẩu đã được cập nhật' : 'Kích hoạt tài khoản hoặc đặt lại mật khẩu'}</h1>
    {complete ? <><p>Bạn có thể đăng nhập bằng mật khẩu vừa đặt.</p><Link className="button button-primary" to="/login">Đăng nhập</Link></>
      : <form className="auth-form" onSubmit={event => void submit(event)}>
        <p>Đặt mật khẩu do chính bạn quản lý. Liên kết chỉ dùng một lần và có thời hạn.</p>
        <label htmlFor="handover-password">Mật khẩu mới<input id="handover-password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={event => setPassword(event.target.value)} /></label>
        <label htmlFor="handover-confirmation">Nhập lại mật khẩu<input id="handover-confirmation" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
        {error && <p role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={saving}>{saving ? 'Đang cập nhật…' : 'Lưu mật khẩu'}</button>
      </form>}
  </main>
}
