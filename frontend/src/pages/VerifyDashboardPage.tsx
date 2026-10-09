import { AlertCircle, CheckCircle2, ChevronRight, Clock3, FlaskConical, Play, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge, formatDateTime } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import type { VerifyResultRow, VerifyRun, VerifySuite } from '../types'

const suiteCounts: Record<VerifySuite, number> = { general: 4, escalation: 5, regression: 15 }

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
    <PageHeader eyebrow="Công cụ QA / Judge" title="Verify workflow" description="Mỗi lần bấm sẽ chạy lại workflow tổng hợp qua backend, rồi so sánh kết quả thực tế với expected. Timeout hoặc lỗi luôn là FAIL/ERROR." actions={<button className="button button-primary" type="button" onClick={() => void start()} disabled={starting}><Play /> {starting ? 'Đang chạy...' : `Run ${suiteCounts[suite]} cases`}</button>} />

    <div className="verify-notice"><FlaskConical /><div><strong>Chấm thử không cần đăng ký hoặc đăng nhập</strong><p>Verify chỉ dùng dữ liệu tổng hợp trong workflow SQLite riêng cho từng case. Provider được gắn nhãn Mock; đây không phải inference thật và không dùng kết quả seed cũ.</p><p>Nhập ca mới bằng cách chọn actor Maker rồi tạo kế hoạch tổng hợp trong Judge Demo. Dữ liệu này nằm ở SQLite demo riêng, không vào hồ sơ Auth/PostgreSQL.</p><Link className="button button-secondary" to="/demo/plans/new">Nhập kế hoạch tổng hợp mới</Link></div></div>

    <ol className="verify-first-use"><li>Chạy Verify chung với 4 ca.</li><li>Chạy Verify → Escalation với 5 ca.</li><li>Dùng bộ hồi quy 15 ca để rà ba nhóm chuyển tiếp và điều kiện biên.</li><li>Mở từng ca để xem expected, actual, bằng chứng và câu hỏi chuyển tiếp.</li></ol>

    <div className="segmented-control" aria-label="Chọn Verify suite">
      <button type="button" aria-pressed={suite === 'general'} className={suite === 'general' ? 'active' : ''} onClick={() => { setSuite('general'); setRun(null); setSelectedCaseId('') }}>Verify chung · 4 ca</button>
      <button type="button" aria-pressed={suite === 'escalation'} className={suite === 'escalation' ? 'active' : ''} onClick={() => { setSuite('escalation'); setRun(null); setSelectedCaseId('') }}>Verify → Escalation · 5 ca</button>
      <button type="button" aria-pressed={suite === 'regression'} className={suite === 'regression' ? 'active' : ''} onClick={() => { setSuite('regression'); setRun(null); setSelectedCaseId('') }}>Bộ hồi quy tổng hợp · 15 ca</button>
    </div>

    {starting && <StatePanel kind="loading" title={`Đang chạy ${suiteCounts[suite]} ca`} description="Backend thực thi từng case trong database in-memory mới." />}
    {error && <StatePanel kind="error" title="Verify không hoàn tất" description={error} action={<button className="button button-secondary" onClick={() => void start()}>Chạy lại</button>} />}
    {!run && !starting && !error && <StatePanel kind="empty" title="Chưa có lần chạy" description="Chọn một bộ Verify rồi bấm Run. Kết quả chỉ xuất hiện sau khi backend thực thi case." />}
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
  return <aside className="verify-detail" aria-labelledby="verify-detail-title"><div className="verify-detail-heading"><span className={`detail-result status-${row.status === 'PASS' ? 'success' : 'danger'}`}><Icon /></span><div><p className="page-eyebrow">Case detail</p><h3 id="verify-detail-title">{row.caseName || row.caseId}</h3><small>{row.caseId}</small></div><button className="button button-secondary" type="button" onClick={onClose}>Đóng</button></div><dl className="definition-grid compact"><div><dt>Expected</dt><dd>{formatOutcome(row.expectedAction, row.expectedCategory)}</dd></div><div><dt>Actual</dt><dd>{formatOutcome(row.actualAction, row.actualCategory)}</dd></div><div><dt>Result</dt><dd><StatusBadge value={row.status} /></dd></div><div><dt>Timestamp</dt><dd>{formatDateTime(row.completedAt)}</dd></div><div><dt>Duration</dt><dd>{row.durationMs == null ? 'API chưa cung cấp' : `${row.durationMs} ms`}</dd></div><div><dt>Policy version</dt><dd>{row.policyVersion || 'Không có kết quả hợp lệ'}</dd></div><div><dt>Data class</dt><dd>{row.dataClassification || 'SYNTHETIC'}</dd></div><div className="definition-wide"><dt>Lý do</dt><dd>{row.reason || row.error?.message || 'Backend chưa cung cấp'}</dd></div></dl>
    {row.input && <section className="verify-evidence"><h4>Dữ liệu đã chạy</h4><pre>{row.input}</pre></section>}
    {row.evidence?.length ? <section className="verify-evidence"><h4>Bằng chứng evaluation</h4><ul>{row.evidence.map((item, index) => <li key={`${item.reference ?? 'evidence'}-${index}`}><strong>{item.reference || item.kind || `Evidence ${index + 1}`}</strong>{item.kind && item.reference && <span> · {item.kind}</span>}{item.observation && <p>{item.observation}</p>}</li>)}</ul></section> : null}
    {row.generatedQuestion?.length ? <section className="verify-escalation-questions" aria-label="Câu hỏi chuyển tiếp"><h4>Câu hỏi cần người xử lý trả lời</h4>{row.generatedQuestion.map((question, index) => <article key={`${question.category}-${index}`}><strong>{question.category || row.actualCategory || 'HUMAN_REVIEW_REQUIRED'}</strong><p>{question.question}</p>{question.disputedOrMissingFact && <p><b>Thông tin cần xác định:</b> {question.disputedOrMissingFact}</p>}{question.applicableRuleOrLimit && <p><b>Quy định/giới hạn:</b> {question.applicableRuleOrLimit}</p>}{question.reason && <p><b>Lý do chuyển tiếp:</b> {question.reason}</p>}{question.evidenceReferences?.length ? <p><b>Bằng chứng liên quan:</b> {question.evidenceReferences.map(reference => <code key={reference}>{reference}</code>)}</p> : null}</article>)}</section> : row.actualAction === 'HUMAN_REVIEW_REQUIRED' && <section className="verify-escalation-questions"><h4>Câu hỏi chuyển tiếp</h4><p>Backend không trả về câu hỏi cụ thể; case này không đạt Verify.</p></section>}
    {row.modelVersion && <p className="detail-timestamp">Model version: {row.modelVersion}</p>}{row.auditReference && <p className="detail-timestamp">Audit reference: {row.auditReference}</p>}
    {row.appliedRuleIds?.length ? <div className="rule-chip-list">{row.appliedRuleIds.map(rule => <Link key={rule} to={`/policy#${encodeURIComponent(rule)}`}>{rule}</Link>)}</div> : null}<p className="detail-timestamp"><Clock3 /> {formatDateTime(row.completedAt)}</p></aside>
}

function formatOutcome(action: VerifyResultRow['actualAction'], category?: string | null) {
  if (!action) return 'Không có outcome'
  return category ? `${action} · ${category}` : action
}
