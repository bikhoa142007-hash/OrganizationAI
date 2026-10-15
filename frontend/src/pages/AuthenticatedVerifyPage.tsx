import { AlertCircle, Download, FlaskConical, Play, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { PageHeader, StatePanel, StatusBadge } from '../components/ui'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { VerifyRun, VerifyRunRow } from '../services/authWorkflow'

function formatVnd(value: unknown) {
  if (typeof value !== 'string' && typeof value !== 'number') return '—'
  try { return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(BigInt(value)) }
  catch { return String(value) }
}

function formatVerifyTime(value: string | null | undefined, timezone: string) {
  if (!value) return 'Chưa có dữ liệu'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: timezone,
  }).format(date)
}

function actualDecision(row: VerifyRunRow) {
  const decision = row.actual?.decision as Record<string, unknown> | undefined
  return typeof decision?.outcome === 'string' ? decision.outcome : 'Chưa có kết quả'
}

function caseBudget(row: VerifyRunRow) {
  const input = row.input as Record<string, unknown> | undefined
  const plan = input?.plan as Record<string, unknown> | undefined
  return formatVnd(plan?.budget_minor_units)
}

function errorMessage(error: unknown) {
  if (error instanceof AuthApiError && error.status === 409) return 'Một lượt Verify khác đang chạy. Màn hình sẽ tiếp tục cập nhật lượt hiện tại.'
  return error instanceof Error ? error.message : 'Không thể kết nối tới dịch vụ Verify.'
}

export function AuthenticatedVerifyPage() {
  const [run, setRun] = useState<VerifyRun | null>(null)
  const [loadingLatest, setLoadingLatest] = useState(true)
  const [starting, setStarting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')
  const [syncError, setSyncError] = useState('')
  const polling = useRef(false)

  useEffect(() => {
    let active = true
    void authWorkflowService.getLatestVerifyRun()
      .then(value => { if (active) setRun(value) })
      .catch(reason => {
        if (!active || (reason instanceof AuthApiError && reason.status === 404)) return
        if (active) setError(errorMessage(reason))
      })
      .finally(() => { if (active) setLoadingLatest(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!run || run.status !== 'RUNNING') return
    let active = true
    const timer = window.setInterval(() => {
      if (polling.current) return
      polling.current = true
      void authWorkflowService.getVerifyRun(run.run_id)
        .then(value => { if (active) { setRun(value); setSyncError('') } })
        .catch(reason => { if (active) setSyncError(errorMessage(reason)) })
        .finally(() => { polling.current = false })
    }, 1200)
    return () => { active = false; window.clearInterval(timer) }
  }, [run?.run_id, run?.status])

  async function startRun() {
    setStarting(true)
    setError('')
    setSyncError('')
    try {
      setRun(await authWorkflowService.startVerifyRun(`verify-${crypto.randomUUID()}`))
    } catch (reason) {
      setError(errorMessage(reason))
      if (reason instanceof AuthApiError && reason.status === 409) {
        try { setRun(await authWorkflowService.getLatestVerifyRun()) } catch { /* the visible conflict remains actionable */ }
      }
    } finally {
      setStarting(false)
    }
  }

  async function downloadReport() {
    if (!run) return
    setDownloading(true)
    setError('')
    try {
      const blob = await authWorkflowService.downloadVerifyReport(run.run_id)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `verify-${run.run_id.replaceAll('-', '').slice(0, 24)}.json`
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setDownloading(false)
    }
  }

  if (loadingLatest) return <StatePanel kind="loading" title="Đang khôi phục lượt Verify gần nhất" />

  const running = run?.status === 'RUNNING'
  const shownRows = run?.rows ?? []

  return <section className="verify-page authenticated-verify-page">
    <PageHeader
      eyebrow="Kiểm thử tổng hợp · VERIFY-1.0"
      title="Verify"
      description="Chạy bốn tình huống tổng hợp qua workflow thật trong cơ sở dữ liệu tạm. Không đọc hoặc ghi dữ liệu kế hoạch thật."
      actions={<button className="button primary" type="button" disabled={starting || running} aria-busy={starting || running} onClick={() => void startRun()}>
        <Play aria-hidden="true" /> {starting ? 'Đang khởi chạy…' : running ? 'Đang chạy Verify…' : 'Chạy kiểm thử'}
      </button>}
    />

    <div className="verify-truth-labels" aria-label="Môi trường kiểm thử">
      <span><ShieldCheck aria-hidden="true" /> Chỉ dữ liệu tổng hợp</span>
      <span><FlaskConical aria-hidden="true" /> Mock VLM · không gọi dịch vụ AI ngoài</span>
      <span>Mỗi tình huống dùng SQLite trong bộ nhớ riêng</span>
    </div>

    {error && <div className="verify-run-alert" role="alert"><AlertCircle aria-hidden="true" />{error}</div>}
    {syncError && <div className="verify-run-alert" role="status"><AlertCircle aria-hidden="true" />{syncError}</div>}

    {!run ? <StatePanel kind="empty" title="Chưa có lượt Verify" description="Chạy bốn tình huống cố định để kiểm tra tự duyệt, giới hạn quyền, thiếu bằng chứng và timeout." /> : <>
      <section className="verify-run-summary" aria-label="Tóm tắt lượt Verify" aria-live="polite">
        <div className="verify-run-heading">
          <div><p className="page-eyebrow">{run.run_id}</p><h3>{running ? `Đang chạy ${run.current_case_id ?? 'TC01'} / TC04` : 'Kết quả lượt chạy'}</h3></div>
          <StatusBadge value={run.status} />
        </div>
        <dl>
          <div><dt>Kết quả</dt><dd>{run.passed_cases} / 4 PASS · {run.failed_cases} FAIL</dd></div>
          <div><dt>Bắt đầu</dt><dd>{formatVerifyTime(run.started_at, run.timezone)}</dd></div>
          <div><dt>Kết thúc</dt><dd>{formatVerifyTime(run.completed_at, run.timezone)}</dd></div>
          <div><dt>Thời lượng</dt><dd>{(run.duration_ms / 1000).toFixed(1)} giây</dd></div>
          <div><dt>Môi trường</dt><dd>{run.environment}</dd></div>
          <div><dt>Provider</dt><dd>{run.provider_mode}</dd></div>
        </dl>
        {run.error && <p className="verify-run-error">{run.error}</p>}
        <div className="verify-run-actions">
          <button className="button secondary" type="button" disabled={downloading} onClick={() => void downloadReport()}>
            <Download aria-hidden="true" /> {downloading ? 'Đang tải…' : 'Tải báo cáo JSON'}
          </button>
          {run.commit_sha && <small>Commit: <code>{run.commit_sha.slice(0, 12)}</code></small>}
        </div>
      </section>

      <div className="verify-case-list">
        {shownRows.map(row => {
          return <article className="verify-case-card" key={row.case_id}>
            <div className="verify-case-main">
              <div className="verify-case-title"><strong>{row.case_id}</strong><div><h3>{row.case_name}</h3><small>Ngân sách: {caseBudget(row)}</small></div></div>
              <div className="verify-case-outcomes"><span><small>Kỳ vọng</small><strong>{String(row.expected.outcome ?? '—')}</strong></span><span><small>Thực tế</small><strong>{actualDecision(row)}</strong></span><StatusBadge value={row.status} /></div>
            </div>
            {(row.reason || row.actual) && <p className="verify-case-reason">{row.reason ?? String((row.actual?.evaluation as Record<string, unknown> | undefined)?.reason ?? 'Workflow đã trả kết quả.')}</p>}
            <div className="verify-case-meta"><span>Bắt đầu: {formatVerifyTime(row.started_at, run.timezone)}</span><span>Kết thúc: {formatVerifyTime(row.completed_at, run.timezone)}</span><span>{(row.duration_ms / 1000).toFixed(2)} giây</span></div>
            <details className="verify-case-details">
              <summary>Chi tiết đầu vào, workflow, AI và audit</summary>
              <pre>{JSON.stringify({ expected: row.expected, actual: row.actual, assertions: row.assertions, input: row.input }, null, 2)}</pre>
            </details>
          </article>
        })}
      </div>
    </>}

    <details className="verify-runbook" open={!run}>
      <summary>Hướng dẫn chạy trong 90 giây</summary>
      <ol>
        <li>Chọn <strong>Chạy kiểm thử</strong>; API tự chạy tuần tự TC01 đến TC04.</li>
        <li>Đợi tối đa 90 giây. Trạng thái và từng kết quả được lưu trong API để khôi phục khi tải lại trang.</li>
        <li>Mở từng tình huống để xem kết quả workflow, schema AI, quyết định, assertion và audit.</li>
        <li>Tải báo cáo JSON. Nhãn môi trường xác nhận đây là dữ liệu tổng hợp và Mock VLM.</li>
      </ol>
      <p>Chi tiết clean-clone, cấu hình và lệnh chạy: <a href="https://github.com/bikhoa142007-hash/OrganizationAI/blob/main/docs/verify-runbook.md" target="_blank" rel="noreferrer">mở Verify runbook</a>.</p>
    </details>
  </section>
}
