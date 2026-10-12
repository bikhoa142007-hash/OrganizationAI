import { Bell, ClipboardCheck, Clock3, FileText, History, LayoutDashboard, LogOut, Settings2, UserRound, UsersRound } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
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
      setLogoutError('Không thể xác nhận đăng xuất với máy chủ. Phiên hiện tại vẫn được giữ; hãy thử lại.')
    } finally {
      setLogoutPending(false)
    }
  }

  return <div className="auth-workflow-shell">
    <header className="auth-workflow-header">
      <Link className="auth-workflow-brand" to="/workflow"><span>OA</span><strong>OrganizationAI<small>Không gian làm việc</small></strong></Link>
      <nav aria-label="Điều hướng không gian làm việc">
        <NavLink to="/workflow/dashboard"><LayoutDashboard aria-hidden="true" /> Tổng quan</NavLink>
        <NavLink to="/workflow/notifications"><Bell aria-hidden="true" /> Thông báo</NavLink>
        {(roles.includes('MAKER') || roles.includes('ADMIN')) && <NavLink to="/workflow/plans"><FileText aria-hidden="true" /> {roles.includes('ADMIN') ? 'Toàn bộ kế hoạch' : 'Kế hoạch của tôi'}</NavLink>}
        {roles.includes('CHECKER') && <NavLink to="/workflow/reviews"><ClipboardCheck aria-hidden="true" /> Hàng chờ duyệt</NavLink>}
        {roles.includes('ADMIN') && <NavLink to="/workflow/audit"><History aria-hidden="true" /> Nhật ký kiểm toán</NavLink>}
        {roles.includes('ADMIN') && <NavLink to="/workflow/employees"><UsersRound aria-hidden="true" /> Nhân viên</NavLink>}
        {roles.includes('ADMIN') && <NavLink to="/workflow/roles"><UsersRound aria-hidden="true" /> Vai trò</NavLink>}
        {roles.includes('ADMIN') && <NavLink to="/workflow/configuration"><Settings2 aria-hidden="true" /> Cấu hình phê duyệt</NavLink>}
        {roles.includes('ADMIN') && user?.effective_permissions?.includes('ADMIN_SLA_MANAGE') && <NavLink to="/workflow/sla"><Clock3 aria-hidden="true" /> Cấu hình SLA</NavLink>}
        <NavLink to="/account"><UserRound aria-hidden="true" /> Tài khoản</NavLink>
      </nav>
      <div className="auth-workflow-user"><span><UserRound aria-hidden="true" /> {user?.display_name}<small>{roles.join(', ') || 'Chưa có vai trò được cấp'}</small></span><button type="button" disabled={logoutPending} aria-busy={logoutPending} onClick={() => void signOut()}><LogOut aria-hidden="true" /> {logoutPending ? 'Đang đăng xuất…' : logoutError ? 'Thử đăng xuất lại' : 'Đăng xuất'}</button></div>
    </header>
    {logoutError && <p role="alert" className="auth-logout-error">{logoutError}</p>}
    <main className="auth-workflow-main"><Outlet /></main>
  </div>
}

export function AuthWorkflowPermissionGuard({
  role,
  permission,
  children,
}: { role: string; permission: string; children: ReactNode }) {
  const { roles, user } = useAuth()
  const location = useLocation()
  if (!roles.includes(role) || !user?.effective_permissions?.includes(permission)) {
    return <Navigate to="/access-denied" replace state={{ from: location }} />
  }
  return children
}
export function AuthWorkflowRoleGuard({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { roles: currentRoles } = useAuth()
  const location = useLocation()
  if (!roles.some(role => currentRoles.includes(role))) {
    return <Navigate to="/access-denied" replace state={{ from: location }} />
  }
  return children
}
