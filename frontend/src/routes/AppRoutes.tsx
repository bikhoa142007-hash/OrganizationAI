import type { ReactNode } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from '../components/AppShell'
import { AuthenticatedWorkflowShell, AuthWorkflowRoleGuard } from '../components/auth/AuthenticatedWorkflowShell'
import { RequireAuth } from '../components/auth/RequireAuth'
import { StatePanel } from '../components/ui'
import { AuthenticatedAccountPage } from '../pages/AuthenticatedAccountPage'
import { AuthenticatedPlansPage } from '../pages/AuthenticatedPlansPage'
import { AuthenticatedWorkflowDetailPage } from '../pages/AuthenticatedWorkflowDetailPage'
import { AuthenticatedWorkflowFormPage } from '../pages/AuthenticatedWorkflowFormPage'
import { AuditTimelinePage } from '../pages/AuditTimelinePage'
import { LandingPage } from '../pages/LandingPage'
import { LoginPage } from '../pages/LoginPage'
import { PlanDetailPage } from '../pages/PlanDetailPage'
import { PlanFormPage } from '../pages/PlanFormPage'
import { PlansPage } from '../pages/PlansPage'
import { PolicyPage } from '../pages/PolicyPage'
import { ProcessingPage } from '../pages/ProcessingPage'
import { RegisterPage } from '../pages/RegisterPage'
import { ResultPage } from '../pages/ResultPage'
import { ReviewQueuePage } from '../pages/ReviewQueuePage'
import { VerifyDashboardPage } from '../pages/VerifyDashboardPage'
import { useSession } from '../services/SessionProvider'
import { useAuth } from '../context/AuthContext'
import { homeForRoles } from '../services/authNavigation'
import { isDemoEnabled } from '../services/apiBaseUrl'

export function AppRoutes() {
  return <Routes>
    <Route path="/" element={<AuthEntryPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/register" element={<RegisterPage />} />
    <Route path="/account" element={<RequireAuth><AuthenticatedAccountPage /></RequireAuth>} />
    <Route path="/access-denied" element={<RequireAuth><AccessDeniedPage /></RequireAuth>} />
    <Route path="/workflow" element={<RequireAuth><AuthenticatedWorkflowShell /></RequireAuth>}>
      <Route index element={<RoleHomePage />} />
      <Route path="plans" element={<AuthWorkflowRoleGuard roles={['MAKER']}><AuthenticatedPlansPage /></AuthWorkflowRoleGuard>} />
      <Route path="plans/new" element={<AuthWorkflowRoleGuard roles={['MAKER']}><AuthenticatedWorkflowFormPage /></AuthWorkflowRoleGuard>} />
      <Route path="plans/:planId" element={<AuthWorkflowRoleGuard roles={['MAKER', 'CHECKER']}><AuthenticatedWorkflowDetailPage /></AuthWorkflowRoleGuard>} />
      <Route path="plans/:planId/edit" element={<AuthWorkflowRoleGuard roles={['MAKER']}><AuthenticatedWorkflowFormPage /></AuthWorkflowRoleGuard>} />
      <Route path="reviews" element={<AuthWorkflowRoleGuard roles={['CHECKER']}><AuthenticatedPlansPage reviews /></AuthWorkflowRoleGuard>} />
    </Route>

    <Route path="/demo" element={isDemoEnabled() ? <AppShell /> : <Navigate to="/" replace />}>
      <Route index element={<LandingPage />} />
      <Route path="plans" element={<PlansPage />} />
      <Route path="plans/:planId" element={<PlanDetailPage />} />
      <Route path="plans/:planId/edit" element={<RoleGuard role="MAKER"><PlanFormPage key="edit" /></RoleGuard>} />
      <Route path="plans/new" element={<RoleGuard role="MAKER"><PlanFormPage key="new" /></RoleGuard>} />
      <Route path="plans/processing" element={<ProcessingPage />} />
      <Route path="plans/:planId/processing" element={<ProcessingPage />} />
      <Route path="plans/result" element={<ResultPage />} />
      <Route path="plans/:planId/result" element={<ResultPage />} />
      <Route path="review" element={<RoleGuard role="CHECKER"><ReviewQueuePage /></RoleGuard>} />
      <Route path="audit" element={<AuditTimelinePage />} />
      <Route path="verify" element={<VerifyDashboardPage />} />
      <Route path="policy" element={<PolicyPage />} />
      <Route path="*" element={<StatePanel kind="error" title="Không tìm thấy trang demo" description="Đường dẫn không tồn tại trong Judge Demo." />} />
    </Route>

    <Route path="/plans/*" element={<LegacyDemoRedirect />} />
    <Route path="/review" element={<LegacyDemoRedirect />} />
    <Route path="/audit" element={<LegacyDemoRedirect />} />
    <Route path="/verify" element={<LegacyDemoRedirect />} />
    <Route path="/policy" element={<LegacyDemoRedirect />} />
    <Route path="*" element={<StatePanel kind="error" title="Không tìm thấy trang" description="Đường dẫn không tồn tại trong OrganizationAI." />} />
  </Routes>
}

function AuthEntryPage() {
  const { isAuthenticated, isLoading, roles, sessionError, refresh } = useAuth()
  if (isLoading) return <p role="status">Đang khôi phục phiên đăng nhập…</p>
  if (sessionError) return <StatePanel kind="error" title="Không thể kết nối dịch vụ đăng nhập" description={sessionError} action={<button type="button" onClick={() => void refresh()}>Thử lại</button>} />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <Navigate to={homeForRoles(roles)} replace />
}

function RoleHomePage() {
  const { roles } = useAuth()
  return <Navigate to={homeForRoles(roles)} replace />
}

function AccessDeniedPage() {
  return <main className="auth-account"><h1>Không có quyền truy cập</h1>
    <p>Tài khoản này không có vai trò được cấp cho trang hoặc thao tác bạn yêu cầu.</p>
    <p><Link to="/account">Quay lại tài khoản</Link></p>
  </main>
}

function LegacyDemoRedirect() {
  const location = useLocation()
  return <Navigate to={`/demo${location.pathname}${location.search}${location.hash}`} replace />
}

function RoleGuard({ role, children }: { role: string; children: ReactNode }) {
  const { config, loading, error } = useSession()
  if (loading) return <StatePanel kind="loading" title="Đang kiểm tra quyền" />
  if (error) return <StatePanel kind="error" title="Không thể xác thực phiên" description={error} />
  if (!config || !config.roles.includes(role)) return <StatePanel kind="error" title={`Không có quyền ${role}`} description="Chọn actor demo có role phù hợp. Backend vẫn kiểm tra quyền ở mọi request." />
  return children
}
