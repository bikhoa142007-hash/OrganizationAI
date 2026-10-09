import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { AuthApiError, authService } from '../services/auth'
import { StatePanel } from '../components/ui'
import { homeForRoles } from '../services/authNavigation'

type RegisterField = 'username' | 'contact' | 'password' | 'confirmation'
type RegisterErrors = Partial<Record<RegisterField, string>>
type RegisterTouched = Record<RegisterField, boolean>

function validateUsername(value: string) {
  const username = value.trim()
  if (!username) return 'Vui lòng nhập tên đăng nhập.'
  if (username.length < 3 || username.length > 80) return 'Tên đăng nhập cần có từ 3 đến 80 ký tự.'
  return ''
}

function validateContact(value: string) {
  const contact = value.trim()
  if (!contact) return 'Vui lòng nhập email hoặc số điện thoại.'
  if (contact.length > 320) return 'Thông tin liên hệ không được vượt quá 320 ký tự.'
  return ''
}

function validatePassword(value: string) {
  if (!value) return 'Vui lòng nhập mật khẩu.'
  if (value.length < 12) return 'Mật khẩu cần có ít nhất 12 ký tự.'
  if (value.length > 1024) return 'Mật khẩu không được vượt quá 1024 ký tự.'
  return ''
}

function validateConfirmation(value: string, password: string) {
  if (!value) return 'Vui lòng nhập lại mật khẩu.'
  if (value !== password) return 'Mật khẩu nhập lại chưa khớp.'
  return ''
}

function withCorrelation(message: string, reason: unknown) {
  return reason instanceof AuthApiError && reason.correlationId
    ? `${message} Mã tham chiếu: ${reason.correlationId}`
    : message
}

export function RegisterPage() {
  const { isAuthenticated, isLoading: sessionLoading, register, roles, sessionError, refresh } = useAuth()
  const navigate = useNavigate()
  const [registrationEnabled, setRegistrationEnabled] = useState<boolean | null>(null)
  const [configLoading, setConfigLoading] = useState(true)
  const [configError, setConfigError] = useState('')
  const [username, setUsername] = useState('')
  const [contact, setContact] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)
  const [touched, setTouched] = useState<RegisterTouched>({
    username: false, contact: false, password: false, confirmation: false,
  })
  const [errors, setErrors] = useState<RegisterErrors>({})
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState('')

  async function loadRegistrationConfig() {
    setConfigLoading(true)
    setConfigError('')
    try {
      const config = await authService.getRegistrationConfig()
      setRegistrationEnabled(config.registration_enabled)
    } catch {
      setConfigError('Không thể tải trạng thái đăng ký. Hãy thử lại khi dịch vụ khả dụng.')
    } finally {
      setConfigLoading(false)
    }
  }

  useEffect(() => { void loadRegistrationConfig() }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    setTouched({ username: true, contact: true, password: true, confirmation: true })

    const nextErrors: RegisterErrors = {
      username: validateUsername(username),
      contact: validateContact(contact),
      password: validatePassword(password),
      confirmation: validateConfirmation(confirmation, password),
    }
    setErrors(nextErrors)

    const firstInvalidField = (['username', 'contact', 'password', 'confirmation'] as const)
      .find(field => nextErrors[field])
    if (firstInvalidField) {
      document.getElementById(`register-${firstInvalidField}`)?.focus()
      return
    }

    setLoading(true)
    try {
      await register(username.trim(), contact.trim(), password)
      navigate('/login', {
        replace: true,
        state: { notice: 'Tạo tài khoản thành công. Đăng nhập bằng tên đăng nhập và mật khẩu của bạn.' },
      })
    } catch (reason) {
      if (reason instanceof AuthApiError && reason.status === 0) {
        setFormError(withCorrelation('Không thể kết nối đến dịch vụ đăng ký. Hãy kiểm tra kết nối rồi thử lại.', reason))
      } else if (reason instanceof AuthApiError && reason.status === 409) {
        setFormError(withCorrelation('Tên đăng nhập hoặc thông tin liên hệ đã được sử dụng.', reason))
      } else if (reason instanceof AuthApiError && reason.status === 422) {
        setFormError(withCorrelation('Vui lòng kiểm tra tên đăng nhập, thông tin liên hệ và mật khẩu.', reason))
      } else if (reason instanceof AuthApiError && reason.status === 403) {
        setFormError(withCorrelation('Hiện chưa thể tự đăng ký tài khoản. Vui lòng liên hệ quản trị viên.', reason))
      } else if (reason instanceof AuthApiError && reason.status === 429) {
        setFormError(withCorrelation('Có quá nhiều lần đăng ký từ thiết bị này. Vui lòng chờ trước khi thử lại.', reason))
      } else if (reason instanceof AuthApiError && reason.status === 503) {
        setFormError(withCorrelation('Dịch vụ đăng ký chưa được cấu hình. Vui lòng thử lại sau.', reason))
      } else {
        setFormError(withCorrelation('Tạo tài khoản chưa thành công. Hãy kiểm tra thông tin và thử lại.', reason))
      }
    } finally {
      setLoading(false)
    }
  }

  const usernameError = touched.username ? (errors.username ?? validateUsername(username)) : ''
  const contactError = touched.contact ? (errors.contact ?? validateContact(contact)) : ''
  const passwordError = touched.password ? (errors.password ?? validatePassword(password)) : ''
  const confirmationError = touched.confirmation
    ? (errors.confirmation ?? validateConfirmation(confirmation, password))
    : ''

  if (sessionLoading) return <p role="status">Đang kiểm tra phiên đăng nhập…</p>
  if (isAuthenticated) return <Navigate to={homeForRoles(roles)} replace />
  if (configLoading) return <p role="status">Đang kiểm tra trạng thái đăng ký…</p>
  if (configError) return <StatePanel kind="error" title="Không thể kiểm tra đăng ký" description={configError} action={<button type="button" onClick={() => void loadRegistrationConfig()}>Thử lại</button>} />
  if (!registrationEnabled) return <main className="login-page"><section className="login-panel"><div className="login-card">
    <h1>Đăng ký tài khoản</h1>
    <p role="status">Tự đăng ký hiện đang tắt. Vui lòng liên hệ quản trị viên OrganizationAI để được cấp tài khoản.</p>
    <p><Link to="/login">Quay lại đăng nhập</Link></p>
  </div></section></main>

  return (
    <main className="login-page register-page">
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
          <h1>Bắt đầu rõ ràng.<br />Làm việc tự tin.</h1>
          <p className="login-lede">Tạo thông tin truy cập để theo dõi kế hoạch, căn cứ đánh giá và các bước phê duyệt.</p>
        </div>
        <ol className="login-steps" aria-label="Các bước trong quy trình">
          <li><span>01</span><div><strong>Kế hoạch</strong><small>Thông tin tập trung</small></div></li>
          <li><span>02</span><div><strong>Đánh giá</strong><small>Căn cứ rõ ràng</small></div></li>
          <li><span>03</span><div><strong>Phê duyệt</strong><small>Đúng người phụ trách</small></div></li>
        </ol>
        <p className="login-story-footnote">
          <span className="login-footnote-mark"><ShieldCheck aria-hidden="true" /></span>
          Tài khoản tự đăng ký chỉ nhận vai trò Maker và không tự đăng nhập sau khi tạo.
        </p>
      </section>

      <section className="login-panel" aria-labelledby="register-title">
        <div className="login-card register-card">
          <header className="login-card-header">
            <p className="login-card-kicker">Tài khoản OrganizationAI</p>
            <h2 id="register-title">Tạo tài khoản</h2>
            <p>Điền thông tin để bắt đầu sử dụng OrganizationAI.</p>
          </header>

          {sessionError && <div className="login-form-message login-session-error" role="alert">
            <p>{sessionError} Bạn vẫn có thể tiếp tục đăng ký.</p>
            <button className="login-session-retry" type="button" onClick={() => void refresh()}>Thử kiểm tra phiên lại</button>
          </div>}

          <form className="login-form register-form" noValidate onSubmit={handleSubmit} aria-busy={loading}>
            <div className={usernameError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="register-username">Tên đăng nhập</label>
              <div className="login-input-wrap">
                <UserRound aria-hidden="true" />
                <input
                  id="register-username" name="username" type="text" autoComplete="username"
                  placeholder="Ví dụ: nguyenminh" maxLength={80} value={username}
                  aria-invalid={Boolean(usernameError)}
                  aria-describedby={usernameError ? 'register-username-error' : undefined}
                  disabled={loading}
                  onChange={event => {
                    const value = event.target.value
                    setUsername(value)
                    setFormError('')
                    if (touched.username) setErrors(previous => ({ ...previous, username: validateUsername(value) }))
                  }}
                  onBlur={() => setTouched(previous => ({ ...previous, username: true }))}
                />
              </div>
              {usernameError && <span className="login-field-message" id="register-username-error">{usernameError}</span>}
            </div>

            <div className={contactError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="register-contact">Email hoặc số điện thoại</label>
              <div className="login-input-wrap">
                <Mail aria-hidden="true" />
                <input
                  id="register-contact" name="contact" type="text" autoComplete="email"
                  placeholder="Email hoặc số điện thoại" maxLength={320} value={contact}
                  aria-invalid={Boolean(contactError)}
                  aria-describedby={contactError ? 'register-contact-error' : undefined}
                  disabled={loading}
                  onChange={event => {
                    const value = event.target.value
                    setContact(value)
                    setFormError('')
                    if (touched.contact) setErrors(previous => ({ ...previous, contact: validateContact(value) }))
                  }}
                  onBlur={() => setTouched(previous => ({ ...previous, contact: true }))}
                />
              </div>
              {contactError && <span className="login-field-message" id="register-contact-error">{contactError}</span>}
            </div>

            <div className={passwordError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="register-password">Mật khẩu</label>
              <div className="login-input-wrap">
                <LockKeyhole aria-hidden="true" />
                <input
                  id="register-password" name="new-password" type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password" placeholder="Tạo mật khẩu" maxLength={1024} value={password}
                  aria-invalid={Boolean(passwordError)}
                  aria-describedby={passwordError ? 'register-password-error' : 'register-password-hint'}
                  disabled={loading}
                  onChange={event => {
                    const value = event.target.value
                    setPassword(value)
                    setFormError('')
                    if (touched.password) setErrors(previous => ({ ...previous, password: validatePassword(value) }))
                    if (touched.confirmation) setErrors(previous => ({ ...previous, confirmation: validateConfirmation(confirmation, value) }))
                  }}
                  onBlur={() => setTouched(previous => ({ ...previous, password: true }))}
                />
                <button className="login-visibility-toggle" type="button" aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  aria-pressed={showPassword} disabled={loading} onClick={() => setShowPassword(value => !value)}>
                  {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </div>
              {passwordError
                ? <span className="login-field-message" id="register-password-error">{passwordError}</span>
                : <span className="register-field-hint" id="register-password-hint">Mật khẩu cần có ít nhất 12 ký tự.</span>}
            </div>

            <div className={confirmationError ? 'login-field login-field-error' : 'login-field'}>
              <label htmlFor="register-confirmation">Nhập lại mật khẩu</label>
              <div className="login-input-wrap">
                <LockKeyhole aria-hidden="true" />
                <input
                  id="register-confirmation" name="new-password-confirmation"
                  type={showConfirmation ? 'text' : 'password'} autoComplete="new-password"
                  placeholder="Nhập lại mật khẩu" maxLength={1024} value={confirmation}
                  aria-invalid={Boolean(confirmationError)}
                  aria-describedby={confirmationError ? 'register-confirmation-error' : undefined}
                  disabled={loading}
                  onChange={event => {
                    const value = event.target.value
                    setConfirmation(value)
                    setFormError('')
                    if (touched.confirmation) setErrors(previous => ({ ...previous, confirmation: validateConfirmation(value, password) }))
                  }}
                  onBlur={() => setTouched(previous => ({ ...previous, confirmation: true }))}
                />
                <button className="login-visibility-toggle" type="button"
                  aria-label={showConfirmation ? 'Ẩn mật khẩu nhập lại' : 'Hiện mật khẩu nhập lại'}
                  aria-pressed={showConfirmation} disabled={loading}
                  onClick={() => setShowConfirmation(value => !value)}>
                  {showConfirmation ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </div>
              {confirmationError && <span className="login-field-message" id="register-confirmation-error">{confirmationError}</span>}
            </div>

            {formError && <p className="login-form-message" role="alert">{formError}</p>}
            <button className="login-submit" type="submit" disabled={loading}>
              {loading ? <><span className="login-spinner" aria-hidden="true" /> Đang tạo tài khoản…</> : <>Đăng ký <ArrowRight aria-hidden="true" /></>}
            </button>
          </form>

          <p className="register-auth-switch">Đã có tài khoản? <Link to="/login">Đăng nhập</Link></p>
        </div>
        <p className="login-panel-footer">OrganizationAI <span aria-hidden="true">·</span> Quản lý phê duyệt marketing</p>
      </section>
    </main>
  )
}
