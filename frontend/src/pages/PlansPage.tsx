import { FilePlus2, Filter, RefreshCw, Search } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import { useSession } from '../services/SessionProvider'
import type { PlanView } from '../types'

export function PlansPage() {
  const services = useServices()
  const { hasRole } = useSession()
  const [plans, setPlans] = useState<PlanView[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('ALL')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try { setPlans(await services.plan.listPlans()) } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) } finally { setLoading(false) }
  }, [services.plan])
  useEffect(() => { void load() }, [load])

  const filtered = useMemo(() => plans.filter(plan => {
    const matchesQuery = `${plan.title || ''} ${plan.planId}`.toLowerCase().includes(query.trim().toLowerCase())
    return matchesQuery && (status === 'ALL' || plan.state?.planStatus === status)
  }), [plans, query, status])

  return <section className="list-page">
    <PageHeader eyebrow="Kế hoạch" title="Danh sách kế hoạch" description="Các hồ sơ backend cho phép actor hiện tại truy cập. Danh sách này không mở rộng quyền ở phía client." actions={<div className="button-row"><button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw /> Tải lại</button>{hasRole('MAKER') && <Link className="button button-primary" to="/plans/new"><FilePlus2 /> Tạo kế hoạch</Link>}</div>} />

    <div className="filter-bar">
      <label className="search-field"><Search aria-hidden="true" /><span className="visually-hidden">Tìm kế hoạch</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm theo tên hoặc mã kế hoạch" /></label>
      <label className="select-field"><Filter aria-hidden="true" /><span className="visually-hidden">Lọc trạng thái</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="ALL">Tất cả trạng thái</option><option value="DRAFT">Bản nháp</option><option value="PENDING_APPROVAL">Chờ duyệt</option><option value="APPROVED">Đã duyệt</option><option value="REJECTED">Đã từ chối</option></select></label>
      <span className="result-count">{filtered.length} / {plans.length} hồ sơ</span>
    </div>

    {loading ? <StatePanel kind="loading" title="Đang tải danh sách" /> : error ? <StatePanel kind="error" title="Không thể tải danh sách" description={error} action={<button className="button button-secondary" onClick={() => void load()}>Thử lại</button>} /> : filtered.length === 0 ? <StatePanel kind="empty" title={plans.length ? 'Không tìm thấy kết quả phù hợp' : 'Chưa có kế hoạch'} description={plans.length ? 'Thay đổi từ khóa hoặc bộ lọc để xem kết quả khác.' : 'Actor hiện tại chưa có hồ sơ được cấp quyền xem.'} /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Kế hoạch</th><th>Trạng thái</th><th>Giai đoạn xử lý</th><th>Version / Round</th><th>Revision</th></tr></thead><tbody>{filtered.map(plan => <tr key={plan.planId}><td data-label="Kế hoạch"><Link className="primary-cell" to={`/plans/${plan.planId}`}>{plan.title || plan.planId}<small>{plan.planId}</small></Link></td><td data-label="Trạng thái"><StatusBadge value={plan.state?.planStatus} /></td><td data-label="Giai đoạn"><StatusBadge value={plan.state?.processingStage} /></td><td data-label="Version / Round">{plan.planVersion ?? 'Draft'} / {plan.approvalRound ?? '—'}</td><td data-label="Revision">{plan.revision ?? '—'}</td></tr>)}</tbody></table></div>}
  </section>
}
