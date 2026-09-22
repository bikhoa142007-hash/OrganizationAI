import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import type { ResultView } from '../types'

export function ResultPage() {
  const { planId: routePlanId } = useParams<{ planId: string }>()
  const services = useServices()
  const [result, setResult] = useState<ResultView | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadResult() {
      setIsLoading(true)
      setLoadError(null)
      try {
        const nextResult = await services.plan.getResult(routePlanId ?? '')
        if (cancelled) return
        setResult(nextResult)
        if (!nextResult) setLoadError('Service chưa cung cấp kết quả cho hồ sơ này.')
      } catch {
        if (!cancelled) setLoadError('Không thể tải kết quả từ service.')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void loadResult()
    return () => { cancelled = true }
  }, [routePlanId, services.plan])

  if (isLoading) return <section className="result-page result-loading" aria-live="polite"><span className="loading-spinner" aria-hidden="true" /><div><span className="section-kicker">Kết quả</span><h2>Đang tải snapshot kết quả</h2><p>Đang chờ service cung cấp dữ liệu.</p></div></section>
  if (loadError || !result) return <section className="result-page result-error" role="alert"><span className="section-kicker">Kết quả</span><h2>Không có dữ liệu kết quả</h2><p>{loadError ?? 'Service không trả về snapshot kết quả.'}</p><div className="result-actions"><Link className="button button-secondary" to="/">Về Landing</Link></div></section>

  return <ResultContent result={result} />
}

function ResultContent({ result }: { result: ResultView }) {
  const isError = result.variant === 'ERROR'
  return (
    <section className="result-page" aria-labelledby="result-title">
      <div className="result-header">
        <div>
          <Link className="back-link" to="/">← Quay lại Landing</Link>
          <span className="section-kicker">Hồ sơ {result.planId}</span>
          <h2 id="result-title">{result.title}</h2>
          <p className="result-status">{result.statusLabel}</p>
        </div>
        <span className={`result-variant result-variant-${result.variant.toLowerCase()}`}>{variantLabel(result.variant)}</span>
      </div>

      {isError && result.error && <section className="result-section result-error-box" role="alert"><h3>Lỗi từ service</h3><p>{result.error.message}</p><small>Mã: {result.error.code}</small></section>}
      {result.decisionSource && <section className="result-section result-primary"><h3>Quyết định cuối cùng</h3><p>{result.decisionSource}</p></section>}
      {result.reviewDetails && <section className="result-section"><h3>Human review</h3><dl className="result-meta">{result.reviewDetails.question && <><dt>Trạng thái</dt><dd>{result.reviewDetails.question}</dd></>}{result.reviewDetails.authority && <><dt>Authority</dt><dd>{result.reviewDetails.authority}</dd></>}</dl></section>}
      <div className="result-grid">
        {(result.score != null || result.confidence != null) && <section className="result-section"><h3>Chỉ số từ service</h3><dl className="result-meta">{result.score != null && <><dt>Score</dt><dd>{result.score}</dd></>}{result.confidence != null && <><dt>Confidence</dt><dd>{result.confidence}</dd></>}</dl></section>}
        {result.media && <section className="result-section"><h3>Media / attachment</h3><p>{result.media.status}</p>{result.media.attachments?.length ? <ul>{result.media.attachments.map((attachment) => <li key={attachment}>{attachment}</li>)}</ul> : <p>Service không cung cấp attachment.</p>}</section>}
        {result.budget && <section className="result-section"><h3>Budget / limit</h3><dl className="result-meta">{result.budget.value && <><dt>Giá trị</dt><dd>{result.budget.value}</dd></>}{result.budget.limit && <><dt>Giới hạn</dt><dd>{result.budget.limit}</dd></>}</dl></section>}
        {result.ruleIds?.length ? <section className="result-section"><h3>Rule IDs</h3><ul>{result.ruleIds.map((ruleId) => <li key={ruleId}>{ruleId}</li>)}</ul></section> : null}
        {result.evidence?.length ? <section className="result-section result-evidence"><h3>Evidence</h3><dl className="result-meta">{result.evidence.map((item) => <div key={item.id}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl></section> : null}
        {result.reason && <section className="result-section"><h3>Reason</h3><p>{result.reason}</p></section>}
        {(result.policyVersion || result.modelVersion) && <section className="result-section"><h3>Version</h3><dl className="result-meta">{result.policyVersion && <><dt>Policy</dt><dd>{result.policyVersion}</dd></>}{result.modelVersion && <><dt>Model</dt><dd>{result.modelVersion}</dd></>}</dl></section>}
      </div>
      <div className="result-actions"><Link className="button button-secondary" to="/">Về Landing</Link>{result.actions?.filter((action) => action.href !== '/' && action.label !== 'Về Landing').map((action) => action.href ? <Link key={action.id} className="button button-primary" to={action.href}>{action.label}</Link> : <button key={action.id} className="button button-primary" type="button">{action.label}</button>)}</div>
    </section>
  )
}

function variantLabel(variant: ResultView['variant']) {
  if (variant === 'SYSTEM_DECISION') return 'System decision'
  if (variant === 'HUMAN_REVIEW') return 'Chờ Checker · chưa có quyết định cuối'
  if (variant === 'HUMAN_DECISION') return 'Quyết định của Checker'
  return 'Error'
}
