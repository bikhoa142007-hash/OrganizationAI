import { Activity, ArrowLeft, ArrowRight, FileImage, History as HistoryIcon, Pencil, Play, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge, formatMoney } from '../components/ui'
import { api } from '../services/api/client'
import { history, type History } from '../services/api'
import { useServices } from '../services/ServiceProvider'
import { useSession } from '../services/SessionProvider'

const fieldLabels: Record<string, string> = {
  title: 'Tên chiến dịch', objective: 'Mục tiêu', summary: 'Tóm tắt / chiến lược', department: 'Phòng ban', checker_id: 'Checker', start_date: 'Ngày bắt đầu', end_date: 'Ngày kết thúc', budget_minor_units: 'Ngân sách', currency: 'Tiền tệ', target_audience: 'Đối tượng', channels: 'Kênh', kpi_expected: 'KPI', notes: 'Ghi chú', maker_id: 'Maker',
}

export function PlanDetailPage() {
  const { planId = '' } = useParams()
  const services = useServices()
  const { config, hasRole } = useSession()
  const [data, setData] = useState<History | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    setError('')
    history(planId).then(value => { if (active) setData(value) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)) })
    return () => { active = false }
  }, [planId, reload])

  async function resume() {
    setBusy(true); setError('')
    try { await services.plan.retryProcessing(planId, {}); setReload(value => value + 1) } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) } finally { setBusy(false) }
  }

  if (!data) return <StatePanel kind={error ? 'error' : 'loading'} title={error ? 'Không thể tải kế hoạch' : 'Đang tải kế hoạch'} description={error || 'Đang lấy payload, phiên bản và lịch sử từ backend.'} action={error ? <Link className="button button-secondary" to="/plans"><ArrowLeft /> Danh sách</Link> : undefined} />
  const plan = data.plan
  const canEdit = hasRole('MAKER') && plan.maker_id === config?.actor && ['DRAFT', 'REJECTED'].includes(plan.state.plan_status)
  const canContinue = plan.state.processing_stage === 'AI_PENDING'

  return <section className="detail-page">
    <PageHeader eyebrow={`Hồ sơ ${plan.plan_id}`} title={String(plan.payload.title || plan.plan_id)} description="Snapshot hiện tại, attachment riêng tư và toàn bộ lịch sử version/round mà backend cho phép truy cập." actions={<div className="button-row"><Link className="button button-secondary" to="/plans"><ArrowLeft /> Danh sách</Link>{canEdit && <Link className="button button-primary" to={`/plans/${planId}/edit`}>{plan.state.plan_status === 'REJECTED' ? <RotateCcw /> : <Pencil />} {plan.state.plan_status === 'REJECTED' ? 'Sửa và gửi lại' : 'Tiếp tục chỉnh sửa'}</Link>}</div>} />
    {error && <div className="alert alert-error" role="alert"><Activity /><div><strong>Không thể cập nhật dữ liệu</strong><p>{error}</p></div></div>}

    <div className="detail-summary">
      <div><span>Trạng thái</span><StatusBadge value={plan.state.plan_status} /></div>
      <div><span>Giai đoạn</span><StatusBadge value={plan.state.processing_stage} /></div>
      <div><span>Version / Round</span><strong>{plan.current_round || 'Draft'} / {plan.current_round || '—'}</strong></div>
      <div><span>Revision</span><strong>{plan.revision}</strong></div>
    </div>

    <div className="detail-actions">
      <Link className="button button-secondary" to={`/plans/${planId}/result`}><ArrowRight /> Xem kết quả</Link>
      <Link className="button button-secondary" to={`/audit?planId=${encodeURIComponent(planId)}`}><Activity /> Xem audit</Link>
      {canContinue && <button className="button button-primary" disabled={busy} onClick={() => void resume()}><Play /> {busy ? 'Đang tiếp tục...' : 'Tiếp tục evaluation đã submit'}</button>}
    </div>

    <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Nội dung hiện tại</p><h3>Thông tin kế hoạch</h3></div>{canEdit ? <span className="readonly-label">Working copy</span> : <span className="readonly-label">Chỉ đọc</span>}</div><dl className="definition-grid">{Object.entries(plan.payload).map(([key, value]) => <div key={key} className={key === 'summary' || key === 'notes' ? 'definition-wide' : ''}><dt>{fieldLabels[key] ?? key}</dt><dd>{formatPayloadValue(key, value, plan.payload.currency)}</dd></div>)}</dl></section>

    <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Attachment</p><h3>Ảnh riêng tư</h3></div><span className="readonly-label"><FileImage /> {plan.attachments.length} tệp</span></div>{plan.attachments.length ? <div className="attachment-grid">{plan.attachments.map(attachment => <PrivateImage key={attachment.attachment_id} planId={planId} attachmentId={attachment.attachment_id} mediaType={attachment.media_type} />)}</div> : <StatePanel kind="empty" title="Chưa có attachment" description="Kế hoạch cần ít nhất một ảnh trước khi gửi duyệt." />}</section>

    <section className="content-section" id="history"><div className="section-toolbar"><div><p className="page-eyebrow">Lịch sử bất biến</p><h3>Version và approval round</h3></div><span className="readonly-label"><HistoryIcon /> {data.versions.length} version</span></div><div className="history-list">{data.versions.length ? data.versions.map(version => <details key={version.plan_version}><summary><span>Version {version.plan_version} / Round {version.approval_round}</span><StatusBadge value={data.rounds.find(round => round.number === version.approval_round)?.decision_id ? 'CLOSED' : 'ACTIVE'} /></summary><dl className="definition-grid compact">{Object.entries(version.payload).map(([key, value]) => <div key={key}><dt>{fieldLabels[key] ?? key}</dt><dd>{formatPayloadValue(key, value, version.payload.currency)}</dd></div>)}</dl></details>) : <StatePanel kind="empty" title="Chưa có version đã gửi" description="Lưu draft không tạo version hoặc approval round." />}</div></section>

    <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Records</p><h3>Evaluation và quyết định</h3></div><span className="readonly-label">{data.records.length} bản ghi</span></div><div className="record-list">{data.records.length ? data.records.map((record, index) => <details key={`${record.kind}-${index}`}><summary><span>{record.kind.replaceAll('_', ' ')}</span><small>Round {String(record.body.approval_round ?? '—')}</small></summary><pre>{JSON.stringify(record.body, null, 2)}</pre></details>) : <StatePanel kind="empty" title="Chưa có evaluation record" />}</div></section>
  </section>
}

function PrivateImage({ planId, attachmentId, mediaType }: { planId: string; attachmentId: string; mediaType: string }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true, objectUrl = ''
    api.attachment(`/plans/${encodeURIComponent(planId)}/attachments/${encodeURIComponent(attachmentId)}`).then(blob => { if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) } }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)) })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attachmentId, planId])
  return <figure className="private-image">{error ? <StatePanel kind="error" title="Không tải được ảnh" description={error} /> : url ? <img src={url} alt={`Ảnh đã submit ${attachmentId}`} /> : <StatePanel kind="loading" title="Đang tải ảnh" />}<figcaption><strong>{attachmentId}</strong><span>{mediaType}</span></figcaption></figure>
}

function formatPayloadValue(key: string, value: unknown, currency: unknown) {
  if (key === 'budget_minor_units' && typeof value === 'string') return formatMoney(value, typeof currency === 'string' ? currency : 'VND')
  if (Array.isArray(value)) return value.join(', ') || '—'
  if (value == null || value === '') return '—'
  return typeof value === 'string' ? value : JSON.stringify(value)
}
