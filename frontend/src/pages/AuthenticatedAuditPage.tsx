import { RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowAuditEvent, WorkflowAuditPage } from '../types/authWorkflow'

const PAGE_SIZE = 50

export function AuthenticatedAuditPage() {
  const [page, setPage] = useState<WorkflowAuditPage | null>(null)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (nextOffset: number) => {
    setError('')
    setLoading(true)
    try {
      setPage(await authWorkflowService.listAuditEvents(nextOffset, PAGE_SIZE))
      setOffset(nextOffset)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load(0) }, [load])

  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading">
      <div><p className="page-eyebrow">Workflow PostgreSQL · Administrator</p><h1>Nhật ký kiểm toán</h1><p>Nhật ký chỉ đọc cho các thao tác kế hoạch và pipeline đã ghi nhận.</p></div>
      <button className="button button-secondary" type="button" disabled={loading} onClick={() => void load(offset)}><RefreshCw /> Tải lại</button>
    </div>
    {loading ? <p className="auth-workflow-state" role="status">Đang tải nhật ký…</p>
      : error ? <section className="auth-workflow-state is-error" role="alert"><h2>Không tải được nhật ký</h2><p>{error}</p><button className="button button-secondary" onClick={() => void load(offset)}>Thử lại</button></section>
        : !page || page.items.length === 0 ? <section className="auth-workflow-state" role="status"><h2>Chưa có sự kiện</h2><p>Các sự kiện workflow sẽ xuất hiện tại đây.</p></section>
          : <>
            <div className="auth-workflow-table-wrap"><table className="auth-workflow-table"><thead><tr><th>Thời điểm</th><th>Kế hoạch</th><th>Hành động</th><th>Người thực hiện</th><th>Trạng thái</th><th>Chi tiết</th></tr></thead><tbody>
              {page.items.map(event => <AuditRow key={event.id} event={event} />)}
            </tbody></table></div>
            <div className="button-row" aria-label="Phân trang nhật ký">
              <button className="button button-secondary" type="button" disabled={loading || offset === 0} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}>Trước</button>
              <span role="status">{offset + 1}–{Math.min(offset + page.items.length, page.total)} / {page.total}</span>
              <button className="button button-secondary" type="button" disabled={loading || offset + page.items.length >= page.total} onClick={() => void load(offset + PAGE_SIZE)}>Tiếp</button>
            </div>
          </>}
  </section>
}

function AuditRow({ event }: { event: WorkflowAuditEvent }) {
  const reason = typeof event.details.reason === 'string' ? event.details.reason.trim() : ''
  const overrideReason = typeof event.details.override_reason === 'string' ? event.details.override_reason.trim() : ''
  const actionReasonLabel = event.action === 'APPROVED' ? 'Lý do phê duyệt' : event.action === 'REJECTED' ? 'Lý do từ chối' : 'Lý do'
  const details = [
    typeof event.details.version === 'number' ? `Version ${event.details.version}` : '',
    typeof event.details.round === 'number' ? `Round ${event.details.round}` : '',
    reason ? `${actionReasonLabel}: ${reason}` : '',
    overrideReason ? `Lý do override AI: ${overrideReason}` : '',
  ].filter(Boolean).join(' · ')
  const transition = event.status_before ? `${event.status_before} → ${event.status_after}` : event.status_after
  return <tr>
    <td>{new Date(event.created_at).toLocaleString('vi-VN')}</td>
    <td>{event.plan_code}</td>
    <td>{event.action}</td>
    <td>{event.actor_name} <small>{event.actor_type === 'SYSTEM' ? 'Hệ thống' : 'Người dùng'}</small></td>
    <td>{transition}</td>
    <td>{details || '—'}</td>
  </tr>
}
