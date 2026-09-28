import { ClipboardCheck, FileText, LogOut, UserRound } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export function AuthenticatedWorkflowShell() {
  const { user, roles, logout } = useAuth()
  const navigate = useNavigate()

  async function signOut() {
    await logout()
    navigate('/login', { replace: true })
  }

  return <div className="auth-workflow-shell">
    <header className="auth-workflow-header">
      <Link className="auth-workflow-brand" to="/workflow/plans"><span>OA</span><strong>OrganizationAI<small>Authenticated workspace</small></strong></Link>
      <nav aria-label="Authenticated workflow">
        {roles.includes('MAKER') && <NavLink to="/workflow/plans"><FileText /> Kế hoạch của tôi</NavLink>}
        {roles.includes('CHECKER') && <NavLink to="/workflow/reviews"><ClipboardCheck /> Hàng chờ duyệt</NavLink>}
      </nav>
      <div className="auth-workflow-user"><span><UserRound /> {user?.display_name}<small>{roles.join(', ')}</small></span><button type="button" onClick={() => void signOut()}><LogOut /> Đăng xuất</button></div>
    </header>
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
