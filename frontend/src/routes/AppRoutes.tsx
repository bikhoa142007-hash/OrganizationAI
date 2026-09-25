import type { ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/AppShell'
import { StatePanel } from '../components/ui'
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

export function AppRoutes() {
  return <Routes><Route path="/login" element={<LoginPage />} /><Route path="/register" element={<RegisterPage />} /><Route element={<AppShell />}>
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
    <Route path="*" element={<StatePanel kind="error" title="Không tìm thấy trang" description="Đường dẫn không tồn tại trong OrganizationAI." />} />
  </Route></Routes>
}

function RoleGuard({ role, children }: { role: string; children: ReactNode }) {
  const { config, loading, error } = useSession()
  if (loading) return <StatePanel kind="loading" title="Đang kiểm tra quyền" />
  if (error) return <StatePanel kind="error" title="Không thể xác thực phiên" description={error} />
  if (!config || !config.roles.includes(role)) return <StatePanel kind="error" title={`Không có quyền ${role}`} description="Chọn actor demo có role phù hợp. Backend vẫn kiểm tra quyền ở mọi request." />
  return children
}
