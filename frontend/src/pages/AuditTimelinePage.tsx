import { Activity, ArrowRight, LockKeyhole, Search } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge, formatDateTime } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import type { AuditEvent, PlanView } from '../types'

export function AuditTimelinePage() {
  const services = useServices()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const planId = searchParams.get('planId') ?? ''
  const [lookup, setLookup] = useState(planId)
  const [plans, setPlans] = useState<PlanView[]>([])
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    services.plan.listPlans().then(value => { if (active) setPlans(value) }).catch(() => undefined)
    return () => { active = false }
  }, [services.plan])

  useEffect(() => {
    setLookup(planId)
    if (!planId) { setEvents([]); setLoading(false); setError(''); return }
    let active = true
    setLoading(true); setError('')
    services.audit.listByPlan(planId).then(value => { if (active) setEvents(value) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Không thể tải audit history từ service.') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [planId, services.audit])

  const selectedPlan = useMemo(() => plans.find(plan => plan.planId === planId), [planId, plans])
  function submit(event: FormEvent) {
    event.preventDefault()
    const value = lookup.trim()
    if (value) navigate(`/audit?planId=${encodeURIComponent(value)}`)
  }

  return <section className="audit-page">
    <PageHeader eyebrow="Audit" title="Lịch sử hoạt động" description="Timeline chỉ đọc từ backend, dùng để truy vết actor, trạng thái, version, policy, model và lý do của từng hành động." actions={<span className="readonly-label"><LockKeyhole /> Read-only</span>} />

    <form className="audit-lookup" onSubmit={submit}>
      <label htmlFor="audit-plan-id">Mã kế hoạch</label>
      <div><Search aria-hidden="true" /><input id="audit-plan-id" list="known-plans" value={lookup} onChange={event => setLookup(event.target.value)} placeholder="Nhập mã kế hoạch" /><button className="button button-primary" type="submit">Tra cứu</button></div>
      <datalist id="known-plans">{plans.map(plan => <option key={plan.planId} value={plan.planId}>{plan.title}</option>)}</datalist>
    </form>

    {!planId && <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Hồ sơ có quyền xem</p><h3>Chọn một kế hoạch</h3></div><span className="readonly-label">{plans.length} hồ sơ</span></div>{plans.length ? <div className="plan-link-list">{plans.slice(0, 10).map(plan => <Link key={plan.planId} to={`/audit?planId=${encodeURIComponent(plan.planId)}`}><span><strong>{plan.title || plan.planId}</strong><small>{plan.planId}</small></span><StatusBadge value={plan.state?.planStatus} /><ArrowRight /></Link>)}</div> : <StatePanel kind="empty" title="Chưa có hồ sơ để tra cứu" description="Actor hiện tại chưa có kế hoạch được cấp quyền đọc." />}</section>}

    {planId && <div className="audit-context"><Activity /><div><span>Đang xem audit cho</span><strong>{selectedPlan?.title || planId}</strong><small>{planId}</small></div></div>}
    {loading && <StatePanel kind="loading" title="Đang tải lịch sử" description="Đang đọc các event bất biến từ plan history." />}
    {error && <StatePanel kind="error" title="Không thể tải audit" description={error} />}
    {!loading && !error && planId && events.length === 0 && <StatePanel kind="empty" title="Chưa có audit event" description="Backend chưa trả về event nào cho kế hoạch này." />}
    {!loading && !error && events.length > 0 && <div className="audit-timeline">{events.map(event => <article className="audit-event" key={event.eventId}><div className="audit-event-marker" aria-hidden="true" /><div className="audit-event-body"><div className="audit-event-top"><div><span className="event-actor">{event.actorId || 'System'}</span><h3>{event.action.replaceAll('_', ' ')}</h3></div><time>{formatDateTime(event.timestamp)}</time></div><p className="event-reason">{event.reason || 'Backend không cung cấp lý do.'}</p><dl className="audit-meta"><div><dt>Input / version</dt><dd>{event.inputVersion || '—'}</dd></div><div><dt>Policy</dt><dd>{event.policyVersion || '—'}</dd></div><div><dt>Model</dt><dd>{event.modelVersion || '—'}</dd></div><div><dt>Correlation</dt><dd>{event.correlationId || '—'}</dd></div>{event.overrideReason && <div><dt>Override reason</dt><dd>{event.overrideReason}</dd></div>}{event.humanAction && <div><dt>Human action</dt><dd>{event.humanAction}</dd></div>}<div className="audit-state-change"><dt>Before</dt><dd>{formatState(event.previousState)}</dd><dt>After</dt><dd>{formatState(event.newState)}</dd></div></dl>{event.appliedRuleIds?.length ? <div className="rule-chip-list">{event.appliedRuleIds.map(rule => <Link key={rule} to={`/policy#${encodeURIComponent(rule)}`}>{rule}</Link>)}</div> : null}</div></article>)}</div>}
  </section>
}

function formatState(value: AuditEvent['newState']) {
  if (!value) return '—'
  return `${value.planStatus} · ${value.processingStage ?? '—'} · ${value.approvalRoundStatus ?? '—'}`
}
