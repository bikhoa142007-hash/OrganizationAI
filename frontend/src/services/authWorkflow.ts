import { AuthApiError } from './auth'
import type { AdminRoleCatalog, AdminRole, EmployeePendingPlanPage, WorkflowAuditPage, WorkflowChecker, WorkflowEmployee, WorkflowEmployeePage, WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'
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

function parseEmployeePage(value: unknown): WorkflowEmployeePage {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new AuthApiError(200, 'The workflow service returned an invalid employee page.', 'INVALID_RESPONSE')
  }
  const page = value as Record<string, unknown>
  const validItem = (item: unknown) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return false
    const employee = item as Record<string, unknown>
    return typeof employee.id === 'string'
      && (employee.account_id === null || typeof employee.account_id === 'string')
      && typeof employee.user_code === 'string'
      && (employee.username === null || typeof employee.username === 'string')
      && typeof employee.display_name === 'string'
      && (employee.email === null || typeof employee.email === 'string')
      && (employee.phone === null || typeof employee.phone === 'string')
      && (employee.department === null || typeof employee.department === 'string')
      && (employee.job_title === null || typeof employee.job_title === 'string')
      && (employee.employment_start_date === null || typeof employee.employment_start_date === 'string')
      && (employee.employment_status === 'ACTIVE' || employee.employment_status === 'INACTIVE')
      && (employee.status === null || employee.status === 'ACTIVE' || employee.status === 'DISABLED')
      && (employee.account_status === null || employee.account_status === 'ACTIVE'
        || employee.account_status === 'DISABLED' || employee.account_status === 'PENDING_ACTIVATION')
      && Array.isArray(employee.roles) && employee.roles.every(role => typeof role === 'string')
      && Array.isArray(employee.effective_permissions) && employee.effective_permissions.every(permission => typeof permission === 'string')
  }
  if (!Array.isArray(page.items) || !page.items.every(validItem)
    || !Number.isInteger(page.offset) || !Number.isInteger(page.limit) || !Number.isInteger(page.total)) {
    throw new AuthApiError(200, 'The workflow service returned an invalid employee page.', 'INVALID_RESPONSE')
  }
  return value as WorkflowEmployeePage
}

function announceAuthFailure(status: number) {
  if (status === 401) window.dispatchEvent(new Event('organizationai:auth-expired'))
  if (status === 403) window.dispatchEvent(new Event('organizationai:access-denied'))
}

async function request<T>(path: string, method: 'GET' | 'POST' | 'PUT' | 'PATCH', body?: unknown, idempotencyKey?: string): Promise<T> {
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

  listEmployees(filters: {
    query?: string
    role?: string
    status?: 'ACTIVE' | 'DISABLED' | 'PENDING_ACTIVATION'
    department?: string
    job_title?: string
    employment_status?: 'ACTIVE' | 'INACTIVE'
    offset?: number
    limit?: number
  } = {}): Promise<WorkflowEmployeePage> {
    const params = new URLSearchParams({
      offset: String(filters.offset ?? 0),
      limit: String(filters.limit ?? 50),
    })
    if (filters.query?.trim()) params.set('query', filters.query.trim())
    if (filters.role) params.set('role', filters.role)
    if (filters.status) params.set('status', filters.status)
    if (filters.department?.trim()) params.set('department', filters.department.trim())
    if (filters.job_title?.trim()) params.set('job_title', filters.job_title.trim())
    if (filters.employment_status) params.set('employment_status', filters.employment_status)
    return request<unknown>(`/workflow/employees?${params.toString()}`, 'GET').then(parseEmployeePage)
  },

  createEmployee(payload: {
    user_code: string; display_name: string; email?: string | null; phone?: string | null
    department?: string | null; job_title?: string | null; employment_start_date?: string | null
  }): Promise<WorkflowEmployee> {
    return request('/workflow/employees', 'POST', payload)
  },

  updateEmployee(employeeId: string, payload: Partial<{
    user_code: string; display_name: string; email: string | null; phone: string | null
    department: string | null; job_title: string | null; employment_start_date: string | null
  }>): Promise<WorkflowEmployee> {
    return request(`/workflow/employees/${encoded(employeeId)}`, 'PUT', payload)
  },

  deactivateEmployee(employeeId: string, reassignments: Record<string, string>): Promise<WorkflowEmployee> {
    return request(`/workflow/employees/${encoded(employeeId)}/deactivation`, 'POST', { reassignments })
  },

  reactivateEmployee(employeeId: string): Promise<WorkflowEmployee> {
    return request(`/workflow/employees/${encoded(employeeId)}/reactivation`, 'POST')
  },

  listPendingCheckerPlans(employeeId: string, offset = 0, limit = 100): Promise<EmployeePendingPlanPage> {
    return request(`/workflow/employees/${encoded(employeeId)}/pending-plans?offset=${offset}&limit=${limit}`, 'GET')
  },

  createEmployeeAccount(employeeId: string, username: string): Promise<{ employee: WorkflowEmployee; handover_token: string; purpose: 'ACTIVATE'; expires_at: string }> {
    return request(`/workflow/employees/${encoded(employeeId)}/account`, 'POST', { username })
  },

  reissueEmployeeActivation(employeeId: string): Promise<{ handover_token: string; purpose: 'ACTIVATE'; expires_at: string }> {
    return request(`/workflow/employees/${encoded(employeeId)}/account/activation`, 'POST')
  },

  requestPasswordReset(employeeId: string): Promise<{ handover_token: string; purpose: 'RESET'; expires_at: string }> {
    return request(`/workflow/employees/${encoded(employeeId)}/account/password-reset`, 'POST')
  },

  lockEmployeeAccount(employeeId: string): Promise<WorkflowEmployee> {
    return request(`/workflow/employees/${encoded(employeeId)}/account/lock`, 'POST')
  },

  unlockEmployeeAccount(employeeId: string): Promise<WorkflowEmployee> {
    return request(`/workflow/employees/${encoded(employeeId)}/account/unlock`, 'POST')
  },

  replaceEmployeeRoles(employeeId: string, roleCodes: string[]): Promise<{ employee_id: string; roles: string[] }> {
    return request(`/workflow/employees/${encoded(employeeId)}/roles`, 'PUT', { role_codes: roleCodes })
  },

  listRoles(filters: { query?: string; status?: 'ACTIVE' | 'INACTIVE'; builtin?: boolean } = {}): Promise<AdminRoleCatalog> {
    const params = new URLSearchParams()
    if (filters.query?.trim()) params.set('query', filters.query.trim())
    if (filters.status) params.set('status', filters.status)
    if (filters.builtin !== undefined) params.set('builtin', String(filters.builtin))
    const suffix = params.size ? `?${params.toString()}` : ''
    return request(`/workflow/roles${suffix}`, 'GET')
  },

  createRole(payload: { code: string; name: string; description: string | null; permissions: string[] }): Promise<AdminRole> {
    return request('/workflow/roles', 'POST', payload)
  },

  updateRole(roleId: string, payload: { name: string; description: string | null; permissions: string[] }): Promise<AdminRole> {
    return request(`/workflow/roles/${encoded(roleId)}`, 'PUT', payload)
  },

  deactivateRole(roleId: string): Promise<AdminRole> {
    return request(`/workflow/roles/${encoded(roleId)}/deactivation`, 'POST')
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
