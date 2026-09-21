import { PlansPage } from '../pages/PlansPage'
import { PlanDetailPage } from '../pages/PlanDetailPage'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/AppShell'
import { AuditTimelinePage } from '../pages/AuditTimelinePage'
import { LandingPage } from '../pages/LandingPage'
import { PlanFormPage } from '../pages/PlanFormPage'
import { PolicyPage } from '../pages/PolicyPage'
import { ProcessingPage } from '../pages/ProcessingPage'
import { ResultPage } from '../pages/ResultPage'
import { ReviewQueuePage } from '../pages/ReviewQueuePage'
import { VerifyDashboardPage } from '../pages/VerifyDashboardPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LandingPage />} />
        <Route path="plans" element={<PlansPage />} /><Route path="plans/:planId" element={<PlanDetailPage />} /><Route path="plans/:planId/edit" element={<PlanFormPage key="edit" />} /><Route path="plans/new" element={<PlanFormPage key="new" />} />
        <Route path="plans/processing" element={<ProcessingPage />} />
        <Route path="plans/:planId/processing" element={<ProcessingPage />} />
        <Route path="plans/result" element={<ResultPage />} />
        <Route path="plans/:planId/result" element={<ResultPage />} />
        <Route path="review" element={<ReviewQueuePage />} />
        <Route path="audit" element={<AuditTimelinePage />} />
        <Route path="verify" element={<VerifyDashboardPage />} />
        <Route path="policy" element={<PolicyPage />} />
      </Route>
    </Routes>
  )
}
