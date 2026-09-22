import { useActor } from '../components/DemoActor'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../services/api/client'
import { history, type History } from '../services/api'
import { useServices } from '../services/ServiceProvider'

export function PlanDetailPage() {
  const actor = useActor()
  const { planId = '' } = useParams(), services = useServices()
  const [data, setData] = useState<History | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { let active = true; history(planId).then(h => { if (active) setData(h) }).catch(e => { if (active) setError(String(e)) }); return () => { active = false } }, [planId])
  async function resume() { setBusy(true); try { await services.plan.retryProcessing(planId, {}); setData(await history(planId)) } catch (e) { setError(String(e)) } finally { setBusy(false) } }
  if (!data) return <p role={error ? 'alert' : 'status'}>{error || 'Đang tải hồ sơ…'}</p>
  const p = data.plan
  return <section className="result-page"><Link to="/plans">← Danh sách</Link><h2>{String(p.payload.title || p.plan_id)}</h2><p>{p.state.plan_status} · Version {p.current_round || 'Draft'} / Round {p.current_round || '—'}</p>
    {error && <p role="alert">{error}</p>}<div className="result-actions">
      {actor?.actor === p.maker_id && actor.roles.includes('MAKER') && ['DRAFT', 'REJECTED'].includes(p.state.plan_status) && <Link className="button button-primary" to={`/plans/${planId}/edit`}>Sửa và gửi lại</Link>}
      <Link to={`/plans/${planId}/result`}>Kết quả</Link><Link to={`/audit?planId=${encodeURIComponent(planId)}`}>Audit</Link>
      {p.state.processing_stage === 'AI_PENDING' && <button disabled={busy} onClick={() => void resume()}>Tiếp tục evaluation đã submit</button>}
    </div><dl className="review-meta">{Object.entries(p.payload).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd></div>)}</dl>
    <h3>Ảnh riêng tư</h3>{p.attachments.map(a => <PrivateImage key={a.attachment_id} planId={planId} attachmentId={a.attachment_id} />)}
    <h3>Phiên bản đã gửi (chỉ đọc)</h3>{data.versions.map(v => <details key={v.plan_version}><summary>Version {v.plan_version} / Round {v.approval_round}</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(v.payload, null, 2)}</pre></details>)}
    <h3>Kết quả và quyết định từng vòng</h3>{data.records.map((r, i) => <details key={i}><summary>{r.kind} · Round {String(r.body.approval_round)}</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(r.body, null, 2)}</pre></details>)}
  </section>
}

function PrivateImage({ planId, attachmentId }: { planId: string; attachmentId: string }) {
  const [url, setUrl] = useState(''), [error, setError] = useState('')
  useEffect(() => {
    let active = true, objectUrl = ''
    api.attachment(`/plans/${encodeURIComponent(planId)}/attachments/${encodeURIComponent(attachmentId)}`).then(blob => {
      if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) }
    }).catch(e => { if (active) setError(String(e)) })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [planId, attachmentId])
  return error ? <p role="alert">{error}</p> : url ? <img src={url} alt={`Ảnh đã submit ${attachmentId}`} style={{ maxWidth: '100%', maxHeight: 360 }} /> : <p>Đang tải ảnh…</p>
}
