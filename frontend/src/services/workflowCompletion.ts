import { AuthApiError } from './auth'
import { resolveApiBaseUrl } from './apiBaseUrl'

export type WorkflowPrincipalScope =
  | 'ADMIN_READ_ONLY'
  | 'MAKER_OWN'
  | 'CHECKER_ASSIGNED'
  | 'MAKER_AND_CHECKER'

export interface WorkflowDashboardCounts {
  draft: number
  pending_ai: number
  human_review: number
  approved: number
  rejected: number
}

export interface WorkflowDashboard {
  as_of: string
  principal_scope: WorkflowPrincipalScope
  counts: WorkflowDashboardCounts
  active_assignments: number
}

export interface WorkflowInternalNote {
  note_id: string
  plan_id: string
  approval_round: number | null
  author_id: string
  created_at: string
  content: string
}

export interface WorkflowInternalNoteDraft {
  approval_round: number | null
  content: string
}

export interface WorkflowEvaluationRetryDraft {
  expected_plan_version: number
  expected_round_revision: number
}

export interface WorkflowEvaluationRetry {
  plan_id: string
  plan_version: number
  approval_round: number
  run_id: string
  run_status: 'PENDING' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT'
  processing_stage: string
  decision_id: string | null
  attempt_number: number
  result_disposition: 'APPLIED' | 'STALE' | null
}

const principalScopes = new Set<WorkflowPrincipalScope>([
  'ADMIN_READ_ONLY',
  'MAKER_OWN',
  'CHECKER_ASSIGNED',
  'MAKER_AND_CHECKER',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function nonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && typeof value === 'number' && value >= 0
}

function parseDashboard(value: unknown): WorkflowDashboard {
  if (!isRecord(value) || !isRecord(value.counts)) {
    throw new AuthApiError(502, 'The workflow service returned an invalid dashboard.', 'INVALID_RESPONSE')
  }
  const counts = value.counts
  const timestamp = value.as_of
  const hasUtcTimestamp = typeof timestamp === 'string'
    && /(?:Z|\+00:00)$/.test(timestamp)
    && Number.isFinite(Date.parse(timestamp))
  const validCounts = ['draft', 'pending_ai', 'human_review', 'approved', 'rejected']
    .every(key => nonNegativeInteger(counts[key]))

  if (!hasUtcTimestamp || typeof value.principal_scope !== 'string'
    || !principalScopes.has(value.principal_scope as WorkflowPrincipalScope)
    || !validCounts || !nonNegativeInteger(value.active_assignments)) {
    throw new AuthApiError(502, 'The workflow service returned an invalid dashboard.', 'INVALID_RESPONSE')
  }

  return value as unknown as WorkflowDashboard
}

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function parseInternalNote(value: unknown): WorkflowInternalNote {
  const expectedKeys = ['note_id', 'plan_id', 'approval_round', 'author_id', 'created_at', 'content']
  if (!isRecord(value) || Object.keys(value).length !== expectedKeys.length
    || !expectedKeys.every(key => key in value)) {
    throw new AuthApiError(502, 'The workflow service returned an invalid internal note.', 'INVALID_RESPONSE')
  }
  const hasUtcTimestamp = typeof value.created_at === 'string'
    && /(?:Z|\+00:00)$/.test(value.created_at)
    && Number.isFinite(Date.parse(value.created_at))
  const validRound = value.approval_round === null
    || (Number.isInteger(value.approval_round) && typeof value.approval_round === 'number' && value.approval_round >= 1)
  if (typeof value.note_id !== 'string' || !uuidPattern.test(value.note_id)
    || typeof value.plan_id !== 'string' || !uuidPattern.test(value.plan_id)
    || typeof value.author_id !== 'string' || !uuidPattern.test(value.author_id)
    || !validRound || !hasUtcTimestamp
    || typeof value.content !== 'string' || value.content.trim().length < 1 || value.content.length > 4000) {
    throw new AuthApiError(502, 'The workflow service returned an invalid internal note.', 'INVALID_RESPONSE')
  }
  return value as unknown as WorkflowInternalNote
}

function parseInternalNotes(value: unknown): WorkflowInternalNote[] {
  if (!isRecord(value) || Object.keys(value).length !== 1 || !Array.isArray(value.items)) {
    throw new AuthApiError(502, 'The workflow service returned an invalid internal note list.', 'INVALID_RESPONSE')
  }
  return value.items.map(parseInternalNote)
}

function parseEvaluationRetry(value: unknown): WorkflowEvaluationRetry {
  const expectedKeys = [
    'plan_id', 'plan_version', 'approval_round', 'run_id', 'run_status',
    'processing_stage', 'decision_id', 'attempt_number', 'result_disposition',
  ]
  if (!isRecord(value) || Object.keys(value).length !== expectedKeys.length
    || !expectedKeys.every(key => key in value)) {
    throw new AuthApiError(502, 'The workflow service returned an invalid retry result.', 'INVALID_RESPONSE')
  }
  const runStatuses = new Set(['PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT'])
  const validDecisionId = value.decision_id === null
    || (typeof value.decision_id === 'string' && value.decision_id.length > 0)
  const validDisposition = value.result_disposition === null
    || value.result_disposition === 'APPLIED' || value.result_disposition === 'STALE'
  if (typeof value.plan_id !== 'string' || !uuidPattern.test(value.plan_id)
    || !Number.isInteger(value.plan_version) || typeof value.plan_version !== 'number' || value.plan_version < 1
    || !Number.isInteger(value.approval_round) || typeof value.approval_round !== 'number' || value.approval_round < 1
    || typeof value.run_id !== 'string' || !value.run_id.trim()
    || typeof value.run_status !== 'string' || !runStatuses.has(value.run_status)
    || typeof value.processing_stage !== 'string' || !/^[A-Z_]+$/.test(value.processing_stage)
    || !validDecisionId
    || !Number.isInteger(value.attempt_number) || typeof value.attempt_number !== 'number' || value.attempt_number < 1
    || !validDisposition) {
    throw new AuthApiError(502, 'The workflow service returned an invalid retry result.', 'INVALID_RESPONSE')
  }
  return value as unknown as WorkflowEvaluationRetry
}

function responseError(response: Response, value: unknown): AuthApiError {
  const body = isRecord(value) ? value : {}
  const message = typeof body.message === 'string' && body.message
    ? body.message
    : 'Authenticated workflow request failed.'
  const code = typeof body.code === 'string' && body.code ? body.code : 'HTTP_ERROR'
  const correlationId = typeof body.correlation_id === 'string'
    ? body.correlation_id
    : response.headers.get('X-Correlation-ID')
  return new AuthApiError(response.status, message, code, correlationId)
}

async function authenticatedRequest(path: string, init: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${resolveApiBaseUrl()}${path}`, { ...init, credentials: 'include' })
  } catch {
    throw new AuthApiError(0, 'Could not connect to the authenticated workflow service.', 'NETWORK_ERROR')
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event('organizationai:auth-expired'))
    if (response.status === 403) window.dispatchEvent(new Event('organizationai:access-denied'))
    throw responseError(response, body)
  }
  return body
}

export const workflowCompletionService = {
  async getDashboard(): Promise<WorkflowDashboard> {
    const body = await authenticatedRequest('/workflow/dashboard', { method: 'GET' })
    return parseDashboard(body)
  },

  async getInternalNotes(planId: string): Promise<WorkflowInternalNote[]> {
    const path = `/workflow/plans/${encodeURIComponent(planId)}/internal-notes`
    return parseInternalNotes(await authenticatedRequest(path, { method: 'GET' }))
  },

  async addInternalNote(
    planId: string,
    draft: WorkflowInternalNoteDraft,
    idempotencyKey: string,
  ): Promise<WorkflowInternalNote> {
    const path = `/workflow/plans/${encodeURIComponent(planId)}/internal-notes`
    const body = await authenticatedRequest(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(draft),
    })
    return parseInternalNote(body)
  },

  async retryEvaluation(
    planId: string,
    approvalRound: number,
    draft: WorkflowEvaluationRetryDraft,
    idempotencyKey: string,
  ): Promise<WorkflowEvaluationRetry> {
    const path = `/workflow/plans/${encodeURIComponent(planId)}/rounds/${approvalRound}/evaluation-retries`
    const body = await authenticatedRequest(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(draft),
    })
    return parseEvaluationRetry(body)
  },
}
