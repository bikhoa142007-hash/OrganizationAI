import { AlertCircle, CheckCircle2, ChevronRight, Clock3, FlaskConical, Play, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge, formatDateTime } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import type { VerifyResultRow, VerifyRun, VerifySuite } from '../types'

export function VerifyDashboardPage() {
  const services = useServices()
  const [suite, setSuite] = useState<VerifySuite>('general')
  const [run, setRun] = useState<VerifyRun | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const selected = useMemo(() => run?.rows.find(row => row.caseId === selectedCaseId) ?? null, [run, selectedCaseId])

  async function start() {
    setStarting(true); setError(''); setRun(null); setSelectedCaseId('')
    try { setRun(await services.verify.startRun(suite)) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể bắt đầu Verify từ service.') } finally { setStarting(false) }
  }

  return <section className="verify-page">
    <PageHeader eyebrow="Công cụ QA / Judge" title="Verify workflow" description="Chạy fixture qua workflow/API thật rồi so sánh actual với expected. Kết quả timeout hoặc lỗi không bao giờ được hiển thị là PASS." actions={<button className="button button-primary" type="button" onClick={() => void start()} disabled={starting}><Play /> {starting ? 'Đang chạy...' : suite === 'general' ? 'Run all 5' : 'Run 15 regressions'}</button>} />

    <div className="verify-notice"><FlaskConical /><div><strong>Không phải màn hình nghiệp vụ người dùng cuối</strong><p>Khu vực này phục vụ kiểm thử hệ thống trong môi trường demo. API hiện cho phép mọi demo actor đã xác thực chạy suite.</p></div></div>

    <div className="segmented-control" aria-label="Chọn Verify suite">
      <button className={suite === 'general' ? 'active' : ''} onClick={() => { setSuite('general'); setRun(null); setSelectedCaseId('') }}>General · 5 case</button>
      <button className={suite === 'escalation' ? 'active' : ''} onClick={() => { setSuite('escalation'); setRun(null); setSelectedCaseId('') }}>Escalation regression · 15 case</button>
    </div>

    {starting && <StatePanel kind="loading" title={`Đang chạy ${suite === 'general' ? '5' : '15'} case`} description="API hiện trả kết quả sau khi suite hoàn tất. Không có progress từng case từ backend." />}
    {error && <StatePanel kind="error" title="Verify không hoàn tất" description={error} action={<button className="button button-secondary" onClick={() => void start()}>Chạy lại</button>} />}
    {!run && !starting && !error && <StatePanel kind="empty" title="Chưa có lần chạy" description="Chọn suite và bắt đầu. Màn hình không đặt sẵn kết quả PASS." />}
    {run && <RunContent run={run} selected={selected} onSelect={setSelectedCaseId} />}
  </section>
}

function RunContent({ run, selected, onSelect }: { run: VerifyRun; selected: VerifyResultRow | null; onSelect: (value: string) => void }) {
  const summary = run.summary
  const passed = summary?.passedCases ?? run.rows.filter(row => row.pass).length
  const total = summary?.totalCases ?? run.rows.length
  return <div className="verify-layout">
    <section className="verify-summary">
      <div className="verify-score"><span className={passed === total ? 'score-success' : 'score-warning'}>{passed}/{total} PASS</span><div><StatusBadge value={run.status} /><small>Run ID: {run.runId}</small></div></div>
      <dl><div><dt>Suite</dt><dd>{run.suite}</dd></div><div><dt>Bắt đầu</dt><dd>{formatDateTime(run.startedAt)}</dd></div><div><dt>Hoàn tất</dt><dd>{formatDateTime(run.completedAt)}</dd></div><div><dt>FAIL / ERROR</dt><dd>{summary?.failedCases ?? 0} / {summary?.errorCases ?? 0}</dd></div></dl>
    </section>

    <section className="content-section"><div className="section-toolbar"><div><p className="page-eyebrow">Actual vs expected</p><h3>Kết quả từng case</h3></div><span className="readonly-label">{run.rows.length} case</span></div><div className="data-table-wrap"><table className="data-table verify-table"><thead><tr><th>Case</th><th>Expected</th><th>Actual</th><th>Result</th><th>Lý do</th><th></th></tr></thead><tbody>{run.rows.map(row => <tr key={row.caseId}><td data-label="Case"><strong>{row.caseName || row.caseId}</strong><small>{row.caseId}</small></td><td data-label="Expected">{formatOutcome(row.expectedAction, row.expectedCategory)}</td><td data-label="Actual">{formatOutcome(row.actualAction, row.actualCategory)}</td><td data-label="Result"><StatusBadge value={row.status} /></td><td data-label="Lý do" className="reason-cell">{row.reason || row.error?.message || 'Backend chưa cung cấp'}</td><td><button className="icon-button subtle" aria-label={`Chi tiết ${row.caseId}`} onClick={() => onSelect(row.caseId)}><ChevronRight /></button></td></tr>)}</tbody></table></div></section>
    {selected && <VerifyDetail row={selected} onClose={() => onSelect('')} />}
  </div>
}

function VerifyDetail({ row, onClose }: { row: VerifyResultRow; onClose: () => void }) {
  const Icon = row.status === 'PASS' ? CheckCircle2 : row.status === 'ERROR' ? AlertCircle : XCircle
  return <aside className="verify-detail" aria-labelledby="verify-detail-title"><div className="verify-detail-heading"><span className={`detail-result status-${row.status === 'PASS' ? 'success' : 'danger'}`}><Icon /></span><div><p className="page-eyebrow">Case detail</p><h3 id="verify-detail-title">{row.caseName || row.caseId}</h3><small>{row.caseId}</small></div><button className="button button-secondary" type="button" onClick={onClose}>Đóng</button></div><dl className="definition-grid compact"><div><dt>Expected</dt><dd>{formatOutcome(row.expectedAction, row.expectedCategory)}</dd></div><div><dt>Actual</dt><dd>{formatOutcome(row.actualAction, row.actualCategory)}</dd></div><div><dt>Result</dt><dd><StatusBadge value={row.status} /></dd></div><div><dt>Timestamp</dt><dd>{formatDateTime(row.completedAt)}</dd></div><div><dt>Duration</dt><dd>{row.durationMs == null ? 'API chưa cung cấp' : `${row.durationMs} ms`}</dd></div><div className="definition-wide"><dt>Lý do</dt><dd>{row.reason || row.error?.message || 'API chưa cung cấp'}</dd></div></dl>{row.appliedRuleIds?.length ? <div className="rule-chip-list">{row.appliedRuleIds.map(rule => <Link key={rule} to={`/policy#${encodeURIComponent(rule)}`}>{rule}</Link>)}</div> : null}<p className="detail-timestamp"><Clock3 /> {formatDateTime(row.completedAt)}</p></aside>
}

function formatOutcome(action: VerifyResultRow['actualAction'], category?: string | null) {
  if (!action) return 'Không có outcome'
  return category ? `${action} · ${category}` : action
}
