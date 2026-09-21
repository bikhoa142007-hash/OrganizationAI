import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import type { PolicyView } from '../types'

export function PolicyPage() {
  const services = useServices()
  const [policy, setPolicy] = useState<PolicyView | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function loadPolicy() {
      setIsLoading(true)
      setError(null)
      try {
        const nextPolicy = await services.policy.getCurrentPolicy()
        if (cancelled) return
        setPolicy(nextPolicy)
      } catch {
        if (!cancelled) {
          setPolicy(null)
          setError('Không thể tải policy từ service.')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void loadPolicy()
    return () => { cancelled = true }
  }, [reloadToken, services.policy])

  return (
    <section className="policy-page" aria-labelledby="policy-title">
      <div className="policy-header">
        <div>
          <Link className="back-link" to="/">← Quay lại Landing</Link>
          <span className="section-kicker">Màn 8 · Policy</span>
          <h2 id="policy-title">Policy</h2>
          <p>PolicyService cung cấp snapshot quy định để xem trong chế độ chỉ đọc.</p>
        </div>
        <span className="policy-readonly">Read-only</span>
      </div>

      {isLoading && <div className="policy-state" aria-live="polite"><span className="loading-spinner" aria-hidden="true" /><div><h3>Đang tải policy</h3><p>Đang chờ PolicyService cung cấp snapshot hiện tại.</p></div></div>}
      {!isLoading && error && <div className="policy-state policy-error" role="alert"><div><h3>Không thể tải policy</h3><p>{error}</p></div><button type="button" className="button button-secondary" onClick={() => setReloadToken((token) => token + 1)}>Thử lại</button></div>}
      {!isLoading && !error && !policy && <div className="policy-state"><div><h3>Chưa có policy hiện tại</h3><p>PolicyService chưa trả về snapshot để hiển thị.</p></div></div>}
      {!isLoading && !error && policy && <PolicyContent policy={policy} />}
    </section>
  )
}

function PolicyContent({ policy }: { policy: PolicyView }) {
  return (
    <div className="policy-content">
      <section className="policy-summary" aria-label="Thông tin policy">
        <div><span>Policy version</span><strong>{policy.policyVersion}</strong></div>
        <div><span>Tên policy</span><strong>{policy.policyName ?? 'Service không cung cấp'}</strong></div>
        <div><span>Trạng thái</span><strong>{policy.status ?? 'Service không cung cấp'}</strong></div>
        <div><span>Nguồn dữ liệu</span><strong>{policy.dataSource === 'MOCK' ? 'Mock service data' : 'Service data'}</strong></div>
      </section>
      <section className="policy-rules" aria-labelledby="policy-rules-title">
        <div className="policy-rules-heading"><div><span className="section-kicker">Rule list</span><h3 id="policy-rules-title">Quy định đang hiển thị</h3></div><span>{policy.rules.length} rule</span></div>
        {policy.rules.length === 0 ? <p className="policy-empty">PolicyService không trả về rule nào.</p> : (
          <div className="policy-rule-list">
            {policy.rules.map((rule) => (
              <article className="policy-rule" id={rule.ruleId} key={rule.ruleId}>
                <div className="policy-rule-heading"><div><span className="policy-rule-id">{rule.ruleId}</span><h4>{rule.title ?? rule.ruleId}</h4></div><a href={`#${rule.ruleId}`} aria-label={`Neo tới rule ${rule.ruleId}`}>#</a></div>
                <p>{rule.description ?? 'Service không cung cấp mô tả.'}</p>
                <dl className="policy-rule-meta">
                  {rule.condition && <><dt>Condition</dt><dd>{rule.condition}</dd></>}
                  {rule.scope && <><dt>Scope</dt><dd>{rule.scope}</dd></>}
                  {(rule.action || rule.effect) && <><dt>Action / effect</dt><dd>{rule.action ?? rule.effect}</dd></>}
                  {rule.reference && <><dt>Reference</dt><dd>{rule.reference}</dd></>}
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
