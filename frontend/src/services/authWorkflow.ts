import { AuthApiError } from './auth'
import type { WorkflowAuditPage, WorkflowChecker, WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'
import { resolveApiBaseUrl } from './apiBaseUrl'

function planListQuery(offset: number, limit: number) {
  return new URLSearchParams({ offset: String(offset), limit: String(limit) })
}

function parseWorkflowPlanList(value: unknown): WorkflowPlan[] {
  if (!Array.isArray(value) || value.some(plan => !plan || typeof plan !== 'object' || Array.isArray(plan)
    || typeof (plan as Record<string, unknown>).id !== 'string'
    || !(plan as Record<string, unknown>).id)) {
    throw new AuthApiError(200, 'The workflow service returned an invalid plan list.', 'INVALID_RESPONSE')
  }
  return value as WorkflowPlan[]
}

function announceAuthFailure(status: number) {
  if (status === 401) window.dispatchEvent(new Event('organizationai:auth-expired'))
  if (status === 403) window.dispatchEvent(new Event('organizationai:access-denied'))
}

async function request<T>(path: string, method: 'GET' | 'POST' | 'PUT', body?: unknown, idempotencyKey?: string): Promise<T> {
  const multipart = body instanceof FormData
  const headers = {
    ...(body !== undefined && !multipart ? { 'Content-Type': 'application/json' } : {}),
    ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
  }
  let response: Response
  try {
    response = await fetch(`${resolveApiBaseUrl()}${path}`, {
      method,
      credentials: 'include',
      headers: Object.keys(headers).length ? headers : undefined,
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    })
  } catch {
    throw new AuthApiError(0, 'Could not connect to the authenticated workflow service.', 'NETWORK_ERROR')
  }

  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    announceAuthFailure(response.status)
    throw workflowApiError(response, data)
  }
  return data as T
}

function workflowApiError(response: Response, data: unknown): AuthApiError {
  const field = (key: string) => {
    if (!data || typeof data !== 'object' || !(key in data)) return null
    const value = (data as Record<string, unknown>)[key]
    return typeof value === 'string' && value.length > 0 ? value : null
  }
  return new AuthApiError(
    response.status,
    field('message') ?? 'Authenticated workflow request failed.',
    field('code') ?? 'HTTP_ERROR',
    field('correlation_id') ?? response.headers.get('X-Correlation-ID'),
  )
}

function encoded(value: string) {
  return encodeURIComponent(value)
}

function creationIntentKey(intentId: string) {
  return `workflow-create:${intentId}`
}

export const authWorkflowService = {
  listAuditEvents(offset = 0, limit = 100): Promise<WorkflowAuditPage> {
    return request(`/workflow/audit?offset=${offset}&limit=${limit}`, 'GET')
  },

  listPlans(offset = 0, limit = 100): Promise<WorkflowPlan[]> {
    const query = planListQuery(offset, limit)
    return request<unknown>(`/workflow/plans?${query.toString()}`, 'GET').then(parseWorkflowPlanList)
  },

  listReviews(offset = 0, limit = 100): Promise<WorkflowPlan[]> {
    const query = planListQuery(offset, limit)
    return request<unknown>(`/workflow/reviews?${query.toString()}`, 'GET').then(parseWorkflowPlanList)
  },

  listCheckers(): Promise<WorkflowChecker[]> {
    return request('/workflow/checkers', 'GET')
  },

  getPlan(planId: string): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}`, 'GET')
  },

  createPlan(payload: WorkflowPayload, checkerUserId: string | null, intentId: string): Promise<WorkflowPlan> {
    const idempotencyKey = creationIntentKey(intentId)
    return request<WorkflowPlan>('/workflow/plans', 'POST', { payload, checker_user_id: checkerUserId }, idempotencyKey)
  },

  updatePlan(planId: string, payload: WorkflowPayload, checkerUserId: string | null, expectedRevision: number): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}`, 'PUT', {
      payload, checker_user_id: checkerUserId, expected_revision: expectedRevision,
    })
  },

  uploadAttachment(planId: string, file: File, expectedRevision: number): Promise<WorkflowPlan> {
    const form = new FormData()
    form.set('file', file)
    form.set('expected_revision', String(expectedRevision))
    return request(`/workflow/plans/${encoded(planId)}/attachments`, 'POST', form)
  },

  submitPlan(planId: string, expectedRevision: number): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}/submit`, 'POST', { expected_revision: expectedRevision })
  },

  recoverStaleEvaluation(planId: string, round: number): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}/rounds/${round}/recovery`, 'POST')
  },

  decide(planId: string, round: number, action: 'APPROVED' | 'REJECTED', reason: string, overrideReason: string): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}/rounds/${round}/decision`, 'POST', {
      action, reason, override_reason: overrideReason,
    })
  },

  async getAttachment(planId: string, attachmentId: string): Promise<Blob> {
    let response: Response
    try {
      response = await fetch(`${resolveApiBaseUrl()}/workflow/plans/${encoded(planId)}/attachments/${encoded(attachmentId)}`, {
        credentials: 'include',
      })
    } catch {
      throw new AuthApiError(0, 'Could not connect to the authenticated workflow service.', 'NETWORK_ERROR')
    }
    if (!response.ok) {
      announceAuthFailure(response.status)
      const data: unknown = await response.json().catch(() => null)
      throw workflowApiError(response, data)
    }
    return response.blob()
  },
}
