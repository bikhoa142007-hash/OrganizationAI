import { useActor } from '../components/DemoActor'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import type { PlanView } from '../types'

export function PlansPage() {
  const services = useServices(), actor = useActor()
  const [plans, setPlans] = useState<PlanView[]>([]), [error, setError] = useState(''), [loading, setLoading] = useState(true)
  useEffect(() => { let active = true; services.plan.listPlans().then(p => { if (active) setPlans(p) }).catch(e => { if (active) setError(String(e)) }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [services.plan])
  return <section><h2>Danh sách kế hoạch</h2>{actor?.roles.includes('MAKER') && <Link className="button button-primary" to="/plans/new">Hồ sơ mới</Link>}
    {loading && <p role="status">Đang tải…</p>}{error && <p role="alert">{error}</p>}
    {!loading && !error && !plans.length && <p>Chưa có hồ sơ cho actor này.</p>}
    <div className="review-table-wrap"><table className="review-table"><thead><tr><th>Kế hoạch</th><th>Trạng thái</th><th>Version / round</th></tr></thead><tbody>{plans.map(p => <tr key={p.planId}><td><Link to={`/plans/${p.planId}`}>{p.title || p.planId}</Link></td><td>{p.state?.planStatus}</td><td>{p.planVersion ?? 'Draft'} / {p.approvalRound ?? '—'}</td></tr>)}</tbody></table></div>
  </section>
}
