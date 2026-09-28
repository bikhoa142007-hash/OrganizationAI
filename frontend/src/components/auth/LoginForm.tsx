import { useState, type FormEvent } from 'react'

interface LoginFormProps {
  error: string
  isLoading: boolean
  onSubmit: (identifier: string, password: string, rememberMe: boolean) => void
}

export function LoginForm({ error, isLoading, onSubmit }: LoginFormProps) {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit(identifier.trim(), password, rememberMe)
  }

  return <form className="auth-form" onSubmit={submit} aria-busy={isLoading}>
    <label htmlFor="login-identifier">Tên đăng nhập, mã người dùng hoặc email</label>
    <input
      id="login-identifier"
      name="identifier"
      type="text"
      autoComplete="username"
      required
      maxLength={320}
      value={identifier}
      onChange={event => setIdentifier(event.target.value)}
      disabled={isLoading}
    />

    <label htmlFor="login-password">Mật khẩu</label>
    <input
      id="login-password"
      name="password"
      type="password"
      autoComplete="current-password"
      required
      maxLength={1024}
      value={password}
      onChange={event => setPassword(event.target.value)}
      disabled={isLoading}
    />

    <label className="auth-form__remember" htmlFor="login-remember">
      <input
        id="login-remember"
        name="rememberMe"
        type="checkbox"
        checked={rememberMe}
        onChange={event => setRememberMe(event.target.checked)}
        disabled={isLoading}
      />
      Ghi nhớ trên thiết bị này
    </label>

    {error && <p className="auth-form__error" role="alert">{error}</p>}

    <button type="submit" disabled={isLoading}>
      {isLoading ? 'Đang đăng nhập…' : 'Đăng nhập'}
    </button>
  </form>
}
