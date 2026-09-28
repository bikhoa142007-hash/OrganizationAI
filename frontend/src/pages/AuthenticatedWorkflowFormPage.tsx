import { ArrowLeft, Check, FileImage, Send, UploadCloud } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowChecker, WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'

const emptyPayload: WorkflowPayload = {
  title: '', objective: '', summary: '', department: '', start_date: '', end_date: '',
  budget_minor_units: '', currency: 'VND', target_audience: '', channels: [], kpi_expected: '', notes: '',
}

export function AuthenticatedWorkflowFormPage() {
  const { planId } = useParams()
  const navigate = useNavigate()
  const [plan, setPlan] = useState<WorkflowPlan | null>(null)
  const [payload, setPayload] = useState<WorkflowPayload>(emptyPayload)
  const [checkerId, setCheckerId] = useState('')
  const [checkers, setCheckers] = useState<WorkflowChecker[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(Boolean(planId))
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    const requests: [Promise<WorkflowChecker[]>, Promise<WorkflowPlan | null>] = [
      authWorkflowService.listCheckers(),
      planId ? authWorkflowService.getPlan(planId) : Promise.resolve(null),
    ]
    Promise.all(requests).then(([available, existing]) => {
      if (!active) return
      setCheckers(available)
      if (existing) {
        setPlan(existing)
        setPayload(existing.payload)
        setCheckerId(existing.checker_id ?? '')
      }
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [planId])

  const locked = Boolean(plan && !['DRAFT', 'REJECTED'].includes(plan.status))
  function update<Key extends keyof WorkflowPayload>(key: Key, value: WorkflowPayload[Key]) {
    setPayload(current => ({ ...current, [key]: value }))
    setError('')
  }

  async function save(submit: boolean) {
    setError(''); setNotice('')
    if (submit) {
      const required: Array<keyof WorkflowPayload> = ['title', 'objective', 'summary', 'start_date', 'end_date', 'budget_minor_units']
      if (required.some(key => !String(payload[key]).trim())) return setError('Điền tên, mục tiêu, tóm tắt, thời gian và ngân sách trước khi gửi.')
      if (!checkerId) return setError('Chọn Checker đang hoạt động trước khi gửi.')
      if (!file && !plan?.attachments.length) return setError('Thêm ít nhất một ảnh PNG, JPEG hoặc WebP trước khi gửi.')
    }
    if (file && !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) return setError('Chỉ hỗ trợ ảnh PNG, JPEG hoặc WebP.')
    if (file && file.size > 5 * 1024 * 1024) return setError('Dung lượng ảnh tối đa là 5 MB.')

    setBusy(true)
    try {
      let saved = plan
        ? await authWorkflowService.updatePlan(plan.id, payload, checkerId || null, plan.revision)
        : await authWorkflowService.createPlan(payload, checkerId || null)
      setPlan(saved)
      if (file) {
        saved = await authWorkflowService.uploadAttachment(saved.id, file, saved.revision)
        setFile(null); setPlan(saved)
      }
      if (submit) {
        saved = await authWorkflowService.submitPlan(saved.id, saved.revision)
        navigate(`/workflow/plans/${saved.id}`)
      } else {
        setNotice('Bản nháp đã được lưu trong PostgreSQL.')
        navigate(`/workflow/plans/${saved.id}`)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      if (plan) authWorkflowService.getPlan(plan.id).then(setPlan).catch(() => undefined)
    } finally { setBusy(false) }
  }

  if (loading) return <p className="auth-workflow-state" role="status">Đang tải bản nháp…</p>
  if (planId && !plan) return <section className="auth-workflow-page auth-workflow-form-page">
    <Link className="auth-back-link" to="/workflow/plans"><ArrowLeft /> Quay lại danh sách</Link>
    <div className="auth-workflow-alert is-error" role="alert"><strong>Không thể tải kế hoạch</strong><p>{error || 'Không tìm thấy kế hoạch hoặc bạn không có quyền truy cập.'}</p></div>
  </section>
  return <section className="auth-workflow-page auth-workflow-form-page">
    <Link className="auth-back-link" to={plan ? `/workflow/plans/${plan.id}` : '/workflow/plans'}><ArrowLeft /> Quay lại</Link>
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">Maker · PostgreSQL</p><h1>{plan ? 'Cập nhật kế hoạch' : 'Tạo kế hoạch marketing'}</h1><p>Bản nháp có thể chưa đầy đủ. Nội dung gửi đi sẽ được chụp thành version chỉ đọc.</p></div></div>
    {error && <div className="auth-workflow-alert is-error" role="alert"><strong>Không thể lưu workflow</strong><p>{error}</p></div>}
    {notice && <div className="auth-workflow-alert is-success" role="status"><Check /><p>{notice}</p></div>}
    {locked && <div className="auth-workflow-alert is-error" role="alert"><p>Hồ sơ đã gửi hoặc đã duyệt và không còn chỉnh sửa được.</p></div>}
    <form className="auth-workflow-form" onSubmit={(event: FormEvent) => { event.preventDefault(); void save(true) }}>
      <fieldset disabled={busy || locked}>
        <div className="auth-workflow-fields">
          <label className="auth-field">Tên kế hoạch<input required value={payload.title} onChange={event => update('title', event.target.value)} /></label>
          <label className="auth-field">Người phê duyệt<select value={checkerId} onChange={event => setCheckerId(event.target.value)}><option value="">Chưa chọn Checker</option>{checkers.map(checker => <option key={checker.id} value={checker.id}>{checker.display_name}</option>)}</select><small>Danh sách này do backend lấy từ các tài khoản có role CHECKER.</small></label>
          <label className="auth-field">Mục tiêu<input value={payload.objective} onChange={event => update('objective', event.target.value)} /></label>
          <label className="auth-field">Bộ phận<input value={payload.department} onChange={event => update('department', event.target.value)} /></label>
          <label className="auth-field">Ngày bắt đầu<input type="date" value={payload.start_date} onChange={event => update('start_date', event.target.value)} /></label>
          <label className="auth-field">Ngày kết thúc<input type="date" value={payload.end_date} onChange={event => update('end_date', event.target.value)} /></label>
          <label className="auth-field">Ngân sách (VND)<input inputMode="numeric" value={payload.budget_minor_units} onChange={event => update('budget_minor_units', event.target.value)} /><small>Nhập số nguyên dương, không dùng dấu phân cách.</small></label>
          <label className="auth-field">Đối tượng mục tiêu<input value={payload.target_audience} onChange={event => update('target_audience', event.target.value)} /></label>
          <label className="auth-field field-wide">Tóm tắt chiến lược<textarea rows={4} value={payload.summary} onChange={event => update('summary', event.target.value)} /></label>
          <label className="auth-field">KPI kỳ vọng<input value={payload.kpi_expected} onChange={event => update('kpi_expected', event.target.value)} /></label>
          <label className="auth-field">Kênh triển khai<input value={payload.channels.join(', ')} onChange={event => update('channels', event.target.value.split(',').map(item => item.trim()).filter(Boolean))} /></label>
          <label className="auth-field field-wide">Ghi chú<textarea rows={3} value={payload.notes} onChange={event => update('notes', event.target.value)} /></label>
        </div>
        <div className="auth-upload-row"><label className="button button-secondary"><UploadCloud /> Chọn ảnh<input aria-label="Chọn ảnh đính kèm" type="file" accept="image/png,image/jpeg,image/webp" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label><span>{file ? `${file.name} · ${Math.ceil(file.size / 1024)} KB` : `${plan?.attachments.length ?? 0} ảnh đã lưu`}</span>{(file || plan?.attachments.length) && <FileImage />}</div>
      </fieldset>
      <div className="auth-workflow-form-footer"><p>Submit sẽ tạo version/round và chuyển hồ sơ cho Checker được gán.</p><div className="button-row"><button className="button button-secondary" type="button" disabled={busy || locked} onClick={() => void save(false)}>{busy ? 'Đang lưu…' : 'Lưu bản nháp'}</button><button className="button button-primary" type="submit" disabled={busy || locked}><Send /> {busy ? 'Đang gửi…' : 'Gửi duyệt'}</button></div></div>
    </form>
  </section>
}
