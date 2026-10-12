import { CheckCheck, ClipboardList, Clock3, FileClock, RefreshCw, UserCheck, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { AuthApiError } from '../services/auth'
import { workflowCompletionService, type WorkflowDashboard } from '../services/workflowCompletion'

const metricCards = [
  { key: 'draft', label: 'Bản nháp', icon: ClipboardList, color: 'stat-slate' },
  { key: 'pending_ai', label: 'Đang xử lý AI', icon: Clock3, color: 'stat-blue' },
  { key: 'human_review', label: 'Chờ Checker', icon: FileClock, color: 'stat-amber' },
  { key: 'approved', label: 'Đã duyệt', icon: CheckCheck, color: 'stat-green' },
  { key: 'rejected', label: 'Đã từ chối', icon: XCircle, color: 'stat-amber' },
] as const

function describeScope(scope: WorkflowDashboard['principal_scope']) {
  switch (scope) {
    case 'ADMIN_READ_ONLY': return 'Số liệu bao gồm các kế hoạch trong phạm vi workflow quản trị chỉ đọc.'
    case 'CHECKER_ASSIGNED': return 'Số liệu chỉ gồm các kế hoạch được giao cho bạn.'
    case 'MAKER_AND_CHECKER': return 'Số liệu chỉ gồm các kế hoạch bạn lập hoặc được giao.'
    default: return 'Số liệu chỉ gồm các kế hoạch do bạn lập.'
  }
}

function formatAsOf(value: string) {
  return `${new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value))} UTC`
}

function dashboardError(error: unknown) {
  if (error instanceof AuthApiError && error.status === 403) {
    return 'Bạn không có quyền xem tổng quan workflow.'
  }
  if (error instanceof AuthApiError && error.status === 401) {
    return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  }
  return error instanceof Error ? error.message : 'Không thể tải tổng quan workflow.'
}

export function AuthenticatedDashboardPage() {
  const [dashboard, setDashboard] = useState<WorkflowDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    workflowCompletionService.getDashboard()
      .then(result => { if (active) setDashboard(result) })
      .catch(reason => { if (active) setError(dashboardError(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reloadKey])

  const empty = dashboard !== null
    && Object.values(dashboard.counts).every(count => count === 0)
    && dashboard.active_assignments === 0
  const cards = dashboard ? [
    ...metricCards.map(metric => ({
      label: metric.label,
      value: dashboard.counts[metric.key],
      icon: metric.icon,
      color: metric.color,
    })),
    {
      label: 'Phân công đang hoạt động',
      value: dashboard.active_assignments,
      icon: UserCheck,
      color: 'stat-blue',
    },
  ] : []

  return <section className="auth-workflow-page" aria-busy={loading}>
    <div className="auth-workflow-page-heading">
      <div>
        <p className="page-eyebrow">Workflow PostgreSQL</p>
        <h1>Tổng quan kế hoạch marketing</h1>
        <p>Thống kê được tổng hợp trên máy chủ theo phạm vi hồ sơ bạn được phép xem.</p>
      </div>
      <button className="button button-secondary" type="button" disabled={loading} onClick={() => setReloadKey(value => value + 1)}>
        <RefreshCw aria-hidden="true" /> Tải lại
      </button>
    </div>

    {loading && !dashboard && <p className="auth-workflow-state" role="status" aria-busy="true">Đang tải tổng quan…</p>}
    {error && <div className="auth-workflow-alert is-error" role="alert">
      <p>{error}</p>
      {!dashboard && <button className="button button-secondary" type="button" disabled={loading} onClick={() => setReloadKey(value => value + 1)}>Thử lại</button>}
    </div>}

    {dashboard && <>
      <p className="auth-workflow-refresh-status">{describeScope(dashboard.principal_scope)} Tổng hợp lúc {formatAsOf(dashboard.as_of)}.</p>
      <div className="stat-grid" aria-label="Số liệu kế hoạch theo trạng thái">
        {cards.map(({ label, value, icon: Icon, color }) => <article key={label}>
          <div className={`stat-icon ${color}`}><Icon aria-hidden="true" /></div>
          <div><strong>{value}</strong><span>{label}</span></div>
        </article>)}
      </div>
      {empty && <div className="auth-workflow-state" role="status">
        <h2>Chưa có kế hoạch</h2>
        <p>Chưa có kế hoạch trong phạm vi bạn được xem.</p>
      </div>}
    </>}
  </section>
}
