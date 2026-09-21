import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import type { AuditEvent, PlanView } from '../types'

export function AuditTimelinePage() {
  const services = useServices()
  const [searchParams] = useSearchParams()
  const planId = searchParams.get('planId') ?? ''
  const [plans, setPlans] = useState<PlanView[]>([])
  useEffect(() => { if (!planId) services.plan.listPlans().then(setPlans).catch(() => setError('Không tải được danh sách hồ sơ.')) }, [planId, services.plan])
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const nextEvents = planId ? await services.audit.listByPlan(planId) : []
        if (!cancelled) setEvents(nextEvents)
      } catch {
        if (!cancelled) setError('Không thể tải audit history từ service.')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [planId, services.audit])

  return <section className="audit-page" aria-labelledby="audit-title">
    <div className="audit-header"><div><Link className="back-link" to="/">← Quay lại Landing</Link><span className="section-kicker">Màn 6</span><h2 id="audit-title">Audit Timeline</h2><p>Lịch sử chỉ đọc do AuditService cung cấp{planId ? ` cho hồ sơ ${planId}` : ''}.</p></div><span className="audit-readonly">Read-only</span></div>
    {!planId && <div><p>Chọn hồ sơ để xem audit:</p>{plans.map(p => <p key={p.planId}><Link to={`/audit?planId=${encodeURIComponent(p.planId)}`}>{p.title || p.planId}</Link></p>)}</div>}{isLoading && <div className="audit-state"><span className="loading-spinner" aria-hidden="true" /> Đang tải lịch sử…</div>}
    {error && <p className="form-error audit-alert" role="alert">{error}</p>}
    {!isLoading && !error && events.length === 0 && <p className="audit-empty">Chưa có audit event từ service.</p>}
    {!isLoading && !error && events.length > 0 && <div className="audit-timeline">{events.map((event) => <article className="audit-event" key={event.eventId}><div className="audit-event-marker" aria-hidden="true" /><div className="audit-event-body"><div className="audit-event-top"><h3>{event.action}</h3><time>{event.timestamp ? formatDate(event.timestamp) : 'Service không cung cấp thời gian'}</time></div><dl className="audit-meta"><dt>Actor</dt><dd>{event.actorId ?? 'Service không cung cấp'}</dd><dt>Input/version</dt><dd>{event.inputVersion ?? 'Service không cung cấp'}</dd><dt>Policy</dt><dd>{event.policyVersion ?? 'Service không cung cấp'}</dd><dt>Model</dt><dd>{event.modelVersion ?? 'Service không cung cấp'}</dd><dt>Reason</dt><dd>{event.reason ?? 'Service không cung cấp'}</dd><dt>Before</dt><dd>{formatState(event.previousState)}</dd><dt>After</dt><dd>{formatState(event.newState)}</dd></dl></div></article>)}</div>}
  </section>
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN')
}

function formatState(value: AuditEvent['newState']) {
  if (!value) return '—'
  return `${value.planStatus} · ${value.processingStage ?? '—'} · ${value.approvalRoundStatus ?? '—'}`
}
