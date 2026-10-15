import { AlertCircle, CheckCircle2, ChevronRight, Clock3, FlaskConical, Play, XCircle } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge, formatDateTime } from '../components/ui'
import { publicJudgeService, type PublicJudgeInputResult } from '../services/publicJudgeService'
import { useServices } from '../services/ServiceProvider'
import type { VerifyResultRow, VerifyRun, VerifySuite } from '../types'
import './VerifyDashboardPage.css'

const suiteCounts: Record<VerifySuite, number> = { general: 4, escalation: 5, regression: 15 }

const inputDefaults = {
  title: 'Synthetic campaign',
  department: 'DEMO-DEPT-01',
  objective: 'Reach a defined demo audience',
  summary: 'A short synthetic plan for checking the Judge input path.',
  targetAudience: 'Synthetic audience',
  channel: 'DEMO_SOCIAL',
  currency: 'VND',
  budgetVnd: '50000000',
  sourceBudgetVnd: '50000000',
}

export function VerifyDashboardPage({ mode = 'demo' }: { mode?: 'demo' | 'public' }) {
  const isPublic = mode === 'public'
  const services = useServices()
  const [suite, setSuite] = useState<VerifySuite>('general')
  const [run, setRun] = useState<VerifyRun | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [inputForm, setInputForm] = useState(inputDefaults)
  const [inputRun, setInputRun] = useState<PublicJudgeInputResult | null>(null)
  const [inputStarting, setInputStarting] = useState(false)
  const [inputError, setInputError] = useState('')
  const selected = useMemo(() => run?.rows.find(row => row.caseId === selectedCaseId) ?? null, [run, selectedCaseId])

  async function start() {
    setStarting(true); setError(''); setRun(null); setSelectedCaseId('')
    try {
      let result: VerifyRun
      if (isPublic) {
        if (suite === 'regression') throw new Error('Public Judge does not expose the regression suite.')
        result = await publicJudgeService.startRun(suite)
      } else result = await services.verify.startRun(suite)
      setRun(result)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thể bắt đầu Verify từ service.') } finally { setStarting(false) }
  }

  async function evaluateInput(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setInputStarting(true); setInputError(''); setInputRun(null)
    try {
      setInputRun(await publicJudgeService.evaluateInput({
        title: inputForm.title,
        department: inputForm.department,
        objective: inputForm.objective,
        summary: inputForm.summary,
        target_audience: inputForm.targetAudience,
        channel: inputForm.channel,
        currency: inputForm.currency,
        budget_vnd: Number(inputForm.budgetVnd),
        source_budget_vnd: inputForm.sourceBudgetVnd === '' ? null : Number(inputForm.sourceBudgetVnd),
      }))
    } catch (reason) {
      setInputError(reason instanceof Error ? reason.message : 'Không thể đánh giá đầu vào mới.')
    } finally { setInputStarting(false) }
  }

  function updateInput(field: keyof typeof inputDefaults, value: string) {
    setInputForm(current => ({ ...current, [field]: value }))
  }

  return <section className="verify-page">
    <PageHeader eyebrow={isPublic ? 'Challenge A / Public Judge' : 'Challenge A / Judge Demo'} title={isPublic ? 'Verify workflow' : 'Verify workflow · Demo'} description={isPublic ? 'Mỗi lần bấm chạy workflow tổng hợp mới qua backend và đối chiếu expected do server giữ. Timeout không chứng minh server đã dừng; Judge không có thao tác stop hoặc undo.' : 'Chạy bộ fixture trong Judge Demo hiện có. Kết quả MOCK chỉ xác nhận demo workflow, không phải public acceptance hoặc inference thật.'} actions={<button className="button button-primary" type="button" onClick={() => void start()} disabled={starting}><Play /> {starting ? 'Đang chạy...' : `Run ${suiteCounts[suite]} cases`}</button>} />

    {isPublic
      ? <div className="verify-notice"><FlaskConical /><div><strong>Judge công khai, không cần tạo tài khoản</strong><p>Verify chạy dữ liệu SYNTHETIC trong workflow in-memory riêng cho từng ca. Provider là MOCK; đây không phải inference thật và không đọc Auth, tài khoản hay dữ liệu production.</p><p>Đầu vào mới được gắn USER_SUPPLIED_UNVERIFIED, xử lý trong request rồi bỏ; không nhập dữ liệu cá nhân hoặc bí mật. Mô phỏng này không đo chất lượng AI và không ghi nhận một phê duyệt thật.</p></div></div>
      : <div className="verify-notice"><FlaskConical /><div><strong>Judge Demo · MOCK — không phải public acceptance</strong><p>Giữ nguyên Verify service và suite hiện có cho route demo. Dữ liệu và kết quả ở đây chỉ kiểm tra workflow demo, không chứng minh inference thật hoặc public Judge đã được triển khai.</p><Link className="button button-secondary" to="/demo/plans/new">Nhập kế hoạch tổng hợp mới</Link></div></div>}

    <p className="verify-first-use">{isPublic ? 'Bước đầu tiên: bấm “Run 4 cases” để chạy Verify chung.' : `Bước đầu tiên: bấm “Run ${suiteCounts[suite]} cases” để chạy Judge Demo.`}</p>

    <div className="segmented-control" aria-label="Chọn Verify suite">
      <button type="button" aria-pressed={suite === 'general'} className={suite === 'general' ? 'active' : ''} onClick={() => { setSuite('general'); setRun(null); setSelectedCaseId('') }}>Verify chung · 4 ca</button>
      <button type="button" aria-pressed={suite === 'escalation'} className={suite === 'escalation' ? 'active' : ''} onClick={() => { setSuite('escalation'); setRun(null); setSelectedCaseId('') }}>Verify → Escalation · 5 ca</button>
      {!isPublic && <button type="button" aria-pressed={suite === 'regression'} className={suite === 'regression' ? 'active' : ''} onClick={() => { setSuite('regression'); setRun(null); setSelectedCaseId('') }}>Bộ hồi quy tổng hợp · 15 ca</button>}
    </div>
    {isPublic && <p className="detail-timestamp">Catalog tham chiếu có 15 ca tổng hợp; hai suite công khai tập trung vào 4 ca Verify chung và 5 ca Verify → Escalation.</p>}

    {starting && <StatePanel kind="loading" title={`Đang chạy ${suiteCounts[suite]} ca`} description="Backend thực thi từng case trong database in-memory mới." />}
    {error && <StatePanel kind="error" title="Verify không hoàn tất" description={error} action={<button className="button button-secondary" onClick={() => void start()}>Chạy lại</button>} />}
    {!run && !starting && !error && <StatePanel kind="empty" title="Chưa có lần chạy" description="Chọn một bộ Verify rồi bấm Run. Kết quả chỉ xuất hiện sau khi backend thực thi case." />}
    {run && !isPublic && <div className="verify-notice"><FlaskConical /><div><strong>DEMO RUN · MOCK</strong><p>Kết quả dưới đây thuộc Judge Demo và không được tính là public acceptance.</p></div></div>}
    {run && <RunContent run={run} selected={selected} onSelect={setSelectedCaseId} />}

    {isPublic && <section className="content-section public-judge-input">
      <div className="section-toolbar"><div><p className="page-eyebrow">Đầu vào mới</p><h3>Thử một bộ dữ liệu có cấu trúc</h3></div><span className="readonly-label">Không lưu</span></div>
      <p>Simulation v1 chỉ áp dụng cho DEMO-DEPT-01, kênh DEMO_SOCIAL hoặc DEMO_EMAIL, tiền tệ VND và ngân sách không quá 100.000.000 VND. Ngoài phạm vi, thiếu/xung đột fact, hoặc vượt trần sẽ chuyển tiếp để người có thẩm quyền xem.</p>
      <form className="public-judge-form" onSubmit={event => void evaluateInput(event)}>
        <label className="public-judge-field"><span>Tên ca</span><input required maxLength={120} value={inputForm.title} onChange={event => updateInput('title', event.target.value)} /></label>
        <label className="public-judge-field"><span>Department</span><input required maxLength={80} value={inputForm.department} onChange={event => updateInput('department', event.target.value)} /></label>
        <label className="public-judge-field"><span>Mục tiêu</span><input required maxLength={500} value={inputForm.objective} onChange={event => updateInput('objective', event.target.value)} /></label>
        <label className="public-judge-field"><span>Tóm tắt</span><textarea required maxLength={1000} value={inputForm.summary} onChange={event => updateInput('summary', event.target.value)} /></label>
        <label className="public-judge-field"><span>Đối tượng</span><input required maxLength={200} value={inputForm.targetAudience} onChange={event => updateInput('targetAudience', event.target.value)} /></label>
        <label className="public-judge-field"><span>Kênh</span><input required maxLength={80} value={inputForm.channel} onChange={event => updateInput('channel', event.target.value)} /></label>
        <label className="public-judge-field"><span>Tiền tệ</span><input required minLength={3} maxLength={3} pattern="[A-Z]{3}" value={inputForm.currency} onChange={event => updateInput('currency', event.target.value.toUpperCase())} /></label>
        <label className="public-judge-field"><span>Ngân sách khai báo (VND)</span><input required type="number" min="0" max="100000000000" step="1" value={inputForm.budgetVnd} onChange={event => updateInput('budgetVnd', event.target.value)} /></label>
        <label className="public-judge-field"><span>Ngân sách theo nguồn (VND)</span><input type="number" min="0" max="100000000000" step="1" value={inputForm.sourceBudgetVnd} onChange={event => updateInput('sourceBudgetVnd', event.target.value)} /><small>Để trống để kiểm tra trường hợp thiếu fact.</small></label>
        <div className="public-judge-actions"><button className="button button-secondary" type="submit" disabled={inputStarting}><Play /> {inputStarting ? 'Đang đánh giá...' : 'Đánh giá đầu vào mới'}</button></div>
      </form>
      {inputError && <StatePanel kind="error" title="Không thể đánh giá đầu vào" description={inputError} />}
      {inputRun && <section className="verify-summary" aria-live="polite"><div className="section-toolbar"><div><p className="page-eyebrow">Kết quả mô phỏng</p><h3>{inputRun.outcome}</h3></div><span className="readonly-label">{inputRun.category ?? 'Không chuyển tiếp'}</span></div><dl><div><dt>Mode / chất lượng</dt><dd>{inputRun.mode} · {inputRun.qualityStatus}</dd></div><div><dt>Phân loại dữ liệu</dt><dd>{inputRun.dataClassification}</dd></div><div><dt>Policy scope</dt><dd>{inputRun.policyVersion}</dd></div><div><dt>Hoàn tất</dt><dd>{formatDateTime(inputRun.completedAt)}</dd></div><div><dt>Thời lượng</dt><dd>{inputRun.durationMs} ms</dd></div><div><dt>Audit action</dt><dd>{inputRun.audit.action}</dd></div><div className="definition-wide"><dt>Lý do</dt><dd>{inputRun.reason}</dd></div><div className="definition-wide"><dt>Input SHA-256</dt><dd><code>{inputRun.audit.inputSha256}</code></dd></div></dl>{inputRun.handoffQuestion && <section className="verify-escalation-questions"><h4>Câu hỏi chuyển tiếp</h4><p>{inputRun.handoffQuestion}</p></section>}</section>}
    </section>}
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
  const auditEvidence = row.evidence?.filter(item => item.kind === 'AUDIT_TRACE') ?? []
  const evaluationEvidence = row.evidence?.filter(item => item.kind !== 'AUDIT_TRACE') ?? []
  return <aside className="verify-detail" aria-labelledby="verify-detail-title"><div className="verify-detail-heading"><span className={`detail-result status-${row.status === 'PASS' ? 'success' : 'danger'}`}><Icon /></span><div><p className="page-eyebrow">Case detail</p><h3 id="verify-detail-title">{row.caseName || row.caseId}</h3><small>{row.caseId}</small></div><button className="button button-secondary" type="button" onClick={onClose}>Đóng</button></div><dl className="definition-grid compact"><div><dt>Expected</dt><dd>{formatOutcome(row.expectedAction, row.expectedCategory)}</dd></div><div><dt>Actual</dt><dd>{formatOutcome(row.actualAction, row.actualCategory)}</dd></div><div><dt>Result</dt><dd><StatusBadge value={row.status} /></dd></div><div><dt>Timestamp</dt><dd>{formatDateTime(row.completedAt)}</dd></div><div><dt>Duration</dt><dd>{row.durationMs == null ? 'API chưa cung cấp' : `${row.durationMs} ms`}</dd></div><div><dt>Policy version</dt><dd>{row.policyVersion || 'Không có kết quả hợp lệ'}</dd></div><div><dt>Data class</dt><dd>{row.dataClassification || 'SYNTHETIC'}</dd></div><div className="definition-wide"><dt>Lý do</dt><dd>{row.reason || row.error?.message || 'Backend chưa cung cấp'}</dd></div></dl>
    {row.input && <section className="verify-evidence"><h4>Dữ liệu đã chạy</h4><pre>{row.input}</pre></section>}
    {evaluationEvidence.length ? <section className="verify-evidence"><h4>Bằng chứng evaluation</h4><ul>{evaluationEvidence.map((item, index) => <li key={`${item.reference ?? 'evidence'}-${index}`}><strong>{item.reference || item.kind || `Evidence ${index + 1}`}</strong>{item.kind && item.reference && <span> · {item.kind}</span>}{item.observation && <p>{item.observation}</p>}</li>)}</ul></section> : null}
    {auditEvidence.length ? <section className="verify-evidence"><h4>Audit events</h4><ul>{auditEvidence.map((item, index) => <li key={`${item.reference ?? 'audit'}-${index}`}><strong>{item.reference || 'Audit event'}</strong>{item.observation && <p>{item.observation}</p>}</li>)}</ul></section> : null}
    {row.generatedQuestion?.length ? <section className="verify-escalation-questions" aria-label="Câu hỏi chuyển tiếp"><h4>Câu hỏi cần người xử lý trả lời</h4>{row.generatedQuestion.map((question, index) => <article key={`${question.category}-${index}`}><strong>{question.category || row.actualCategory || 'HUMAN_REVIEW_REQUIRED'}</strong><p>{question.question}</p>{question.disputedOrMissingFact && <p><b>Thông tin cần xác định:</b> {question.disputedOrMissingFact}</p>}{question.applicableRuleOrLimit && <p><b>Quy định/giới hạn:</b> {question.applicableRuleOrLimit}</p>}{question.reason && <p><b>Lý do chuyển tiếp:</b> {question.reason}</p>}{question.evidenceReferences?.length ? <p><b>Bằng chứng liên quan:</b> {question.evidenceReferences.map(reference => <code key={reference}>{reference}</code>)}</p> : null}</article>)}</section> : row.actualAction === 'HUMAN_REVIEW_REQUIRED' && <section className="verify-escalation-questions"><h4>Câu hỏi chuyển tiếp</h4><p>Backend không trả về câu hỏi cụ thể; case này không đạt Verify.</p></section>}
    {row.modelVersion && <p className="detail-timestamp">Model version: {row.modelVersion}</p>}{row.auditReference && <p className="detail-timestamp">Audit reference: {row.auditReference}</p>}
    {row.appliedRuleIds?.length ? <div className="rule-chip-list" aria-label="Applied rules">{row.appliedRuleIds.map(rule => <code key={rule}>{rule}</code>)}</div> : null}<p className="detail-timestamp"><Clock3 /> {formatDateTime(row.completedAt)}</p></aside>
}

function formatOutcome(action: VerifyResultRow['actualAction'], category?: string | null) {
  if (!action) return 'Không có outcome'
  return category ? `${action} · ${category}` : action
}
