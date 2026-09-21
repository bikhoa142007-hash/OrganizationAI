import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import type { HumanAction, ReviewDecisionResult, ReviewDetail, ReviewItem } from '../types'

export function ReviewQueuePage() {
  const services = useServices()
  const [queue, setQueue] = useState<ReviewItem[]>([])
  const [selected, setSelected] = useState<ReviewDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<HumanAction | null>(null)
  const [isActionPending, setIsActionPending] = useState(false)
  const [conflictMessage, setConflictMessage] = useState<string | null>(null)

  const loadQueue = useCallback(async () => {
    setIsLoading(true)
    setSelected(null)
    setLoadError(null)
    try {
      setQueue(await services.review.listPendingReviews())
    } catch {
      setLoadError('Không thể tải danh sách hồ sơ cần human review.')
    } finally {
      setIsLoading(false)
    }
  }, [services.review])

  useEffect(() => { void loadQueue() }, [loadQueue])

  async function selectReview(planId: string) {
    setActionError(null)
    setSuccessMessage(null)
    setConflictMessage(null)
    try {
      const detail = await services.review.getReview(planId)
      setSelected(detail)
      setReason('')
      setOverrideReason('')
      setReasonError(null)
    } catch {
      setActionError('Không thể tải chi tiết hồ sơ.')
    }
  }

  async function confirmAction() {
    if (!selected || !pendingAction) return
    if (!reason.trim()) {
      setReasonError('Vui lòng nhập lý do trước khi xác nhận action.')
      return
    }
    setReasonError(null)
    setIsActionPending(true)
    setActionError(null)
    setConflictMessage(null)
    try {
      const result = await services.review.decide(selected.planId, { action: pendingAction, reason: reason.trim(), overrideReason: overrideReason.trim() || undefined }, { expectedRevision: selected.revision, idempotencyKey: `ui-review-${Date.now()}` })
      handleDecisionResult(result)
    } catch {
      setActionError('Không thể gửi action tới service.')
    } finally {
      setIsActionPending(false)
      setPendingAction(null)
    }
  }

  function handleDecisionResult(result: ReviewDecisionResult) {
    if (result.status === 'UPDATED') {
      setSuccessMessage(result.message ?? 'Service đã cập nhật hồ sơ.')
      setSelected(null)
      setReason('')
      setOverrideReason('')
      setReasonError(null)
      void loadQueue()
      return
    }
    if (result.status === 'STALE') {
      setConflictMessage(result.message ?? 'Hồ sơ đã thay đổi. Vui lòng tải lại.')
      return
    }
    setActionError(result.message ?? 'Service không thể cập nhật hồ sơ.')
  }

  return (
    <section className="review-page" aria-labelledby="review-title">
      <div className="review-header">
        <div><Link className="back-link" to="/">← Quay lại Landing</Link><span className="section-kicker">Màn 5</span><h2 id="review-title">Human Review Queue</h2><p>Danh sách hồ sơ đang chờ service chuyển tới người có thẩm quyền.</p></div>
        <button type="button" className="button button-secondary" onClick={() => void loadQueue()} disabled={isLoading}>Tải lại</button>
      </div>
      {loadError && <p className="form-error review-alert" role="alert">{loadError}</p>}
      {actionError && <p className="form-error review-alert" role="alert">{actionError}</p>}
      {successMessage && <p className="review-success" role="status">{successMessage}</p>}
      {conflictMessage && <p className="review-conflict" role="alert">{conflictMessage}</p>}
      <div className="review-layout">
        <section className="review-queue-panel" aria-label="Danh sách hồ sơ">
          <h3>Hồ sơ chờ xử lý</h3>
          {isLoading && <div className="review-loading"><span className="loading-spinner" aria-hidden="true" /> Đang tải queue…</div>}
          {!isLoading && !loadError && queue.length === 0 && <p className="review-empty">Hiện không có hồ sơ đang chờ human review.</p>}
          {!isLoading && queue.length > 0 && <div className="review-table-wrap"><table className="review-table"><thead><tr><th>Campaign</th><th>Escalation</th><th>Lý do</th><th>Ưu tiên</th><th>Authority</th><th>Thời gian</th><th>Trạng thái</th></tr></thead><tbody>{queue.map((item) => <tr key={item.planId} className={selected?.planId === item.planId ? 'review-row-selected' : ''} onClick={() => void selectReview(item.planId)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') void selectReview(item.planId) }}><td><strong>{item.title ?? item.planId}</strong><small>{item.planId}</small></td><td>{item.escalationCategory ?? 'Service không cung cấp'}</td><td>{item.reason ?? 'Service không cung cấp'}</td><td>{item.priority ?? 'Service không cung cấp'}</td><td>{item.authority ?? 'Service không cung cấp'}</td><td>{item.createdAt ? formatDate(item.createdAt) : 'Service không cung cấp'}</td><td><span className="review-status">{item.status ?? 'Service cung cấp'}</span></td></tr>)}</tbody></table></div>}
        </section>
        {selected && <ReviewDetailPanel overrideReason={overrideReason} setOverrideReason={setOverrideReason} detail={selected} reason={reason} reasonError={reasonError} setReason={setReason} setReasonError={setReasonError} pendingAction={pendingAction} setPendingAction={setPendingAction} isActionPending={isActionPending} onConfirm={() => void confirmAction()} onClose={() => setSelected(null)} />}
      </div>
    </section>
  )
}

interface ReviewDetailPanelProps {
  overrideReason: string
  setOverrideReason: (value: string) => void
  detail: ReviewDetail
  reason: string
  reasonError: string | null
  setReason: (value: string) => void
  setReasonError: (value: string | null) => void
  pendingAction: HumanAction | null
  setPendingAction: (action: HumanAction | null) => void
  isActionPending: boolean
  onConfirm: () => void
  onClose: () => void
}

function ReviewDetailPanel({ overrideReason, setOverrideReason, detail, reason, reasonError, setReason, setReasonError, pendingAction, setPendingAction, isActionPending, onConfirm, onClose }: ReviewDetailPanelProps) {
  const actionLabel = pendingAction === 'APPROVED' ? 'Approve' : pendingAction === 'REJECTED' ? 'Reject' : 'Request Changes'
  return <aside className="review-detail-panel" aria-labelledby="review-detail-title">
    <div className="review-detail-heading"><div><span className="section-kicker">Review Detail</span><h3 id="review-detail-title">{detail.title ?? detail.planId}</h3><p>{detail.planId} · {detail.status ?? 'Service cung cấp'}</p></div><button type="button" className="button button-secondary" onClick={onClose}>Đóng</button></div>
    {detail.originalInput && <section className="review-detail-section"><h4>Input gốc</h4><dl className="review-meta">{Object.entries(detail.originalInput).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></section>}
    <section className="review-detail-section"><h4>Media / attachment</h4>{detail.attachments?.length ? <ul>{detail.attachments.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Service không cung cấp attachment.</p>}</section>
    {detail.evidence?.length ? <section className="review-detail-section"><h4>VLM evidence</h4><dl className="review-meta">{detail.evidence.map((item) => <div key={item.id}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl></section> : null}
    {detail.appliedRuleIds?.length ? <section className="review-detail-section"><h4>Applied rules</h4><ul>{detail.appliedRuleIds.map((ruleId) => <li key={ruleId}>{ruleId}</li>)}</ul></section> : null}
    {detail.handoffQuestions?.length ? <section className="review-detail-section"><h4>Câu hỏi chuyển tiếp</h4><ul>{detail.handoffQuestions.map((question) => <li key={question}>{question}</li>)}</ul></section> : null}
    {detail.currentDecision && <section className="review-detail-section"><h4>Decision hiện tại</h4><p>{detail.currentDecision}</p></section>}
    <section className="review-decision"><Link to={`/plans/${detail.planId}`}>Xem ảnh và version</Link><label htmlFor="override-reason">Lý do override (bắt buộc nếu đổi khuyến nghị)</label><textarea id="override-reason" value={overrideReason} onChange={e => setOverrideReason(e.target.value)} disabled={isActionPending} /><label htmlFor="review-reason">Lý do <em>*</em></label><textarea id="review-reason" aria-invalid={reasonError ? 'true' : 'false'} value={reason} onChange={(event) => { setReason(event.target.value); if (event.target.value.trim()) setReasonError(null) }} placeholder="Nhập lý do cho action human…" disabled={isActionPending} />{reasonError ? <small className="form-error" role="alert">{reasonError}</small> : <small>Reason là bắt buộc trước khi xác nhận action.</small>}<div className="review-actions"><button type="button" className="button button-primary" disabled={isActionPending} onClick={() => { if (!reason.trim()) { setReasonError('Vui lòng nhập lý do trước khi xác nhận action.'); return } setPendingAction('APPROVED') }}>Approve</button><button type="button" className="button button-danger" disabled={isActionPending} onClick={() => { if (!reason.trim()) { setReasonError('Vui lòng nhập lý do trước khi xác nhận action.'); return } setPendingAction('REJECTED') }}>Reject</button></div></section>
    {pendingAction && <div className="review-confirmation" role="alertdialog"><h4>Xác nhận {actionLabel}?</h4><p>Service sẽ ghi nhận action cùng reason đã nhập.</p><div className="review-actions"><button type="button" className="button button-secondary" onClick={() => setPendingAction(null)} disabled={isActionPending}>Hủy</button><button type="button" className="button button-primary" onClick={onConfirm} disabled={isActionPending}>{isActionPending ? 'Đang gửi…' : 'Xác nhận'}</button></div></div>}
  </aside>
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN')
}
