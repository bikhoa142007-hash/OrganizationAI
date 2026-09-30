import { ArrowLeft, Check, Clock3, FileText, History, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowPlan, WorkflowVlmExtraction } from '../types/authWorkflow'

export function AuthenticatedWorkflowDetailPage() {
  const { planId = '' } = useParams()
  const { user, roles } = useAuth()
  const [plan, setPlan] = useState<WorkflowPlan | null>(null)
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    setError('')
    authWorkflowService.getPlan(planId)
      .then(value => { if (active) setPlan(value) })
      .catch(failure => { if (active) setError(failure instanceof Error ? failure.message : String(failure)) })
    return () => { active = false }
  }, [planId, reload])

  async function decide(action: 'APPROVED' | 'REJECTED') {
    const activeRound = plan?.current_round ?? 0
    const evaluation = plan?.ai_evaluations.find(item => item.round_number === activeRound)?.evaluation
    const expected = action === 'APPROVED' ? 'RECOMMEND_AUTO_APPROVAL' : 'RECOMMEND_HUMAN_REVIEW'
    if (evaluation?.proposed_action !== expected && !overrideReason.trim()) {
      setError('Nhập lý do override khi quyết định khác hoặc chưa có khuyến nghị AI.')
      return
    }
    if (action === 'REJECTED' && !reason.trim()) {
      setError('Nhập lý do từ chối trước khi tiếp tục.')
      return
    }
    setBusy(true); setError('')
    try {
      const result = await authWorkflowService.decide(planId, plan?.current_round ?? 0, action, reason, overrideReason)
      setPlan(result); setReason(''); setOverrideReason('')
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)) }
    finally { setBusy(false) }
  }

  if (!plan) return <section className={`auth-workflow-state${error ? ' is-error' : ''}`} role={error ? 'alert' : 'status'}><h1>{error ? 'Không thể mở kế hoạch' : 'Đang tải kế hoạch…'}</h1>{error && <><p>{error}</p><Link to="/workflow/plans">Quay lại danh sách</Link></>}</section>
  const isMaker = roles.includes('MAKER') && plan.maker_id === user?.id
  const isAssignedChecker = roles.includes('CHECKER') && plan.checker_id === user?.id
  const canEdit = isMaker && ['DRAFT', 'REJECTED'].includes(plan.status)
  const canDecide = isAssignedChecker && plan.status === 'PENDING_APPROVAL'

  return <section className="auth-workflow-page">
    <Link className="auth-back-link" to={isAssignedChecker ? '/workflow/reviews' : '/workflow/plans'}><ArrowLeft /> Quay lại danh sách</Link>
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">{plan.code} · Version {plan.current_version || '—'} · Round {plan.current_round || '—'}</p><h1>{plan.payload.title || 'Kế hoạch chưa có tên'}</h1><p>Maker: {plan.maker_name} <span aria-hidden="true">·</span> Checker: {plan.checker_name || 'Chưa gán'}</p></div><span className={`workflow-status status-${plan.status.toLowerCase()}`}>{statusLabel(plan.status)}</span></div>
    {error && <div className="auth-workflow-alert is-error" role="alert"><p>{error}</p></div>}
    {['AI_PENDING', 'AI_PROCESSING'].includes(plan.processing_stage) && <div className="auth-workflow-alert is-progress" role="status"><Clock3 /><div><strong>Đang đánh giá kế hoạch</strong><p>Snapshot đã được lưu. Tải lại để xem trạng thái mới nhất.</p></div></div>}
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
      </dl>{plan.decision_reason && <div className={`auth-workflow-alert ${plan.status === 'REJECTED' ? 'is-error' : 'is-review'}`}><strong>{plan.status === 'REJECTED' ? 'Lý do từ chối' : 'Lý do chuyển Checker'}</strong><p>{plan.decision_reason}</p></div>}
        <div className="auth-workflow-attachments"><h3>Ảnh đính kèm</h3>{plan.attachments.length ? plan.attachments.map(item => <div key={item.id} className="auth-workflow-attachment"><AuthAttachmentPreview planId={plan.id} attachmentId={item.id} filename={item.filename} /><span><strong>{item.filename}</strong><small>{item.media_type} · {Math.ceil(item.byte_size / 1024)} KB · SHA-256 {item.content_hash.slice(0, 12)}…</small></span></div>) : <p>Chưa có ảnh đính kèm.</p>}</div>
      </section>
      <section className="auth-workflow-card"><div className="auth-workflow-card-heading"><History /><h2>Lịch sử xử lý</h2></div><ol className="auth-workflow-history">{plan.history.map(event => <li key={event.id}><span className="history-icon">{event.action === 'APPROVED' || event.action === 'AI_AUTO_APPROVED' ? <Check /> : event.action === 'REJECTED' ? <X /> : <Clock3 />}</span><div><strong>{eventLabel(event.action)}</strong><p>{event.actor_name} · {new Date(event.created_at).toLocaleString('vi-VN')}</p>{typeof event.details.reason === 'string' && <blockquote>{event.details.reason}</blockquote>}{typeof event.details.version === 'number' && typeof event.details.round === 'number' && <small>Version {event.details.version} / Round {event.details.round}</small>}</div></li>)}</ol></section>
    </div>
    {plan.ai_evaluations.length > 0 && <section className="auth-workflow-card auth-ai-results"><div className="auth-workflow-card-heading"><History /><h2>Kết quả đánh giá AI</h2></div>{plan.ai_evaluations.map(item => {
      const evaluation = item.evaluation
      const decision = plan.engine_decisions.find(entry => entry.round_number === item.round_number)
      return <details key={item.id} open={item.round_number === plan.current_round}>
        <summary>Version {item.version_number} · Round {item.round_number} · {evaluation ? evaluationStatusLabel(evaluation.status) : runStatusLabel(item.status)}</summary>
        <div className="auth-ai-metadata"><span>{providerLabel(item.provider)}</span><span>Model ID: {item.model_id || item.model_version || 'Chưa xác định'}</span>{item.model_id && item.model_version && <span>Model revision: {item.model_version}</span>}<span>Policy: {item.policy_version}</span><span>Lần thử: {item.attempts}{item.retried ? ' · đã retry' : ''}</span></div>
        {item.visual_extraction && <VlmExtractionDetails extraction={item.visual_extraction} plan={plan} />}
        {evaluation ? <>
          <section className="auth-ai-phase"><h3>Đánh giá tổng thể</h3><p>{evaluation.reason}</p></section>
          <dl className="auth-workflow-definition-grid auth-ai-metrics">
            <div><dt>Media Compliance</dt><dd>{evaluation.media_result || 'Chưa có kết quả'}{evaluation.media_confidence !== null && ` · ${percent(evaluation.media_confidence)}`}</dd></div>
            <div><dt>Strategy Evaluation</dt><dd>{evaluation.feasibility_score === null ? 'Chưa có điểm' : `${evaluation.feasibility_score} / 100`}{evaluation.feasibility_confidence !== null && ` · ${percent(evaluation.feasibility_confidence)}`}</dd></div>
            <div><dt>Khuyến nghị</dt><dd>{recommendationLabel(evaluation.proposed_action)}</dd></div>
            <div><dt>Input hash</dt><dd className="auth-hash">{item.input_hash}</dd></div>
          </dl>
          {evaluation.criterion_scores.length > 0 && <div><h3>Strategy Evaluation · điểm theo tiêu chí</h3><ul>{evaluation.criterion_scores.map(score => <li key={score.criterion_id}>{score.criterion_id}: {score.score} / {score.maximum_score} — {score.rationale}</li>)}</ul></div>}
          {evaluation.media_findings.length > 0 && <div><h3>Media Compliance · phát hiện</h3><ul>{evaluation.media_findings.map(finding => <li key={finding.finding_id}><strong>{finding.severity}</strong>: {finding.description}</li>)}</ul></div>}
          {evaluation.evidence_conflicts.length > 0 && <div><h3>Thông tin chưa thống nhất</h3><ul>{evaluation.evidence_conflicts.map(conflict => <li key={conflict.conflict_id}>{conflict.description}</li>)}</ul></div>}
          {evaluation.missing_facts.length > 0 && <div><h3>Thông tin còn thiếu</h3><ul>{evaluation.missing_facts.map(fact => <li key={fact}>{fact}</li>)}</ul></div>}
          {evaluation.evidence.length > 0 && <div><h3>Bằng chứng</h3><ul>{evaluation.evidence.map(evidence => <li key={evidence.evidence_id}>{evidence.observation} <small>({evidence.source_type})</small></li>)}</ul></div>}
          {evaluation.assumptions.length > 0 && <div><h3>Giả định</h3><ul>{evaluation.assumptions.map((assumption, index) => <li key={`${index}-${assumption}`}>{assumption}</li>)}</ul></div>}
          {evaluation.agent_errors.length > 0 && <div className="auth-workflow-alert is-error"><div><strong>Pipeline cần Checker xử lý</strong><ul>{evaluation.agent_errors.map((failure, index) => <li key={`${failure.component}-${index}`}>{failure.component}: {failure.code} — {evaluationErrorLabel(failure.code, failure.message)}</li>)}</ul></div></div>}
        </> : <p>Kết quả xử lý: {item.failure_reason || 'Đang chờ xử lý.'}</p>}
        {decision && <div className={`auth-ai-decision ${decision.outcome === 'AUTO_APPROVED' ? 'is-approved' : 'is-review'}`}><strong>{decision.outcome === 'AUTO_APPROVED' ? 'Đã tự động phê duyệt theo policy' : 'Đã chuyển Checker theo policy'}</strong><p>{decision.decision.reason}</p><small>Ngân sách: {decision.decision.budget_validation.result}{decision.decision.budget_validation.limit_minor_units && ` · hạn mức ${formatBudget(decision.decision.budget_validation.limit_minor_units, decision.decision.budget_validation.currency || plan.payload.currency)}`}</small>{decision.decision.rule_checks.some(check => check.result !== 'PASS') && <ul>{decision.decision.rule_checks.filter(check => check.result !== 'PASS').map(check => <li key={check.rule_id}>{check.rule_id}: {check.result}</li>)}</ul>}</div>}
      </details>
    })}</section>}
    {plan.versions.length > 0 && <section className="auth-workflow-card auth-version-card"><div className="auth-workflow-card-heading"><History /><h2>Snapshot đã gửi</h2></div>{plan.versions.map(version => <details key={version.version_number}><summary>Version {version.version_number} · Round {version.round_number} · {new Date(version.created_at).toLocaleString('vi-VN')}</summary><p>{version.payload.summary}</p><ul>{version.attachments.map(item => <li key={item.id}>{item.filename} · SHA-256 {item.content_hash}</li>)}</ul></details>)}</section>}
    {canEdit && <div className="auth-workflow-actions"><Link className="button button-secondary" to={`/workflow/plans/${plan.id}/edit`}>Chỉnh sửa và gửi lại</Link></div>}
    {canDecide && <section className="auth-workflow-card auth-decision-card"><div className="auth-workflow-card-heading"><Check /><h2>Quyết định Checker</h2></div><p>Nội dung và snapshot được lưu chỉ đọc. Từ chối cần có lý do.</p><label className="auth-field">Lý do hoặc nhận xét<textarea rows={3} value={reason} onChange={event => setReason(event.target.value)} placeholder="Bắt buộc khi từ chối" /></label><label className="auth-field">Lý do override AI<textarea rows={2} value={overrideReason} onChange={event => setOverrideReason(event.target.value)} placeholder="Bắt buộc khi quyết định khác hoặc chưa có khuyến nghị AI" /></label><div className="button-row"><button className="button button-secondary" disabled={busy} onClick={() => void decide('REJECTED')}>{busy ? 'Đang xử lý…' : 'Từ chối'}</button><button className="button button-primary" disabled={busy} onClick={() => void decide('APPROVED')}><Check /> {busy ? 'Đang xử lý…' : 'Phê duyệt'}</button></div></section>}
    <button className="auth-quiet-refresh" onClick={() => setReload(value => value + 1)}>Tải lại trạng thái</button>
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
          {attachment.error_code && <p className="auth-vlm-error">{extractionErrorLabel(attachment.error_code)}</p>}
          {attachment.ocr_text && <div><strong>Văn bản OCR</strong><blockquote>{attachment.ocr_text}</blockquote></div>}
          {attachment.evidence.filter(item => item.kind === 'OBSERVATION').length > 0 && <div>
            <strong>Quan sát</strong><ul>{attachment.evidence.filter(item => item.kind === 'OBSERVATION').map(item => <li key={item.evidence_id}>
              {item.text}<small>Evidence ID: {item.evidence_id}</small>
            </li>)}</ul>
          </div>}
          {attachment.evidence.filter(item => item.kind === 'OCR_TEXT').map(item => <small key={item.evidence_id}>OCR evidence ID: {item.evidence_id}</small>)}
          {attachment.uncertainties.length > 0 && <div><strong>Chưa đọc được hoặc chưa chắc chắn</strong><ul>
            {attachment.uncertainties.map((item, index) => <li key={`${attachment.attachment_id}-${index}`}>{item.text}</li>)}
          </ul></div>}
        </li>
      })}
    </ul>
  </section>
}

function eventLabel(action: string) {
  return ({ CREATED: 'Tạo bản nháp', UPDATED: 'Cập nhật nội dung', ATTACHMENT_UPLOADED: 'Tải ảnh lên', SUBMITTED: 'Gửi duyệt', AI_EVALUATION_QUEUED: 'Đã xếp đánh giá AI', AI_EVALUATION_STARTED: 'Bắt đầu đánh giá AI', AI_EVALUATION_COMPLETED: 'Hoàn tất đánh giá AI', AI_REVIEW_ROUTED: 'Chuyển Checker theo policy', AI_AUTO_APPROVED: 'AI tự động phê duyệt', APPROVED: 'Đã phê duyệt', REJECTED: 'Đã từ chối' } as Record<string, string>)[action] ?? action
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

function extractionStatusLabel(status: string) {
  return ({
    SUCCEEDED: 'Trích xuất ảnh thành công',
    COMPLETE: 'Trích xuất đầy đủ',
    PARTIAL: 'Trích xuất một phần',
    UNREADABLE: 'Ảnh không đọc được',
    FAILED: 'Trích xuất ảnh thất bại',
  } as Record<string, string>)[status] ?? status
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
