import type { WorkflowPlan } from '../types/authWorkflow'

export const WORKFLOW_PLAN_STATUSES = ['DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED'] as const

export const WORKFLOW_PLAN_STATUS_LABELS: Record<(typeof WORKFLOW_PLAN_STATUSES)[number], string> = {
  DRAFT: 'Bản nháp',
  PENDING_APPROVAL: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  REJECTED: 'Đã từ chối',
}

export interface WorkflowPlanFilters {
  q: string
  status: (typeof WORKFLOW_PLAN_STATUSES)[number] | ''
  department: string
  created_from: string
  created_to: string
}

export const EMPTY_WORKFLOW_PLAN_FILTERS: WorkflowPlanFilters = {
  q: '',
  status: '',
  department: '',
  created_from: '',
  created_to: '',
}

const FILTER_PARAMS = ['q', 'status', 'department', 'created_from', 'created_to'] as const

export function isIsoCalendarDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false
  const date = new Date(`${value}T00:00:00.000Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
}

export function parseWorkflowPlanFilters(params: URLSearchParams) {
  let invalid = false
  const rawQuery = params.get('q') ?? ''
  const q = rawQuery.trim().slice(0, 120)
  if (rawQuery !== q) invalid = true

  const rawStatus = params.get('status') ?? ''
  const status = WORKFLOW_PLAN_STATUSES.find(value => value === rawStatus) ?? ''
  if (rawStatus && !status) invalid = true

  const rawDepartment = params.get('department') ?? ''
  const department = rawDepartment.trim()
  if (rawDepartment !== department) invalid = true

  const rawCreatedFrom = params.get('created_from') ?? ''
  const rawCreatedTo = params.get('created_to') ?? ''
  let created_from = isIsoCalendarDate(rawCreatedFrom) ? rawCreatedFrom : ''
  let created_to = isIsoCalendarDate(rawCreatedTo) ? rawCreatedTo : ''
  if ((rawCreatedFrom && !created_from) || (rawCreatedTo && !created_to)) invalid = true
  if (created_from && created_to && created_from > created_to) {
    created_from = ''
    created_to = ''
    invalid = true
  }

  return {
    filters: { q, status, department, created_from, created_to } satisfies WorkflowPlanFilters,
    invalid,
  }
}

export function writeWorkflowPlanFilters(filters: WorkflowPlanFilters, source = new URLSearchParams()) {
  const params = new URLSearchParams(source)
  FILTER_PARAMS.forEach(key => params.delete(key))

  const q = filters.q.trim().slice(0, 120)
  if (q) params.set('q', q)
  if (WORKFLOW_PLAN_STATUSES.includes(filters.status as (typeof WORKFLOW_PLAN_STATUSES)[number])) {
    params.set('status', filters.status)
  }
  const department = filters.department.trim()
  if (department) params.set('department', department)
  const createdFrom = isIsoCalendarDate(filters.created_from) ? filters.created_from : ''
  const createdTo = isIsoCalendarDate(filters.created_to) ? filters.created_to : ''
  if (!(createdFrom && createdTo && createdFrom > createdTo)) {
    if (createdFrom) params.set('created_from', createdFrom)
    if (createdTo) params.set('created_to', createdTo)
  }
  return params
}

export function filterWorkflowPlans(plans: WorkflowPlan[], filters: WorkflowPlanFilters) {
  const query = filters.q.trim().toLocaleLowerCase('vi-VN')
  if (filters.created_from && filters.created_to && filters.created_from > filters.created_to) return []

  return plans.filter(plan => {
    if (query) {
      const searchableFields = [
        readString(plan?.id),
        readString(plan?.code),
        readString(plan?.payload?.title),
        readString(plan?.maker_name),
        readString(plan?.checker_name),
        readString(plan?.payload?.department),
      ]
      if (!searchableFields.some(field => field.toLocaleLowerCase('vi-VN').includes(query))) return false
    }

    if (filters.status && plan?.status !== filters.status) return false
    if (filters.department && readString(plan?.payload?.department).trim() !== filters.department) return false

    if (filters.created_from || filters.created_to) {
      const createdDate = backendCalendarDate(plan?.created_at)
      if (!createdDate) return false
      if (filters.created_from && createdDate < filters.created_from) return false
      if (filters.created_to && createdDate > filters.created_to) return false
    }
    return true
  })
}

export function workflowPlanDepartments(plans: WorkflowPlan[]) {
  return [...new Set(plans
    .map(plan => readString(plan?.payload?.department).trim())
    .filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, 'vi-VN'))
}

export function activeWorkflowPlanFilterCount(filters: WorkflowPlanFilters) {
  return FILTER_PARAMS.filter(key => Boolean(filters[key])).length
}

export function backendCalendarDate(value: unknown) {
  if (typeof value !== 'string') return ''
  const date = value.match(/^(\d{4}-\d{2}-\d{2})(?:T|$)/)?.[1] ?? ''
  return isIsoCalendarDate(date) ? date : ''
}

function readString(value: unknown) {
  return typeof value === 'string' ? value : ''
}
