import { Activity, AlertTriangle, ArrowLeft, ArrowRight, BookOpenCheck, Bot, CheckCircle2, ClipboardCheck, FileImage, Gauge, Scale, ShieldCheck, UserCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge, formatMoney } from '../components/ui'
import { api } from '../services/api/client'
import { useServices } from '../services/ServiceProvider'
import type { ResultView } from '../types'

export function ResultPage() {
  const { planId = '' } = useParams<{ planId: string }>()
  const services = useServices()
  const [result, setResult] = useState<ResultView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    services.plan.getResult(planId).then(value => { if (active) { setResult(value); if (!value) setError('Backend chưa có kết quả cho hồ sơ này.') } }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [planId, services.plan])
  if (loading) return <StatePanel kind="loading" title="Đang tải kết quả" description="Đang lấy evaluation, decision, evidence và policy metadata từ backend." />
  if (error || !result) return <StatePanel kind="error" title="Không có dữ liệu kết quả" description={error || 'Service không trả về snapshot kết quả.'} action={<Link className="button button-secondary" to={`/plans/${planId}`}><ArrowLeft /> Chi tiết hồ sơ</Link>} />
  return <ResultContent result={result} />
}

function ResultContent({ result }: { result: ResultView }) {
  const isReview = result.variant === 'HUMAN_REVIEW'
  const isError = result.variant === 'ERROR'
  const ResultIcon = isError ? AlertTriangle : isReview ? ClipboardCheck : result.variant === 'HUMAN_DECISION' ? UserCheck : CheckCircle2
  return <section className="result-page">
    <PageHeader eyebrow={`Kết quả · ${result.planId}`} title={result.title} description="Kết quả bên dưới là snapshot do backend lưu. Frontend không tự suy luận hoặc thay đổi outcome." actions={<Link className="button button-secondary" to={`/plans/${result.planId}`}><ArrowLeft /> Chi tiết hồ sơ</Link>} />

    <section className={`decision-banner decision-${result.variant.toLowerCase()}`}>
      <span className="decision-icon"><ResultIcon /></span>
      <div><p className="page-eyebrow">Kết quả chính</p><h3>{result.statusLabel}</h3><p>{result.reason || (isReview ? 'Kế hoạch đang chờ người có thẩm quyền thẩm định.' : 'Backend chưa cung cấp diễn giải.')}</p></div>
      <StatusBadge value={isReview ? 'HUMAN_REVIEW_REQUIRED' : isError ? 'ERROR' : 'APPROVED'} />
    </section>

    {result.decisionSource && <section className="decision-source"><span>{result.variant === 'HUMAN_DECISION' ? <UserCheck /> : <Bot />}</span><div><small>Nguồn quyết định</small><strong>{result.decisionSource}</strong></div></section>}
    {result.reviewDetails && <section className="review-callout"><ClipboardCheck /><div><strong>Cần Human Review</strong><p>{result.reviewDetails.question || 'Backend chưa cung cấp câu hỏi chuyển tiếp.'}</p><span>Người/cấp xử lý: {result.reviewDetails.authority || 'Chưa được cung cấp'}</span></div></section>}

    <div className="result-layout">
      <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Đánh giá</p><h3>Score và confidence</h3></div><Gauge /></div><dl className="metric-list"><div><dt>Feasibility score</dt><dd>{result.score == null ? 'Chưa có dữ liệu' : result.score}</dd></div><div><dt>Confidence</dt><dd>{result.confidence == null ? 'Chưa có dữ liệu' : `${Math.round(result.confidence * 100)}%`}</dd></div><div><dt>Media</dt><dd>{result.media?.status || 'Chưa có dữ liệu'}</dd></div></dl></section>
      <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Ngân sách</p><h3>Giá trị và hạn mức</h3></div><Scale /></div><dl className="metric-list"><div><dt>Ngân sách</dt><dd>{formatMoney(result.budget?.value)}</dd></div><div><dt>Hạn mức áp dụng</dt><dd>{formatMoney(result.budget?.limit)}</dd></div></dl></section>
      <section className="content-section result-wide"><div className="section-toolbar"><div><p className="page-eyebrow">Evidence</p><h3>Bằng chứng đã lưu</h3></div><ShieldCheck /></div>{result.evidence?.length ? <div className="evidence-list">{result.evidence.map(item => <article key={item.id}><span>{item.label}</span><p>{item.value}</p><small>{item.id}</small></article>)}</div> : <StatePanel kind="empty" title="Backend chưa cung cấp evidence" />}</section>
      <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Rules</p><h3>Applied rule IDs</h3></div><BookOpenCheck /></div>{result.ruleIds?.length ? <div className="rule-chip-list">{result.ruleIds.map(rule => <Link key={rule} to={`/policy#${encodeURIComponent(rule)}`}>{rule}</Link>)}</div> : <p className="secondary-text">Backend chưa cung cấp rule ID.</p>}</section>
      <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Phiên bản</p><h3>Policy và model</h3></div><Bot /></div><dl className="metric-list"><div><dt>Policy</dt><dd>{result.policyVersion || 'Chưa có dữ liệu'}</dd></div><div><dt>Model</dt><dd>{result.modelVersion || 'Chưa có dữ liệu'}</dd></div></dl></section>
      {result.media?.attachments?.length ? <section className="content-section result-wide"><div className="section-toolbar"><div><p className="page-eyebrow">Attachment</p><h3>Ảnh đã đánh giá</h3></div><FileImage /></div><div className="attachment-grid">{result.media.attachments.map(id => <ResultAttachment key={id} planId={result.planId} attachmentId={id} />)}</div></section> : null}
    </div>

    <footer className="result-footer"><Link className="button button-secondary" to={`/audit?planId=${encodeURIComponent(result.planId)}`}><Activity /> Xem audit</Link>{result.actions?.filter(action => action.href && !action.href.startsWith('/audit')).map(action => <Link key={action.id} className="button button-primary" to={action.href!}>{action.label}<ArrowRight /></Link>)}</footer>
  </section>
}

function ResultAttachment({ planId, attachmentId }: { planId: string; attachmentId: string }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let active = true, objectUrl = ''
    api.attachment(`/plans/${encodeURIComponent(planId)}/attachments/${encodeURIComponent(attachmentId)}`).then(blob => { if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) } }).catch(() => undefined)
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attachmentId, planId])
  return <figure className="private-image">{url ? <img src={url} alt={`Ảnh đánh giá ${attachmentId}`} /> : <StatePanel kind="loading" title="Đang tải ảnh" />}<figcaption><strong>{attachmentId}</strong><span>Private attachment</span></figcaption></figure>
}
