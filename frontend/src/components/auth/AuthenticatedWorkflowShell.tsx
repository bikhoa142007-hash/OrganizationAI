import { ClipboardCheck, FileText, History, LogOut, UserRound } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export function AuthenticatedWorkflowShell() {
  const { user, roles, logout } = useAuth()
  const navigate = useNavigate()
  const [logoutError, setLogoutError] = useState('')
  const [logoutPending, setLogoutPending] = useState(false)

  async function signOut() {
    setLogoutError('')
    setLogoutPending(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch {
      setLogoutError('Không thể đăng xuất vì dịch vụ chưa phản hồi. Phiên hiện tại vẫn được giữ; hãy thử lại.')
    } finally {
      setLogoutPending(false)
    }
  }

  return <div className="auth-workflow-shell">
    <header className="auth-workflow-header">
      <Link className="auth-workflow-brand" to="/workflow/plans"><span>OA</span><strong>OrganizationAI<small>Authenticated workspace</small></strong></Link>
      <nav aria-label="Authenticated workflow">
        {(roles.includes('MAKER') || roles.includes('ADMIN')) && <NavLink to="/workflow/plans"><FileText /> {roles.includes('ADMIN') ? 'Toàn bộ kế hoạch' : 'Kế hoạch của tôi'}</NavLink>}
        {roles.includes('CHECKER') && <NavLink to="/workflow/reviews"><ClipboardCheck /> Hàng chờ duyệt</NavLink>}
        {roles.includes('ADMIN') && <NavLink to="/workflow/audit"><History /> Nhật ký kiểm toán</NavLink>}
      </nav>
      <div className="auth-workflow-user"><span><UserRound /> {user?.display_name}<small>{roles.join(', ')}</small></span><button type="button" disabled={logoutPending} onClick={() => void signOut()}><LogOut /> {logoutPending ? 'Đang đăng xuất…' : 'Đăng xuất'}</button></div>
    </header>
    {logoutError && <p role="alert" className="auth-logout-error">{logoutError}</p>}
    <main className="auth-workflow-main"><Outlet /></main>
  </div>
}

export function AuthWorkflowRoleGuard({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { roles: currentRoles } = useAuth()
  if (!roles.some(role => currentRoles.includes(role))) {
    return <section className="auth-workflow-panel" role="alert"><h1>Không có quyền truy cập</h1><p>Tài khoản này không có vai trò phù hợp với trang workflow.</p><Link to="/account">Quay lại tài khoản</Link></section>
  }
  return children
}
