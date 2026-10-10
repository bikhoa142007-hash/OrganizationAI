import { RefreshCw, Search } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowEmployeePage } from '../types/authWorkflow'
import type { WorkflowEmployee } from '../types/authWorkflow'
import type { EmployeePendingPlanPage } from '../types/authWorkflow'

const PAGE_SIZE = 25
type DirectoryFilters = { query: string; role: string; status: '' | 'ACTIVE' | 'DISABLED' | 'PENDING_ACTIVATION' }
type EmployeeFilters = DirectoryFilters & {
  department: string
  job_title: string
  employment_status: '' | 'ACTIVE' | 'INACTIVE'
}
const EMPTY_FILTERS: EmployeeFilters = {
  query: '', role: '', status: '', department: '', job_title: '', employment_status: '',
}

function roleLabel(role: string) {
  if (role === 'MAKER') return 'Maker'
  if (role === 'CHECKER') return 'Checker'
  if (role === 'ADMIN') return 'Quản trị viên'
  return role
}

export function AuthenticatedEmployeesPage() {
  const [page, setPage] = useState<WorkflowEmployeePage | null>(null)
  const [offset, setOffset] = useState(0)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [draftFilters, setDraftFilters] = useState(EMPTY_FILTERS)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [roleOptions, setRoleOptions] = useState<string[]>([])
  const [mutationError, setMutationError] = useState('')
  const [handoverLink, setHandoverLink] = useState('')
  const [creating, setCreating] = useState(false)
  const [newProfile, setNewProfile] = useState({ user_code: '', display_name: '', email: '', phone: '', department: '', job_title: '' })
  const [deactivation, setDeactivation] = useState<{ employee: WorkflowEmployee; plans: EmployeePendingPlanPage['items']; checkers: WorkflowEmployee[]; replacements: Record<string, string> } | null>(null)

  const load = useCallback(async (nextOffset: number, nextFilters: EmployeeFilters) => {
    setError('')
    setLoading(true)
    try {
      const [result, roleCatalog] = await Promise.all([authWorkflowService.listEmployees({
        query: nextFilters.query,
        role: nextFilters.role,
        status: nextFilters.status || undefined,
        department: nextFilters.department,
        job_title: nextFilters.job_title,
        employment_status: nextFilters.employment_status || undefined,
        offset: nextOffset,
        limit: PAGE_SIZE,
      }), authWorkflowService.listRoles()])
      setPage(result)
      setRoleOptions(roleCatalog.items.filter(role => !role.is_builtin && role.status === 'ACTIVE').map(role => role.code))
      setOffset(nextOffset)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load(0, EMPTY_FILTERS) }, [load])

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = { ...draftFilters }
    setFilters(next)
    void load(0, next)
  }

  function clearFilters() {
    setDraftFilters(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    void load(0, EMPTY_FILTERS)
  }

  async function createProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMutationError('')
    setCreating(true)
    try {
      await authWorkflowService.createEmployee({
        user_code: newProfile.user_code.trim(), display_name: newProfile.display_name.trim(),
        email: newProfile.email.trim() || null, phone: newProfile.phone.trim() || null,
        department: newProfile.department.trim() || null, job_title: newProfile.job_title.trim() || null,
      })
      setNewProfile({ user_code: '', display_name: '', email: '', phone: '', department: '', job_title: '' })
      await load(0, filters)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setCreating(false)
    }
  }

  function createHandoverLink(token: string) {
    const url = new URL('/activate', window.location.origin)
    // URL fragments are not sent in HTTP requests or access logs.
    url.hash = new URLSearchParams({ token }).toString()
    setHandoverLink(url.toString())
  }

  async function issueAccount(employeeId: string, displayName: string) {
    const username = window.prompt(`Tên đăng nhập cho ${displayName}`)?.trim()
    if (!username) return
    setMutationError('')
    try {
      const result = await authWorkflowService.createEmployeeAccount(employeeId, username)
      createHandoverLink(result.handover_token)
      await load(offset, filters)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function issueReset(employeeId: string) {
    setMutationError('')
    try {
      const result = await authWorkflowService.requestPasswordReset(employeeId)
      createHandoverLink(result.handover_token)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function reissueActivation(employeeId: string) {
    setMutationError('')
    try {
      const result = await authWorkflowService.reissueEmployeeActivation(employeeId)
      createHandoverLink(result.handover_token)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function setAccountLock(employeeId: string, locked: boolean) {
    setMutationError('')
    try {
      if (locked) await authWorkflowService.lockEmployeeAccount(employeeId)
      else await authWorkflowService.unlockEmployeeAccount(employeeId)
      await load(offset, filters)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function reactivateEmployee(employeeId: string) {
    setMutationError('')
    try {
      await authWorkflowService.reactivateEmployee(employeeId)
      await load(offset, filters)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function assignRoles(employeeId: string, roleCodes: string[]) {
    setMutationError('')
    try {
      await authWorkflowService.replaceEmployeeRoles(employeeId, roleCodes)
      await load(offset, filters)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function beginDeactivation(employee: WorkflowEmployee) {
    setMutationError('')
    try {
      const plans: EmployeePendingPlanPage['items'] = []
      let planOffset = 0
      while (true) {
        const page = await authWorkflowService.listPendingCheckerPlans(employee.id, planOffset, 200)
        plans.push(...page.items)
        planOffset += page.items.length
        if (plans.length >= page.total) break
        if (page.items.length === 0 || planOffset > 20000) throw new Error('Không thể tải đầy đủ danh sách hồ sơ chờ duyệt.')
      }
      if (plans.length === 0) {
        await authWorkflowService.deactivateEmployee(employee.id, {})
        await load(offset, filters)
        return
      }
      const checkerPage = await authWorkflowService.listEmployees({ role: 'CHECKER', status: 'ACTIVE', employment_status: 'ACTIVE', limit: 200 })
      const checkers = checkerPage.items.filter(item => item.account_status === 'ACTIVE' && item.account_id !== employee.account_id)
      setDeactivation({ employee, plans, checkers, replacements: {} })
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  async function confirmDeactivation() {
    if (!deactivation || deactivation.plans.some(plan => !deactivation.replacements[plan.id])) return
    setMutationError('')
    try {
      await authWorkflowService.deactivateEmployee(deactivation.employee.id, deactivation.replacements)
      setDeactivation(null)
      await load(offset, filters)
    } catch (failure) {
      setMutationError(failure instanceof Error ? failure.message : String(failure))
    }
  }

  const first = page && page.total > 0 ? offset + 1 : 0
  const last = page ? Math.min(offset + page.items.length, page.total) : 0

  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading">
      <div><p className="page-eyebrow">Workflow PostgreSQL · Administrator</p><h1>Danh sách nhân viên</h1><p>Tra cứu hồ sơ nhân viên, tài khoản đăng nhập và vai trò được cấp.</p></div>
      <button className="button button-secondary" type="button" disabled={loading} onClick={() => void load(offset, filters)}><RefreshCw aria-hidden="true" /> Tải lại</button>
    </div>

    <details className="auth-employee-create">
      <summary>Thêm hồ sơ nhân viên</summary>
      <form className="auth-plan-filters" onSubmit={event => void createProfile(event)}>
        <div className="auth-plan-filter-controls">
          <label>Mã nhân viên<input required maxLength={32} value={newProfile.user_code} onChange={event => setNewProfile(current => ({ ...current, user_code: event.target.value }))} /></label>
          <label>Họ và tên<input required maxLength={160} value={newProfile.display_name} onChange={event => setNewProfile(current => ({ ...current, display_name: event.target.value }))} /></label>
          <label>Email<input type="email" maxLength={320} value={newProfile.email} onChange={event => setNewProfile(current => ({ ...current, email: event.target.value }))} /></label>
          <label>Điện thoại<input type="tel" maxLength={16} value={newProfile.phone} onChange={event => setNewProfile(current => ({ ...current, phone: event.target.value }))} /></label>
          <label>Bộ phận nhân viên<input maxLength={120} value={newProfile.department} onChange={event => setNewProfile(current => ({ ...current, department: event.target.value }))} /></label>
          <label>Chức danh nhân viên<input maxLength={120} value={newProfile.job_title} onChange={event => setNewProfile(current => ({ ...current, job_title: event.target.value }))} /></label>
          <button className="button button-primary" type="submit" disabled={creating}>{creating ? 'Đang lưu…' : 'Tạo hồ sơ'}</button>
          <span>Hồ sơ được tạo độc lập; tài khoản đăng nhập có thể cấp sau.</span>
        </div>
      </form>
    </details>
    {mutationError && <p className="auth-workflow-state is-error" role="alert">{mutationError}</p>}
    {handoverLink && <section className="auth-handover-link" aria-label="Liên kết bàn giao">
      <h2>Liên kết chỉ dùng một lần · hết hạn trong 30 phút</h2>
      <p>Admin tự bàn giao liên kết cho nhân viên. Liên kết chưa được gửi tự động.</p>
      <input aria-label="Liên kết kích hoạt hoặc đặt lại mật khẩu" readOnly value={handoverLink} onFocus={event => event.currentTarget.select()} />
      <button className="button button-secondary" type="button" onClick={() => void navigator.clipboard?.writeText(handoverLink)}>Sao chép liên kết</button>
      <button className="button button-secondary" type="button" onClick={() => setHandoverLink('')}>Ẩn liên kết</button>
    </section>}
    {deactivation && <section className="auth-workflow-state" role="dialog" aria-modal="true" aria-labelledby="employee-deactivate-title">
      <h2 id="employee-deactivate-title">Chọn Checker thay thế cho {deactivation.employee.display_name}</h2>
      <p>Mỗi hồ sơ Chờ duyệt cần một Checker đang hoạt động. Hệ thống chỉ đổi assignment sau khi có đủ lựa chọn và cùng lúc ngừng nhân viên.</p>
      {deactivation.plans.map(plan => <label key={plan.id}>{plan.code}<select required value={deactivation.replacements[plan.id] || ''} onChange={event => setDeactivation(current => current ? ({ ...current, replacements: { ...current.replacements, [plan.id]: event.target.value } }) : current)}><option value="">Chọn Checker</option>{deactivation.checkers.filter(checker => checker.account_id !== plan.maker_id).map(checker => <option key={checker.account_id!} value={checker.account_id!}>{checker.display_name} · {checker.user_code}</option>)}</select></label>)}
      {deactivation.checkers.length === 0 && <p role="alert">Không có Checker thay thế đủ điều kiện. Chưa thay đổi assignment hay trạng thái nhân viên.</p>}
      <div className="button-row"><button className="button button-primary" type="button" disabled={deactivation.plans.some(plan => !deactivation.replacements[plan.id]) || deactivation.plans.some(plan => !deactivation.checkers.some(checker => checker.account_id !== plan.maker_id))} onClick={() => void confirmDeactivation()}>Chuyển hồ sơ và ngừng nhân viên</button><button className="button button-secondary" type="button" onClick={() => setDeactivation(null)}>Hủy</button></div>
    </section>}

    <form className="auth-plan-filters" role="search" aria-label="Lọc nhân viên" onSubmit={applyFilters}>
      <div className="auth-plan-filter-controls">
        <label htmlFor="employee-query">Tìm nhân viên<input id="employee-query" type="search" maxLength={120} value={draftFilters.query} onChange={event => setDraftFilters(current => ({ ...current, query: event.target.value }))} placeholder="Tên, mã, tài khoản, email hoặc điện thoại" /></label>
        <label htmlFor="employee-role">Vai trò<select id="employee-role" value={draftFilters.role} onChange={event => setDraftFilters(current => ({ ...current, role: event.target.value }))}><option value="">Tất cả vai trò</option><option value="MAKER">Maker</option><option value="CHECKER">Checker</option><option value="ADMIN">Quản trị viên</option></select></label>
        <label htmlFor="employee-department">Bộ phận<input id="employee-department" type="search" maxLength={120} value={draftFilters.department} onChange={event => setDraftFilters(current => ({ ...current, department: event.target.value }))} /></label>
        <label htmlFor="employee-job-title">Chức danh<input id="employee-job-title" type="search" maxLength={120} value={draftFilters.job_title} onChange={event => setDraftFilters(current => ({ ...current, job_title: event.target.value }))} /></label>
        <label htmlFor="employee-employment-status">Trạng thái nhân viên<select id="employee-employment-status" value={draftFilters.employment_status} onChange={event => setDraftFilters(current => ({ ...current, employment_status: event.target.value as EmployeeFilters['employment_status'] }))}><option value="">Tất cả trạng thái</option><option value="ACTIVE">Đang làm việc</option><option value="INACTIVE">Đã nghỉ việc</option></select></label>
        <label htmlFor="employee-status">Trạng thái tài khoản<select id="employee-status" value={draftFilters.status} onChange={event => setDraftFilters(current => ({ ...current, status: event.target.value as EmployeeFilters['status'] }))}><option value="">Tất cả trạng thái</option><option value="ACTIVE">Đang hoạt động</option><option value="DISABLED">Đã vô hiệu hóa</option><option value="PENDING_ACTIVATION">Chờ kích hoạt</option></select></label>
        <div className="auth-employee-filter-actions"><button className="button button-primary" type="submit" disabled={loading}><Search aria-hidden="true" /> Tìm kiếm</button><button className="button button-secondary" type="button" disabled={loading} onClick={clearFilters}>Xóa lọc</button></div>
      </div>
    </form>

    {loading ? <p className="auth-workflow-state" role="status">Đang tải danh sách nhân viên…</p>
      : error ? <section className="auth-workflow-state is-error" role="alert"><h2>Không tải được danh sách</h2><p>{error}</p><button className="button button-secondary" type="button" onClick={() => void load(offset, filters)}>Thử lại</button></section>
        : !page || page.items.length === 0 ? <section className="auth-workflow-state" role="status"><h2>Không tìm thấy nhân viên</h2><p>Thử thay đổi nội dung tìm kiếm hoặc bộ lọc.</p></section>
          : <>
            <div className="auth-workflow-table-wrap"><table className="auth-workflow-table"><caption className="auth-employee-table-caption">Danh sách nhân viên, {first}–{last} trên {page.total}</caption><thead><tr><th>Mã nhân viên</th><th>Họ và tên</th><th>Tên đăng nhập</th><th>Email</th><th>Điện thoại</th><th>Bộ phận</th><th>Chức danh</th><th>Ngày bắt đầu</th><th>Trạng thái nhân viên</th><th>Trạng thái tài khoản</th><th>Vai trò</th><th>Thao tác</th></tr></thead><tbody>
              {page.items.map(employee => <tr key={employee.id}>
                <td>{employee.user_code}</td><td>{employee.display_name}</td><td>{employee.username || 'Chưa có tài khoản'}</td><td>{employee.email || '—'}</td><td>{employee.phone || '—'}</td>
                <td>{employee.department || '—'}</td><td>{employee.job_title || '—'}</td><td>{employee.employment_start_date || '—'}</td>
                <td>{employee.employment_status === 'ACTIVE' ? 'Đang làm việc' : 'Đã nghỉ việc'}</td>
                <td>{employee.account_status === 'ACTIVE' ? 'Đang hoạt động' : employee.account_status === 'DISABLED' ? 'Đã vô hiệu hóa' : employee.account_status === 'PENDING_ACTIVATION' ? 'Chờ kích hoạt' : 'Chưa có tài khoản'}</td><td>{employee.roles.map(roleLabel).join(', ') || 'Chưa được cấp'}{employee.effective_permissions.length > 0 && <details><summary>Quyền hiệu lực</summary>{employee.effective_permissions.map(permission => <div key={permission}><code>{permission}</code></div>)}</details>}</td>
                <td><div className="auth-employee-actions">
                  {!employee.account_id && employee.employment_status === 'ACTIVE' && <button className="button button-secondary" type="button" onClick={() => void issueAccount(employee.id, employee.display_name)}>Tạo tài khoản</button>}
                  {employee.account_id && employee.account_status === 'PENDING_ACTIVATION' && employee.employment_status === 'ACTIVE' && <button className="button button-secondary" type="button" onClick={() => void reissueActivation(employee.id)}>Cấp lại link kích hoạt</button>}
                  <EmployeeProfileEditor employee={employee} onSave={changes => void authWorkflowService.updateEmployee(employee.id, changes).then(() => load(offset, filters)).catch(failure => setMutationError(failure instanceof Error ? failure.message : String(failure)))} />
                  {employee.account_id && employee.account_status === 'ACTIVE' && <>
                    <button className="button button-secondary" type="button" onClick={() => void issueReset(employee.id)}>Tạo link đặt lại mật khẩu</button>
                    <button className="button button-secondary" type="button" onClick={() => void setAccountLock(employee.id, true)}>Khóa tài khoản</button>
                  </>}
                  {employee.account_id && employee.account_status === 'DISABLED' && employee.employment_status === 'ACTIVE' && <button className="button button-secondary" type="button" onClick={() => void setAccountLock(employee.id, false)}>Mở khóa</button>}
                  {employee.account_id && ['ACTIVE', 'DISABLED'].includes(employee.account_status || '') && <EmployeeRoleEditor employee={employee} customRoleOptions={roleOptions} canAssign={employee.account_status === 'ACTIVE' && employee.employment_status === 'ACTIVE'} onSave={roles => void assignRoles(employee.id, roles)} />}
                  {employee.employment_status === 'INACTIVE' && <button className="button button-secondary" type="button" onClick={() => void reactivateEmployee(employee.id)}>Kích hoạt lại nhân viên</button>}
                  {employee.employment_status === 'ACTIVE' && <button className="button button-secondary" type="button" onClick={() => void beginDeactivation(employee)}>Ngừng hoạt động</button>}
                </div></td>
              </tr>)}
            </tbody></table></div>
            <div className="button-row" aria-label="Phân trang nhân viên">
              <button className="button button-secondary" type="button" disabled={loading || offset === 0} onClick={() => void load(Math.max(0, offset - PAGE_SIZE), filters)}>Trước</button>
              <span role="status">{first}–{last} / {page.total}</span>
              <button className="button button-secondary" type="button" disabled={loading || offset + page.items.length >= page.total} onClick={() => void load(offset + PAGE_SIZE, filters)}>Tiếp</button>
            </div>
          </>}
  </section>
}

function EmployeeProfileEditor({ employee, onSave }: { employee: WorkflowEmployee; onSave: (changes: Partial<Pick<WorkflowEmployee, 'user_code' | 'display_name' | 'email' | 'phone' | 'department' | 'job_title' | 'employment_start_date'>>) => void }) {
  const [values, setValues] = useState({ user_code: employee.user_code, display_name: employee.display_name, email: employee.email || '', phone: employee.phone || '', department: employee.department || '', job_title: employee.job_title || '', employment_start_date: employee.employment_start_date || '' })
  return <details><summary>Sửa hồ sơ</summary><form onSubmit={event => { event.preventDefault(); onSave({ ...values, email: values.email || null, phone: values.phone || null, department: values.department || null, job_title: values.job_title || null, employment_start_date: values.employment_start_date || null }) }}>
    <label>Mã<input required maxLength={32} value={values.user_code} onChange={event => setValues(current => ({ ...current, user_code: event.target.value }))} /></label>
    <label>Họ tên<input required maxLength={160} value={values.display_name} onChange={event => setValues(current => ({ ...current, display_name: event.target.value }))} /></label>
    <label>Email<input type="email" maxLength={320} value={values.email} onChange={event => setValues(current => ({ ...current, email: event.target.value }))} /></label>
    <label>Điện thoại<input type="tel" maxLength={16} value={values.phone} onChange={event => setValues(current => ({ ...current, phone: event.target.value }))} /></label>
    <label>Bộ phận hồ sơ<input maxLength={120} value={values.department} onChange={event => setValues(current => ({ ...current, department: event.target.value }))} /></label>
    <label>Chức danh hồ sơ<input maxLength={120} value={values.job_title} onChange={event => setValues(current => ({ ...current, job_title: event.target.value }))} /></label>
    <label>Ngày bắt đầu<input type="date" value={values.employment_start_date} onChange={event => setValues(current => ({ ...current, employment_start_date: event.target.value }))} /></label>
    <button className="button button-secondary" type="submit">Lưu hồ sơ</button>
  </form></details>
}

function EmployeeRoleEditor({ employee, customRoleOptions, canAssign, onSave }: { employee: WorkflowEmployeePage['items'][number]; customRoleOptions: string[]; canAssign: boolean; onSave: (roles: string[]) => void }) {
  const [maker, setMaker] = useState(employee.roles.includes('MAKER'))
  const [checker, setChecker] = useState(employee.roles.includes('CHECKER'))
  const [custom, setCustom] = useState(employee.roles.filter(role => customRoleOptions.includes(role)))
  function toggleCustom(code: string) { setCustom(current => current.includes(code) ? current.filter(role => role !== code) : [...current, code]) }
  return <details><summary>Vai trò</summary>{!canAssign && <p>Account đang khóa hoặc nhân viên inactive: chỉ có thể thu hồi vai trò.</p>}<label><input type="checkbox" checked={maker} disabled={!canAssign && !maker} onChange={event => setMaker(event.target.checked)} /> Maker</label><label><input type="checkbox" checked={checker} disabled={!canAssign && !checker} onChange={event => setChecker(event.target.checked)} /> Checker</label>{customRoleOptions.map(code => <label key={code}><input type="checkbox" checked={custom.includes(code)} disabled={!canAssign && !custom.includes(code)} onChange={() => toggleCustom(code)} /> {code}</label>)}<button className="button button-secondary" type="button" onClick={() => onSave([...custom, ...(maker ? ['MAKER'] : []), ...(checker ? ['CHECKER'] : [])])}>Lưu vai trò</button></details>
}
