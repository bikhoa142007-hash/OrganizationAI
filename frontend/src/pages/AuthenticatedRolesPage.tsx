import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { authWorkflowService } from '../services/authWorkflow'
import type { AdminRole, AdminRoleCatalog } from '../types/authWorkflow'

const EMPTY_FORM = { code: '', name: '', description: '', permissions: [] as string[] }

export function AuthenticatedRolesPage() {
  const [catalog, setCatalog] = useState<AdminRoleCatalog | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState<AdminRole | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'' | 'ACTIVE' | 'INACTIVE'>('')
  const [draftQuery, setDraftQuery] = useState('')
  const [draftStatus, setDraftStatus] = useState<'' | 'ACTIVE' | 'INACTIVE'>('')

  const load = useCallback(async (nextQuery = query, nextStatus = status) => {
    setError('')
    setLoading(true)
    try { setCatalog(await authWorkflowService.listRoles({ query: nextQuery, status: nextStatus || undefined })) }
    catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)) }
    finally { setLoading(false) }
  }, [query, status])
  useEffect(() => { void load() }, [load])

  function beginEdit(role: AdminRole) {
    setEditing(role)
    setForm({ code: role.code, name: role.name, description: role.description || '', permissions: [...role.permissions] })
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    try {
      if (editing) await authWorkflowService.updateRole(editing.id, { name: form.name, description: form.description || null, permissions: form.permissions })
      else await authWorkflowService.createRole({ code: form.code, name: form.name, description: form.description || null, permissions: form.permissions })
      setEditing(null)
      setForm(EMPTY_FORM)
      await load()
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)) }
  }

  async function deactivate(role: AdminRole) {
    setError('')
    try { await authWorkflowService.deactivateRole(role.id); await load() }
    catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)) }
  }

  function togglePermission(code: string) {
    setForm(current => ({ ...current, permissions: current.permissions.includes(code)
      ? current.permissions.filter(value => value !== code) : [...current.permissions, code] }))
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setQuery(draftQuery); setStatus(draftStatus) }

  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">Workflow PostgreSQL · Administrator</p><h1>Vai trò và quyền</h1><p>Vai trò Maker, Checker và Admin là vai trò hệ thống cố định. Vai trò tùy chỉnh chỉ dùng quyền trong danh mục Phase 1.</p></div><button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}>Tải lại</button></div>
    {error && <p className="auth-workflow-state is-error" role="alert">{error}</p>}
    <form className="auth-plan-filters" role="search" aria-label="Lọc vai trò" onSubmit={applyFilters}><div className="auth-plan-filter-controls"><label htmlFor="role-query">Tìm vai trò<input id="role-query" type="search" maxLength={120} value={draftQuery} onChange={event => setDraftQuery(event.target.value)} /></label><label htmlFor="role-status">Trạng thái<select id="role-status" value={draftStatus} onChange={event => setDraftStatus(event.target.value as typeof status)}><option value="">Tất cả</option><option value="ACTIVE">Hoạt động</option><option value="INACTIVE">Ngừng hoạt động</option></select></label><button className="button button-primary" type="submit">Tìm kiếm</button></div></form>
    <form className="auth-plan-filters" onSubmit={event => void submit(event)}>
      <h2>{editing ? `Sửa ${editing.name}` : 'Tạo vai trò tùy chỉnh'}</h2>
      <div className="auth-plan-filter-controls">
        {!editing && <label>Mã vai trò<input required minLength={8} maxLength={40} pattern="CUSTOM_[A-Za-z0-9_]{2,35}" value={form.code} onChange={event => setForm(current => ({ ...current, code: event.target.value.toUpperCase() }))} placeholder="CUSTOM_CAMPAIGN_REVIEW" /></label>}
        <label>Tên<input required maxLength={100} value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} /></label>
        <label>Mô tả<input maxLength={500} value={form.description} onChange={event => setForm(current => ({ ...current, description: event.target.value }))} /></label>
      </div>
      <fieldset className="auth-role-permissions"><legend>Quyền Phase 1</legend>
        {catalog?.permission_catalog.map(permission => <label key={permission.code}><input type="checkbox" checked={form.permissions.includes(permission.code)} onChange={() => togglePermission(permission.code)} /> <span>{permission.name} <code>{permission.code}</code></span></label>)}
      </fieldset>
      <div className="button-row"><button className="button button-primary" type="submit">{editing ? 'Lưu thay đổi' : 'Tạo vai trò'}</button>{editing && <button className="button button-secondary" type="button" onClick={() => { setEditing(null); setForm(EMPTY_FORM) }}>Hủy sửa</button>}</div>
    </form>
    {loading ? <p role="status">Đang tải vai trò…</p> : <div className="auth-workflow-table-wrap"><table className="auth-workflow-table"><thead><tr><th>Vai trò</th><th>Loại</th><th>Trạng thái</th><th>Người được gán</th><th>Quyền hiệu lực</th><th>Thao tác</th></tr></thead><tbody>{(catalog?.items ?? []).map(role => <tr key={role.id}><td><strong>{role.name}</strong><br /><code>{role.code}</code></td><td>{role.is_builtin ? 'Hệ thống · cố định' : 'Tùy chỉnh'}</td><td>{role.status === 'ACTIVE' ? 'Hoạt động' : 'Ngừng hoạt động'}</td><td>{role.assigned_users}</td><td>{role.permissions.map(code => <div key={code}><code>{code}</code></div>)}</td><td>{!role.is_builtin && <div className="auth-employee-actions"><button className="button button-secondary" type="button" onClick={() => beginEdit(role)}>Sửa</button>{role.status === 'ACTIVE' && <button className="button button-secondary" type="button" disabled={role.assigned_users > 0} onClick={() => void deactivate(role)}>Ngừng hoạt động</button>}</div>}</td></tr>)}</tbody></table></div>}
  </section>
}
