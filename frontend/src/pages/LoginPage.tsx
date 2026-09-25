import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

type FieldErrors = {
  identifier?: string
  password?: string
}

function validateIdentifier(value: string) {
  const identifier = value.trim()
  if (!identifier) return 'Vui lòng nhập email hoặc tên người dùng.'
  if (identifier.includes('@') && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identifier)) {
    return 'Email chưa đúng định dạng.'
  }
  return ''
}

function validatePassword(value: string) {
  return value ? '' : 'Vui lòng nhập mật khẩu.'
}

export function LoginPage() {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState({ identifier: false, password: false })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState('')
  const submitTimer = useRef<number | null>(null)

  useEffect(() => () => {
    if (submitTimer.current !== null) window.clearTimeout(submitTimer.current)
  }, [])

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
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
    submitTimer.current = window.setTimeout(() => {
      setLoading(false)
      setFormError('Không thể đăng nhập lúc này. Vui lòng thử lại sau.')
    }, 650)
  }

  const identifierError = touched.identifier ? (errors.identifier ?? validateIdentifier(identifier)) : ''
  const passwordError = touched.password ? (errors.password ?? validatePassword(password)) : ''

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

          <form className="login-form" noValidate onSubmit={handleSubmit} aria-busy={loading}>
            <div className={identifierError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="login-identifier">Email hoặc tên người dùng</label>
              <div className="login-input-wrap">
                <Mail aria-hidden="true" />
                <input
                  id="login-identifier"
                  name="username"
                  type="text"
                  autoComplete="username"
                  placeholder="ten@congty.com"
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
