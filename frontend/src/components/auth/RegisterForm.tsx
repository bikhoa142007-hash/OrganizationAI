import { useState, type FormEvent } from 'react'

interface RegisterFormProps {
  error: string
  isLoading: boolean
  onSubmit: (username: string, contact: string, password: string) => void
}

export function RegisterForm({ error, isLoading, onSubmit }: RegisterFormProps) {
  const [username, setUsername] = useState('')
  const [contact, setContact] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [confirmationError, setConfirmationError] = useState('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirmation) {
      setConfirmationError('Mật khẩu xác nhận chưa khớp.')
      return
    }
    setConfirmationError('')
    onSubmit(username.trim(), contact.trim(), password)
  }

  return <form className="auth-form" onSubmit={submit} aria-busy={isLoading}>
    <label htmlFor="register-username">Tên đăng nhập</label>
    <input
      id="register-username"
      name="username"
      type="text"
      autoComplete="username"
      required
      minLength={3}
      maxLength={80}
      value={username}
      onChange={event => setUsername(event.target.value)}
      disabled={isLoading}
    />

    <label htmlFor="register-contact">Email hoặc số điện thoại quốc tế</label>
    <input
      id="register-contact"
      name="contact"
      type="text"
      autoComplete="email"
      aria-describedby="register-contact-hint"
      required
      maxLength={320}
      value={contact}
      onChange={event => setContact(event.target.value)}
      disabled={isLoading}
    />
    <small id="register-contact-hint">Số điện thoại cần có mã quốc gia, ví dụ +84901234567.</small>

    <label htmlFor="register-password">Mật khẩu</label>
    <input
      id="register-password"
      name="password"
      type="password"
      autoComplete="new-password"
      required
      minLength={12}
      maxLength={1024}
      value={password}
      onChange={event => setPassword(event.target.value)}
      disabled={isLoading}
    />

    <label htmlFor="register-confirmation">Xác nhận mật khẩu</label>
    <input
      id="register-confirmation"
      name="confirmation"
      type="password"
      autoComplete="new-password"
      required
      maxLength={1024}
      value={confirmation}
      onChange={event => setConfirmation(event.target.value)}
      disabled={isLoading}
    />

    {(error || confirmationError) &&
      <p className="auth-form__error" role="alert">{confirmationError || error}</p>}

    <button type="submit" disabled={isLoading}>
      {isLoading ? 'Đang tạo tài khoản…' : 'Đăng ký'}
    </button>
  </form>
}
