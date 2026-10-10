import { useEffect, useState } from 'react'
import {
  activeWorkflowPlanFilterCount,
  WORKFLOW_PLAN_STATUS_LABELS,
  WORKFLOW_PLAN_STATUSES,
} from '../../../services/workflowPlanFilters'
import type { WorkflowPlanFilters as WorkflowPlanFilterValues } from '../../../services/workflowPlanFilters'

interface WorkflowPlanFiltersProps {
  filters: WorkflowPlanFilterValues
  departments: string[]
  urlNotice: string
  onChange: (filters: WorkflowPlanFilterValues) => void
  onClear: () => void
}

export function WorkflowPlanFilters({ filters, departments, urlNotice, onChange, onClear }: WorkflowPlanFiltersProps) {
  const [dateRangeError, setDateRangeError] = useState('')
  const [queryDraft, setQueryDraft] = useState(filters.q)
  const activeCount = activeWorkflowPlanFilterCount(filters)
  const departmentOptions = filters.department && !departments.includes(filters.department)
    ? [...departments, filters.department].sort((left, right) => left.localeCompare(right, 'vi-VN'))
    : departments

  useEffect(() => { setQueryDraft(filters.q) }, [filters.q])

  function update(next: WorkflowPlanFilterValues) {
    if (next.created_from && next.created_to && next.created_from > next.created_to) {
      setDateRangeError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
      return
    }
    setDateRangeError('')
    onChange(next)
  }

  const chips: Array<{ label: string; field: string; key: keyof WorkflowPlanFilterValues }> = []
  if (filters.q) chips.push({ label: `Từ khóa: ${filters.q}`, field: 'từ khóa', key: 'q' })
  if (filters.status) chips.push({ label: `Trạng thái: ${WORKFLOW_PLAN_STATUS_LABELS[filters.status]}`, field: 'trạng thái', key: 'status' })
  if (filters.department) chips.push({ label: `Bộ phận: ${filters.department}`, field: 'bộ phận', key: 'department' })
  if (filters.created_from) chips.push({ label: `Tạo từ: ${filters.created_from}`, field: 'ngày tạo từ', key: 'created_from' })
  if (filters.created_to) chips.push({ label: `Tạo đến: ${filters.created_to}`, field: 'ngày tạo đến', key: 'created_to' })

  return <section className="auth-plan-filters" aria-label="Tìm kiếm và lọc yêu cầu">
    <details open className="auth-plan-filter-disclosure">
      <summary>Tìm kiếm và lọc <span>{activeCount ? `${activeCount} đang áp dụng` : 'trong dữ liệu đã tải'}</span></summary>
      <div className="auth-plan-filter-controls">
        <div className="auth-plan-search-field">
          <label htmlFor="workflow-plan-search">Tìm trong các yêu cầu đã tải</label>
          <input
            id="workflow-plan-search"
            type="search"
            maxLength={120}
            aria-describedby="workflow-plan-search-help"
            value={queryDraft}
            placeholder="Tên, mã, người lập hoặc bộ phận"
            onChange={event => {
              const value = event.target.value.slice(0, 120)
              setQueryDraft(value)
              update({ ...filters, q: value })
            }}
          />
          <small id="workflow-plan-search-help">{queryDraft.length}/120 ký tự · Chỉ tìm trong dữ liệu đã tải.</small>
        </div>
        <label htmlFor="workflow-plan-status-filter">Trạng thái
          <select id="workflow-plan-status-filter" value={filters.status} onChange={event => update({ ...filters, status: event.target.value as WorkflowPlanFilterValues['status'] })}>
            <option value="">Tất cả trạng thái</option>
            {WORKFLOW_PLAN_STATUSES.map(status => <option key={status} value={status}>{WORKFLOW_PLAN_STATUS_LABELS[status]}</option>)}
          </select>
        </label>
        <label htmlFor="workflow-plan-department-filter">Bộ phận
          <select id="workflow-plan-department-filter" value={filters.department} onChange={event => update({ ...filters, department: event.target.value })}>
            <option value="">Tất cả bộ phận</option>
            {departmentOptions.map(department => <option key={department} value={department}>{department}</option>)}
          </select>
        </label>
        <label htmlFor="workflow-plan-created-from">Ngày tạo từ
          <input id="workflow-plan-created-from" type="date" max={filters.created_to || undefined} value={filters.created_from} onChange={event => update({ ...filters, created_from: event.target.value })} />
        </label>
        <label htmlFor="workflow-plan-created-to">Ngày tạo đến
          <input id="workflow-plan-created-to" type="date" min={filters.created_from || undefined} value={filters.created_to} onChange={event => update({ ...filters, created_to: event.target.value })} />
        </label>
        <button className="button button-secondary auth-plan-clear-filters" type="button" disabled={activeCount === 0} onClick={onClear}>Xóa bộ lọc</button>
      </div>
    </details>
    {dateRangeError && <p className="auth-plan-filter-notice" role="alert">{dateRangeError}</p>}
    {urlNotice && <p className="auth-plan-filter-notice" role="status">{urlNotice}</p>}
    {chips.length > 0 && <ul className="auth-plan-filter-chips" aria-label="Bộ lọc đang áp dụng">
      {chips.map(chip => <li key={chip.key}><span>{chip.label}</span><button type="button" aria-label={`Xóa bộ lọc ${chip.field}`} onClick={() => update({ ...filters, [chip.key]: '' })}>×</button></li>)}
    </ul>}
  </section>
}
