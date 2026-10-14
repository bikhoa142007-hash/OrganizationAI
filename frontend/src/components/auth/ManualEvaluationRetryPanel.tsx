import { RotateCcw } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
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
    if (error.status === 409) return 'Thông tin hồ sơ đã thay đổi hoặc yêu cầu không còn phù hợp. Hãy tải lại trạng thái trước khi thử lại.'
  }
  return 'Không thể chạy lại đánh giá AI. Hãy thử lại cùng yêu cầu hiện tại.'
}

function resultMessage(result: WorkflowEvaluationRetry): string {
  if (result.result_disposition === 'STALE') {
    return 'Kết quả đánh giá không được áp dụng vì trạng thái hồ sơ đã thay đổi. Hãy tải lại trạng thái trước khi tiếp tục.'
  }
  if (result.processing_stage === 'HUMAN_REVIEW_REQUIRED') {
    return 'Hồ sơ đang chờ Checker xem xét.'
  }
  if (result.processing_stage === 'AI_AUTO_APPROVED') {
    return 'Kế hoạch đã được tự động phê duyệt.'
  }
  if (result.run_status === 'FAILED' || result.run_status === 'TIMED_OUT') {
    return 'AI chưa thể hoàn tất đánh giá. Hãy tải lại trạng thái hồ sơ để xem thông tin mới nhất.'
  }
  return 'Đã ghi nhận yêu cầu đánh giá. Hãy tải lại trạng thái hồ sơ để xem kết quả mới nhất.'
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

  useEffect(() => {
    setError('')
    setMessage('')
    pendingRequest.current = null
  }, [planId, approvalRound])

  if (!isAssignedChecker || (!isRetryAvailable && !message) || planVersion < 1 || approvalRound < 1 || roundRevision < 0) {
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
    <p>Yêu cầu mới sử dụng nội dung hồ sơ trong vòng duyệt hiện tại. Các kết quả trước đó vẫn được lưu lại.</p>
    {error && <p className="auth-workflow-alert is-error" role="alert">{error}</p>}
    {message && <p className="auth-workflow-alert is-progress" role="status">{message}</p>}
    {isRetryAvailable && <button className="button button-secondary" type="button" onClick={() => void retry()} disabled={busy}>
      {busy ? 'Đang chạy lại…' : 'Chạy lại AI'}
    </button>}
  </section>
}
