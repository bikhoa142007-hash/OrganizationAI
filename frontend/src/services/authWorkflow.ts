import { AuthApiError } from './auth'
import type { WorkflowChecker, WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8010/api').replace(/\/$/, '')

async function request<T>(path: string, method: 'GET' | 'POST' | 'PUT', body?: unknown): Promise<T> {
  const multipart = body instanceof FormData
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      credentials: 'include',
      headers: body === undefined || multipart ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    })
  } catch {
    throw new AuthApiError(0, 'Could not connect to the authenticated workflow service.')
  }

  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
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
    return request('/workflow/plans', 'POST', { payload, checker_user_id: checkerUserId })
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

  decide(planId: string, round: number, action: 'APPROVED' | 'REJECTED', reason: string, overrideReason: string): Promise<WorkflowPlan> {
    return request(`/workflow/plans/${encoded(planId)}/rounds/${round}/decision`, 'POST', {
      action, reason, override_reason: overrideReason,
    })
  },

  async getAttachment(planId: string, attachmentId: string): Promise<Blob> {
    const response = await fetch(`${baseUrl}/workflow/plans/${encoded(planId)}/attachments/${encoded(attachmentId)}`, {
      credentials: 'include',
    })
    if (!response.ok) throw new AuthApiError(response.status, 'Could not load this private attachment.')
    return response.blob()
  },
}
