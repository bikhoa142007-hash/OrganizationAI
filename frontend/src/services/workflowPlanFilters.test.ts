import { describe, expect, it } from 'vitest'
import type { WorkflowPlan } from '../types/authWorkflow'
import {
  activeWorkflowPlanFilterCount,
  backendCalendarDate,
  EMPTY_WORKFLOW_PLAN_FILTERS,
  filterWorkflowPlans,
  parseWorkflowPlanFilters,
  workflowPlanDepartments,
  writeWorkflowPlanFilters,
} from './workflowPlanFilters'

function plan(overrides: Partial<WorkflowPlan> = {}): WorkflowPlan {
  return {
    id: 'request-1', code: 'MKT-1',
    payload: {
      title: 'Autumn campaign', objective: '', summary: '', department: 'Marketing',
      start_date: '', end_date: '', budget_minor_units: '', currency: 'VND', target_audience: '',
      channels: [], kpi_expected: '', notes: '',
    },
    status: 'PENDING_APPROVAL', processing_stage: 'HUMAN_REVIEW_REQUIRED',
    maker_id: 'maker-1', maker_name: 'Linh Nguyen', checker_id: 'checker-1', checker_name: 'An Tran',
    current_version: 1, current_round: 1, revision: 1, decision_reason: null,
    attachments: [], versions: [], ai_evaluations: [], engine_decisions: [], history: [],
    created_at: '2026-10-02T00:30:00+07:00', updated_at: '2026-10-03T00:30:00+07:00',
    ...overrides,
  }
}

describe('workflow plan filters', () => {
  it('combines trimmed case-insensitive search, status, department and inclusive backend date range', () => {
    const matching = plan()
    const differentStatus = plan({ id: 'request-2', status: 'APPROVED' })
    const differentDepartment = plan({
      id: 'request-3',
      payload: { ...matching.payload, department: 'Sales' },
    })
    const plans = [matching, differentStatus, differentDepartment]
    const filters = {
      ...EMPTY_WORKFLOW_PLAN_FILTERS,
      q: '  AUTUMN  ', status: 'PENDING_APPROVAL' as const, department: 'Marketing',
      created_from: '2026-10-02', created_to: '2026-10-02',
    }

    expect(filterWorkflowPlans(plans, filters)).toEqual([matching])
    expect(plans).toEqual([matching, differentStatus, differentDepartment])
  })

  it('searches only real request fields and tolerates null or missing optional values', () => {
    const makerMatch = plan({ id: 'unique-request-id', payload: { ...plan().payload, title: 'Launch' } })
    const codeMatch = plan({ id: 'request-2', code: 'ABC-204', maker_name: 'Mai' })
    const departmentMatch = plan({ id: 'request-3', payload: { ...plan().payload, department: 'Operations' } })
    const sparse = { id: 'sparse-request', payload: null, code: null, maker_name: null, checker_name: null } as unknown as WorkflowPlan

    expect(filterWorkflowPlans([makerMatch], { ...EMPTY_WORKFLOW_PLAN_FILTERS, q: '  launch ' })).toEqual([makerMatch])
    expect(filterWorkflowPlans([codeMatch], { ...EMPTY_WORKFLOW_PLAN_FILTERS, q: 'abc-204' })).toEqual([codeMatch])
    expect(filterWorkflowPlans([departmentMatch], { ...EMPTY_WORKFLOW_PLAN_FILTERS, q: 'operations' })).toEqual([departmentMatch])
    expect(filterWorkflowPlans([sparse], { ...EMPTY_WORKFLOW_PLAN_FILTERS, q: 'missing' })).toEqual([])
    expect(filterWorkflowPlans([sparse], EMPTY_WORKFLOW_PLAN_FILTERS)).toEqual([sparse])
  })

  it('compares backend calendar dates without converting timezone offsets', () => {
    const offsetDate = plan({ created_at: '2026-10-01T23:30:00-07:00' })
    const nextBackendDate = plan({ id: 'request-2', created_at: '2026-10-02T00:00:00Z' })

    expect(backendCalendarDate(offsetDate.created_at)).toBe('2026-10-01')
    expect(filterWorkflowPlans([offsetDate, nextBackendDate], {
      ...EMPTY_WORKFLOW_PLAN_FILTERS, created_to: '2026-10-01',
    })).toEqual([offsetDate])
    expect(backendCalendarDate(null)).toBe('')
    expect(backendCalendarDate('invalid')).toBe('')
  })

  it('normalizes invalid URL filters and preserves unrelated query parameters when writing filters', () => {
    const invalidSearch = new URLSearchParams({
      tab: 'assigned', q: ` ${'x'.repeat(121)} `, status: 'UNKNOWN', department: '  ',
      created_from: '2026-03-01', created_to: '2026-02-01',
    })
    const parsed = parseWorkflowPlanFilters(invalidSearch)
    expect(parsed.invalid).toBe(true)
    expect(parsed.filters).toEqual({
      ...EMPTY_WORKFLOW_PLAN_FILTERS, q: 'x'.repeat(120),
    })
    expect(parseWorkflowPlanFilters(new URLSearchParams('created_from=2026-02-30'))).toMatchObject({
      invalid: true, filters: EMPTY_WORKFLOW_PLAN_FILTERS,
    })

    const written = writeWorkflowPlanFilters({
      ...EMPTY_WORKFLOW_PLAN_FILTERS, q: '  campaign  ', status: 'REJECTED',
      department: 'Sales', created_from: '2026-10-10', created_to: '2026-10-01',
    }, invalidSearch)
    expect(written.get('tab')).toBe('assigned')
    expect(written.get('q')).toBe('campaign')
    expect(written.get('status')).toBe('REJECTED')
    expect(written.get('department')).toBe('Sales')
    expect(written.has('created_from')).toBe(false)
    expect(written.has('created_to')).toBe(false)
    expect(activeWorkflowPlanFilterCount(parsed.filters)).toBe(1)
  })

  it('derives department options only from loaded records and known statuses stay contract-bound', () => {
    const plans = [
      plan(), plan({ id: 'request-2', payload: { ...plan().payload, department: 'Sales' } }),
      plan({ id: 'request-3', payload: { ...plan().payload, department: 'Marketing' } }),
    ]
    expect(workflowPlanDepartments(plans)).toEqual(['Marketing', 'Sales'])
    expect(parseWorkflowPlanFilters(new URLSearchParams('status=APPROVED')).filters.status).toBe('APPROVED')
    expect(parseWorkflowPlanFilters(new URLSearchParams('status=WAITING')).filters.status).toBe('')
  })
})
