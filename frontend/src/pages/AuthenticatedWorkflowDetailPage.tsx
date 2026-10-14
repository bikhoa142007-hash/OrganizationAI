import { ArrowLeft, Check, Clock3, FileText, History, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { formatDateTime } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import { InternalNotesPanel } from '../components/auth/InternalNotesPanel'
import { ManualEvaluationRetryPanel } from '../components/auth/ManualEvaluationRetryPanel'
import type { WorkflowAiEvaluation, WorkflowEvent, WorkflowPlan, WorkflowSlaRound, WorkflowTaskEvaluation, WorkflowVlmExtraction } from '../types/authWorkflow'

export function AuthenticatedWorkflowDetailPage() {
  const { planId = '' } = useParams()
  const location = useLocation()
  const { user, roles } = useAuth()
  const [plan, setPlan] = useState<WorkflowPlan | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailLoadFailed, setDetailLoadFailed] = useState(false)
  const [reason, setReason] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [recoveryBusy, setRecoveryBusy] = useState(false)
  const [decisionNotice, setDecisionNotice] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    setError('')
    setDecisionNotice('')
    setDetailLoadFailed(false)
    setPlan(current => current?.id === planId ? current : null)
    setLoading(true)
    authWorkflowService.getPlan(planId)
      .then(value => { if (active) setPlan(value) })
      .catch(failure => {
        if (!active) return
        setError(detailErrorText(failure))
        setDetailLoadFailed(true)
        if (shouldClearPlanDetail(failure)) setPlan(null)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [planId, reload])

  function reloadDetail() {
    setReload(value => value + 1)
  }

  async function decide(action: 'APPROVED' | 'REJECTED') {
    if (!plan || !isAssignedChecker || plan.status !== 'PENDING_APPROVAL') return
    if (['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage)) {
      setError('AI vẫn đang xử lý hồ sơ. Hãy tải lại sau khi hoàn tất trước khi quyết định.')
      return
    }
    if (plan.current_round < 1) {
      setError('Hồ sơ chưa sẵn sàng để Checker đưa ra quyết định.')
      return
    }
    if (reason.length > 5000 || overrideReason.length > 5000) {
      setError('Mỗi phần lý do không được vượt quá 5.000 ký tự.')
      return
    }
    const activeRound = plan.current_round
    const evaluation = plan.ai_evaluations.find(item => item.round_number === activeRound)?.evaluation
    if (action === 'REJECTED' && !reason.trim()) {
      setError('Nhập lý do từ chối trước khi tiếp tục.')
      return
    }
    const expected = action === 'APPROVED' ? 'RECOMMEND_AUTO_APPROVAL' : 'RECOMMEND_HUMAN_REVIEW'
    if (evaluation?.proposed_action !== expected && !overrideReason.trim()) {
      setError('Vui lòng giải thích khi quyết định khác với khuyến nghị của AI hoặc chưa có khuyến nghị.')
      return
    }
    setBusy(true); setError(''); setDecisionNotice('')
    try {
      const result = await authWorkflowService.decide(planId, activeRound, action, reason, overrideReason)
      setPlan(result)
      setReason('')
      setOverrideReason('')
      setDecisionNotice(action === 'APPROVED' ? 'Hệ thống đã xác nhận phê duyệt hồ sơ.' : 'Hệ thống đã xác nhận từ chối hồ sơ.')
    } catch (failure) {
      const decisionError = failure instanceof AuthApiError
        ? failure
        : new AuthApiError(0, failure instanceof Error ? failure.message : 'Không thể hoàn tất quyết định.', 'CLIENT_ERROR')
      if (decisionError.status === 409 || decisionError.code === 'CONFLICT') {
        setError('Vòng duyệt đã thay đổi hoặc đã được xử lý. Đang đồng bộ trạng thái mới nhất; quyết định chưa được gửi lại.')
        try {
          const latest = await authWorkflowService.getPlan(planId)
          setPlan(latest)
          setError('Vòng duyệt đã thay đổi hoặc đã được xử lý. Đã tải trạng thái mới nhất; hãy kiểm tra trước khi tiếp tục.')
        } catch (refreshFailure) {
          const refreshError = refreshFailure instanceof AuthApiError
            ? refreshFailure
            : new AuthApiError(0, 'Không thể tải lại trạng thái hồ sơ.', 'CLIENT_ERROR')
          if (shouldClearPlanDetail(refreshError)) setPlan(null)
          setError(detailErrorText(refreshError))
        }
      } else {
        setError(decisionErrorText(decisionError))
        if ([401, 403, 404].includes(decisionError.status) || ['UNAUTHENTICATED', 'FORBIDDEN', 'NOT_FOUND'].includes(decisionError.code || '')) {
          setPlan(null)
        }
      }
    }
    finally { setBusy(false) }
  }

  async function recoverInterruptedEvaluation() {
    if (!plan) return
    setRecoveryBusy(true); setError('')
    try {
      setPlan(await authWorkflowService.recoverStaleEvaluation(planId, plan.current_round))
    } catch (failure) {
      setError(detailErrorText(failure))
    } finally {
      setRecoveryBusy(false)
    }
  }

  const navigationNotice = location.state && typeof location.state === 'object'
    && 'workflowNotice' in location.state && typeof location.state.workflowNotice === 'string'
    ? location.state.workflowNotice
    : ''
  if (!plan || plan.id !== planId) return <section className={`auth-workflow-state${error ? ' is-error' : ''}`} role={error ? 'alert' : 'status'}>
    <h1>{error ? 'Không thể mở kế hoạch' : loading ? 'Đang tải kế hoạch…' : 'Kế hoạch chưa được tải'}</h1>
    {error && <><p>{error}</p><div className="button-row"><Link to="/workflow/plans">Quay lại danh sách</Link><button className="button button-secondary" type="button" disabled={loading} onClick={reloadDetail}>{loading ? 'Đang tải…' : 'Thử tải lại'}</button></div></>}
  </section>
  const displayablePlanReason = displayableReason(plan.decision_reason)
  const planReasonWasFiltered = Boolean(plan.decision_reason?.trim()) && !displayablePlanReason
  const isMaker = roles.includes('MAKER') && plan.maker_id === user?.id
  const isAssignedChecker = roles.includes('CHECKER') && plan.checker_id === user?.id
  const canViewAttachments = isMaker || isAssignedChecker
  const history = safeWorkflowEvents(plan.history)
  const canEdit = isMaker && ['DRAFT', 'REJECTED'].includes(plan.status)
  const canDecide = isAssignedChecker && plan.status === 'PENDING_APPROVAL'
  const decisionLocked = busy || ['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) || plan.current_round < 1
  const finalCheckerDecision = [...history].reverse().find(event =>
    event.actor_type === 'HUMAN' && ['APPROVED', 'REJECTED'].includes(event.action),
  )
  const latestRoundRun = latestRunForRound(plan.ai_evaluations, plan.current_round)
  const retryAvailable = plan.status === 'PENDING_APPROVAL'
    && plan.processing_stage === 'HUMAN_REVIEW_REQUIRED'
    && isRetryableEvaluationRun(latestRoundRun)

  return <section className="auth-workflow-page">
    <Link className="auth-back-link" to={isAssignedChecker ? '/workflow/reviews' : '/workflow/plans'}><ArrowLeft /> Quay lại danh sách</Link>
    {navigationNotice && <div className="auth-workflow-alert is-success" role="status"><Check /><p>{navigationNotice}</p></div>}
    {decisionNotice && <div className="auth-workflow-alert is-success" role="status"><Check aria-hidden="true" /><p>{decisionNotice}</p><Link to="/workflow/reviews">Quay lại hàng chờ duyệt</Link></div>}
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">{plan.code} · Phiên bản {plan.current_version || '—'} · Vòng {plan.current_round || '—'}</p><h1>{plan.payload.title || 'Kế hoạch chưa có tên'}</h1><p>Người tạo: {plan.maker_name} <span aria-hidden="true">·</span> Checker: {plan.checker_name || 'Chưa gán'} <span aria-hidden="true">·</span> Cập nhật: {formatDateTime(plan.updated_at)}</p></div><div className="auth-workflow-status-pair"><span className={`workflow-status status-${plan.status.toLowerCase()}`}>{statusLabel(plan.status)}</span><span className="workflow-processing-stage">Giai đoạn: {workflowStageLabel(plan.processing_stage)}</span></div></div>
    {loading && <p className="auth-workflow-refresh-status" role="status">Đang cập nhật kế hoạch… Nội dung hiện có vẫn được giữ.</p>}
    {error && <div className="auth-workflow-alert is-error" role="alert"><div><p>{error}</p></div>{detailLoadFailed && <button className="button button-secondary" type="button" disabled={loading} onClick={reloadDetail}>{loading ? 'Đang tải…' : 'Thử tải lại'}</button>}</div>}
    {['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) && <div className="auth-workflow-alert is-progress" role="status"><Clock3 /><div><strong>Đang đánh giá kế hoạch</strong><p>AI đang xử lý hồ sơ. Tải lại trang để xem trạng thái mới nhất.</p>{isAssignedChecker && <button type="button" className="button button-secondary" disabled={recoveryBusy} onClick={() => void recoverInterruptedEvaluation()}>{recoveryBusy ? 'Đang kiểm tra…' : 'Kiểm tra tiến độ'}</button>}</div></div>}
    <SlaRoundHistory plan={plan} />
    <div className="auth-workflow-detail-grid">
      <section className="auth-workflow-card"><div className="auth-workflow-card-heading"><FileText /><h2>Nội dung kế hoạch</h2></div><dl className="auth-workflow-definition-grid">
        <div><dt>Mục tiêu</dt><dd>{plan.payload.objective || '—'}</dd></div>
        <div><dt>Bộ phận</dt><dd>{plan.payload.department || '—'}</dd></div>
        <div><dt>Thời gian</dt><dd>{plan.payload.start_date || '—'} — {plan.payload.end_date || '—'}</dd></div>
        <div><dt>Ngân sách</dt><dd>{formatBudget(plan.payload.budget_minor_units, plan.payload.currency)}</dd></div>
        <div className="field-wide"><dt>Tóm tắt chiến lược</dt><dd>{plan.payload.summary || '—'}</dd></div>
        <div><dt>Đối tượng mục tiêu</dt><dd>{plan.payload.target_audience || '—'}</dd></div>
        <div><dt>KPI kỳ vọng</dt><dd>{plan.payload.kpi_expected || '—'}</dd></div>
        <div><dt>Kênh</dt><dd>{plan.payload.channels.join(', ') || '—'}</dd></div>
        <div><dt>Ghi chú</dt><dd>{plan.payload.notes || '—'}</dd></div>
      </dl>{Boolean(plan.decision_reason?.trim()) && ['REJECTED', 'PENDING_APPROVAL'].includes(plan.status) && <div className={`auth-workflow-alert ${plan.status === 'REJECTED' ? 'is-error' : 'is-review'}`}><strong>{plan.status === 'REJECTED' ? 'Kết quả xử lý' : 'Trạng thái hồ sơ'}</strong><p>{plan.status === 'REJECTED' ? 'Hồ sơ đã bị từ chối.' : plan.processing_stage === 'HUMAN_REVIEW_REQUIRED' ? 'Hồ sơ đang chờ Checker xem xét.' : 'Hồ sơ đang được xử lý.'}</p>{displayablePlanReason ? <p>{displayablePlanReason}</p> : planReasonWasFiltered && <p role="status">Chi tiết lý do hiện chưa có nội dung phù hợp để hiển thị.</p>}</div>}
        <div className="auth-workflow-attachments"><h3>Ảnh đính kèm</h3>{plan.attachments.length ? plan.attachments.map(item => <div key={item.id} className="auth-workflow-attachment">{canViewAttachments && <AuthAttachmentPreview planId={plan.id} attachmentId={item.id} filename={item.filename} />}<span><strong>{item.filename}</strong><small>{item.media_type} · {Math.ceil(item.byte_size / 1024)} KB</small></span></div>) : <p>Chưa có ảnh đính kèm.</p>}</div>
      </section>
      <section className="auth-workflow-card"><div className="auth-workflow-card-heading"><History /><h2>Lịch sử xử lý</h2><span className="auth-workflow-history-count">{history.length} sự kiện</span></div>{history.length === 0 ? <p className="auth-workflow-history-empty">Chưa có sự kiện hoạt động được ghi nhận.</p> : <ol className="auth-workflow-history" aria-label="Sự kiện của kế hoạch">{history.map((event, index) => {
        const timestamp = eventTimestamp(event.created_at)
        const transition = eventStatusTransition(event)
        const version = event.details.version
        const round = event.details.round
        const reasonSource = typeof event.details.reason === 'string' ? event.details.reason : ''
        const reason = displayableReason(reasonSource)
        const reasonWasFiltered = Boolean(reasonSource.trim()) && !reason
        const overrideReasonSource = typeof event.details.override_reason === 'string' ? event.details.override_reason : ''
        const overrideReason = displayableReason(overrideReasonSource)
        const overrideReasonWasFiltered = Boolean(overrideReasonSource.trim()) && !overrideReason
        const actionReasonLabel = event.action === 'APPROVED' ? 'Lý do phê duyệt' : event.action === 'REJECTED' ? 'Lý do từ chối' : ''
        return <li key={event.id || `${event.action}-${index}`}>
          <span className="history-icon">
            {event.action === 'APPROVED' || event.action === 'AI_AUTO_APPROVED'
              ? <Check aria-hidden="true" />
              : event.action === 'REJECTED' ? <X aria-hidden="true" /> : <Clock3 aria-hidden="true" />}
          </span>
          <div>
            <strong>{eventLabel(event.action)}</strong>
            <p><span>{eventActorName(event)}</span> · {timestamp.dateTime
              ? <time dateTime={timestamp.dateTime}>{timestamp.label}</time>
              : <span>{timestamp.label}</span>}</p>
            {transition && <p className="auth-workflow-history-transition">{transition}</p>}
            {(reason || reasonWasFiltered) && <div>
              {actionReasonLabel && <strong>{actionReasonLabel}</strong>}
              {reason ? <blockquote>{reason}</blockquote> : <p role="status">Chi tiết lý do hiện chưa có nội dung phù hợp để hiển thị.</p>}
            </div>}
            {(overrideReason || overrideReasonWasFiltered) && <div>
              <strong>Lý do xử lý khác với đề xuất AI</strong>
              {overrideReason ? <blockquote>{overrideReason}</blockquote> : <p role="status">Chi tiết lý do hiện chưa có nội dung phù hợp để hiển thị.</p>}
            </div>}
            {typeof version === 'number' && Number.isFinite(version)
              && typeof round === 'number' && Number.isFinite(round)
              && <small>Phiên bản {version} · Vòng {round}</small>}
          </div>
        </li>
      })}</ol>}</section>
    </div>
    <AiEvaluationResults plan={plan} finalCheckerDecision={finalCheckerDecision} />
    {plan.versions.length > 0 && <section className="auth-workflow-card auth-version-card"><div className="auth-workflow-card-heading"><History /><h2>Lịch sử phiên bản</h2></div>{plan.versions.map(version => <details key={version.version_number}><summary>Phiên bản {version.version_number} · Vòng {version.round_number} · {new Date(version.created_at).toLocaleString('vi-VN')}</summary><p>{version.payload.summary}</p><ul>{version.attachments.map(item => <li key={item.id}>{item.filename}</li>)}</ul></details>)}</section>}
    {canEdit && <div className="auth-workflow-actions"><Link className="button button-secondary" to={`/workflow/plans/${plan.id}/edit`}>Chỉnh sửa và gửi lại</Link></div>}
    {isAssignedChecker && plan.current_round > 0 && <InternalNotesPanel planId={plan.id} approvalRound={plan.current_round} />}
    {isAssignedChecker && <ManualEvaluationRetryPanel
      planId={plan.id}
      planVersion={plan.current_version}
      approvalRound={plan.current_round}
      roundRevision={plan.revision}
      isAssignedChecker={isAssignedChecker}
      isRetryAvailable={retryAvailable}
      onRetryComplete={reloadDetail}
    />}
    {canDecide && <section className="auth-workflow-card auth-decision-card">
      <div className="auth-workflow-card-heading"><Check aria-hidden="true" /><h2>Quyết định Checker</h2></div>
      <p>Nội dung đã gửi được lưu thành phiên bản chỉ đọc. Từ chối cần có lý do.</p>
      {['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) && <div className="auth-workflow-alert is-progress" role="status">
        <Clock3 aria-hidden="true" /><p>AI đang xử lý. Bạn có thể đưa ra quyết định sau khi kết quả được cập nhật.</p>
      </div>}
      {plan.current_round < 1 && <div className="auth-workflow-alert is-review" role="status"><p>Hồ sơ chưa sẵn sàng để Checker đưa ra quyết định.</p></div>}
      <label className="auth-field">Lý do hoặc nhận xét
        <textarea rows={3} maxLength={5000} aria-describedby="review-reason-help" disabled={decisionLocked} value={reason} onChange={event => setReason(event.target.value)} placeholder="Bắt buộc khi từ chối" />
      </label>
      <small id="review-reason-help" className="auth-workflow-form-hint">{reason.length}/5.000 ký tự · Bắt buộc khi từ chối.</small>
      <label className="auth-field">Lý do xử lý khác với đề xuất AI
        <textarea rows={2} maxLength={5000} aria-describedby="review-override-help" disabled={decisionLocked} value={overrideReason} onChange={event => setOverrideReason(event.target.value)} placeholder="Bắt buộc khi quyết định khác hoặc chưa có khuyến nghị AI" />
      </label>
      <small id="review-override-help" className="auth-workflow-form-hint">{overrideReason.length}/5.000 ký tự · Hãy nêu lý do khi quyết định khác với đề xuất AI hoặc khi chưa có đề xuất.</small>
      <div className="button-row">
        <button className="button button-secondary" type="button" aria-busy={busy} disabled={decisionLocked} onClick={() => void decide('REJECTED')}>{busy ? 'Đang xử lý…' : 'Từ chối'}</button>
        <button className="button button-primary" type="button" aria-busy={busy} disabled={decisionLocked} onClick={() => void decide('APPROVED')}><Check aria-hidden="true" /> {busy ? 'Đang xử lý…' : 'Phê duyệt'}</button>
      </div>
    </section>}
    <button className="auth-quiet-refresh" type="button" aria-busy={loading} disabled={busy || loading} onClick={reloadDetail}>{loading ? 'Đang tải…' : 'Tải lại trạng thái'}</button>
  </section>
}

const RETRYABLE_AI_FAILURE_CODES = new Set([
  'PIPELINE_TIMEOUT',
  'PROVIDER_TIMEOUT',
  'PROVIDER_ERROR',
  'INVALID_SCHEMA',
  'INVALID_PROVIDER_RESPONSE',
])

function latestRunForRound(runs: WorkflowAiEvaluation[], roundNumber: number): WorkflowAiEvaluation | null {
  return runs
    .filter(run => run.round_number === roundNumber)
    .reduce<WorkflowAiEvaluation | null>((latest, run) =>
      !latest || (run.attempt_number ?? 1) > (latest.attempt_number ?? 1) ? run : latest, null)
}

function isRetryableEvaluationRun(run: WorkflowAiEvaluation | null): boolean {
  if (!run || !['FAILED', 'TIMED_OUT'].includes(run.status)
    || run.result_disposition !== 'APPLIED' || (run.attempt_number ?? 1) !== 1) {
    return false
  }
  const codes = new Set<string>()
  if (run.failure_reason) codes.add(run.failure_reason)
  for (const error of run.evaluation?.agent_errors ?? []) codes.add(error.code)
  return codes.size > 0 && [...codes].every(code => RETRYABLE_AI_FAILURE_CODES.has(code))
}

type AiStatusTone = 'success' | 'review' | 'pending' | 'unavailable' | 'neutral'

function AiEvaluationResults({ plan, finalCheckerDecision }: {
  plan: WorkflowPlan
  finalCheckerDecision: WorkflowEvent | undefined
}) {
  const latestRun = latestRunForRound(plan.ai_evaluations, plan.current_round)
    ?? plan.ai_evaluations[plan.ai_evaluations.length - 1]
    ?? null
  const overallStatus = latestRun
    ? aiRunStatus(plan, latestRun)
    : { label: 'Chưa có kết quả đánh giá AI', tone: 'neutral' as const }

  return <section className="auth-workflow-card auth-ai-results" aria-labelledby="auth-ai-results-title">
    <header className="auth-ai-results-heading">
      <span className="auth-ai-heading-icon" aria-hidden="true"><History /></span>
      <div className="auth-ai-heading-copy">
        <p>Đánh giá hồ sơ</p>
        <h2 id="auth-ai-results-title">Kết quả đánh giá AI</h2>
      </div>
      {plan.ai_evaluations.length > 0 && <AiStatusBadge label={overallStatus.label} tone={overallStatus.tone} />}
    </header>

    {plan.ai_evaluations.length === 0
      ? <div className="auth-ai-empty" role="status">
        <FileText aria-hidden="true" />
        <p>Chưa có kết quả đánh giá AI cho hồ sơ này.</p>
      </div>
      : <div className="auth-ai-run-list">{plan.ai_evaluations.map(item => {
        const evaluation = item.evaluation
        const decision = plan.engine_decisions.find(entry => entry.round_number === item.round_number)
        const runStatus = aiRunStatus(plan, item)
        const reviewPending = isCheckerReviewPending(plan, item.round_number)
        const evaluationReasonSource = evaluation?.status === 'SUCCEEDED' ? evaluation.reason : ''
        const evaluationReason = displayableReason(evaluationReasonSource)
        const evaluationReasonWasFiltered = Boolean(evaluationReasonSource?.trim()) && !evaluationReason
        const engineDecisionReasonSource = decision?.decision.reason ?? ''
        const engineDecisionReason = displayableReason(engineDecisionReasonSource)
        const engineDecisionReasonWasFiltered = Boolean(engineDecisionReasonSource.trim()) && !engineDecisionReason
        const strategyResult = item.strategy_evaluation?.status === 'SUCCEEDED'
          ? item.strategy_evaluation.result : null
        const stageOnlyStrategyScore = evaluation?.status !== 'SUCCEEDED'
          && evaluation?.feasibility_score == null
          && strategyResult?.feasibility_score != null
        const strategyScore = evaluation?.feasibility_score ?? strategyResult?.feasibility_score ?? null

        return <details className="auth-ai-run" key={item.id} open={item.round_number === plan.current_round}>
          <summary>
            <span className="auth-ai-run-context"><strong>Vòng {item.round_number}</strong><small>Phiên bản {item.version_number}</small></span>
            <AiStatusBadge label={runStatus.label} tone={runStatus.tone} />
          </summary>
          <div className="auth-ai-run-content">
            <div className="auth-ai-stage-grid">
              {item.visual_extraction
                ? <VlmExtractionDetails extraction={item.visual_extraction} reviewPending={reviewPending} />
                : <AiStageCard title="Trích xuất nội dung ảnh" statusLabel={runStatusForMissingStage(item.status)} tone={statusTone(item.status)}>
                  <p>Chưa có nội dung trích xuất cho bước này.</p>
                </AiStageCard>}
              <TaskEvaluationDetails title="Đánh giá nội dung hình ảnh" stage={item.media_evaluation} kind="media" reviewPending={reviewPending} />
              <TaskEvaluationDetails title="Đánh giá tính khả thi" stage={item.strategy_evaluation} kind="strategy" reviewPending={reviewPending} />
              <AiStageCard
                title="Đánh giá tổng thể"
                statusLabel={evaluation ? evaluationStatusLabel(evaluation.status) : runStatus.label}
                tone={evaluation ? statusTone(evaluation.status) : runStatus.tone}
                wide
              >
                {evaluation
                  ? <>
                    {evaluation.status === 'SUCCEEDED'
                      ? evaluationReason
                        ? <p><strong>Giải thích đánh giá</strong>{evaluationReason}</p>
                        : evaluationReasonWasFiltered && <p role="status">Chưa có giải thích phù hợp để hiển thị.</p>
                      : <p role="status">{incompleteEvaluationMessage(plan, item.round_number)}</p>}
                    <div className="auth-ai-outcome-grid">
                      <div>
                        <span>Đánh giá nội dung hình ảnh</span>
                        <strong>{mediaOutcomeLabel(evaluation.media_result)}</strong>
                        {evaluation.media_confidence !== null && <small>Mức độ tin cậy: {percent(evaluation.media_confidence)}</small>}
                      </div>
                      <div>
                        <span>Đánh giá tính khả thi</span>
                        <strong>{strategyScore === null
                          ? 'Chưa có điểm'
                          : (stageOnlyStrategyScore ? 'Điểm riêng: ' : '') + strategyScore + ' / 100'}</strong>
                        {evaluation.feasibility_confidence !== null && <small>Mức độ tin cậy: {percent(evaluation.feasibility_confidence)}</small>}
                      </div>
                      <div><span>Khuyến nghị</span><strong>{recommendationLabel(evaluation.proposed_action)}</strong></div>
                    </div>
                    {stageOnlyStrategyScore && <p role="status">Điểm đánh giá riêng đã được lưu nhưng chưa đủ để kết luận kết quả tổng thể.</p>}
                    {evaluation.criterion_scores.length > 0 && <div className="auth-ai-result-group">
                      <h4>Đánh giá theo tiêu chí</h4>
                      <ul className="auth-ai-result-list">{evaluation.criterion_scores.map((score, index) => {
                        const rationale = displayableReason(score.rationale)
                        return <li key={index}><strong>{criterionLabel(score.criterion_id)} · {score.score} / {score.maximum_score}</strong>{rationale && <p>{rationale}</p>}</li>
                      })}</ul>
                    </div>}
                    {evaluation.media_findings.length > 0 && <div className="auth-ai-result-group">
                      <h4>Phát hiện từ hình ảnh</h4>
                      <ul className="auth-ai-result-list">{evaluation.media_findings.map((finding, index) => {
                        const description = displayableReason(finding.description)
                        return description ? <li key={index}><strong>{severityLabel(finding.severity)}</strong><p>{description}</p></li> : null
                      })}</ul>
                    </div>}
                    {evaluation.evidence_conflicts.length > 0 && <div className="auth-ai-result-group">
                      <h4>Thông tin chưa thống nhất</h4>
                      <ul className="auth-ai-result-list">{evaluation.evidence_conflicts.map((conflict, index) => {
                        const description = displayableReason(conflict.description)
                        return description ? <li key={index}>{description}</li> : null
                      })}</ul>
                    </div>}
                    {evaluation.missing_facts.length > 0 && <p role="status">{reviewPending ? 'Hồ sơ cần được Checker xem xét.' : 'AI cần thêm thông tin để hoàn tất đánh giá.'}</p>}
                    {evaluation.evidence.length > 0 && <div className="auth-ai-result-group">
                      <h4>Bằng chứng</h4>
                      <ul className="auth-ai-result-list">{evaluation.evidence.map((evidence, index) => {
                        const observation = displayableReason(evidence.observation)
                        return observation ? <li key={index}>{observation}</li> : null
                      })}</ul>
                    </div>}
                    {evaluation.assumptions.length > 0 && <div className="auth-ai-result-group">
                      <h4>Giả định</h4>
                      <ul className="auth-ai-result-list">{evaluation.assumptions.map((assumption, index) => {
                        const safeAssumption = displayableReason(assumption)
                        return safeAssumption ? <li key={index}>{safeAssumption}</li> : null
                      })}</ul>
                    </div>}
                  </>
                  : <p role="status">{runMessage(item.status)}</p>}
              </AiStageCard>
            </div>

            {decision && <section className={'auth-ai-decision ' + (decision.outcome === 'AUTO_APPROVED' ? 'is-approved' : 'is-review')} aria-label="Kết quả xử lý hồ sơ">
              <div>
                <strong>{decision.outcome === 'AUTO_APPROVED'
                  ? 'Kế hoạch đã được tự động phê duyệt.'
                  : plan.status === 'PENDING_APPROVAL'
                    ? 'Hồ sơ cần được Checker xem xét.'
                    : 'Hồ sơ đã được chuyển Checker xem xét trong vòng duyệt này.'}</strong>
                {finalCheckerDecision && ['APPROVED', 'REJECTED'].includes(plan.status)
                  && <p>{finalCheckerDecision.action === 'APPROVED' ? 'Checker đã phê duyệt hồ sơ.' : 'Checker đã từ chối hồ sơ.'}</p>}
                {engineDecisionReason && <p><strong>Lý do xử lý:</strong> {engineDecisionReason}</p>}
                {engineDecisionReasonWasFiltered && <p role="status">Chi tiết lý do xử lý hiện chưa có nội dung phù hợp để hiển thị.</p>}
              </div>
              <small>Ngân sách: {budgetValidationLabel(decision.decision.budget_validation.result)}
                {decision.decision.budget_validation.limit_minor_units
                  && ' · hạn mức ' + formatBudget(decision.decision.budget_validation.limit_minor_units, decision.decision.budget_validation.currency || plan.payload.currency)}
              </small>
              {decision.decision.rule_checks.some(check => check.result !== 'PASS')
                && <p>Một số tiêu chí ở lần đánh giá này cần Checker xem xét.</p>}
            </section>}
          </div>
        </details>
      })}</div>}
  </section>
}

function AiStageCard({ title, statusLabel, tone, wide = false, children }: {
  title: string
  statusLabel: string
  tone: AiStatusTone
  wide?: boolean
  children: ReactNode
}) {
  return <section className={'auth-ai-stage-card' + (wide ? ' is-wide' : '')}>
    <header className="auth-ai-stage-heading">
      <h3>{title}</h3>
      <AiStatusBadge label={statusLabel} tone={tone} />
    </header>
    <div className="auth-ai-stage-content">{children}</div>
  </section>
}

function AiStatusBadge({ label, tone }: { label: string; tone: AiStatusTone }) {
  const Icon = tone === 'success' ? Check
    : tone === 'pending' || tone === 'review' ? Clock3
      : tone === 'unavailable' ? X : FileText
  return <span className={'auth-ai-status-badge is-' + tone}><Icon aria-hidden="true" />{label}</span>
}

function aiRunStatus(plan: WorkflowPlan, run: WorkflowAiEvaluation) {
  if (isCheckerReviewPending(plan, run.round_number)) {
    return { label: 'Hồ sơ cần được Checker xem xét.', tone: 'review' as const }
  }
  if (run.evaluation) {
    return { label: evaluationStatusLabel(run.evaluation.status), tone: statusTone(run.evaluation.status) }
  }
  return { label: runStatusLabel(run.status), tone: statusTone(run.status) }
}

function isCheckerReviewPending(plan: WorkflowPlan, roundNumber: number) {
  return plan.current_round === roundNumber
    && plan.status === 'PENDING_APPROVAL'
    && plan.processing_stage === 'HUMAN_REVIEW_REQUIRED'
}

function statusTone(status: string): AiStatusTone {
  if (status === 'SUCCEEDED' || status === 'PASS') return 'success'
  if (status === 'REVIEW_REQUIRED' || status === 'HUMAN_REVIEW_REQUIRED') return 'review'
  if (status === 'PENDING' || status === 'PROCESSING') return 'pending'
  if (status === 'FAILED' || status === 'TIMED_OUT' || status === 'NOT_CONFIGURED' || status === 'UNREADABLE') return 'unavailable'
  return 'neutral'
}

function runStatusForMissingStage(status: string) {
  if (status === 'PROCESSING') return 'Đang đánh giá'
  if (status === 'PENDING') return 'Đang chờ đánh giá'
  return 'Chưa có dữ liệu'
}

function runMessage(status: string) {
  if (status === 'FAILED' || status === 'TIMED_OUT') return 'Đánh giá AI chưa hoàn tất.'
  if (status === 'PROCESSING') return 'Đang đánh giá.'
  if (status === 'PENDING') return 'Đang chờ đánh giá.'
  if (status === 'SUCCEEDED') return 'Chưa có kết quả tổng thể.'
  return 'Chưa có dữ liệu đánh giá.'
}

function mediaOutcomeLabel(result: 'PASS' | 'REVIEW_REQUIRED' | null) {
  if (result === 'PASS') return 'Đạt yêu cầu'
  if (result === 'REVIEW_REQUIRED') return 'Cần Checker xem xét'
  return 'Chưa có kết quả'
}

function TaskEvaluationDetails({ title, stage, kind, reviewPending }: {
  title: string
  stage: WorkflowTaskEvaluation | null
  kind: 'media' | 'strategy'
  reviewPending: boolean
}) {
  if (!stage) return <AiStageCard title={title} statusLabel="Chưa có dữ liệu" tone="neutral"><p>Chưa có kết quả cho bước này.</p></AiStageCard>

  const result = stage.result
  const mediaOutOfScope = kind === 'media' && stage.status === 'REVIEW_REQUIRED'
    && stage.attempts === 0 && stage.raw_output_hash === null
    && result?.outcome === 'REVIEW_REQUIRED' && result.confidence == null
  const statusLabel = mediaOutOfScope ? 'Không thuộc phạm vi đánh giá' : taskStatusLabel(stage.status)
  const tone = mediaOutOfScope ? 'neutral' : statusTone(stage.status)
  const showResult = stage.status === 'SUCCEEDED' || stage.status === 'REVIEW_REQUIRED' && !mediaOutOfScope
  const reasonSource = showResult ? result?.reason : ''
  const reason = displayableReason(reasonSource)
  const reasonWasFiltered = Boolean(reasonSource?.trim()) && !reason
  const findings = showResult ? (result?.findings ?? []).flatMap(item => {
    const description = displayableReason(item.description)
    return description ? [{ severity: item.severity, description }] : []
  }) : []
  const ruleResults = showResult ? (result?.rule_results ?? []).flatMap(item => {
    const rationale = displayableReason(item.rationale)
    return rationale ? [{ result: item.result, rationale }] : []
  }) : []
  const criteria = showResult ? (result?.criterion_scores ?? []).flatMap(item => {
    const rationale = displayableReason(item.rationale)
    return [{ criterionId: item.criterion_id, score: item.score, maximumScore: item.maximum_score, weight: item.weight, rationale }]
  }) : []
  const assumptions = showResult ? (result?.assumptions ?? []).map(displayableReason).filter(Boolean) : []

  return <AiStageCard title={title} statusLabel={statusLabel} tone={tone}>
    {mediaOutOfScope && <p>Ảnh trong hồ sơ không thuộc phạm vi đánh giá.</p>}
    {stage.status === 'NOT_CONFIGURED' && <p role="status">Bước đánh giá này hiện chưa khả dụng.</p>}
    {(stage.status === 'FAILED' || stage.status === 'TIMED_OUT')
      && <p role="status">{reviewPending ? 'Hồ sơ cần được Checker xem xét.' : 'Đánh giá AI chưa hoàn tất.'}</p>}
    {stage.status === 'REVIEW_REQUIRED' && !mediaOutOfScope
      && <p role="status">Hồ sơ cần được Checker xem xét.</p>}
    {reason && <p className="auth-ai-explanation">{reason}</p>}
    {reasonWasFiltered && <p role="status">Chưa có giải thích phù hợp để hiển thị.</p>}
    {showResult && kind === 'media' && result?.outcome
      && <p>Kết quả: <strong>{mediaOutOfScope ? 'Không đánh giá: ngoài phạm vi' : result.outcome === 'PASS' ? 'Đạt yêu cầu' : 'Cần Checker xem xét'}</strong></p>}
    {findings.length > 0 && <div className="auth-ai-result-group"><h4>Phát hiện</h4><ul className="auth-ai-result-list">
      {findings.map((item, index) => <li key={index}><strong>{severityLabel(item.severity)}</strong><p>{item.description}</p></li>)}
    </ul></div>}
    {ruleResults.length > 0 && <div className="auth-ai-result-group"><h4>Kết quả theo tiêu chí</h4><ul className="auth-ai-result-list">
      {ruleResults.map((item, index) => <li key={index}><strong>{ruleResultLabel(item.result)}</strong><p>{item.rationale}</p></li>)}
    </ul></div>}
    {kind === 'media' && showResult && Boolean(result?.missing_evidence?.length)
      && <p role="status">{reviewPending ? 'Hồ sơ cần được Checker xem xét.' : 'Cần bổ sung bằng chứng để hoàn tất đánh giá.'}</p>}
    {kind === 'strategy' && showResult && result?.feasibility_score != null
      && <p>Điểm đánh giá: <strong>{result.feasibility_score} / 100</strong>{result.confidence != null && <small className="auth-ai-inline-note">Mức độ tin cậy: {percent(result.confidence)}</small>}</p>}
    {kind === 'strategy' && criteria.length > 0 && <div className="auth-ai-result-group">
      <h4>Đánh giá theo tiêu chí</h4>
      <ul className="auth-ai-score-list">{criteria.map((item, index) => <li key={index}>
        <div><strong>{criterionLabel(item.criterionId)}</strong><span>{item.score} / {item.maximumScore}</span></div>
        <small>Trọng số {item.weight}% · Phần điểm {(item.score * item.weight / 100).toFixed(2)}</small>
        {item.rationale && <p>{item.rationale}</p>}
      </li>)}</ul>
    </div>}
    {kind === 'strategy' && assumptions.length > 0 && <div className="auth-ai-result-group"><h4>Giả định</h4><ul className="auth-ai-result-list">
      {assumptions.map((item, index) => <li key={index}>{item}</li>)}
    </ul></div>}
    {kind === 'strategy' && showResult && Boolean(result?.missing_facts?.length)
      && <p role="status">{reviewPending ? 'Hồ sơ cần được Checker xem xét.' : 'AI cần thêm thông tin để hoàn tất đánh giá.'}</p>}
    {kind === 'strategy' && showResult && Boolean(result?.critical_gaps?.length)
      && <p role="status">{reviewPending ? 'Hồ sơ cần được Checker xem xét.' : 'Đánh giá AI chưa hoàn tất.'}</p>}
  </AiStageCard>
}

function VlmExtractionDetails({ extraction, reviewPending }: {
  extraction: WorkflowVlmExtraction
  reviewPending: boolean
}) {
  const hasFailedAttachment = extraction.attachments.some(attachment => Boolean(attachment.error_code))
  const incomplete = extraction.status === 'FAILED' || hasFailedAttachment

  return <AiStageCard title="Trích xuất nội dung ảnh" statusLabel={extractionStatusLabel(extraction.status)} tone={statusTone(extraction.status)}>
    <p>Kết quả trích xuất giúp Checker đối chiếu nội dung trong ảnh với hồ sơ.</p>
    {incomplete && <p role="status">{reviewPending ? 'Hồ sơ cần được Checker xem xét.' : 'Đánh giá AI chưa hoàn tất.'}</p>}
    {extraction.attachments.length === 0
      ? <p>Chưa có nội dung trích xuất cho bước này.</p>
      : <ul className="auth-vlm-attachments">{extraction.attachments.map((attachment, index) => {
        const ocrText = displayableReason(attachment.ocr_text)
        const observations = attachment.evidence.filter(item => item.kind === 'OBSERVATION')
          .map(item => displayableReason(item.text)).filter(Boolean)
        const detections = (attachment.object_detections ?? []).map(displayableReason).filter(Boolean)
        const qualityFindings = (attachment.visual_quality?.findings ?? []).map(displayableReason).filter(Boolean)
        const uncertainties = attachment.uncertainties.map(item => displayableReason(item.text)).filter(Boolean)
        const hasSafeContent = Boolean(ocrText) || observations.length > 0 || detections.length > 0
          || qualityFindings.length > 0 || uncertainties.length > 0

        return <li key={attachment.attachment_id}>
          <h4>Ảnh đính kèm {index + 1} · {extractionStatusLabel(attachment.status)}</h4>
          {ocrText && <div><strong>Văn bản trong ảnh</strong><blockquote>{ocrText}</blockquote></div>}
          {observations.length > 0 && <div><strong>Quan sát</strong><ul>{observations.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></div>}
          {detections.length > 0 && <div><strong>Đối tượng nhận diện</strong><ul>{detections.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></div>}
          {attachment.visual_quality && <div><strong>Chất lượng ảnh: {visualQualityLabel(attachment.visual_quality.result)}</strong>
            {qualityFindings.length > 0 && <ul>{qualityFindings.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul>}
          </div>}
          {uncertainties.length > 0 && <div><strong>Nội dung cần xác minh</strong><ul>{uncertainties.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul></div>}
          {!hasSafeContent && <p>Chưa có nội dung phù hợp để hiển thị cho ảnh này.</p>}
        </li>
      })}</ul>}
  </AiStageCard>
}

function SlaRoundHistory({ plan }: { plan: WorkflowPlan }) {
  const rounds = plan.sla_history ?? []
  const current = plan.sla_current ?? null
  const [now, setNow] = useState(() => Date.now())
  const [serverReadAt, setServerReadAt] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => { setServerReadAt(Date.now()) }, [current?.round_number, current?.seconds_until_due, current?.status])

  const isOpen = current?.applicable === true && current.closed_at === null
  const secondsLeft = isOpen && current.seconds_until_due !== null
    ? current.seconds_until_due - Math.floor((now - serverReadAt) / 1000)
    : null
  const warningBefore = current?.warning_before_minutes
  const liveStatus = secondsLeft === null ? current?.status ?? 'NOT_APPLICABLE'
    : secondsLeft <= 0 ? 'OVERDUE'
      : warningBefore !== null && warningBefore !== undefined && secondsLeft <= warningBefore * 60 ? 'WARNING'
        : 'IN_PROGRESS'

  return <section className="auth-workflow-card workflow-sla-card" aria-labelledby="workflow-sla-title">
    <div className="auth-workflow-card-heading"><Clock3 aria-hidden="true" /><h2 id="workflow-sla-title">Thời hạn duyệt</h2></div>
    {!current ? <p>Chưa có vòng duyệt.</p> : !current.applicable
      ? <p>Thời hạn duyệt không áp dụng cho vòng {current.round_number}.</p>
      : <div className="workflow-sla-current">
        <div><span className={`workflow-sla-status status-${liveStatus.toLowerCase()}`}>{slaStatusLabel(liveStatus)}</span><small>Vòng {current.round_number} · Phiên bản {current.version_number}</small></div>
        <strong aria-live="off">{secondsLeft === null ? '' : secondsLeft >= 0 ? `Còn ${formatCountdown(secondsLeft)}` : `Quá hạn ${formatCountdown(Math.abs(secondsLeft))}`}</strong>
        <dl><div><dt>Bắt đầu</dt><dd>{formatSlaDate(current.started_at)}</dd></div><div><dt>Cảnh báo</dt><dd>{formatSlaDate(current.warning_at)}</dd></div><div><dt>Hạn chót</dt><dd>{formatSlaDate(current.due_at)}</dd></div><div><dt>Đóng vòng</dt><dd>{formatSlaDate(current.closed_at)}</dd></div></dl>
        {isOpen && <small className="workflow-sla-note">Thời gian được tính từ lần cập nhật gần nhất. Tải lại để kiểm tra thông tin mới.</small>}
      </div>}
    {rounds.length > 0 && <details className="workflow-sla-history"><summary>Lịch sử SLA ({rounds.length} vòng)</summary><div className="auth-workflow-table-wrap"><table className="auth-workflow-table"><thead><tr><th>Vòng / Phiên bản</th><th>Trạng thái</th><th>Thời hạn</th><th>Hạn chót</th><th>Đóng vòng</th></tr></thead><tbody>
      {rounds.map(round => <SlaHistoryRow key={`${round.round_number}-${round.version_number}`} round={round} />)}
    </tbody></table></div></details>}
  </section>
}

function SlaHistoryRow({ round }: { round: WorkflowSlaRound }) {
  return <tr><td>{round.round_number} / {round.version_number}</td><td>{slaStatusLabel(round.status)}</td><td>{round.applicable ? formatMinutesForSla(round.duration_minutes) : '—'}</td><td>{formatSlaDate(round.due_at)}</td><td>{formatSlaDate(round.closed_at)}</td></tr>
}

function slaStatusLabel(value: string) {
  return ({ NOT_APPLICABLE: 'Không áp dụng', IN_PROGRESS: 'Đang trong hạn', WARNING: 'Sắp đến hạn', OVERDUE: 'Quá hạn', CLOSED_ON_TIME: 'Đóng đúng hạn', CLOSED_LATE: 'Đóng trễ' } as Record<string, string>)[value] ?? 'Chưa xác định'
}

function formatCountdown(seconds: number) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor(seconds % 3600 / 60)
  const remainder = seconds % 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`
}

function formatMinutesForSla(total: number | null) {
  if (total === null) return '—'
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return [hours ? `${hours} giờ` : '', minutes ? `${minutes} phút` : ''].filter(Boolean).join(' ') || '0 phút'
}

function formatSlaDate(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}
function safeWorkflowEvents(value: unknown): WorkflowEvent[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((candidate, index) => {
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return []
    const record = candidate as Record<string, unknown>
    if (typeof record.action !== 'string' || !record.action.trim()) return []
    if (record.actor_type !== 'HUMAN' && record.actor_type !== 'SYSTEM') return []
    const details = record.details && typeof record.details === 'object' && !Array.isArray(record.details)
      ? record.details as Record<string, unknown>
      : {}
    return [{
      id: typeof record.id === 'string' ? record.id : `event-${index}`,
      actor_id: typeof record.actor_id === 'string' ? record.actor_id : null,
      actor_type: record.actor_type,
      actor_name: typeof record.actor_name === 'string' ? record.actor_name : '',
      action: record.action,
      status_before: typeof record.status_before === 'string' ? record.status_before : null,
      status_after: typeof record.status_after === 'string' ? record.status_after : '',
      details,
      created_at: typeof record.created_at === 'string' ? record.created_at : '',
    }]
  })
}

function eventLabel(action: string) {
  return ({
    CREATED: 'Tạo bản nháp',
    UPDATED: 'Cập nhật nội dung',
    ATTACHMENT_UPLOADED: 'Tải ảnh lên',
    SUBMITTED: 'Gửi duyệt',
    AI_EVALUATION_QUEUED: 'Đã xếp đánh giá AI',
    AI_EVALUATION_STARTED: 'Bắt đầu đánh giá AI',
    AI_RESULT_IGNORED_STALE: 'Bỏ qua kết quả cũ',
    AI_REVIEW_ROUTED: 'Chuyển Checker theo policy',
    AI_EVALUATION_COMPLETED: 'Hoàn tất đánh giá AI',
    AI_RECOVERY_REVIEW_ROUTED: 'Chuyển Checker sau khi khôi phục',
    AI_AUTO_APPROVED: 'AI tự động phê duyệt',
    SLA_WARNING_SENT: 'Đã gửi cảnh báo SLA',
    SLA_OVERDUE_SENT: 'Đã gửi cảnh báo quá hạn SLA',
    CHECKER_REASSIGNED: 'Đổi Checker được giao',
    APPROVED: 'Đã phê duyệt',
    REJECTED: 'Đã từ chối',
  } as Record<string, string>)[action] ?? 'Hoạt động khác'
}

function eventActorName(event: WorkflowEvent) {
  const name = event.actor_name.trim()
  if (name) return name
  return event.actor_type === 'SYSTEM' ? 'Hệ thống' : 'Người dùng'
}

function eventTimestamp(value: string) {
  if (!value) return { dateTime: '', label: 'Không rõ thời gian' }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return { dateTime: '', label: 'Không rõ thời gian' }
  return { dateTime: value, label: date.toLocaleString('vi-VN') }
}

function eventStatusTransition(event: WorkflowEvent) {
  const before = event.status_before?.trim() || ''
  const after = event.status_after.trim()
  if (before && after) return `Trạng thái: ${workflowStageLabel(before)} → ${workflowStageLabel(after)}`
  if (after) return `Trạng thái: ${workflowStageLabel(after)}`
  return ''
}

function shouldClearPlanDetail(failure: unknown) {
  if (!(failure instanceof AuthApiError)) return false
  return [401, 403, 404].includes(failure.status)
    || ['UNAUTHENTICATED', 'FORBIDDEN', 'NOT_FOUND'].includes(failure.code || '')
}

const INTERNAL_REASON_PATTERNS = [
  /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/i,
  /\b[A-Za-z_$][A-Za-z0-9_$]*(?:Error|Exception|Fault|Failure)\b/i,
  /\b(?:model|provider)[\s_-]*(?:id|name|version|revision)\b/i,
  /\b(?:model|provider)\s*[:=]\s*[^\s,;]+/i,
  /\bmodel\b/i,
  /\b(?:provider|backend|inference|endpoint|configuration)\b/i,
  /\bpolicy\s*[:=]\s*[^\s,;]+/i,
  /\bstage\s*[:=]\s*[^\s,;]+/i,
  /\b(?:prompt|schema)[\s_-]*(?:id|name|version|revision|v\d+)\b/i,
  /\b(?:prompt|schema|json|payload|hash|exception|traceback)\b/i,
  /\b(?:error|failure)\s*[:=]/i,
  /\bpolicy[\s_-]*(?:id|version|snapshot|hash|revision|configuration)\b/i,
  /\b(?:attachment|asset)[\s_-]*(?:id|uuid)\b/i,
  /\bsha[\s-]*256\b/i,
  /\b(?:attempts?|provider[\s_-]*calls?|calls?[\s_-]*to[\s_-]*provider)\b/i,
  /\bidentity[\s_-]*mode\b/i,
  /\b(?:configuration|metadata)[\s_-]*(?:id|version|hash|value|details?)\b/i,
  /\b(?:inference|endpoint|traceback|exception|stack[\s_-]*trace)\b/i,
  /\bstack[\s_-]*trace\b/i,
  /\b(?:raw[_ -]*(?:json|payload)|json[_ -]*payload)\b/i,
  /\bmissing[_ -]+fields?\b/i,
  /\b(?:error|failure)[_ -]*(?:code|message|details?)\b/i,
  /\b(?:correlation|trace|reference)[_ -]*id\b/i,
  /\b(?:gpt|claude|gemini|llama)[-_]?\d[\w.-]*\b/i,
  /\b[a-f\d]{32,}\b/i,
  /\b[a-f\d]{8}-(?:[a-f\d]{4}-){3}[a-f\d]{12}\b/i,
  /\b(?:https?:\/\/|(?:GET|POST|PUT|PATCH|DELETE)\s+\/|[A-Z]:\\|\/(?:api|inference|backend)\/)\S*/i,
  /^\s*[\[{]\s*["'][^"']+["']\s*:/,
]

const INTERNAL_REASON_LABEL_SUFFIX = /(?:^|[\s,;—–-])(?:mã lỗi|error[\s_-]*(?:code|message|details?)|failure[\s_-]*(?:code|message|details?)|mô hình\s+AI|model(?:[\s_-]*(?:id|name|version|revision)|\s+AI)?|provider(?:[\s_-]*(?:id|name|version|revision|calls?))?|prompt(?:[\s_-]*(?:id|version|revision))?|schema(?:[\s_-]*(?:id|version|revision))?|policy(?:[\s_-]*(?:id|version|snapshot|hash|revision|configuration))?|attachment[\s_-]*(?:id|uuid)|sha[\s-]*256|hash|attempts?|identity[\s_-]*mode|configuration|metadata|stage|backend|inference|endpoint|stack[\s_-]*trace|raw[\s_-]*(?:json|payload)|json[\s_-]*payload|payload|exception|traceback)\s*[:=]?\s*[\s\S]*$/i
const INTERNAL_REASON_TOKEN_SUFFIX = /(?:[,;—–-]\s*)[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\s*[.!?]?\s*$/i
const INTERNAL_REASON_HASH_SUFFIX = /(?:[,;—–-]\s*)(?:[a-f\d]{32,}|[a-f\d]{8}-(?:[a-f\d]{4}-){3}[a-f\d]{12})\s*[.!?]?\s*$/i

function containsInternalReasonDetails(value: string) {
  return INTERNAL_REASON_PATTERNS.some(pattern => pattern.test(value))
}

function displayableReason(value: string | null | undefined) {
  const reason = value?.trim() ?? ''
  if (!reason) return ''

  const safeSegments = reason
    .split(/(?<=[.!?;])\s+|\r?\n+/)
    .map(segment => segment
      .replace(/\([^()]*\)/g, part => containsInternalReasonDetails(part) ? ' ' : part)
      .replace(/\[[^\[\]]*\]/g, part => containsInternalReasonDetails(part) ? ' ' : part)
      .replace(INTERNAL_REASON_LABEL_SUFFIX, '')
      .replace(INTERNAL_REASON_TOKEN_SUFFIX, '')
      .replace(INTERNAL_REASON_HASH_SUFFIX, '')
      .replace(/\s+([,.!?;:])/g, '$1')
      .trim())
    .filter(segment => segment && !containsInternalReasonDetails(segment))

  return safeSegments
    .map((segment, index) => index === safeSegments.length - 1 ? segment.replace(/[;,]\s*$/, '') : segment)
    .join(' ')
}

function runStatusLabel(status: string) {
  return ({ PENDING: 'Đang chờ đánh giá', PROCESSING: 'Đang đánh giá', FAILED: 'Đánh giá AI chưa hoàn tất.', TIMED_OUT: 'Đánh giá AI chưa hoàn tất.', SUCCEEDED: 'Đánh giá hoàn tất' } as Record<string, string>)[status] ?? 'Chưa có kết quả'
}

function evaluationStatusLabel(status: string) {
  return ({ SUCCEEDED: 'Đánh giá hoàn tất', FAILED: 'Đánh giá AI chưa hoàn tất.', TIMED_OUT: 'Đánh giá AI chưa hoàn tất.' } as Record<string, string>)[status] ?? 'Chưa có kết quả'
}

function taskStatusLabel(status: string) {
  return ({
    PENDING: 'Đang chờ đánh giá', PROCESSING: 'Đang đánh giá', SUCCEEDED: 'Hoàn tất',
    REVIEW_REQUIRED: 'Cần Checker xem xét', NOT_CONFIGURED: 'Chưa khả dụng',
    FAILED: 'Chưa hoàn tất', TIMED_OUT: 'Chưa hoàn tất',
  } as Record<string, string>)[status] ?? 'Chưa có kết quả'
}

function extractionStatusLabel(status: string) {
  return ({
    SUCCEEDED: 'Đã đọc nội dung ảnh',
    COMPLETE: 'Đã đọc đủ nội dung ảnh',
    PARTIAL: 'Đã đọc một phần nội dung ảnh',
    UNREADABLE: 'Chưa đọc được nội dung ảnh',
    FAILED: 'Chưa thể đọc nội dung ảnh',
  } as Record<string, string>)[status] ?? 'Chưa có kết quả'
}

function visualQualityLabel(result: 'PASS' | 'REVIEW_REQUIRED' | 'UNKNOWN') {
  return ({ PASS: 'Đủ rõ để kiểm tra', REVIEW_REQUIRED: 'Cần Checker xem lại', UNKNOWN: 'Chưa đánh giá' })[result]
}

function incompleteEvaluationMessage(plan: WorkflowPlan, roundNumber: number) {
  return isCheckerReviewPending(plan, roundNumber)
    ? 'Hồ sơ cần được Checker xem xét.'
    : 'Đánh giá AI chưa hoàn tất.'
}

function criterionLabel(id: string) {
  return ({
    objective: 'Mục tiêu', audience: 'Đối tượng', channel: 'Kênh', timeline: 'Thời gian',
    kpi: 'KPI', budget_efficiency: 'Hiệu quả ngân sách', risk_control: 'Kiểm soát rủi ro',
  } as Record<string, string>)[id] ?? 'Tiêu chí đánh giá'
}

function severityLabel(severity: string) {
  return ({ HARD_VIOLATION: 'Cần xử lý', WARNING: 'Cần lưu ý' } as Record<string, string>)[severity] ?? 'Cần xem xét'
}

function ruleResultLabel(result: string) {
  return ({ PASS: 'Đạt', FAIL: 'Cần Checker xem xét', REVIEW_REQUIRED: 'Cần Checker xem xét', UNKNOWN: 'Chưa đủ thông tin' } as Record<string, string>)[result] ?? 'Cần xem xét'
}

function budgetValidationLabel(result: 'PASS' | 'FAIL' | 'UNKNOWN') {
  return ({ PASS: 'Trong hạn mức', FAIL: 'Vượt hạn mức', UNKNOWN: 'Chưa đủ thông tin' })[result]
}

function recommendationLabel(action: string | null) {
  return action === 'RECOMMEND_AUTO_APPROVAL' ? 'Đề xuất đủ điều kiện tự động duyệt'
    : action === 'RECOMMEND_HUMAN_REVIEW' ? 'Đề xuất Checker xem xét' : 'Không có khuyến nghị'
}

function percent(value: number) { return `${Math.round(value * 100)}%` }

function detailErrorText(failure: unknown) {
  if (failure instanceof AuthApiError) {
    if (failure.status === 404 || failure.code === 'NOT_FOUND') return 'Kế hoạch không còn tồn tại hoặc không thuộc phạm vi tài khoản hiện tại.'
    if (failure.status === 403 || failure.code === 'FORBIDDEN') return 'Tài khoản hiện tại không có quyền xem kế hoạch này.'
    if (failure.status === 401 || failure.code === 'UNAUTHENTICATED') return 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.'
    if (failure.status === 409 || failure.code === 'CONFLICT') return 'Vòng duyệt đã thay đổi. Hãy tải trạng thái mới nhất trước khi tiếp tục.'
    if (failure.status === 422 || failure.code === 'VALIDATION_ERROR') return 'Dữ liệu hồ sơ chưa hợp lệ. Hãy kiểm tra nội dung rồi thử lại.'
    if (failure.code === 'NETWORK_ERROR') return 'Không kết nối được hệ thống xử lý hồ sơ. Kiểm tra kết nối rồi tải lại.'
    if (failure.status >= 500) return 'Hệ thống chưa thể tải trạng thái hồ sơ. Hãy thử tải lại.'
    return 'Không thể tải dữ liệu kế hoạch. Hãy thử tải lại.'
  }
  return 'Không thể tải dữ liệu kế hoạch. Hãy thử tải lại.'
}

function decisionErrorText(failure: AuthApiError) {
  if (failure.status === 401 || failure.code === 'UNAUTHENTICATED') return 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.'
  if (failure.status === 403 || failure.code === 'FORBIDDEN') return 'Bạn không còn quyền quyết định hồ sơ này.'
  if (failure.status === 404 || failure.code === 'NOT_FOUND') return 'Hồ sơ không còn khả dụng hoặc không thuộc phạm vi tài khoản hiện tại.'
  if (failure.status === 409 || failure.code === 'CONFLICT') return 'Vòng duyệt đã thay đổi. Trạng thái hồ sơ sẽ được tải lại.'
  if (failure.status === 422 || failure.code === 'VALIDATION_ERROR') return 'Dữ liệu quyết định chưa hợp lệ. Hãy kiểm tra lý do rồi thử lại.'
  if (failure.code === 'NETWORK_ERROR') return 'Không xác nhận được quyết định do lỗi kết nối. Nội dung vẫn được giữ; hãy kiểm tra trạng thái trước khi gửi lại.'
  if (failure.status >= 500) return 'Hệ thống chưa xác nhận được quyết định. Nội dung vẫn được giữ; hãy tải lại trạng thái trước khi gửi lại.'
  return 'Không thể hoàn tất quyết định. Nội dung vẫn được giữ; hãy kiểm tra trạng thái trước khi gửi lại.'
}

function statusLabel(status: WorkflowPlan['status']) {
  return ({ DRAFT: 'Bản nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối' })[status]
}

function workflowStageLabel(status: string) {
  return ({
    DRAFT: 'Bản nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối',
    AI_PENDING: 'Đang chờ đánh giá', AI_PROCESSING: 'Đang đánh giá',
    AI_PROCESSING_FAILED: 'Chưa thể hoàn tất đánh giá', HUMAN_REVIEW_REQUIRED: 'Chờ Checker xem xét',
    AI_AUTO_APPROVED: 'Đã tự động phê duyệt', COMPLETED: 'Hoàn tất',
  } as Record<string, string>)[status] ?? 'Trạng thái chưa xác định'
}

function formatBudget(value: string, currency: string) {
  const amount = Number(value)
  return value === '0' || (Number.isFinite(amount) && amount > 0) ? `${new Intl.NumberFormat('vi-VN').format(amount)} ${currency}` : '—'
}

function AuthAttachmentPreview({ planId, attachmentId, filename }: { planId: string; attachmentId: string; filename: string }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let objectUrl = ''
    authWorkflowService.getAttachment(planId, attachmentId)
      .then(blob => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => { if (active) setError('Không thể tải ảnh đính kèm. Hãy tải lại trang để thử lại.') })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attachmentId, planId])
  return error ? <span role="alert">{error}</span> : url ? <img className="auth-workflow-image-preview" src={url} alt={`Tệp đính kèm ${filename}`} /> : <span role="status">Đang tải ảnh…</span>
}
