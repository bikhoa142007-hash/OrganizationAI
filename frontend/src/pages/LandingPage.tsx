import { ArrowRight, BriefcaseBusiness, CheckCircle2, CircleDashed, ClipboardCheck, FilePlus2, ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import { useSession } from '../services/SessionProvider'
import type { PlanView } from '../types'

export function LandingPage() {
  const services = useServices()
  const { config, loading: sessionLoading, error: sessionError } = useSession()
  const [plans, setPlans] = useState<PlanView[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    services.plan.listPlans().then(value => { if (active) setPlans(value) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [services.plan])

  const stats = useMemo(() => ({
    total: plans.length,
    draft: plans.filter(plan => plan.state?.planStatus === 'DRAFT').length,
    pending: plans.filter(plan => plan.state?.planStatus === 'PENDING_APPROVAL').length,
    approved: plans.filter(plan => plan.state?.planStatus === 'APPROVED').length,
    review: plans.filter(plan => plan.state?.processingStage === 'HUMAN_REVIEW_REQUIRED').length,
  }), [plans])
  const isMaker = Boolean(config?.roles.includes('MAKER'))
  const isChecker = Boolean(config?.roles.includes('CHECKER'))

  return <section className="dashboard-page">
    <PageHeader
      eyebrow="Không gian làm việc"
      title={isChecker && !isMaker ? 'Hồ sơ cần bạn thẩm định' : 'Tổng quan kế hoạch marketing'}
      description="Theo dõi kế hoạch, kết quả đánh giá và các công việc đang chờ xử lý từ dữ liệu backend hiện tại."
      actions={isMaker ? <Link className="button button-primary" to="/plans/new"><FilePlus2 /> Tạo kế hoạch</Link> : isChecker ? <Link className="button button-primary" to="/review"><ClipboardCheck /> Mở hàng chờ duyệt</Link> : undefined}
    />

    {(sessionLoading || sessionError) && <StatePanel kind={sessionError ? 'error' : 'loading'} title={sessionError ? 'Không tải được phiên xác thực' : 'Đang xác nhận phiên'} description={sessionError || 'Đang lấy role và cấu hình từ backend.'} />}

    {config && <div className="environment-banner"><ShieldAlert aria-hidden="true" /><div><strong>{config.provider === 'MOCK_VLM' ? 'Môi trường demo dùng model mô phỏng' : `Provider: ${config.provider}`}</strong><span>Quyền và dữ liệu đang hiển thị theo actor {config.actor}. Mọi quyết định vẫn do backend ghi nhận.</span></div></div>}

    <div className="stat-grid" aria-label="Tổng quan trạng thái">
      <article><span className="stat-icon stat-blue"><BriefcaseBusiness /></span><div><strong>{stats.total}</strong><span>Kế hoạch có quyền xem</span></div></article>
      <article><span className="stat-icon stat-slate"><CircleDashed /></span><div><strong>{stats.draft}</strong><span>Bản nháp</span></div></article>
      <article><span className="stat-icon stat-amber"><ClipboardCheck /></span><div><strong>{isChecker ? stats.review : stats.pending}</strong><span>{isChecker ? 'Cần thẩm định' : 'Đang chờ duyệt'}</span></div></article>
      <article><span className="stat-icon stat-green"><CheckCircle2 /></span><div><strong>{stats.approved}</strong><span>Đã duyệt</span></div></article>
    </div>

    <div className="dashboard-layout">
      <section className="dashboard-section">
        <div className="section-toolbar"><div><p className="page-eyebrow">Gần đây</p><h3>Kế hoạch mới nhất</h3></div><Link className="text-link" to="/plans">Xem tất cả <ArrowRight /></Link></div>
        {loading ? <StatePanel kind="loading" title="Đang tải kế hoạch" /> : error ? <StatePanel kind="error" title="Không thể tải kế hoạch" description={error} /> : plans.length === 0 ? <StatePanel kind="empty" title="Chưa có kế hoạch" description={isMaker ? 'Tạo kế hoạch đầu tiên để bắt đầu quy trình phê duyệt.' : 'Actor hiện tại chưa có hồ sơ được cấp quyền xem.'} /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Kế hoạch</th><th>Trạng thái</th><th>Giai đoạn</th><th>Vòng</th><th></th></tr></thead><tbody>{plans.slice(0, 6).map(plan => <tr key={plan.planId}><td data-label="Kế hoạch"><Link className="primary-cell" to={`/plans/${plan.planId}`}>{plan.title || plan.planId}<small>{plan.planId}</small></Link></td><td data-label="Trạng thái"><StatusBadge value={plan.state?.planStatus} /></td><td data-label="Giai đoạn"><span className="secondary-text">{plan.state?.processingStage ? <StatusBadge value={plan.state.processingStage} /> : 'Chưa gửi'}</span></td><td data-label="Vòng">{plan.approvalRound ?? '—'}</td><td><Link className="icon-button subtle" to={`/plans/${plan.planId}`} aria-label={`Mở ${plan.title || plan.planId}`}><ArrowRight /></Link></td></tr>)}</tbody></table></div>}
      </section>

      <aside className="dashboard-aside">
        <div className="section-toolbar"><div><p className="page-eyebrow">Tác vụ</p><h3>Đi nhanh</h3></div></div>
        <div className="quick-actions">
          {isMaker && <Link to="/plans/new"><FilePlus2 /><span><strong>Tạo kế hoạch</strong><small>Lưu nháp, tải ảnh và gửi duyệt.</small></span><ArrowRight /></Link>}
          {isChecker && <Link to="/review"><ClipboardCheck /><span><strong>Hàng chờ duyệt</strong><small>Xem evidence và ra quyết định.</small></span><ArrowRight /></Link>}
          <Link to="/audit"><BriefcaseBusiness /><span><strong>Tra cứu audit</strong><small>Xem lịch sử theo mã kế hoạch.</small></span><ArrowRight /></Link>
        </div>
      </aside>
    </div>
  </section>
}
