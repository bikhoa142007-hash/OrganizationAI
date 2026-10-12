import { RotateCcw } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { AuthApiError } from '../../services/auth'
import {
  workflowCompletionService,
  type WorkflowEvaluationRetry,
} from '../../services/workflowCompletion'

interface ManualEvaluationRetryPanelProps {
  planId: string
  planVersion: number
  approvalRound: number
  roundRevision: number
  isAssignedChecker: boolean
  /** Derive from the latest terminal technical failure; the backend remains authoritative. */
  isRetryAvailable: boolean
  onRetryComplete?: (result: WorkflowEvaluationRetry) => void
}

function messageFor(error: unknown): string {
  if (error instanceof AuthApiError) {
    if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
    if (error.status === 403) return 'Chỉ Checker đang được giao cho kế hoạch này mới có thể chạy lại AI.'
    if (error.status === 404) return 'Không tìm thấy kế hoạch hoặc vòng duyệt.'
    if (error.status === 409) return 'Vòng duyệt hoặc revision đã thay đổi, hoặc lần chạy này không đủ điều kiện.'
  }
  return 'Không thể chạy lại đánh giá AI. Hãy thử lại cùng yêu cầu hiện tại.'
}

function resultMessage(result: WorkflowEvaluationRetry): string {
  if (result.result_disposition === 'STALE') {
    return `Lần chạy ${result.run_id} đã được lưu nhưng không áp dụng vào trạng thái hiện tại.`
  }
  if (result.run_status === 'FAILED' || result.run_status === 'TIMED_OUT'
    || result.processing_stage === 'HUMAN_REVIEW_REQUIRED') {
    return `Lần chạy ${result.run_id} kết thúc cần Checker xem xét. Evidence của lần chạy trước vẫn được giữ nguyên.`
  }
  if (result.processing_stage === 'AI_AUTO_APPROVED') {
    return `Lần chạy ${result.run_id} hoàn tất và kế hoạch đã được tự động duyệt.`
  }
  return `Đã ghi nhận lần chạy ${result.run_id}. Evidence của lần chạy trước vẫn được giữ nguyên.`
}

export function ManualEvaluationRetryPanel({
  planId,
  planVersion,
  approvalRound,
  roundRevision,
  isAssignedChecker,
  isRetryAvailable,
  onRetryComplete,
}: ManualEvaluationRetryPanelProps) {
  const headingId = useId()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const pendingRequest = useRef<{ fingerprint: string; key: string } | null>(null)

  if (!isAssignedChecker || !isRetryAvailable || planVersion < 1 || approvalRound < 1 || roundRevision < 0) {
    return null
  }

  async function retry() {
    if (busy) return
    const fingerprint = JSON.stringify([planId, planVersion, approvalRound, roundRevision])
    if (pendingRequest.current?.fingerprint !== fingerprint) {
      pendingRequest.current = { fingerprint, key: crypto.randomUUID() }
    }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await workflowCompletionService.retryEvaluation(
        planId,
        approvalRound,
        { expected_plan_version: planVersion, expected_round_revision: roundRevision },
        pendingRequest.current.key,
      )
      pendingRequest.current = null
      setMessage(resultMessage(result))
      onRetryComplete?.(result)
    } catch (reason) {
      setError(messageFor(reason))
    } finally {
      setBusy(false)
    }
  }

  return <section className="auth-workflow-card" aria-busy={busy} aria-labelledby={headingId}>
    <div className="auth-workflow-card-heading">
      <RotateCcw aria-hidden="true" />
      <h2 id={headingId}>Chạy lại đánh giá AI</h2>
    </div>
    <p>Lần chạy mới dùng snapshot của vòng hiện tại. Evidence của lần chạy trước vẫn được giữ nguyên.</p>
    {error && <p className="auth-workflow-alert is-error" role="alert">{error}</p>}
    {message && <p className="auth-workflow-alert is-progress" role="status">{message}</p>}
    <button className="button button-secondary" type="button" onClick={() => void retry()} disabled={busy}>
      {busy ? 'Đang chạy lại…' : 'Chạy lại AI'}
    </button>
  </section>
}
