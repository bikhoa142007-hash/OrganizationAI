import { ArrowLeft, Check, Clock3, FileText, History, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPlan } from '../types/authWorkflow'

export function AuthenticatedWorkflowDetailPage() {
  const { planId = '' } = useParams()
  const { user, roles } = useAuth()
  const [plan, setPlan] = useState<WorkflowPlan | null>(null)
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    setError('')
    authWorkflowService.getPlan(planId)
      .then(value => { if (active) setPlan(value) })
      .catch(failure => { if (active) setError(failure instanceof Error ? failure.message : String(failure)) })
    return () => { active = false }
  }, [planId, reload])

  async function decide(action: 'APPROVED' | 'REJECTED') {
    setBusy(true); setError('')
    try {
      const result = await authWorkflowService.decide(planId, plan?.current_round ?? 0, action, reason)
      setPlan(result); setReason('')
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)) }
    finally { setBusy(false) }
  }

  if (!plan) return <section className={`auth-workflow-state${error ? ' is-error' : ''}`} role={error ? 'alert' : 'status'}><h1>{error ? 'Không thể mở kế hoạch' : 'Đang tải kế hoạch…'}</h1>{error && <><p>{error}</p><Link to="/workflow/plans">Quay lại danh sách</Link></>}</section>
  const isMaker = roles.includes('MAKER') && plan.maker_id === user?.id
  const isAssignedChecker = roles.includes('CHECKER') && plan.checker_id === user?.id
  const canEdit = isMaker && ['DRAFT', 'REJECTED'].includes(plan.status)
  const canDecide = isAssignedChecker && plan.status === 'PENDING_APPROVAL'

  return <section className="auth-workflow-page">
    <Link className="auth-back-link" to={isAssignedChecker ? '/workflow/reviews' : '/workflow/plans'}><ArrowLeft /> Quay lại danh sách</Link>
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">{plan.code} · Version {plan.current_version || '—'} · Round {plan.current_round || '—'}</p><h1>{plan.payload.title || 'Kế hoạch chưa có tên'}</h1><p>Maker: {plan.maker_name} <span aria-hidden="true">·</span> Checker: {plan.checker_name || 'Chưa gán'}</p></div><span className={`workflow-status status-${plan.status.toLowerCase()}`}>{statusLabel(plan.status)}</span></div>
    {error && <div className="auth-workflow-alert is-error" role="alert"><p>{error}</p></div>}
    <div className="auth-workflow-detail-grid">
      <section className="auth-workflow-card"><div className="auth-workflow-card-heading"><FileText /><h2>Nội dung kế hoạch</h2></div><dl className="auth-workflow-definition-grid">
        <div><dt>Mục tiêu</dt><dd>{plan.payload.objective || '—'}</dd></div>
        <div><dt>Bộ phận</dt><dd>{plan.payload.department || '—'}</dd></div>
        <div><dt>Thời gian</dt><dd>{plan.payload.start_date || '—'} — {plan.payload.end_date || '—'}</dd></div>
        <div><dt>Ngân sách</dt><dd>{formatBudget(plan.payload.budget_minor_units, plan.payload.currency)}</dd></div>
        <div className="field-wide"><dt>Tóm tắt chiến lược</dt><dd>{plan.payload.summary || '—'}</dd></div>
        <div><dt>Đối tượng mục tiêu</dt><dd>{plan.payload.target_audience || '—'}</dd></div>
        <div><dt>KPI kỳ vọng</dt><dd>{plan.payload.kpi_expected || '—'}</dd></div>
        <div><dt>Kênh</dt><dd>{plan.payload.channels.join(', ') || '—'}</dd></div>
        <div><dt>Ghi chú</dt><dd>{plan.payload.notes || '—'}</dd></div>
      </dl>{plan.decision_reason && <div className="auth-workflow-alert is-error"><strong>Lý do từ chối</strong><p>{plan.decision_reason}</p></div>}
        <div className="auth-workflow-attachments"><h3>Ảnh đính kèm</h3>{plan.attachments.length ? plan.attachments.map(item => <div key={item.id} className="auth-workflow-attachment"><AuthAttachmentPreview planId={plan.id} attachmentId={item.id} filename={item.filename} /><span><strong>{item.filename}</strong><small>{item.media_type} · {Math.ceil(item.byte_size / 1024)} KB · SHA-256 {item.content_hash.slice(0, 12)}…</small></span></div>) : <p>Chưa có ảnh đính kèm.</p>}</div>
      </section>
      <section className="auth-workflow-card"><div className="auth-workflow-card-heading"><History /><h2>Lịch sử xử lý</h2></div><ol className="auth-workflow-history">{plan.history.map(event => <li key={event.id}><span className="history-icon">{event.action === 'APPROVED' ? <Check /> : event.action === 'REJECTED' ? <X /> : <Clock3 />}</span><div><strong>{eventLabel(event.action)}</strong><p>{event.actor_name} · {new Date(event.created_at).toLocaleString('vi-VN')}</p>{typeof event.details.reason === 'string' && <blockquote>{event.details.reason}</blockquote>}{typeof event.details.version === 'number' && typeof event.details.round === 'number' && <small>Version {event.details.version} / Round {event.details.round}</small>}</div></li>)}</ol></section>
    </div>
    {plan.versions.length > 0 && <section className="auth-workflow-card auth-version-card"><div className="auth-workflow-card-heading"><History /><h2>Snapshot đã gửi</h2></div>{plan.versions.map(version => <details key={version.version_number}><summary>Version {version.version_number} · Round {version.round_number} · {new Date(version.created_at).toLocaleString('vi-VN')}</summary><p>{version.payload.summary}</p><ul>{version.attachments.map(item => <li key={item.id}>{item.filename} · SHA-256 {item.content_hash}</li>)}</ul></details>)}</section>}
    {canEdit && <div className="auth-workflow-actions"><Link className="button button-secondary" to={`/workflow/plans/${plan.id}/edit`}>Chỉnh sửa và gửi lại</Link></div>}
    {canDecide && <section className="auth-workflow-card auth-decision-card"><div className="auth-workflow-card-heading"><Check /><h2>Quyết định Checker</h2></div><p>Nội dung và snapshot được lưu chỉ đọc. Từ chối cần có lý do.</p><label className="auth-field">Lý do hoặc nhận xét<textarea rows={3} value={reason} onChange={event => setReason(event.target.value)} placeholder="Bắt buộc khi từ chối" /></label><div className="button-row"><button className="button button-secondary" disabled={busy} onClick={() => void decide('REJECTED')}>{busy ? 'Đang xử lý…' : 'Từ chối'}</button><button className="button button-primary" disabled={busy} onClick={() => void decide('APPROVED')}><Check /> {busy ? 'Đang xử lý…' : 'Phê duyệt'}</button></div></section>}
    <button className="auth-quiet-refresh" onClick={() => setReload(value => value + 1)}>Tải lại trạng thái</button>
  </section>
}

function eventLabel(action: string) {
  return ({ CREATED: 'Tạo bản nháp', UPDATED: 'Cập nhật nội dung', ATTACHMENT_UPLOADED: 'Tải ảnh lên', SUBMITTED: 'Gửi duyệt', APPROVED: 'Đã phê duyệt', REJECTED: 'Đã từ chối' } as Record<string, string>)[action] ?? action
}

function statusLabel(status: WorkflowPlan['status']) {
  return ({ DRAFT: 'Bản nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối' })[status]
}

function formatBudget(value: string, currency: string) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? `${new Intl.NumberFormat('vi-VN').format(amount)} ${currency}` : '—'
}

function AuthAttachmentPreview({ planId, attachmentId, filename }: { planId: string; attachmentId: string; filename: string }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let objectUrl = ''
    authWorkflowService.getAttachment(planId, attachmentId)
      .then(blob => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(failure => { if (active) setError(failure instanceof Error ? failure.message : String(failure)) })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attachmentId, planId])
  return error ? <span role="alert">{error}</span> : url ? <img className="auth-workflow-image-preview" src={url} alt={`Tệp đính kèm ${filename}`} /> : <span role="status">Đang tải ảnh…</span>
}
