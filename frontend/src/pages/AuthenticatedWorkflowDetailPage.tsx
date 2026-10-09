import { ArrowLeft, Check, Clock3, FileText, History, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { formatDateTime, statusLabel as processingStageLabel } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowEvent, WorkflowPlan, WorkflowTaskEvaluation, WorkflowVlmExtraction } from '../types/authWorkflow'

export function AuthenticatedWorkflowDetailPage() {
  const { planId = '' } = useParams()
  const location = useLocation()
  const { user, roles } = useAuth()
  const [plan, setPlan] = useState<WorkflowPlan | null>(null)
  const [error, setError] = useState('')
  const [errorReference, setErrorReference] = useState('')
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
    setErrorReference('')
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
        if (failure instanceof AuthApiError && failure.correlationId) setErrorReference(failure.correlationId)
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
      setError('Hồ sơ chưa có vòng duyệt hợp lệ theo dữ liệu máy chủ.')
      return
    }
    if (reason.length > 5000 || overrideReason.length > 5000) {
      setError('Lý do và lý do override không được vượt quá 5.000 ký tự.')
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
      setError('Nhập lý do override khi quyết định khác hoặc chưa có khuyến nghị AI.')
      return
    }
    setBusy(true); setError(''); setErrorReference(''); setDecisionNotice('')
    try {
      const result = await authWorkflowService.decide(planId, activeRound, action, reason, overrideReason)
      setPlan(result)
      setReason('')
      setOverrideReason('')
      setDecisionNotice(action === 'APPROVED' ? 'Máy chủ đã xác nhận phê duyệt hồ sơ.' : 'Máy chủ đã xác nhận từ chối hồ sơ.')
    } catch (failure) {
      const decisionError = failure instanceof AuthApiError
        ? failure
        : new AuthApiError(0, failure instanceof Error ? failure.message : 'Không thể hoàn tất quyết định.', 'CLIENT_ERROR')
      setErrorReference(decisionError.correlationId || '')
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
          setErrorReference(refreshError.correlationId || decisionError.correlationId || '')
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
      setError(failure instanceof Error ? failure.message : String(failure))
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
    {error && <><p>{error}</p>{errorReference && <p className="auth-workflow-error-reference">Mã tham chiếu: {errorReference}</p>}<div className="button-row"><Link to="/workflow/plans">Quay lại danh sách</Link><button className="button button-secondary" type="button" disabled={loading} onClick={reloadDetail}>{loading ? 'Đang tải…' : 'Thử tải lại'}</button></div></>}
  </section>
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

  return <section className="auth-workflow-page">
    <Link className="auth-back-link" to={isAssignedChecker ? '/workflow/reviews' : '/workflow/plans'}><ArrowLeft /> Quay lại danh sách</Link>
    {navigationNotice && <div className="auth-workflow-alert is-success" role="status"><Check /><p>{navigationNotice}</p></div>}
    {decisionNotice && <div className="auth-workflow-alert is-success" role="status"><Check aria-hidden="true" /><p>{decisionNotice}</p><Link to="/workflow/reviews">Quay lại hàng chờ duyệt</Link></div>}
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">{plan.code} · Version {plan.current_version || '—'} · Round {plan.current_round || '—'}</p><h1>{plan.payload.title || 'Kế hoạch chưa có tên'}</h1><p>Maker: {plan.maker_name} <span aria-hidden="true">·</span> Checker: {plan.checker_name || 'Chưa gán'} <span aria-hidden="true">·</span> Cập nhật: {formatDateTime(plan.updated_at)}</p></div><div className="auth-workflow-status-pair"><span className={`workflow-status status-${plan.status.toLowerCase()}`}>{statusLabel(plan.status)}</span><span className="workflow-processing-stage">Giai đoạn: {processingStageLabel(plan.processing_stage)}</span></div></div>
    {loading && <p className="auth-workflow-refresh-status" role="status">Đang cập nhật kế hoạch… Nội dung hiện có vẫn được giữ.</p>}
    {error && <div className="auth-workflow-alert is-error" role="alert"><div><p>{error}</p>{errorReference && <small>Mã tham chiếu: {errorReference}</small>}</div>{detailLoadFailed && <button className="button button-secondary" type="button" disabled={loading} onClick={reloadDetail}>{loading ? 'Đang tải…' : 'Thử tải lại'}</button>}</div>}
    {['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) && <div className="auth-workflow-alert is-progress" role="status"><Clock3 /><div><strong>Đang đánh giá kế hoạch</strong><p>Snapshot đã được lưu. Tải lại để xem trạng thái mới nhất. Checker được phân công có thể kiểm tra tác vụ đã gián đoạn; hệ thống chỉ chuyển sang Human Review sau 4 phút không hoàn tất.</p>{isAssignedChecker && <button type="button" className="button button-secondary" disabled={recoveryBusy} onClick={() => void recoverInterruptedEvaluation()}>{recoveryBusy ? 'Đang kiểm tra…' : 'Kiểm tra pipeline bị gián đoạn'}</button>}</div></div>}
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
      </dl>{plan.decision_reason && <div className={`auth-workflow-alert ${plan.status === 'REJECTED' ? 'is-error' : 'is-review'}`}><strong>{plan.status === 'REJECTED' ? 'Lý do từ chối' : plan.status === 'PENDING_APPROVAL' ? 'Lý do chuyển Checker' : 'Lý do chuyển Checker (lịch sử)'}</strong><p>{plan.decision_reason}</p></div>}
        <div className="auth-workflow-attachments"><h3>Ảnh đính kèm</h3>{plan.attachments.length ? plan.attachments.map(item => <div key={item.id} className="auth-workflow-attachment">{canViewAttachments && <AuthAttachmentPreview planId={plan.id} attachmentId={item.id} filename={item.filename} />}<span><strong>{item.filename}</strong><small>{item.media_type} · {Math.ceil(item.byte_size / 1024)} KB · SHA-256 {item.content_hash.slice(0, 12)}…</small></span></div>) : <p>Chưa có ảnh đính kèm.</p>}</div>
      </section>
      <section className="auth-workflow-card"><div className="auth-workflow-card-heading"><History /><h2>Lịch sử xử lý</h2><span className="auth-workflow-history-count">{history.length} sự kiện</span></div>{history.length === 0 ? <p className="auth-workflow-history-empty">Chưa có sự kiện hoạt động được ghi nhận.</p> : <ol className="auth-workflow-history" aria-label="Sự kiện của kế hoạch">{history.map((event, index) => {
        const timestamp = eventTimestamp(event.created_at)
        const transition = eventStatusTransition(event)
        const version = event.details.version
        const round = event.details.round
        return <li key={event.id || `${event.action}-${index}`}><span className="history-icon">{event.action === 'APPROVED' || event.action === 'AI_AUTO_APPROVED' ? <Check aria-hidden="true" /> : event.action === 'REJECTED' ? <X aria-hidden="true" /> : <Clock3 aria-hidden="true" />}</span><div><strong>{eventLabel(event.action)}</strong><p><span>{eventActorName(event)}</span> · {timestamp.dateTime ? <time dateTime={timestamp.dateTime}>{timestamp.label}</time> : <span>{timestamp.label}</span>}</p>{transition && <p className="auth-workflow-history-transition">{transition}</p>}{typeof event.details.reason === 'string' && event.details.reason.trim() && <blockquote>{event.details.reason}</blockquote>}{typeof version === 'number' && Number.isFinite(version) && typeof round === 'number' && Number.isFinite(round) && <small>Version {version} / Round {round}</small>}</div></li>
      })}</ol>}</section>
    </div>
    {plan.ai_evaluations.length > 0 && <section className="auth-workflow-card auth-ai-results"><div className="auth-workflow-card-heading"><History /><h2>Kết quả đánh giá AI</h2></div>{plan.ai_evaluations.map(item => {
      const evaluation = item.evaluation
      const decision = plan.engine_decisions.find(entry => entry.round_number === item.round_number)
      const strategyResult = item.strategy_evaluation?.status === 'SUCCEEDED'
        ? item.strategy_evaluation.result : null
      const stageOnlyStrategyScore = evaluation?.status !== 'SUCCEEDED'
        && evaluation?.feasibility_score == null
        && strategyResult?.feasibility_score != null
      const strategyScore = evaluation?.feasibility_score ?? strategyResult?.feasibility_score ?? null
      return <details key={item.id} open={item.round_number === plan.current_round}>
        <summary>Version {item.version_number} · Round {item.round_number} · {evaluation ? evaluationStatusLabel(evaluation.status) : runStatusLabel(item.status)}</summary>
        <div className="auth-ai-metadata"><span>{providerLabel(item.provider)}</span><span>Model ID: {item.model_id || item.model_version || 'Chưa xác định'}</span>{item.model_id && item.model_version && <span>Model revision: {item.model_version}</span>}<span>Policy: {item.policy_version}</span><span>Tổng lượt gọi provider qua các stage: {item.attempts}{item.retried ? ' · có retry' : ''}</span></div>
        {item.visual_extraction
          ? <VlmExtractionDetails extraction={item.visual_extraction} plan={plan} />
          : <section className="auth-ai-phase"><h3>Trích xuất ảnh (VLM) · {item.status === 'PROCESSING' ? 'Đang xử lý' : item.status === 'PENDING' ? 'Đang chờ' : 'Chưa có kết quả riêng'}</h3><p>Ảnh chỉ được trích xuất một lần cho snapshot đã gửi. Tải lại trang chỉ đọc kết quả đã lưu.</p></section>}
        <TaskEvaluationDetails title="Media Compliance" stage={item.media_evaluation} kind="media" />
        <TaskEvaluationDetails title="Strategy Evaluation" stage={item.strategy_evaluation} kind="strategy" />
        {evaluation ? <>
          <section className="auth-ai-phase"><h3>Đánh giá tổng thể</h3><p>{evaluation.reason}</p></section>
          <p>Trạng thái đánh giá AI tổng thể: {evaluationStatusLabel(evaluation.status)}</p>
          <dl className="auth-workflow-definition-grid auth-ai-metrics">
            <div><dt>Media Compliance</dt><dd>{evaluation.media_result || 'Chưa có kết quả'}{evaluation.media_confidence !== null && ` · ${percent(evaluation.media_confidence)}`}</dd></div>
            <div><dt>Strategy Evaluation</dt><dd>{strategyScore === null ? 'Chưa có điểm' : `${stageOnlyStrategyScore ? 'Strategy đã đánh giá: ' : ''}${strategyScore} / 100`}{evaluation.feasibility_confidence !== null && ` · ${percent(evaluation.feasibility_confidence)}`}</dd></div>
            <div><dt>Khuyến nghị</dt><dd>{recommendationLabel(evaluation.proposed_action)}</dd></div>
            <div><dt>Input hash</dt><dd className="auth-hash">{item.input_hash}</dd></div>
          </dl>
          {stageOnlyStrategyScore && <p role="status">Điểm Strategy được lưu thành công ở riêng stage, nhưng không được engine sử dụng vì đánh giá tổng thể chưa hợp lệ ({evaluation.status}).</p>}
          {evaluation.criterion_scores.length > 0 && <div><h3>Strategy Evaluation · điểm theo tiêu chí</h3><ul>{evaluation.criterion_scores.map(score => <li key={score.criterion_id}>{score.criterion_id}: {score.score} / {score.maximum_score} — {score.rationale}</li>)}</ul></div>}
          {evaluation.media_findings.length > 0 && <div><h3>Media Compliance · phát hiện</h3><ul>{evaluation.media_findings.map(finding => <li key={finding.finding_id}><strong>{finding.severity}</strong>: {finding.description}</li>)}</ul></div>}
          {evaluation.evidence_conflicts.length > 0 && <div><h3>Thông tin chưa thống nhất</h3><ul>{evaluation.evidence_conflicts.map(conflict => <li key={conflict.conflict_id}>{conflict.description}</li>)}</ul></div>}
          {evaluation.missing_facts.length > 0 && <div><h3>Thông tin còn thiếu</h3><ul>{evaluation.missing_facts.map(fact => <li key={fact}>{fact}</li>)}</ul></div>}
          {evaluation.evidence.length > 0 && <div><h3>Bằng chứng</h3><ul>{evaluation.evidence.map(evidence => <li key={evidence.evidence_id}>{evidence.observation} <small>({evidence.source_type})</small></li>)}</ul></div>}
          {evaluation.assumptions.length > 0 && <div><h3>Giả định</h3><ul>{evaluation.assumptions.map((assumption, index) => <li key={`${index}-${assumption}`}>{assumption}</li>)}</ul></div>}
          {evaluation.agent_errors.length > 0 && <div className="auth-workflow-alert is-error"><div><strong>Pipeline cần Checker xử lý</strong><ul>{evaluation.agent_errors.map((failure, index) => <li key={`${failure.component}-${index}`}>{failure.component}: {failure.code} — {evaluationErrorLabel(failure.code, failure.message)}</li>)}</ul></div></div>}
        </> : <p>Kết quả xử lý: {item.failure_reason || 'Đang chờ xử lý.'}</p>}
        {decision && <div className={`auth-ai-decision ${decision.outcome === 'AUTO_APPROVED' ? 'is-approved' : 'is-review'}`}><strong>{decision.outcome === 'AUTO_APPROVED' ? 'Engine đã tự động phê duyệt theo policy.' : plan.status === 'PENDING_APPROVAL' ? 'Engine đã chuyển Checker; hồ sơ đang chờ quyết định.' : 'Engine đã chuyển hồ sơ sang Checker (lịch sử).'}</strong><p>{decision.decision.reason}</p>{finalCheckerDecision && ['APPROVED', 'REJECTED'].includes(plan.status) && <p>{finalCheckerDecision.action === 'APPROVED' ? 'Checker đã phê duyệt hồ sơ.' : 'Checker đã từ chối hồ sơ.'}</p>}<small>Ngân sách: {decision.decision.budget_validation.result}{decision.decision.budget_validation.limit_minor_units && ` · hạn mức ${formatBudget(decision.decision.budget_validation.limit_minor_units, decision.decision.budget_validation.currency || plan.payload.currency)}`}</small>{decision.decision.rule_checks.some(check => check.result !== 'PASS') && <ul>{decision.decision.rule_checks.filter(check => check.result !== 'PASS').map(check => <li key={check.rule_id}>{check.rule_id}: {check.result}</li>)}</ul>}</div>}
      </details>
    })}</section>}
    {plan.versions.length > 0 && <section className="auth-workflow-card auth-version-card"><div className="auth-workflow-card-heading"><History /><h2>Snapshot đã gửi</h2></div>{plan.versions.map(version => <details key={version.version_number}><summary>Version {version.version_number} · Round {version.round_number} · {new Date(version.created_at).toLocaleString('vi-VN')}</summary><p>{version.payload.summary}</p><ul>{version.attachments.map(item => <li key={item.id}>{item.filename} · SHA-256 {item.content_hash}</li>)}</ul></details>)}</section>}
    {canEdit && <div className="auth-workflow-actions"><Link className="button button-secondary" to={`/workflow/plans/${plan.id}/edit`}>Chỉnh sửa và gửi lại</Link></div>}
    {canDecide && <section className="auth-workflow-card auth-decision-card">
      <div className="auth-workflow-card-heading"><Check aria-hidden="true" /><h2>Quyết định Checker</h2></div>
      <p>Nội dung và snapshot được lưu chỉ đọc. Từ chối cần có lý do.</p>
      {['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) && <div className="auth-workflow-alert is-progress" role="status">
        <Clock3 aria-hidden="true" /><p>AI đang xử lý. Các quyết định được khóa cho đến khi máy chủ cập nhật kết quả.</p>
      </div>}
      {plan.current_round < 1 && <div className="auth-workflow-alert is-review" role="status"><p>Chưa có vòng duyệt hợp lệ để gửi quyết định.</p></div>}
      <label className="auth-field">Lý do hoặc nhận xét
        <textarea rows={3} maxLength={5000} aria-describedby="review-reason-help" disabled={decisionLocked} value={reason} onChange={event => setReason(event.target.value)} placeholder="Bắt buộc khi từ chối" />
      </label>
      <small id="review-reason-help" className="auth-workflow-form-hint">{reason.length}/5.000 ký tự · Bắt buộc khi từ chối.</small>
      <label className="auth-field">Lý do override AI
        <textarea rows={2} maxLength={5000} aria-describedby="review-override-help" disabled={decisionLocked} value={overrideReason} onChange={event => setOverrideReason(event.target.value)} placeholder="Bắt buộc khi quyết định khác hoặc chưa có khuyến nghị AI" />
      </label>
      <small id="review-override-help" className="auth-workflow-form-hint">{overrideReason.length}/5.000 ký tự · Bắt buộc khi quyết định khác hoặc chưa có khuyến nghị AI.</small>
      <div className="button-row">
        <button className="button button-secondary" type="button" aria-busy={busy} disabled={decisionLocked} onClick={() => void decide('REJECTED')}>{busy ? 'Đang xử lý…' : 'Từ chối'}</button>
        <button className="button button-primary" type="button" aria-busy={busy} disabled={decisionLocked} onClick={() => void decide('APPROVED')}><Check aria-hidden="true" /> {busy ? 'Đang xử lý…' : 'Phê duyệt'}</button>
      </div>
    </section>}
    <button className="auth-quiet-refresh" type="button" aria-busy={loading} disabled={busy || loading} onClick={reloadDetail}>{loading ? 'Đang tải…' : 'Tải lại trạng thái'}</button>
  </section>
}

function TaskEvaluationDetails({ title, stage, kind }: {
  title: string
  stage: WorkflowTaskEvaluation | null
  kind: 'media' | 'strategy'
}) {
  if (!stage) return <section className="auth-ai-phase"><h3>{title}</h3><p>Phiên xử lý cũ chưa lưu riêng bước này.</p></section>
  const result = stage.result
  const mediaOutOfScope = kind === 'media' && stage.status === 'REVIEW_REQUIRED'
    && stage.attempts === 0 && stage.raw_output_hash === null
    && result?.outcome === 'REVIEW_REQUIRED' && result.confidence == null
  return <section className="auth-ai-phase auth-task-evaluation">
    <h3>{title} · {mediaOutOfScope ? 'Không đánh giá: ngoài phạm vi policy' : taskStatusLabel(stage.status)}</h3>
    <div className="auth-ai-metadata">
      {!mediaOutOfScope && <><span>Model: {stage.model_id || 'Chưa cấu hình'}</span>
      {stage.model_version && <span>Model version: {stage.model_version}</span>}</>}
      <span>Policy/Rubric: {stage.configuration_id || 'Chưa cấu hình'}{stage.configuration_version ? ` · ${stage.configuration_version}` : ''}</span>
      {!mediaOutOfScope && stage.prompt_version && <span>Prompt: {stage.prompt_version}</span>}
      {!mediaOutOfScope && stage.schema_version && <span>Schema: {stage.schema_version}</span>}
      {stage.raw_output_hash && <span>Output SHA-256: {stage.raw_output_hash}</span>}
      <span>{mediaOutOfScope ? 'Provider không được gọi vì kế hoạch nằm ngoài phạm vi policy.' : `Lượt gọi provider của stage: ${stage.attempts}${stage.retried ? ' · có retry' : ''}`}</span>
    </div>
    {stage.reason && <p>{stage.reason}</p>}
    {stage.error_code && <div className="auth-workflow-alert is-review" role="status">{stage.error_code} · Checker cần xem xét bước này.</div>}
    {result?.reason && result.reason !== stage.reason && <p>{result.reason}</p>}
    {kind === 'media' && result?.outcome && <p>Kết quả: <strong>{mediaOutOfScope ? 'Không đánh giá: ngoài phạm vi policy' : result.outcome === 'PASS' ? 'Đạt policy' : 'Cần Checker xem xét'}</strong>{result.confidence != null && ` · ${percent(result.confidence)}`}</p>}
    {kind === 'media' && result?.findings?.length ? <div><h4>Phát hiện</h4><ul>{result.findings.map(item => <li key={item.finding_id}><strong>{item.severity}</strong>: {item.description}</li>)}</ul></div> : null}
    {kind === 'media' && result?.rule_results?.length ? <div><h4>Kết quả theo quy tắc</h4><ul>{result.rule_results.map(item => <li key={item.rule_id}>{item.rule_id}: {item.result} — {item.rationale}</li>)}</ul></div> : null}
    {kind === 'media' && result?.missing_evidence?.length ? <div><h4>Bằng chứng ảnh còn thiếu</h4><ul>{result.missing_evidence.map(item => <li key={`${item.rule_id}-${item.evidence_kind}`}>{item.rule_id}: cần {item.evidence_kind}</li>)}</ul></div> : null}
    {kind === 'strategy' && result?.feasibility_score != null && <p>Điểm có trọng số do backend tính: <strong>{result.feasibility_score} / 100</strong>{result.confidence != null && ` · ${percent(result.confidence)}`}</p>}
    {kind === 'strategy' && result?.criterion_scores?.length ? <div className="auth-task-score-table-wrap"><table className="auth-task-score-table"><thead><tr><th>Tiêu chí</th><th>Điểm / 100</th><th>Trọng số</th><th>Phần điểm</th><th>Căn cứ</th></tr></thead><tbody>{result.criterion_scores.map(item => <tr key={item.criterion_id}><th scope="row">{item.criterion_id}</th><td>{item.score} / {item.maximum_score}</td><td>{item.weight}%</td><td>{(item.score * item.weight / 100).toFixed(2)}</td><td>{item.rationale}<small>{item.evidence_refs.join(', ')}</small></td></tr>)}</tbody></table></div> : null}
    {kind === 'strategy' && result?.assumptions?.length ? <div><h4>Giả định</h4><ul>{result.assumptions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></div> : null}
    {kind === 'strategy' && result?.missing_facts?.length ? <div><h4>Thông tin còn thiếu</h4><ul>{result.missing_facts.map(item => <li key={item}>{item}</li>)}</ul></div> : null}
    {kind === 'strategy' && result?.critical_gaps?.length ? <div><h4>Khoảng trống quan trọng</h4><ul>{result.critical_gaps.map(item => <li key={item}>{item}</li>)}</ul></div> : null}
  </section>
}

function VlmExtractionDetails({ extraction, plan }: {
  extraction: WorkflowVlmExtraction
  plan: WorkflowPlan
}) {
  return <section className="auth-ai-phase auth-vlm-extraction">
    <h3>Trích xuất ảnh (VLM) · {extractionStatusLabel(extraction.status)}</h3>
    <p>Bằng chứng trích xuất là dữ liệu cần Checker xác minh; kết quả này không phải đánh giá toàn bộ.</p>
    <div className="auth-ai-metadata">
      <span>Model ID: {extraction.model_id || 'Chưa cấu hình'}</span>
      <span>Runtime revision: {extraction.model_revision || 'Runtime không cung cấp'}</span>
      <span>Prompt: {extraction.prompt_version}</span>
      <span>Schema: {extraction.schema_version}</span>
      {extraction.confidence != null && <span>Confidence trích xuất (tự báo, chưa hiệu chuẩn): {percent(extraction.confidence)}</span>}
      {extraction.raw_output_hash && <span>Output SHA-256: {extraction.raw_output_hash}</span>}
    </div>
    {extraction.status === 'FAILED' && extraction.error_code && <div className="auth-workflow-alert is-error" role="status">
      {extractionErrorLabel(extraction.error_code)}
    </div>}
    <ul className="auth-vlm-attachments">
      {extraction.attachments.map(attachment => {
        const source = plan.attachments.find(item => item.id === attachment.attachment_id)
        return <li key={attachment.attachment_id}>
          <h4>{source?.filename || `Ảnh ${attachment.attachment_id}`} · {extractionStatusLabel(attachment.status)}</h4>
          <p>Attachment ID: {attachment.attachment_id} · SHA-256 {attachment.content_hash}</p>
          {attachment.confidence != null && <p>Confidence ảnh (tự báo, chưa hiệu chuẩn): {percent(attachment.confidence)}</p>}
          {attachment.error_code && <p className="auth-vlm-error">{extractionErrorLabel(attachment.error_code)}</p>}
          {attachment.ocr_text && <div><strong>Văn bản OCR</strong><blockquote>{attachment.ocr_text}</blockquote></div>}
          {attachment.evidence.filter(item => item.kind === 'OBSERVATION').length > 0 && <div>
            <strong>Quan sát</strong><ul>{attachment.evidence.filter(item => item.kind === 'OBSERVATION').map(item => <li key={item.evidence_id}>
              {item.text}<small>Evidence ID: {item.evidence_id}</small>
            </li>)}</ul>
          </div>}
          {attachment.evidence.filter(item => item.kind === 'OCR_TEXT').map(item => <small key={item.evidence_id}>OCR evidence ID: {item.evidence_id}</small>)}
          {attachment.object_detections?.length ? <div><strong>Đối tượng nhận diện</strong><ul>
            {attachment.object_detections.map((item, index) => <li key={`${attachment.attachment_id}-object-${index}`}>{item}</li>)}
          </ul></div> : null}
          {attachment.visual_quality && <div><strong>Chất lượng kỹ thuật ảnh: {visualQualityLabel(attachment.visual_quality.result)}</strong>
            {attachment.visual_quality.findings.length > 0 && <ul>{attachment.visual_quality.findings.map((item, index) => <li key={`${attachment.attachment_id}-quality-${index}`}>{item}</li>)}</ul>}
          </div>}
          {attachment.uncertainties.length > 0 && <div><strong>Chưa đọc được hoặc chưa chắc chắn</strong><ul>
            {attachment.uncertainties.map((item, index) => <li key={`${attachment.attachment_id}-${index}`}>{item.text}</li>)}
          </ul></div>}
        </li>
      })}
    </ul>
  </section>
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
  if (before && after) return `Trạng thái: ${processingStageLabel(before)} → ${processingStageLabel(after)}`
  if (after) return `Trạng thái: ${processingStageLabel(after)}`
  return ''
}

function shouldClearPlanDetail(failure: unknown) {
  if (!(failure instanceof AuthApiError)) return false
  return [401, 403, 404].includes(failure.status)
    || ['UNAUTHENTICATED', 'FORBIDDEN', 'NOT_FOUND'].includes(failure.code || '')
}

function providerLabel(provider: 'LOCAL_VLM' | 'MOCK_VLM') {
  return provider === 'MOCK_VLM' ? 'Mô phỏng (Mock VLM)' : 'Mô hình cục bộ (Local VLM)'
}

function runStatusLabel(status: string) {
  return ({ PENDING: 'Đang chờ', PROCESSING: 'Đang xử lý', FAILED: 'Thất bại', TIMED_OUT: 'Hết thời gian chờ', SUCCEEDED: 'Hoàn tất' } as Record<string, string>)[status] ?? status
}

function evaluationStatusLabel(status: string) {
  return ({ SUCCEEDED: 'Đánh giá toàn bộ hoàn tất', FAILED: 'Đánh giá toàn bộ chưa hoàn tất · cần Checker', TIMED_OUT: 'Đánh giá toàn bộ hết thời gian chờ' } as Record<string, string>)[status] ?? status
}

function taskStatusLabel(status: string) {
  return ({
    PENDING: 'Đang chờ', PROCESSING: 'Đang xử lý', SUCCEEDED: 'Hoàn tất',
    REVIEW_REQUIRED: 'Cần Checker xem xét', NOT_CONFIGURED: 'Chưa cấu hình',
    FAILED: 'Thất bại · cần Checker', TIMED_OUT: 'Hết thời gian chờ · cần Checker',
  } as Record<string, string>)[status] ?? status
}

function extractionStatusLabel(status: string) {
  return ({
    SUCCEEDED: 'Trích xuất ảnh thành công',
    COMPLETE: 'Trích xuất đầy đủ',
    PARTIAL: 'Trích xuất một phần',
    UNREADABLE: 'Ảnh không đọc được',
    FAILED: 'Trích xuất ảnh thất bại',
  } as Record<string, string>)[status] ?? status
}

function visualQualityLabel(result: 'PASS' | 'REVIEW_REQUIRED' | 'UNKNOWN') {
  return ({ PASS: 'Đủ rõ để kiểm tra', REVIEW_REQUIRED: 'Cần Checker xem lại', UNKNOWN: 'Chưa đánh giá' })[result]
}

function extractionErrorLabel(code: string) {
  return ({
    PROVIDER_NOT_CONFIGURED: 'Chưa cấu hình model ID hoặc địa chỉ inference ở backend.',
    INVALID_PROVIDER_CONFIGURATION: 'Cấu hình inference backend không hợp lệ.',
    MODEL_CONFIGURATION_CHANGED: 'Model cấu hình đã thay đổi sau khi gửi; Checker cần xem hồ sơ.',
    PROVIDER_UNAVAILABLE: 'Không kết nối được inference runtime.',
    MODEL_NOT_FOUND: 'Không tìm thấy model đã cấu hình trong inference runtime.',
    IMAGE_UNSUPPORTED: 'Model hoặc runtime chưa hỗ trợ đầu vào ảnh.',
    STRUCTURED_OUTPUT_UNSUPPORTED: 'Runtime chưa hỗ trợ structured output theo schema yêu cầu.',
    REQUEST_UNSUPPORTED: 'Runtime từ chối định dạng request ảnh hoặc structured output.',
    RESOURCE_EXHAUSTED: 'Inference runtime hết tài nguyên hoặc phản hồi vượt giới hạn.',
    RATE_LIMITED: 'Inference runtime đang giới hạn request; Checker cần xem xét.',
    PROVIDER_ERROR: 'Inference runtime không hoàn tất yêu cầu.',
    PROVIDER_TIMEOUT: 'Inference runtime vượt quá thời gian chờ.',
    TRUNCATED_OUTPUT: 'Kết quả inference bị cắt do giới hạn token và không được sử dụng.',
    INVALID_PROVIDER_RESPONSE: 'Inference runtime trả phản hồi không đọc được.',
    INVALID_SCHEMA: 'Kết quả trích xuất sai schema và không được dùng làm đánh giá.',
    SNAPSHOT_INTEGRITY: 'Không xác minh được ảnh trong snapshot đã gửi.',
    INPUT_TOO_LARGE: 'Tổng ảnh vượt giới hạn xử lý VLM; hồ sơ được chuyển Checker.',
  } as Record<string, string>)[code] ?? 'Không thể xác minh kết quả trích xuất; Checker cần xem hồ sơ.'
}

function evaluationErrorLabel(code: string, fallback: string) {
  if (code === 'MISSING_REQUIRED_EVALUATORS') {
    return 'Media Compliance và Strategy chưa được cấu hình; hồ sơ được chuyển Checker.'
  }
  return extractionErrorLabel(code) || fallback
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
    if (failure.status === 422 || failure.code === 'VALIDATION_ERROR') return failure.message || 'Dữ liệu quyết định chưa hợp lệ.'
    if (failure.code === 'NETWORK_ERROR') return 'Không kết nối được dịch vụ workflow. Kiểm tra kết nối rồi tải lại.'
    if (failure.status >= 500) return 'Dịch vụ workflow chưa trả được trạng thái kế hoạch. Hãy thử tải lại.'
    return failure.message
  }
  return failure instanceof Error ? failure.message : 'Không thể tải dữ liệu kế hoạch.'
}

function decisionErrorText(failure: AuthApiError) {
  if (failure.status === 401 || failure.code === 'UNAUTHENTICATED') return 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.'
  if (failure.status === 403 || failure.code === 'FORBIDDEN') return 'Bạn không còn quyền quyết định hồ sơ này.'
  if (failure.status === 404 || failure.code === 'NOT_FOUND') return 'Hồ sơ không còn khả dụng hoặc không thuộc phạm vi tài khoản hiện tại.'
  if (failure.status === 409 || failure.code === 'CONFLICT') return 'Vòng duyệt đã thay đổi. Trạng thái hồ sơ sẽ được tải lại.'
  if (failure.status === 422 || failure.code === 'VALIDATION_ERROR') return failure.message || 'Máy chủ từ chối dữ liệu quyết định. Kiểm tra lý do rồi thử lại.'
  if (failure.code === 'NETWORK_ERROR') return 'Không xác nhận được quyết định do lỗi kết nối. Nội dung vẫn được giữ; hãy kiểm tra trạng thái trước khi gửi lại.'
  if (failure.status >= 500) return 'Dịch vụ chưa xác nhận được quyết định. Nội dung vẫn được giữ; hãy tải lại trạng thái trước khi gửi lại.'
  return failure.message || 'Không thể hoàn tất quyết định.'
}

function statusLabel(status: WorkflowPlan['status']) {
  return ({ DRAFT: 'Bản nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối' })[status]
}

function formatBudget(value: string, currency: string) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? `${new Intl.NumberFormat('vi-VN').format(amount)} ${currency}` : '—'
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
      .catch(failure => { if (active) setError(failure instanceof Error ? failure.message : String(failure)) })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attachmentId, planId])
  return error ? <span role="alert">{error}</span> : url ? <img className="auth-workflow-image-preview" src={url} alt={`Tệp đính kèm ${filename}`} /> : <span role="status">Đang tải ảnh…</span>
}
