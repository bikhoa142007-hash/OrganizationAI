import { useActor } from '../components/DemoActor'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'
import { api, ApiError } from '../services/api/client'
import type { PlanView } from '../types'

const empty = { title: '', objective: '', summary: '', department: '', checker_id: '', start_date: '', end_date: '', budget_minor_units: '', currency: 'VND', target_audience: '', kpi_expected: '', notes: '' }
const fields = [
  ['title', 'Tên chiến dịch', 'text', true], ['objective', 'Mục tiêu', 'text', true],
  ['department', 'Phòng ban', 'text', true], ['checker_id', 'Checker được giao', 'text', true],
  ['start_date', 'Ngày bắt đầu', 'date', true], ['end_date', 'Ngày kết thúc', 'date', true],
  ['budget_minor_units', 'Ngân sách (VND)', 'text', true], ['target_audience', 'Đối tượng', 'text', false],
  ['kpi_expected', 'KPI', 'text', false],
] as const

const help: Record<string, string> = {
  title: 'Ví dụ: Chiến dịch giới thiệu sản phẩm tháng 10.',
  objective: 'Nêu kết quả muốn đạt, ví dụ: thu hút 1.200 đăng ký tư vấn.',
  department: 'Phòng ban tổng hợp được backend cấu hình cho demo.',
  checker_id: 'Backend phân công theo phòng ban; người lập không được tự duyệt.',
  start_date: 'Ngày bắt đầu chiến dịch (YYYY-MM-DD).',
  end_date: 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.',
  budget_minor_units: 'Số nguyên VND lớn hơn 0; ví dụ 50000000 = 50 triệu đồng. Không nhập dấu chấm/phẩy.',
  target_audience: 'Không bắt buộc. Mô tả nhóm khách hàng cần tiếp cận.',
  kpi_expected: 'Không bắt buộc. Nêu chỉ số, số lượng và thời hạn dự kiến.',
}
const placeholders = new Set(['test', 'tbd', 'todo', 'n/a', 'na', 'null', 'undefined', 'placeholder', 'lorem ipsum', 'abc', 'asdf', 'xxx', '123', 'đang cập nhật'])

export function PlanFormPage() {
  const actor = useActor()
  const { planId } = useParams()
  const id = useRef(planId ?? `DEMO-${crypto.randomUUID()}`)
  const services = useServices(), navigate = useNavigate()
  const [values, setValues] = useState(empty), [plan, setPlan] = useState<PlanView | null>(null)
  const [file, setFile] = useState<File | null>(null), [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(Boolean(planId)), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [failedLoad, setFailedLoad] = useState(false)
  useEffect(() => {
    let cancelled = false
    if (planId) services.plan.getPlan(planId).then(p => { if (!cancelled && p) { setPlan(p); setValues(Object.fromEntries(Object.keys(empty).map(k => [k, String(p.payload?.[k] ?? empty[k as keyof typeof empty])])) as typeof empty); setLoading(false) } }).catch(e => { if (!cancelled) { setError(String(e)); setLoading(false); setFailedLoad(true) } })
    else api.request<{ checker_id: string; department: string }>('/config').then(c => { if (!cancelled) setValues(v => ({ ...v, checker_id: c.checker_id, department: c.department })) }).catch(e => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [planId, services.plan])
  const locked = Boolean(plan && (!['DRAFT', 'REJECTED'].includes(plan.state?.planStatus ?? '') || plan.payload?.maker_id !== actor?.actor))

  async function save(submit: boolean) {
    setError(''); setNotice('')
    if (submit && (fields.some(([key, , , required]) => required && !values[key].trim()) || !values.summary.trim())) { setError('Điền đủ các trường bắt buộc trước khi gửi duyệt.'); return }
    if (values.budget_minor_units && !/^[1-9][0-9]*$/.test(values.budget_minor_units)) { setError('Ngân sách phải là số nguyên VND lớn hơn 0, không có dấu phân cách.'); return }
    if (submit && [values.title, values.objective, values.summary].some(text => placeholders.has(text.trim().replace(/\s+/g, ' ').toLowerCase()) || !/\p{L}/u.test(text))) { setError('Nhập tên, mục tiêu và chiến lược cụ thể; không dùng test, TBD hoặc nội dung mẫu.'); return }
    if (values.start_date && values.end_date && values.end_date < values.start_date) { setError('Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.'); return }
    if (submit && !file && !plan?.attachments?.length) { setError('Cần ít nhất một ảnh đính kèm.'); return }
    if (file && (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5_000_000)) { setError('Chỉ nhận PNG/JPEG/WebP tối đa 5 MB.'); return }
    setBusy(true)
    try {
      let saved = await services.plan.saveDraft(id.current, { ...values, ...(plan?.payload?.channels ? { channels: plan.payload.channels } : {}) }, { expectedRevision: plan?.revision ?? 0 })
      if (!saved) throw new Error('Backend không trả draft.')
      setPlan(saved)
      if (file) {
        await services.plan.uploadAttachment(id.current, file, { expectedRevision: saved.revision })
        setFile(null)
        saved = await services.plan.getPlan(id.current)
        setPlan(saved)
      }
      if (submit) {
        await services.plan.submitPlan(id.current, { expectedRevision: saved?.revision })
        navigate(`/plans/${id.current}/result`)
      } else { setNotice('Đã lưu draft.'); navigate(`/plans/${id.current}/edit`, { replace: true }) }
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e))
      // Reconcile a possibly committed submit before allowing another edit.
      try { const current = await services.plan.getPlan(id.current); if (current) setPlan(current) } catch { /* Original error remains visible. */ }
    } finally { setBusy(false) }
  }
  const onSubmit = (event: FormEvent) => { event.preventDefault(); void save(true) }
  if (loading) return <p role="status">Đang tải draft…</p>
  return <section className="form-page"><div className="form-page-header"><div><Link to="/plans">← Danh sách hồ sơ</Link><h2>{planId ? 'Sửa kế hoạch marketing' : 'Gửi kế hoạch marketing'}</h2><p>Draft có thể chưa đầy đủ. Các trường * bắt buộc khi gửi duyệt. Gửi duyệt khóa phiên bản và chuyển đánh giá AI; Checker quyết định cuối cùng.</p></div><span className="form-mode-label">Demo · Backend API</span></div>
    {error && <p role="alert" className="form-error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {locked && <p>Hồ sơ đã khóa. <Link to={`/plans/${id.current}`}>Xem chi tiết và tiếp tục xử lý</Link></p>}
    <form className="plan-form" onSubmit={onSubmit} noValidate><fieldset disabled={busy || locked || failedLoad}><legend>Thông tin kế hoạch</legend><div className="field-grid">
      {fields.map(([key, label, type, required]) => <div className="field" key={key}><label htmlFor={key}><span>{label}{required ? ' *' : ' (không bắt buộc)'}</span></label><input id={key} type={type} value={values[key]} onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))} readOnly={key === 'checker_id' || key === 'department'} aria-required={required} aria-describedby={`${key}-help`} /><small id={`${key}-help`}>{help[key]}</small></div>)}
    </div><label className="field field-full" htmlFor="summary"><span>Tóm tắt / chiến lược *</span><textarea id="summary" rows={5} aria-required="true" aria-describedby="summary-help" value={values.summary} onChange={e => setValues(v => ({ ...v, summary: e.target.value }))} /><small id="summary-help">Nêu hoạt động, kênh triển khai, nguồn lực và cách đo kết quả.</small></label></fieldset>
    <fieldset disabled={busy || locked || failedLoad}><legend>Ảnh đính kèm *</legend><p>Ít nhất một ảnh khi gửi duyệt. PNG/JPEG/WebP, tối đa 5 MB mỗi ảnh.</p><input aria-label="Ảnh đính kèm" type="file" accept="image/png,image/jpeg,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)} />{file && <p>{file.name} · Chưa upload</p>}<p>{plan?.attachments?.length ?? 0} ảnh đã lưu trên backend</p></fieldset>
    <div className="form-actions"><Link className="button button-secondary" to="/plans">Danh sách</Link><button type="button" className="button button-secondary" disabled={busy || locked || failedLoad} onClick={() => void save(false)}>Lưu draft</button><button className="button button-primary" type="submit" disabled={busy || locked || failedLoad}>{busy ? 'Đang lưu / đánh giá…' : 'Gửi duyệt'}</button></div></form></section>
}
