import { AuthApiError } from './auth'
import type { WorkflowAuditPage, WorkflowChecker, WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'
import { resolveApiBaseUrl } from './apiBaseUrl'

const pendingDraftKeys = new Map<string, string>()

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
    throw new AuthApiError(0, 'Could not connect to the authenticated workflow service.')
  }

  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status < 500 && idempotencyKey) {
      for (const [fingerprint, key] of pendingDraftKeys) {
        if (key === idempotencyKey) pendingDraftKeys.delete(fingerprint)
      }
    }
    announceAuthFailure(response.status)
    const message = data && typeof data === 'object' && 'message' in data && typeof data.message === 'string'
      ? data.message
      : 'Authenticated workflow request failed.'
    throw new AuthApiError(response.status, message)
  }
  return data as T
}

function encoded(value: string) {
  return encodeURIComponent(value)
}

export const authWorkflowService = {
  listAuditEvents(offset = 0, limit = 100): Promise<WorkflowAuditPage> {
    return request(`/workflow/audit?offset=${offset}&limit=${limit}`, 'GET')
  },

  listPlans(): Promise<WorkflowPlan[]> {
    return request('/workflow/plans', 'GET')
  },

  listReviews(): Promise<WorkflowPlan[]> {
    return request('/workflow/reviews', 'GET')
  },

  listCheckers(): Promise<WorkflowChecker[]> {
    return request('/workflow/checkers', 'GET')
  },

  getPlan(planId: string): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}`, 'GET')
  },

  createPlan(payload: WorkflowPayload, checkerUserId: string | null): Promise<WorkflowPlan> {
    const fingerprint = JSON.stringify({ payload, checkerUserId })
    const idempotencyKey = pendingDraftKeys.get(fingerprint) ?? crypto.randomUUID()
    pendingDraftKeys.set(fingerprint, idempotencyKey)
    return request<WorkflowPlan>('/workflow/plans', 'POST', { payload, checker_user_id: checkerUserId }, idempotencyKey)
      .then(plan => {
        pendingDraftKeys.delete(fingerprint)
        return plan
      })
      .catch(failure => {
        if (failure instanceof AuthApiError && failure.status >= 500) throw failure
        if (!(failure instanceof AuthApiError) || failure.status !== 0) pendingDraftKeys.delete(fingerprint)
        throw failure
      })
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
    const response = await fetch(`${resolveApiBaseUrl()}/workflow/plans/${encoded(planId)}/attachments/${encoded(attachmentId)}`, {
      credentials: 'include',
    })
    if (!response.ok) {
      announceAuthFailure(response.status)
      throw new AuthApiError(response.status, 'Could not load this private attachment.')
    }
    return response.blob()
  },
}
