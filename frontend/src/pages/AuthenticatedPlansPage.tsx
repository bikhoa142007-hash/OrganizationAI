import { FilePlus2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPlan } from '../types/authWorkflow'

export function AuthenticatedPlansPage({ reviews = false }: { reviews?: boolean }) {
  const { roles } = useAuth()
  const [plans, setPlans] = useState<WorkflowPlan[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(async () => {
    setError(''); setLoading(true)
    try { setPlans(reviews ? await authWorkflowService.listReviews() : await authWorkflowService.listPlans()) }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setLoading(false) }
  }, [reviews])
  useEffect(() => { void load() }, [load])

  const title = reviews ? 'Kế hoạch chờ tôi duyệt' : 'Kế hoạch của tôi'
  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">Workflow PostgreSQL · {reviews ? 'Checker' : 'Maker'}</p><h1>{title}</h1><p>{reviews ? 'Chỉ các hồ sơ đang chờ và được giao cho tài khoản hiện tại.' : 'Các bản nháp, hồ sơ đã gửi và lịch sử do tài khoản hiện tại tạo.'}</p></div><div className="button-row"><button className="button button-secondary" onClick={() => void load()} disabled={loading}><RefreshCw /> Tải lại</button>{!reviews && roles.includes('MAKER') && <Link className="button button-primary" to="/workflow/plans/new"><FilePlus2 /> Tạo kế hoạch</Link>}</div></div>
    {loading ? <p className="auth-workflow-state" role="status">Đang tải dữ liệu từ PostgreSQL…</p>
      : error ? <section className="auth-workflow-state is-error" role="alert"><h2>Không tải được danh sách</h2><p>{error}</p><button className="button button-secondary" onClick={() => void load()}>Thử lại</button></section>
        : plans.length === 0 ? <section className="auth-workflow-state"><h2>{reviews ? 'Chưa có hồ sơ được giao' : 'Chưa có kế hoạch'}</h2><p>{reviews ? 'Các kế hoạch được gửi tới tài khoản này sẽ xuất hiện tại đây.' : 'Tạo bản nháp đầu tiên để bắt đầu workflow Auth.'}</p></section>
          : <div className="auth-workflow-table-wrap"><table className="auth-workflow-table"><thead><tr><th>Kế hoạch</th><th>Người lập</th><th>Trạng thái</th><th>Checker</th><th>Vòng duyệt</th><th>Cập nhật</th></tr></thead><tbody>{plans.map(plan => <tr key={plan.id}><td><Link to={`/workflow/plans/${plan.id}`}><strong>{plan.payload.title || plan.code}</strong><small>{plan.code}</small></Link></td><td>{plan.maker_name}</td><td><span className={`workflow-status status-${plan.status.toLowerCase()}`}>{statusLabel(plan.status)}</span>{['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) && <small className="auth-stage-note">AI đang đánh giá</small>}{plan.processing_stage === 'HUMAN_REVIEW_REQUIRED' && <small className="auth-stage-note">Chờ Checker xem xét</small>}</td><td>{plan.checker_name || 'Chưa gán'}</td><td>{plan.current_round || '—'}</td><td>{new Date(plan.updated_at).toLocaleDateString('vi-VN')}</td></tr>)}</tbody></table></div>}
  </section>
}

function statusLabel(status: WorkflowPlan['status']) {
  return ({ DRAFT: 'Bản nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối' })[status]
}
