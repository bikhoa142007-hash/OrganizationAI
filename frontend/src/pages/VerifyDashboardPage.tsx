import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import type { VerifyResultRow, VerifyRun } from '../types'

const VERIFY_SUITE = 'general'

export function VerifyDashboardPage() {
  const services = useServices()
  const [run, setRun] = useState<VerifyRun | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)

  useEffect(() => {
    if (!run || run.status !== 'RUNNING') return
    const runningRun = run

    let cancelled = false
    async function refreshRun() {
      try {
        const nextRun = await services.verify.getRun(runningRun.runId)
        if (cancelled) return
        if (!nextRun) throw new Error('VERIFY_RUN_NOT_FOUND')
        setRun(nextRun)
      } catch {
        if (cancelled) return
        setError('Không thể cập nhật trạng thái Verify từ service. Bạn có thể chạy lại toàn bộ suite.')
        setRun((current) => current ? {
          ...current,
          status: 'ERROR',
          currentCaseId: null,
          error: { code: 'VERIFY_RUN_REFRESH_FAILED', message: 'Service không trả về được snapshot Verify.' },
        } : current)
      }
    }

    void refreshRun()
    const intervalId = window.setInterval(() => void refreshRun(), 250)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [run?.runId, run?.status, services.verify])

  const selectedRow = useMemo(
    () => run?.rows.find((row) => row.caseId === selectedCaseId) ?? null,
    [run?.rows, selectedCaseId],
  )

  async function handleStartRun() {
    setIsStarting(true)
    setError(null)
    setSelectedCaseId(null)
    try {
      const nextRun = await services.verify.startRun(VERIFY_SUITE)
      setRun(nextRun)
    } catch {
      setRun(null)
      setError('Không thể bắt đầu Verify từ service. Vui lòng thử lại.')
    } finally {
      setIsStarting(false)
    }
  }

  const isRunning = isStarting || run?.status === 'RUNNING'

  return (
    <section className="verify-page" aria-labelledby="verify-title">
      <div className="verify-header">
        <div>
          <Link className="back-link" to="/">← Quay lại Landing</Link>
          <span className="section-kicker">Màn 7 · Verify</span>
          <h2 id="verify-title">Verify Dashboard</h2>
          <p>Chạy tuần tự năm case do VerifyService cung cấp và xem snapshot kết quả theo từng case.</p>
        </div>
        <div className="verify-header-actions">
          {run?.dataSource === 'MOCK' && <span className="verify-source">Mock service data</span>}
          <button type="button" className="button button-primary" onClick={() => void handleStartRun()} disabled={isRunning}>
            {isRunning ? 'Đang chạy 5 case…' : 'Run all 5'}
          </button>
        </div>
      </div>

      {error && <div className="verify-alert" role="alert"><p>{error}</p><button type="button" className="button button-secondary" onClick={() => void handleStartRun()} disabled={isRunning}>Run lại</button></div>}

      {!run && !isStarting && !error && <EmptyVerifyState />}
      {(run || isStarting) && <RunContent run={run} selectedRow={selectedRow} onSelectCase={setSelectedCaseId} />}
    </section>
  )
}

function EmptyVerifyState() {
  return (
    <div className="verify-state verify-empty">
      <span className="verify-state-icon" aria-hidden="true">5</span>
      <div>
        <h3>Chưa có lần chạy</h3>
        <p>Kết quả chỉ xuất hiện sau khi VerifyService bắt đầu một run. Không có kết quả PASS được đặt sẵn trên màn hình này.</p>
      </div>
    </div>
  )
}

interface RunContentProps {
  run: VerifyRun | null
  selectedRow: VerifyResultRow | null
  onSelectCase: (caseId: string) => void
}

function RunContent({ run, selectedRow, onSelectCase }: RunContentProps) {
  if (!run) {
    return <div className="verify-state verify-loading" aria-live="polite"><span className="loading-spinner" aria-hidden="true" /><div><h3>Đang bắt đầu Verify</h3><p>Đang chờ VerifyService tạo run.</p></div></div>
  }

  const summary = run.summary
  const currentCase = run.rows.find((row) => row.caseId === run.currentCaseId)
  return (
    <div className="verify-layout">
      <section className="verify-run-card" aria-label="Tổng quan lần chạy Verify">
        <div className="verify-run-heading">
          <div>
            <span className="section-kicker">Run summary</span>
            <h3>{run.status === 'RUNNING' ? 'Verify đang chạy' : run.status === 'ERROR' ? 'Verify gặp lỗi' : 'Verify đã hoàn tất'}</h3>
          </div>
          <span className={`verify-run-status verify-run-status-${run.status.toLowerCase()}`}>{runStatusLabel(run.status)}</span>
        </div>
        <dl className="verify-meta">
          <div><dt>Run ID</dt><dd>{run.runId}</dd></div>
          <div><dt>Bắt đầu</dt><dd>{formatDate(run.startedAt)}</dd></div>
          <div><dt>Hoàn tất</dt><dd>{formatDate(run.completedAt)}</dd></div>
          <div><dt>Tổng case</dt><dd>{summary?.totalCases ?? run.rows.length}</dd></div>
          <div><dt>PASS</dt><dd>{summary?.passedCases ?? 0}</dd></div>
          <div><dt>FAIL</dt><dd>{summary?.failedCases ?? 0}</dd></div>
          <div><dt>ERROR</dt><dd>{summary?.errorCases ?? 0}</dd></div>
        </dl>
        <div className="verify-progress" aria-live="polite">
          <div><span>{run.status === 'RUNNING' && currentCase ? `Đang chạy: ${currentCase.caseName ?? currentCase.caseId}` : 'Tiến độ do VerifyService cung cấp'}</span><strong>{summary?.progressPercent ?? 0}%</strong></div>
          <progress value={summary?.progressPercent ?? 0} max="100" aria-label="Tiến độ chạy Verify" />
        </div>
        <p className="verify-score"><strong>{summary?.passedCases ?? 0}/{summary?.totalCases ?? run.rows.length} PASS</strong><span>{summary?.completedCases ?? 0}/{summary?.totalCases ?? run.rows.length} case đã hoàn tất</span></p>
        {run.error && <p className="verify-run-error" role="alert">{run.error.message} <small>Mã: {run.error.code}</small></p>}
      </section>

      <section className="verify-results" aria-labelledby="verify-results-title">
        <div className="verify-results-heading"><div><span className="section-kicker">Case results</span><h3 id="verify-results-title">Kết quả từng case</h3></div><span>{run.rows.length} case</span></div>
        {run.rows.length === 0 ? <p className="verify-empty-results">VerifyService không trả về case nào cho run này.</p> : (
          <div className="verify-table-wrap">
            <table className="verify-table">
              <thead><tr><th>Case</th><th>Expected</th><th>Actual</th><th>Result</th><th>Reason</th><th>Timestamp</th><th><span className="visually-hidden">Chi tiết</span></th></tr></thead>
              <tbody>{run.rows.map((row) => <VerifyRow key={row.caseId} row={row} onSelectCase={onSelectCase} />)}</tbody>
            </table>
          </div>
        )}
      </section>

      {selectedRow && <VerifyDetail row={selectedRow} onClose={() => onSelectCase('')} />}
    </div>
  )
}

function VerifyRow({ row, onSelectCase }: { row: VerifyResultRow; onSelectCase: (caseId: string) => void }) {
  const hasObservedResult = row.status === 'PASS' || row.status === 'FAIL' || row.status === 'ERROR'
  return (
    <tr>
      <td><strong>{row.caseName ?? row.caseId}</strong><small>{row.caseId}</small></td>
      <td>{formatOutcome(row.expectedAction, row.expectedCategory)}</td>
      <td>{hasObservedResult ? formatOutcome(row.actualAction, row.actualCategory) : row.status === 'RUNNING' ? 'Đang chạy' : 'Chờ chạy'}</td>
      <td><span className={`verify-result verify-result-${row.status?.toLowerCase() ?? 'pending'}`}>{rowStatusLabel(row.status)}</span></td>
      <td>{hasObservedResult ? row.reason ?? row.error?.message ?? 'Service không cung cấp lý do' : '—'}</td>
      <td>{hasObservedResult ? formatDate(row.completedAt) : '—'}</td>
      <td><button type="button" className="verify-detail-button" onClick={() => onSelectCase(row.caseId)}>Chi tiết</button></td>
    </tr>
  )
}

function VerifyDetail({ row, onClose }: { row: VerifyResultRow; onClose: () => void }) {
  return (
    <aside className="verify-detail" aria-labelledby="verify-detail-title">
      <div className="verify-detail-heading"><div><span className="section-kicker">Case detail</span><h3 id="verify-detail-title">{row.caseName ?? row.caseId}</h3><p>{row.caseId}</p></div><button type="button" className="button button-secondary" onClick={onClose}>Đóng</button></div>
      <dl className="verify-detail-meta">
        <div><dt>Input</dt><dd>{row.input ?? 'Service không cung cấp input.'}</dd></div>
        <div><dt>Expected</dt><dd>{formatOutcome(row.expectedAction, row.expectedCategory)}</dd></div>
        <div><dt>Actual</dt><dd>{formatOutcome(row.actualAction, row.actualCategory)}</dd></div>
        <div><dt>Result</dt><dd>{rowStatusLabel(row.status)}</dd></div>
        <div><dt>Reason</dt><dd>{row.reason ?? row.error?.message ?? 'Service chưa cung cấp lý do.'}</dd></div>
        <div><dt>Timestamp</dt><dd>{formatDate(row.completedAt)}</dd></div>
        <div><dt>Duration</dt><dd>{row.durationMs == null ? 'Service chưa cung cấp' : `${row.durationMs} ms`}</dd></div>
      </dl>
      {row.error && <p className="verify-detail-error" role="alert">{row.error.message} <small>Mã: {row.error.code}</small></p>}
      {row.appliedRuleIds?.length ? <section className="verify-detail-section"><h4>Applied rules</h4><ul>{row.appliedRuleIds.map((ruleId) => <li key={ruleId}><Link to={`/policy#${encodeURIComponent(ruleId)}`}>{ruleId}</Link></li>)}</ul></section> : null}
      {row.auditReference && <Link className="button button-secondary" to="/audit">Xem audit</Link>}
    </aside>
  )
}

function runStatusLabel(status: VerifyRun['status']) {
  if (status === 'RUNNING') return 'RUNNING'
  if (status === 'COMPLETED') return 'COMPLETED'
  if (status === 'ERROR') return 'ERROR'
  return 'NOT RUN'
}

function rowStatusLabel(status: VerifyResultRow['status']) {
  if (status === 'PASS') return 'PASS'
  if (status === 'FAIL') return 'FAIL'
  if (status === 'ERROR') return 'ERROR'
  if (status === 'RUNNING') return 'RUNNING'
  return 'PENDING'
}

function formatOutcome(action: VerifyResultRow['actualAction'], category: string | null | undefined) {
  if (!action) return 'Không có actual outcome'
  return category ? `${action} · ${category}` : action
}

function formatDate(value: string | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN')
}
