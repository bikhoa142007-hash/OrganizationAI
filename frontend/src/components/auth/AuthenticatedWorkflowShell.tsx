import { Bell, ChevronDown, ClipboardCheck, Clock3, FileText, FlaskConical, History, LayoutDashboard, LogOut, Menu, Settings2, UserRound, UsersRound, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

export function AuthenticatedWorkflowShell() {
  const { user, roles, logout } = useAuth()
  const permissions = user?.effective_permissions ?? []
  const navigate = useNavigate()
  const location = useLocation()
  const [logoutError, setLogoutError] = useState('')
  const [logoutPending, setLogoutPending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const userMenuRef = useRef<HTMLDetailsElement>(null)

  useEffect(() => {
    if (sidebarOpen) closeSidebar()
    if (userMenuRef.current) userMenuRef.current.open = false
  }, [location.pathname])

  useEffect(() => {
    if (!sidebarOpen) return

    sidebarRef.current?.querySelector<HTMLElement>('.auth-workflow-navigation a')?.focus()

    function handleDrawerKeys(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        closeSidebar()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [])
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const focusIsOutsideDrawer = !sidebarRef.current?.contains(document.activeElement)
      if (event.shiftKey && (document.activeElement === first || focusIsOutsideDrawer)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || focusIsOutsideDrawer)) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleDrawerKeys)
    return () => document.removeEventListener('keydown', handleDrawerKeys)
  }, [sidebarOpen])

  function closeSidebar() {
    setSidebarOpen(false)
    menuButtonRef.current?.focus()
  }

  async function signOut() {
    setLogoutError('')
    setLogoutPending(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch {
      setLogoutError('Chưa thể đăng xuất. Phiên hiện tại vẫn đang hoạt động; hãy thử lại.')
    } finally {
      setLogoutPending(false)
    }
  }

  const displayName = user?.display_name?.trim() || 'Tài khoản'
  const userInitial = displayName.charAt(0).toLocaleUpperCase() || 'T'

  return <div className="auth-workflow-shell">
    <aside ref={sidebarRef} id="auth-workflow-sidebar" className={`auth-workflow-sidebar${sidebarOpen ? ' is-open' : ''}`}>
      <Link className="auth-workflow-brand" to="/workflow">
        <span aria-hidden="true">OA</span>
        <strong>OrganizationAI<small>Không gian làm việc</small></strong>
      </Link>
      <nav className="auth-workflow-navigation" aria-label="Điều hướng không gian làm việc">
        <NavLink to="/workflow/dashboard"><span className="auth-workflow-nav-icon"><LayoutDashboard aria-hidden="true" /></span><span>Tổng quan</span></NavLink>
        {roles.includes('ADMIN') && <NavLink to="/workflow/verify"><span className="auth-workflow-nav-icon"><FlaskConical aria-hidden="true" /></span><span>Verify</span></NavLink>}
        <NavLink to="/workflow/notifications"><span className="auth-workflow-nav-icon"><Bell aria-hidden="true" /></span><span>Thông báo</span></NavLink>
        {(roles.includes('MAKER') || roles.includes('ADMIN')) && <NavLink to="/workflow/plans"><span className="auth-workflow-nav-icon"><FileText aria-hidden="true" /></span><span>{roles.includes('ADMIN') ? 'Toàn bộ kế hoạch' : 'Kế hoạch của tôi'}</span></NavLink>}
        {roles.includes('CHECKER') && <NavLink to="/workflow/reviews"><span className="auth-workflow-nav-icon"><ClipboardCheck aria-hidden="true" /></span><span>Hàng chờ duyệt</span></NavLink>}
        {roles.includes('ADMIN') && permissions.includes('ADMIN_AUDIT_READ') && <NavLink to="/workflow/audit"><span className="auth-workflow-nav-icon"><History aria-hidden="true" /></span><span>Nhật ký kiểm toán</span></NavLink>}
        {roles.includes('ADMIN') && permissions.includes('ADMIN_EMPLOYEE_MANAGE') && <NavLink to="/workflow/employees"><span className="auth-workflow-nav-icon"><UsersRound aria-hidden="true" /></span><span>Nhân viên</span></NavLink>}
        {roles.includes('ADMIN') && permissions.includes('ADMIN_ROLE_MANAGE') && <NavLink to="/workflow/roles"><span className="auth-workflow-nav-icon"><UsersRound aria-hidden="true" /></span><span>Vai trò</span></NavLink>}
        {roles.includes('ADMIN') && <NavLink to="/workflow/configuration"><span className="auth-workflow-nav-icon"><Settings2 aria-hidden="true" /></span><span>Cấu hình phê duyệt</span></NavLink>}
        {roles.includes('ADMIN') && user?.effective_permissions?.includes('ADMIN_SLA_MANAGE') && <NavLink to="/workflow/sla"><span className="auth-workflow-nav-icon"><Clock3 aria-hidden="true" /></span><span>Cấu hình SLA</span></NavLink>}
        <NavLink to="/account"><span className="auth-workflow-nav-icon"><UserRound aria-hidden="true" /></span><span>Tài khoản</span></NavLink>
      </nav>
    </aside>

    {sidebarOpen && <button className="auth-workflow-sidebar-scrim" type="button" aria-label="Đóng menu điều hướng" onClick={closeSidebar} />}

    <div className="auth-workflow-workspace">
      <header className="auth-workflow-topbar">
        <button
          ref={menuButtonRef}
          className="auth-workflow-menu-toggle"
          type="button"
          aria-label={sidebarOpen ? 'Đóng menu điều hướng' : 'Mở menu điều hướng'}
          aria-expanded={sidebarOpen}
          aria-controls="auth-workflow-sidebar"
          onClick={() => setSidebarOpen(open => !open)}
        >
          {sidebarOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>

        <div className="auth-workflow-topbar-actions">
          <NavLink className="auth-workflow-notification-link" to="/workflow/notifications" aria-label="Mở trang Thông báo">
            <Bell aria-hidden="true" />
          </NavLink>
          <details ref={userMenuRef} className="auth-workflow-user-menu">
            <summary aria-label={`${displayName}, ${roles.join(', ') || 'Chưa có vai trò được cấp'}`}>
              <span className="auth-workflow-user-avatar" aria-hidden="true">{userInitial}</span>
              <span className="auth-workflow-user-copy">
                <strong>{displayName}</strong>
                <small>{roles.join(', ') || 'Chưa có vai trò được cấp'}</small>
              </span>
              <ChevronDown className="auth-workflow-user-chevron" aria-hidden="true" />
            </summary>
            <div className="auth-workflow-user-menu-panel">
              <button type="button" disabled={logoutPending} aria-busy={logoutPending} onClick={() => void signOut()}>
                <LogOut aria-hidden="true" /> {logoutPending ? 'Đang đăng xuất…' : logoutError ? 'Thử đăng xuất lại' : 'Đăng xuất'}
              </button>
            </div>
          </details>
        </div>
      </header>

      {logoutError && <p role="alert" className="auth-logout-error">{logoutError}</p>}
      <main className="auth-workflow-main"><Outlet /></main>
    </div>
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
