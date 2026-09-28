import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'

type FieldErrors = { identifier?: string; password?: string }

function validateIdentifier(value: string) {
  const identifier = value.trim()
  if (!identifier) return 'Vui lòng nhập email, tên đăng nhập hoặc mã người dùng.'
  if (identifier.includes('@') && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identifier)) {
    return 'Email chưa đúng định dạng.'
  }
  return ''
}

function validatePassword(value: string) {
  return value ? '' : 'Vui lòng nhập mật khẩu.'
}

function safeReturnPath(state: unknown): string {
  if (!state || typeof state !== 'object' || !('from' in state) || typeof state.from !== 'string') {
    return '/account'
  }
  return state.from.startsWith('/') && !state.from.startsWith('//') ? state.from : '/account'
}

export function LoginPage() {
  const { isAuthenticated, isLoading: sessionLoading, login } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState({ identifier: false, password: false })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    setTouched({ identifier: true, password: true })

    const nextErrors = {
      identifier: validateIdentifier(identifier),
      password: validatePassword(password),
    }
    setErrors(nextErrors)

    if (nextErrors.identifier || nextErrors.password) {
      const firstInvalidField = nextErrors.identifier ? 'login-identifier' : 'login-password'
      document.getElementById(firstInvalidField)?.focus()
      return
    }

    setLoading(true)
    try {
      await login(identifier.trim(), password, remember)
      navigate(safeReturnPath(location.state), { replace: true })
    } catch (reason) {
      if (reason instanceof AuthApiError && reason.status === 0) {
        setFormError('Không thể kết nối đến dịch vụ đăng nhập. Hãy kiểm tra kết nối rồi thử lại.')
      } else if (reason instanceof AuthApiError && reason.status === 401) {
        setFormError('Thông tin đăng nhập không chính xác hoặc tài khoản đã bị vô hiệu hóa.')
      } else if (reason instanceof AuthApiError && reason.status === 503) {
        setFormError('Dịch vụ đăng nhập chưa được cấu hình. Vui lòng thử lại sau.')
      } else {
        setFormError('Đăng nhập chưa thành công. Hãy kiểm tra thông tin và thử lại.')
      }
    } finally {
      setLoading(false)
    }
  }

  const identifierError = touched.identifier ? (errors.identifier ?? validateIdentifier(identifier)) : ''
  const passwordError = touched.password ? (errors.password ?? validatePassword(password)) : ''
  const notice = location.state && typeof location.state === 'object'
    && 'notice' in location.state && typeof location.state.notice === 'string'
    ? location.state.notice
    : ''

  if (sessionLoading) return <p role="status">Đang kiểm tra phiên đăng nhập…</p>
  if (isAuthenticated) return <Navigate to={safeReturnPath(location.state)} replace />

  return (
    <main className="login-page">
      <section className="login-story" aria-label="Giới thiệu OrganizationAI">
        <div className="login-brand">
          <span className="brand-mark"><ShieldCheck aria-hidden="true" /></span>
          <span className="login-brand-copy">
            <strong>OrganizationAI</strong>
            <small>Quản lý phê duyệt marketing</small>
          </span>
        </div>

        <div className="login-story-copy">
          <p className="login-eyebrow"><span aria-hidden="true" /> Nền tảng phê duyệt marketing</p>
          <h1>Rõ từng bước.<br />Vững mỗi quyết định.</h1>
          <p className="login-lede">
            Theo dõi kế hoạch, kết quả đánh giá và các bước phê duyệt trong cùng một không gian làm việc.
          </p>
        </div>

        <ol className="login-steps" aria-label="Các bước trong quy trình">
          <li><span>01</span><div><strong>Kế hoạch</strong><small>Thông tin tập trung</small></div></li>
          <li><span>02</span><div><strong>Đánh giá</strong><small>Căn cứ rõ ràng</small></div></li>
          <li><span>03</span><div><strong>Phê duyệt</strong><small>Đúng người phụ trách</small></div></li>
        </ol>

        <p className="login-story-footnote">
          <span className="login-footnote-mark"><ShieldCheck aria-hidden="true" /></span>
          Trạng thái và lịch sử xử lý được trình bày minh bạch theo từng kế hoạch.
        </p>
      </section>

      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-card">
          <header className="login-card-header">
            <p className="login-card-kicker">Không gian làm việc</p>
            <h2 id="login-title">Chào mừng trở lại</h2>
            <p>Đăng nhập bằng tài khoản OrganizationAI của bạn.</p>
          </header>

          {notice && <p className="login-form-message" role="status">{notice}</p>}

          <form className="login-form" noValidate onSubmit={handleSubmit} aria-busy={loading}>
            <div className={identifierError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="login-identifier">Tên đăng nhập, mã người dùng hoặc email</label>
              <div className="login-input-wrap">
                <Mail aria-hidden="true" />
                <input
                  id="login-identifier"
                  name="identifier"
                  type="text"
                  autoComplete="username"
                  placeholder="maker, USR-000001 hoặc ten@congty.com"
                  maxLength={320}
                  value={identifier}
                  aria-invalid={Boolean(identifierError)}
                  aria-describedby={identifierError ? 'login-identifier-error' : undefined}
                  disabled={loading}
                  onChange={event => {
                    const value = event.target.value
                    setIdentifier(value)
                    setFormError('')
                    if (touched.identifier) setErrors(previous => ({ ...previous, identifier: validateIdentifier(value) }))
                  }}
                  onBlur={() => setTouched(previous => ({ ...previous, identifier: true }))}
                />
              </div>
              {identifierError && <span className="login-field-message" id="login-identifier-error">{identifierError}</span>}
            </div>

            <div className={passwordError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="login-password">Mật khẩu</label>
              <div className="login-input-wrap">
                <LockKeyhole aria-hidden="true" />
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Nhập mật khẩu"
                  maxLength={1024}
                  value={password}
                  aria-invalid={Boolean(passwordError)}
                  aria-describedby={passwordError ? 'login-password-error' : undefined}
                  disabled={loading}
                  onChange={event => {
                    const value = event.target.value
                    setPassword(value)
                    setFormError('')
                    if (touched.password) setErrors(previous => ({ ...previous, password: validatePassword(value) }))
                  }}
                  onBlur={() => setTouched(previous => ({ ...previous, password: true }))}
                />
                <button
                  className="login-visibility-toggle"
                  type="button"
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  aria-pressed={showPassword}
                  disabled={loading}
                  onClick={() => setShowPassword(value => !value)}
                >
                  {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </div>
              {passwordError && <span className="login-field-message" id="login-password-error">{passwordError}</span>}
            </div>

            <label className="login-remember">
              <input type="checkbox" checked={remember} disabled={loading} onChange={event => setRemember(event.target.checked)} />
              <span className="login-checkbox" aria-hidden="true" />
              <span>Ghi nhớ trên thiết bị này</span>
            </label>

            {formError && <p className="login-form-message" role="alert">{formError}</p>}

            <button className="login-submit" type="submit" disabled={loading}>
              {loading ? <><span className="login-spinner" aria-hidden="true" /> Đang đăng nhập…</> : <>Đăng nhập <ArrowRight aria-hidden="true" /></>}
            </button>
          </form>

          <p className="register-auth-switch login-auth-switch">Chưa có tài khoản? <Link to="/register">Đăng ký</Link></p>
        </div>

        <p className="login-panel-footer">OrganizationAI <span aria-hidden="true">·</span> Quản lý phê duyệt marketing</p>
      </section>
    </main>
  )
}
