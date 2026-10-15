import { resolveApiBaseUrl } from './apiBaseUrl'
import type { RuntimeOutcome, VerifyEvidence, VerifyEscalationQuestion, VerifyRun } from '../types'

export type PublicJudgeSuite = 'general' | 'escalation'
export type PublicJudgeCaseAction = 'APPROVE' | 'REJECT' | 'STOP'
export type PublicJudgeActionStatus = 'HUMAN_APPROVED' | 'HUMAN_REJECTED' | 'STOPPED'

export interface PublicJudgeAuditEvent {
  eventId?: string
  actor: 'ANONYMOUS_PUBLIC_JUDGE'
  action: string
  timestamp: string
  inputSha256?: string | null
  reason: string
}

export interface PublicJudgeCaseActionResult {
  runId: string
  caseId: string
  status: PublicJudgeActionStatus
  action: PublicJudgeCaseAction
  isOverride: boolean
  timestamp: string
  inputSha256: string
  reason: string
  audit: PublicJudgeAuditEvent[]
  idempotentReplay: boolean
}

export interface PublicJudgeInput {
  title: string
  department: string
  objective: string
  summary: string
  target_audience: string
  channel: string
  currency: string
  budget_vnd: number
  source_budget_vnd: number | null
}

export interface PublicJudgeInputResult {
  runId: string
  mode: 'MOCK'
  processingMode: 'DETERMINISTIC_INPUT_SIMULATION'
  dataClassification: 'USER_SUPPLIED_UNVERIFIED'
  qualityStatus: 'NOT_MEASURED'
  outcome: 'SIMULATED_AUTO_APPROVE' | 'HUMAN_REVIEW_REQUIRED'
  humanActionAvailable: boolean
  humanActionStatus: PublicJudgeActionStatus | null
  category: string | null
  policyVersion: string
  reason: string
  handoffQuestion?: string | null
  startedAt: string
  completedAt: string
  durationMs: number
  audit: { action: string; timestamp: string; inputSha256: string; reason: string }
}

interface WireRunRow {
  case_id: string
  case_name?: string | null
  status: 'PASS' | 'FAIL' | 'ERROR'
  passed: boolean
  expected_action?: RuntimeOutcome | null
  expected_category?: string | null
  actual_action?: RuntimeOutcome | null
  actual_category?: string | null
  started_at: string
  completed_at: string
  duration_ms: number
  reason?: string | null
  input?: unknown
  evidence?: Array<{ reference?: string; kind?: string; observation?: string }>
  questions?: Array<{
    category?: string
    question?: string
    disputed_or_missing_fact?: string
    applicable_rule_or_limit?: string
    reason?: string
    evidence_references?: string[]
  }>
  applied_rule_ids?: string[]
  policy_version?: string | null
  model_version?: string | null
  audit?: Array<{ event_id?: string; action?: string; timestamp?: string; input_sha256?: string; reason?: string }>
  human_action_available?: boolean
  human_action_status?: PublicJudgeActionStatus | null
}

interface WireRun {
  run_id: string
  suite: PublicJudgeSuite
  status: 'COMPLETED' | 'ERROR'
  mode: 'MOCK'
  data_classification: 'SYNTHETIC'
  started_at?: string
  completed_at: string
  duration_ms: number
  summary: { total_cases: number; passed_cases: number; failed_cases: number; error_cases: number }
  rows: WireRunRow[]
}

interface WireInputResult {
  run_id: string
  mode: 'MOCK'
  processing_mode: 'DETERMINISTIC_INPUT_SIMULATION'
  data_classification: 'USER_SUPPLIED_UNVERIFIED'
  quality_status: 'NOT_MEASURED'
  outcome: PublicJudgeInputResult['outcome']
  human_action_available: boolean
  human_action_status: PublicJudgeActionStatus | null
  category: string | null
  policy_version: string
  reason: string
  handoff_question?: string | null
  started_at: string
  completed_at: string
  duration_ms: number
  audit: { action: string; timestamp: string; input_sha256: string; reason: string }
}

interface WirePublicJudgeAuditEvent {
  event_id?: string | null
  actor: 'ANONYMOUS_PUBLIC_JUDGE'
  action: string
  timestamp: string
  input_sha256?: string | null
  reason: string
}

interface WirePublicJudgeCaseActionResult {
  run_id: string
  case_id: string
  status: PublicJudgeActionStatus
  action: PublicJudgeCaseAction
  is_override: boolean
  timestamp: string
  input_sha256: string
  reason: string
  audit: WirePublicJudgeAuditEvent[]
  idempotent_replay: boolean
}

export class PublicJudgeError extends Error {
  constructor(message: string, public code: string, public correlationId?: string, public httpStatus?: number) {
    super(message)
    this.name = 'PublicJudgeError'
  }
}

const safeMessage: Record<string, string> = {
  VALIDATION_ERROR: 'Kiểm tra lại các trường được phép nhập.',
  INPUT_TOO_LARGE: 'Đầu vào vượt giới hạn 16 KiB.',
  RATE_LIMITED: 'Judge đang nhận quá nhiều yêu cầu. Hãy thử lại sau.',
  UNAVAILABLE: 'Judge chưa thể hoàn tất lần chạy này.',
  IDEMPOTENCY_KEY_REQUIRED: 'Thiếu khóa idempotency cho thao tác mô phỏng.',
  IDEMPOTENCY_KEY_INVALID: 'Khóa thao tác không hợp lệ. Hãy chạy một ca tổng hợp mới.',
  IDEMPOTENCY_CONFLICT: 'Khóa này đã gắn với thao tác khác; hành động của ca không thể bị thay thế.',
  ACTION_ALREADY_FINAL: 'Ca tổng hợp này đã có hành động cuối cùng.',
  ACTION_SESSION_UNAVAILABLE: 'Phiên mô phỏng tạm thời không còn khả dụng. Hãy chạy một ca mới.',
  JUDGE_CAPACITY_REACHED: 'Judge đang hết chỗ cho phiên mô phỏng. Có thể thử lại cùng thao tác sau.',
}

export class PublicJudgeService {
  private readonly baseUrl: string

  constructor(
    configuredBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined,
    development = import.meta.env.DEV,
    private readonly transport: typeof fetch = (...args) => fetch(...args),
  ) {
    this.baseUrl = resolveApiBaseUrl(configuredBaseUrl, development)
  }

  async startRun(suite: PublicJudgeSuite): Promise<VerifyRun> {
    const response = await this.post<WireRun>('/runs', { suite })
    const rows = response.rows.map(row => ({
      caseId: row.case_id,
      caseName: row.case_name ?? undefined,
      input: row.input == null ? undefined : JSON.stringify(row.input, null, 2),
      dataClassification: 'SYNTHETIC',
      expectedAction: row.expected_action,
      expectedCategory: row.expected_category,
      actualAction: row.actual_action,
      actualCategory: row.actual_category,
      humanActionAvailable: row.human_action_available,
      humanActionStatus: row.human_action_status,
      status: row.status,
      pass: row.passed,
      reason: row.reason ?? undefined,
      startedAt: row.started_at,
      completedAt: row.completed_at,
      durationMs: row.duration_ms,
      evidence: [
        ...(row.evidence ?? []) as VerifyEvidence[],
        ...(row.audit ?? []).map(event => ({
          reference: event.event_id,
          kind: 'AUDIT_TRACE',
          observation: `Action: ${event.action ?? 'unknown'} · Time: ${event.timestamp ?? 'unknown'} · Input SHA-256: ${event.input_sha256 ?? 'unavailable'} · Reason: ${event.reason ?? 'not provided'}`,
        })),
      ],
      generatedQuestion: row.questions?.map(question => ({
        category: question.category ?? row.actual_category ?? 'HUMAN_REVIEW_REQUIRED',
        question: question.question ?? 'Chưa có câu hỏi chuyển tiếp từ backend.',
        disputedOrMissingFact: question.disputed_or_missing_fact,
        applicableRuleOrLimit: question.applicable_rule_or_limit,
        reason: question.reason,
        evidenceReferences: question.evidence_references,
      })) as VerifyEscalationQuestion[] | undefined,
      appliedRuleIds: row.applied_rule_ids,
      policyVersion: row.policy_version ?? undefined,
      modelVersion: row.model_version ?? undefined,
      auditReference: row.audit?.map(event => event.event_id).filter(Boolean).join(', '),
      error: row.status === 'ERROR' ? { code: 'RUN_ERROR', message: row.reason ?? 'Judge case failed.' } : null,
    }))
    return {
      runId: response.run_id,
      suite: response.suite,
      status: response.status,
      rows,
      startedAt: response.started_at ?? rows[0]?.startedAt,
      completedAt: response.completed_at,
      dataSource: 'API',
      summary: {
        totalCases: response.summary.total_cases,
        completedCases: response.summary.total_cases - response.summary.error_cases,
        passedCases: response.summary.passed_cases,
        failedCases: response.summary.failed_cases,
        errorCases: response.summary.error_cases,
        progressPercent: 100,
      },
    }
  }

  async evaluateInput(input: PublicJudgeInput): Promise<PublicJudgeInputResult> {
    const response = await this.post<WireInputResult>('/input-runs', input)
    return {
      runId: response.run_id,
      mode: response.mode,
      processingMode: response.processing_mode,
      dataClassification: response.data_classification,
      qualityStatus: response.quality_status,
      outcome: response.outcome,
      humanActionAvailable: response.human_action_available,
      humanActionStatus: response.human_action_status,
      category: response.category,
      policyVersion: response.policy_version,
      reason: response.reason,
      handoffQuestion: response.handoff_question,
      startedAt: response.started_at,
      completedAt: response.completed_at,
      durationMs: response.duration_ms,
      audit: {
        action: response.audit.action,
        timestamp: response.audit.timestamp,
        inputSha256: response.audit.input_sha256,
        reason: response.audit.reason,
      },
    }
  }

  async actOnCase(
    runId: string,
    caseId: string,
    action: PublicJudgeCaseAction,
    reason: string,
    idempotencyKey: string,
  ): Promise<PublicJudgeCaseActionResult> {
    const response = await this.post<WirePublicJudgeCaseActionResult>(
      `/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/action`,
      { action, reason },
      { 'Idempotency-Key': idempotencyKey },
    )
    return {
      runId: response.run_id,
      caseId: response.case_id,
      status: response.status,
      action: response.action,
      isOverride: response.is_override,
      timestamp: response.timestamp,
      inputSha256: response.input_sha256,
      reason: response.reason,
      audit: response.audit.map(event => ({
        eventId: event.event_id ?? undefined,
        actor: event.actor,
        action: event.action,
        timestamp: event.timestamp,
        inputSha256: event.input_sha256,
        reason: event.reason,
      })),
      idempotentReplay: response.idempotent_replay,
    }
  }

  private async post<T>(path: string, body: unknown, additionalHeaders: Record<string, string> = {}): Promise<T> {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 30_000)
    try {
      const response = await this.transport(`${this.baseUrl}/public/judge${path}`, {
        method: 'POST',
        credentials: 'omit',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json', ...additionalHeaders },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      let data: Record<string, unknown>
      try {
        data = await response.json() as Record<string, unknown>
      } catch {
        throw new PublicJudgeError('Judge returned an invalid response.', 'INVALID_RESPONSE')
      }
      if (!response.ok) {
        const code = typeof data.code === 'string' ? data.code : 'UNAVAILABLE'
        throw new PublicJudgeError(safeMessage[code] ?? 'Judge request failed.', code,
          typeof data.correlation_id === 'string' ? data.correlation_id : undefined, response.status)
      }
      return data as T
    } catch (error) {
      if (error instanceof PublicJudgeError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new PublicJudgeError(
          'Request timed out; the outcome is unknown. Timeout does not stop server work or undo an effect.',
          'OUTCOME_UNKNOWN',
        )
      }
      throw new PublicJudgeError('Could not reach the public Judge service.', 'NETWORK_ERROR')
    } finally {
      window.clearTimeout(timeout)
    }
  }
}

export const publicJudgeService = new PublicJudgeService()
