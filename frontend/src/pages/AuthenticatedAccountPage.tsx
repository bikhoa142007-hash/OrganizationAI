import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

function roleLabel(role: string) {
  if (role === 'MAKER') return 'Maker'
  if (role === 'CHECKER') return 'Checker'
  if (role === 'ADMIN') return 'Quản trị viên'
  return role
}

export function AuthenticatedAccountPage() {
  const { user, roles, logout } = useAuth()
  const [logoutError, setLogoutError] = useState('')
  const [logoutPending, setLogoutPending] = useState(false)

  async function signOut() {
    setLogoutError('')
    setLogoutPending(true)
    try {
      await logout()
    } catch {
      setLogoutError('Không thể xác nhận đăng xuất với máy chủ. Phiên hiện tại vẫn được giữ; hãy thử lại.')
    } finally {
      setLogoutPending(false)
    }
  }

  return <main className="auth-account auth-account-page" aria-labelledby="account-title">
    <header className="auth-account-heading">
      <p className="login-card-kicker">OrganizationAI</p>
      <h1 id="account-title">Tài khoản</h1>
      <p>Thông tin tài khoản và quyền truy cập hiện tại.</p>
    </header>

    <dl className="auth-account-details">
      <div><dt>Tên hiển thị</dt><dd>{user?.display_name || 'Chưa cung cấp'}</dd></div>
      <div><dt>Tên đăng nhập</dt><dd>{user?.username || 'Chưa cung cấp'}</dd></div>
      <div><dt>Mã người dùng</dt><dd>{user?.user_code || 'Chưa cung cấp'}</dd></div>
      <div><dt>Email</dt><dd>{user?.email || 'Chưa cung cấp'}</dd></div>
      <div><dt>Số điện thoại</dt><dd>{user?.phone || 'Chưa cung cấp'}</dd></div>
      <div><dt>Trạng thái</dt><dd><span className={`auth-account-status ${user?.status === 'ACTIVE' ? 'is-active' : 'is-disabled'}`}>
        {user?.status === 'ACTIVE' ? 'Đang hoạt động' : 'Đã vô hiệu hóa'}
      </span></dd></div>
      <div className="auth-account-role-row"><dt>Vai trò</dt><dd>
        {roles.length
          ? <ul className="auth-account-roles">{roles.map(role => <li key={role}>{roleLabel(role)}</li>)}</ul>
          : <span>Chưa có vai trò được cấp</span>}
      </dd></div>
    </dl>

    {logoutError && <p className="auth-account-error" role="alert">{logoutError}</p>}
    <div className="auth-account-actions">
      {roles.includes('MAKER') && <Link className="button button-secondary" to="/workflow/plans">Mở workspace Maker</Link>}
      {roles.includes('CHECKER') && <Link className="button button-secondary" to="/workflow/reviews">Mở workspace Checker</Link>}
      {roles.includes('ADMIN') && <Link className="button button-secondary" to="/workflow/plans">Mở danh sách kế hoạch quản trị (chỉ đọc)</Link>}
      <button
        className="button button-danger"
        type="button"
        disabled={logoutPending}
        aria-busy={logoutPending}
        onClick={() => { void signOut() }}
      >
        {logoutPending ? 'Đang đăng xuất…' : logoutError ? 'Thử đăng xuất lại' : 'Đăng xuất'}
      </button>
    </div>
  </main>
}
