import { BookOpenCheck, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import type { PolicyView } from '../types'

export function PolicyPage() {
  const services = useServices()
  const [policy, setPolicy] = useState<PolicyView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    services.policy.getCurrentPolicy().then(value => { if (active) setPolicy(value) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reload, services.policy])

  return <section className="policy-page">
    <PageHeader eyebrow="Policy snapshot" title="Chính sách phê duyệt" description="Cấu hình chỉ đọc do backend cung cấp cho phiên hiện tại. Giao diện không cho phép sửa threshold, rule hoặc hạn mức." actions={<span className="readonly-label"><LockKeyhole /> Read-only</span>} />
    {loading ? <StatePanel kind="loading" title="Đang tải policy" description="Đang đọc snapshot hiện hành từ /api/config." /> : error ? <StatePanel kind="error" title="Không thể tải policy" description={error} action={<button className="button button-secondary" onClick={() => setReload(value => value + 1)}><RefreshCw /> Thử lại</button>} /> : !policy ? <StatePanel kind="empty" title="Chưa có policy hiện hành" /> : <PolicyContent policy={policy} />}
  </section>
}

function PolicyContent({ policy }: { policy: PolicyView }) {
  return <div className="policy-content">
    <section className="policy-overview"><div className="policy-identity"><span><ShieldCheck /></span><div><p className="page-eyebrow">Phiên bản hiện hành</p><h3>{policy.policyName || 'Marketing approval policy'}</h3><strong>{policy.policyVersion}</strong></div></div><StatusBadge value={policy.status} /></section>
    <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Cấu hình</p><h3>Thông số backend cung cấp</h3></div><span className="readonly-label">API data</span></div>{policy.settings?.length ? <dl className="settings-grid">{policy.settings.map(setting => <div key={setting.label}><dt>{setting.label}</dt><dd>{setting.value}</dd></div>)}</dl> : <StatePanel kind="empty" title="Backend chưa cung cấp thông số policy" />}</section>
    <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Decision gates</p><h3>Rule IDs đang áp dụng</h3></div><span className="readonly-label"><BookOpenCheck /> {policy.rules.length} rules</span></div>{policy.rules.length ? <div className="policy-rule-list">{policy.rules.map((rule, index) => <article className="policy-rule" id={rule.ruleId} key={rule.ruleId}><span>{String(index + 1).padStart(2, '0')}</span><div><h4>{rule.title || rule.ruleId}</h4><p>{rule.description || 'API hiện chỉ cung cấp rule ID; mô tả chi tiết cần backend/API bổ sung.'}</p>{(rule.condition || rule.scope || rule.action || rule.effect) && <dl><dt>Điều kiện</dt><dd>{rule.condition || '—'}</dd><dt>Phạm vi</dt><dd>{rule.scope || '—'}</dd><dt>Hiệu lực</dt><dd>{rule.action || rule.effect || '—'}</dd></dl>}</div><Link to={`#${encodeURIComponent(rule.ruleId)}`} aria-label={`Neo tới rule ${rule.ruleId}`}>#</Link></article>)}</div> : <StatePanel kind="empty" title="Backend chưa cung cấp rule ID" />}</section>
  </div>
}
