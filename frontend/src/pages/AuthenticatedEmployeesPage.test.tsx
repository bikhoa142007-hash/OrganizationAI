import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowEmployee, WorkflowEmployeePage } from '../types/authWorkflow'
import { AuthenticatedEmployeesPage } from './AuthenticatedEmployeesPage'

function employee(index: number): WorkflowEmployee {
  return {
    id: `employee-${index}`,
    account_id: `user-${index}`,
    user_code: `USR-${String(index).padStart(4, '0')}`,
    username: `person.${String(index).padStart(2, '0')}`,
    display_name: `Person ${index}`,
    email: `person${index}@example.com`,
    phone: null,
    department: 'Marketing',
    job_title: 'Planner',
    employment_start_date: '2022-04-15',
    employment_status: 'ACTIVE',
    status: 'ACTIVE',
    account_status: 'ACTIVE',
    effective_permissions: [],
    roles: index === 1 ? ['ADMIN'] : ['MAKER'],
  }
}

function page(items = Array.from({ length: 25 }, (_, index) => employee(index + 1)), offset = 0, total = 30): WorkflowEmployeePage {
  return { items, offset, limit: 25, total }
}

afterEach(() => vi.restoreAllMocks())

it('searches and filters the Admin directory, then keeps those filters while paging', async () => {
  const user = userEvent.setup()
  const listEmployees = vi.spyOn(authWorkflowService, 'listEmployees').mockResolvedValue(page(
    Array.from({ length: 5 }, (_, index) => employee(index + 1)),
  ))
  vi.spyOn(authWorkflowService, 'listRoles').mockResolvedValue({ items: [], permission_catalog: [] })
  render(<MemoryRouter><AuthenticatedEmployeesPage /></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Danh sách nhân viên' })).toBeVisible()
  expect(await screen.findByText('Person 1')).toBeVisible()
  expect(screen.getByText('person1@example.com')).toBeVisible()
  expect(within(screen.getByRole('table')).getAllByText('Planner')).toHaveLength(5)

  await user.type(screen.getByLabelText('Tìm nhân viên'), 'sales')
  await user.selectOptions(screen.getByLabelText('Vai trò'), 'CHECKER')
  await user.selectOptions(screen.getByLabelText('Trạng thái tài khoản'), 'DISABLED')
  await user.type(screen.getByLabelText('Bộ phận'), 'Marketing')
  await user.type(screen.getByLabelText('Chức danh'), 'Planner')
  await user.selectOptions(screen.getByLabelText('Trạng thái nhân viên'), 'INACTIVE')
  await user.click(screen.getByRole('button', { name: 'Tìm kiếm' }))

  await waitFor(() => expect(listEmployees).toHaveBeenLastCalledWith({
    query: 'sales', role: 'CHECKER', status: 'DISABLED', department: 'Marketing',
    job_title: 'Planner', employment_status: 'INACTIVE', offset: 0, limit: 25,
  }))
  await user.click(within(screen.getByLabelText('Phân trang nhân viên')).getByRole('button', { name: 'Tiếp' }))
  await waitFor(() => expect(listEmployees).toHaveBeenLastCalledWith({
    query: 'sales', role: 'CHECKER', status: 'DISABLED', department: 'Marketing',
    job_title: 'Planner', employment_status: 'INACTIVE', offset: 25, limit: 25,
  }))
})

it('shows an empty result message without a blank data table', async () => {
  vi.spyOn(authWorkflowService, 'listEmployees').mockResolvedValue(page([], 0, 0))
  vi.spyOn(authWorkflowService, 'listRoles').mockResolvedValue({ items: [], permission_catalog: [] })
  render(<MemoryRouter><AuthenticatedEmployeesPage /></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Không tìm thấy nhân viên' })).toBeVisible()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})

it('keeps the directory page after deactivation without pending plans', async () => {
  const user = userEvent.setup()
  const rows = Array.from({ length: 5 }, (_, index) => employee(index + 1))
  const listEmployees = vi.spyOn(authWorkflowService, 'listEmployees').mockResolvedValue(page(rows))
  vi.spyOn(authWorkflowService, 'listRoles').mockResolvedValue({ items: [], permission_catalog: [] })
  vi.spyOn(authWorkflowService, 'listPendingCheckerPlans').mockResolvedValue({
    items: [], offset: 0, limit: 200, total: 0,
  })
  const deactivate = vi.spyOn(authWorkflowService, 'deactivateEmployee').mockResolvedValue(employee(1))
  render(<MemoryRouter><AuthenticatedEmployeesPage /></MemoryRouter>)

  await screen.findByText('Person 1')
  await user.click(within(screen.getByLabelText('Phân trang nhân viên')).getByRole('button', { name: 'Tiếp' }))
  await waitFor(() => expect(listEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })))
  await user.click(within(screen.getAllByRole('row')[1]).getByRole('button', { name: 'Ngừng hoạt động' }))

  await waitFor(() => expect(deactivate).toHaveBeenCalledWith('employee-1', {}))
  await waitFor(() => expect(listEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })))
})

it('reactivates employment separately while keeping account and role controls explicit', async () => {
  const user = userEvent.setup()
  const inactive = {
    ...employee(7), employment_status: 'INACTIVE' as const, status: 'DISABLED' as const,
    account_status: 'DISABLED' as const, roles: ['MAKER'],
  }
  vi.spyOn(authWorkflowService, 'listEmployees').mockResolvedValue(page([inactive], 0, 1))
  vi.spyOn(authWorkflowService, 'listRoles').mockResolvedValue({ items: [], permission_catalog: [] })
  const replaceRoles = vi.spyOn(authWorkflowService, 'replaceEmployeeRoles').mockResolvedValue({ employee_id: inactive.id, roles: [] })
  const reactivate = vi.spyOn(authWorkflowService, 'reactivateEmployee').mockResolvedValue({
    ...inactive, employment_status: 'ACTIVE', account_status: 'DISABLED', roles: [],
  })
  render(<MemoryRouter><AuthenticatedEmployeesPage /></MemoryRouter>)

  await screen.findByText('Person 7')
  await user.click(screen.getByText('Vai trò', { selector: 'summary' }))
  const makerRole = screen.getByRole('checkbox', { name: 'Maker' })
  expect(makerRole).toBeEnabled()
  await user.click(makerRole)
  expect(makerRole).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Lưu vai trò' }))
  await waitFor(() => expect(replaceRoles).toHaveBeenCalledWith(inactive.id, []))

  await user.click(screen.getByRole('button', { name: 'Kích hoạt lại nhân viên' }))
  await waitFor(() => expect(reactivate).toHaveBeenCalledWith(inactive.id))
})

it('lets Admin reissue an activation link for an active employee awaiting activation', async () => {
  const user = userEvent.setup()
  const pending = {
    ...employee(8), employment_status: 'ACTIVE' as const, status: 'DISABLED' as const,
    account_status: 'PENDING_ACTIVATION' as const, roles: [],
  }
  vi.spyOn(authWorkflowService, 'listEmployees').mockResolvedValue(page([pending], 0, 1))
  vi.spyOn(authWorkflowService, 'listRoles').mockResolvedValue({ items: [], permission_catalog: [] })
  const reissue = vi.spyOn(authWorkflowService, 'reissueEmployeeActivation').mockResolvedValue({
    handover_token: 'synthetic-activation-token', purpose: 'ACTIVATE', expires_at: '2026-10-10T13:30:00Z',
  })
  render(<MemoryRouter><AuthenticatedEmployeesPage /></MemoryRouter>)

  await screen.findByText('Person 8')
  await user.click(screen.getByRole('button', { name: 'Cấp lại link kích hoạt' }))

  expect(await screen.findByLabelText('Liên kết kích hoạt hoặc đặt lại mật khẩu')).toHaveValue(
    `${window.location.origin}/activate#token=synthetic-activation-token`,
  )
  expect(reissue).toHaveBeenCalledWith(pending.id)
})
