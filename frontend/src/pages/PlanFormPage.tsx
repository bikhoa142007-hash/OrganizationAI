import { ArrowLeft, CalendarDays, Check, FileImage, Info, Save, Send, Trash2, UploadCloud } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PageHeader, StatePanel } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import { useSession } from '../services/SessionProvider'
import { ApiError } from '../services/api/client'
import type { PlanView } from '../types'

type FormValues = typeof empty
type FormErrors = Partial<Record<keyof FormValues | 'attachment' | 'form', string>>

const empty = {
  title: '', objective: '', summary: '', department: '', checker_id: '', start_date: '', end_date: '',
  budget_minor_units: '', currency: 'VND', target_audience: '', channels: '', kpi_expected: '', notes: '',
}
const placeholders = new Set(['test', 'tbd', 'todo', 'n/a', 'na', 'null', 'undefined', 'placeholder', 'lorem ipsum', 'abc', 'asdf', 'xxx', '123', 'đang cập nhật'])

export function PlanFormPage() {
  const { planId } = useParams()
  const id = useRef(planId ?? `DEMO-${crypto.randomUUID()}`)
  const services = useServices()
  const { config, hasRole } = useSession()
  const navigate = useNavigate()
  const [values, setValues] = useState<FormValues>(empty)
  const [plan, setPlan] = useState<PlanView | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(Boolean(planId))
  const [errors, setErrors] = useState<FormErrors>({})
  const [notice, setNotice] = useState('')
  const [failedLoad, setFailedLoad] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (planId) {
      services.plan.getPlan(planId).then(value => {
        if (cancelled) return
        if (!value) { setFailedLoad(true); setErrors({ form: 'Không tìm thấy kế hoạch.' }); setLoading(false); return }
        setPlan(value)
        setValues(toFormValues(value))
        setLoading(false)
      }).catch(reason => { if (!cancelled) { setErrors({ form: reason instanceof Error ? reason.message : String(reason) }); setLoading(false); setFailedLoad(true) } })
    } else {
      setValues(current => ({ ...current, checker_id: config?.checkerId ?? current.checker_id, department: config?.department ?? current.department, currency: config?.currency ?? current.currency }))
    }
    return () => { cancelled = true }
  }, [config?.checkerId, config?.currency, config?.department, planId, services.plan])

  const previewUrl = useMemo(() => file ? URL.createObjectURL(file) : '', [file])
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])
  const locked = Boolean(plan && (!['DRAFT', 'REJECTED'].includes(plan.state?.planStatus ?? '') || plan.makerId !== config?.actor))
  const allowedMediaTypes = config?.allowedMediaTypes ?? []
  const maxAttachmentBytes = config?.maxAttachmentBytes ?? 0

  function update(key: keyof FormValues, value: string) {
    setValues(current => ({ ...current, [key]: value }))
    setErrors(current => ({ ...current, [key]: undefined, form: undefined }))
  }

  function validate(submit: boolean) {
    const next: FormErrors = {}
    const required: Array<keyof FormValues> = ['title', 'objective', 'summary', 'department', 'checker_id', 'start_date', 'end_date', 'budget_minor_units', 'currency']
    if (submit) for (const key of required) if (!values[key].trim()) next[key] = 'Trường này bắt buộc khi gửi duyệt.'
    const validBudget = /^(0|[1-9][0-9]*)$/.test(values.budget_minor_units)
    if (values.budget_minor_units && !validBudget) next.budget_minor_units = 'Nhập số nguyên VND, không dùng dấu phân cách.'
    if (submit && validBudget && BigInt(values.budget_minor_units) <= 0n) next.budget_minor_units = 'Ngân sách phải lớn hơn 0 khi gửi duyệt.'
    if (submit && [values.title, values.objective, values.summary].some(text => text.trim() && (placeholders.has(text.trim().replace(/\s+/g, ' ').toLowerCase()) || !/\p{L}/u.test(text)))) next.form = 'Nhập tên, mục tiêu và chiến lược cụ thể; không dùng nội dung mẫu.'
    if (values.start_date && values.end_date && values.start_date > values.end_date) next.end_date = 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.'
    if (submit && !file && !plan?.attachments?.length) next.attachment = 'Cần ít nhất một ảnh hợp lệ trước khi gửi duyệt.'
    if (file && !allowedMediaTypes.includes(file.type)) next.attachment = `Định dạng không được policy cho phép: ${file.type || 'không xác định'}.`
    if (file && maxAttachmentBytes > 0 && file.size > maxAttachmentBytes) next.attachment = `Dung lượng tối đa là ${Math.round(maxAttachmentBytes / 1_000_000)} MB theo policy hiện tại.`
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function save(submit: boolean) {
    setNotice('')
    if (!validate(submit)) return
    setBusy(true)
    try {
      const payload = {
        ...values,
        channels: values.channels.trim() ? values.channels.split(',').map(value => value.trim()).filter(Boolean) : [],
      }
      let saved = await services.plan.saveDraft(id.current, payload, { expectedRevision: plan?.revision ?? 0 })
      if (!saved) throw new Error('Backend không trả draft sau khi lưu.')
      setPlan(saved)
      if (file) {
        await services.plan.uploadAttachment(id.current, file, { expectedRevision: saved.revision })
        setFile(null)
        saved = await services.plan.getPlan(id.current)
        if (!saved) throw new Error('Không đọc được draft sau khi upload.')
        setPlan(saved)
      }
      if (submit) {
        await services.plan.submitPlan(id.current, { expectedRevision: saved.revision })
        navigate(`/plans/${id.current}/result`)
      } else {
        setNotice('Draft đã được lưu trên backend.')
        navigate(`/plans/${id.current}/edit`, { replace: true })
      }
    } catch (reason) {
      const message = reason instanceof ApiError ? `${reason.code}: ${reason.message}${reason.correlationId ? ` · Correlation ${reason.correlationId}` : ''}` : reason instanceof Error ? reason.message : String(reason)
      setErrors({ form: message })
      try { const current = await services.plan.getPlan(id.current); if (current) setPlan(current) } catch { /* Keep the original error visible. */ }
    } finally { setBusy(false) }
  }

  const onSubmit = (event: FormEvent) => { event.preventDefault(); void save(true) }
  if (loading) return <StatePanel kind="loading" title="Đang tải bản nháp" description="Đang lấy revision và dữ liệu hiện tại từ backend." />
  if (!hasRole('MAKER')) return <StatePanel kind="error" title="Bạn không có quyền tạo kế hoạch" description="Role hiện tại không có quyền Maker. Backend vẫn là nơi kiểm tra quyền cuối cùng." />

  return <section className="form-page">
    <PageHeader eyebrow={planId ? 'Chỉnh sửa hồ sơ' : 'Hồ sơ mới'} title={planId ? 'Cập nhật kế hoạch marketing' : 'Tạo kế hoạch marketing'} description="Có thể lưu bản nháp chưa đầy đủ. Những trường đánh dấu bắt buộc phải hợp lệ khi gửi duyệt." actions={<Link className="button button-secondary" to="/plans"><ArrowLeft /> Danh sách</Link>} />

    {errors.form && <div className="alert alert-error" role="alert"><Info /><div><strong>Không thể hoàn tất yêu cầu</strong><p>{errors.form}</p></div></div>}
    {notice && <div className="alert alert-success" role="status"><Check /><div><strong>Đã lưu</strong><p>{notice}</p></div></div>}
    {locked && <div className="alert alert-warning"><Info /><div><strong>Nội dung đã khóa</strong><p>Hồ sơ đã được gửi. <Link to={`/plans/${id.current}`}>Mở chi tiết và lịch sử</Link>.</p></div></div>}

    <form className="plan-form" onSubmit={onSubmit} noValidate>
      <section className="form-section">
        <div className="form-section-heading"><span>01</span><div><h3>Thông tin chiến dịch</h3><p>Nội dung chính được lưu vào snapshot khi gửi duyệt.</p></div></div>
        <fieldset disabled={busy || locked || failedLoad}>
          <div className="field-grid">
            <TextField label="Tên chiến dịch" name="title" value={values.title} error={errors.title} required onChange={update} />
            <TextField label="Mục tiêu" name="objective" value={values.objective} error={errors.objective} required onChange={update} />
            <TextField label="Đối tượng mục tiêu" name="target_audience" value={values.target_audience} error={errors.target_audience} onChange={update} placeholder="Tùy chọn" />
            <TextField label="Kênh truyền thông" name="channels" value={values.channels} error={errors.channels} onChange={update} placeholder="Ví dụ: Facebook, Website" helper="Phân tách nhiều kênh bằng dấu phẩy." />
            <TextField label="KPI kỳ vọng" name="kpi_expected" value={values.kpi_expected} error={errors.kpi_expected} onChange={update} placeholder="Tùy chọn" />
            <TextField label="Phòng ban" name="department" value={values.department} error={errors.department} required readOnly onChange={update} helper="Do backend cấu hình cho phiên hiện tại." />
          </div>
          <TextArea label="Tóm tắt / chiến lược" name="summary" value={values.summary} error={errors.summary} required onChange={update} helper="Mô tả cách thực hiện, thông điệp chính và các giả định quan trọng." />
          <TextArea label="Ghi chú bổ sung" name="notes" value={values.notes} error={errors.notes} onChange={update} rows={3} />
        </fieldset>
      </section>

      <section className="form-section">
        <div className="form-section-heading"><span>02</span><div><h3>Thời gian và ngân sách</h3><p>Budget engine sử dụng giá trị số do backend nhận được.</p></div></div>
        <fieldset disabled={busy || locked || failedLoad}>
          <div className="field-grid">
            <TextField label="Ngày bắt đầu" name="start_date" type="date" value={values.start_date} error={errors.start_date} required icon={<CalendarDays />} onChange={update} />
            <TextField label="Ngày kết thúc" name="end_date" type="date" value={values.end_date} error={errors.end_date} required icon={<CalendarDays />} onChange={update} />
            <TextField label="Ngân sách (VND)" name="budget_minor_units" inputMode="numeric" value={values.budget_minor_units} error={errors.budget_minor_units} required onChange={update} helper="Nhập số nguyên, không dùng dấu phân cách." />
            <TextField label="Tiền tệ" name="currency" value={values.currency} error={errors.currency} required readOnly onChange={update} />
            <TextField label="Checker được giao" name="checker_id" value={values.checker_id} error={errors.checker_id} required readOnly onChange={update} helper="Được backend chỉ định cho demo hiện tại." />
          </div>
        </fieldset>
      </section>

      <section className="form-section">
        <div className="form-section-heading"><span>03</span><div><h3>Ảnh đính kèm</h3><p>{allowedMediaTypes.join(', ') || 'Định dạng do backend cấu hình'}, tối đa {maxAttachmentBytes ? `${Math.round(maxAttachmentBytes / 1_000_000)} MB` : 'theo policy backend'}. File chỉ được đọc qua endpoint có kiểm tra quyền.</p></div></div>
        <fieldset disabled={busy || locked || failedLoad}>
          <div className={`upload-zone ${errors.attachment ? 'field-invalid' : ''}`}>
            <input id="attachment" className="visually-hidden" aria-label="Ảnh đính kèm" type="file" accept={allowedMediaTypes.join(',')} onChange={event => { setFile(event.target.files?.[0] ?? null); setErrors(current => ({ ...current, attachment: undefined })) }} />
            {file && previewUrl ? <div className="upload-preview"><img src={previewUrl} alt="Xem trước ảnh đã chọn" /><div><FileImage /><strong>{file.name}</strong><span>{Math.ceil(file.size / 1024)} KB · Chưa upload</span><button className="text-button danger" type="button" onClick={() => setFile(null)}><Trash2 /> Bỏ ảnh</button></div></div> : <label className="upload-prompt" htmlFor="attachment"><UploadCloud /><strong>Chọn ảnh để tải lên</strong><span>File sẽ được upload khi bạn lưu draft hoặc gửi duyệt.</span><span className="button button-secondary">Chọn tệp</span></label>}
          </div>
          {errors.attachment && <p className="field-error">{errors.attachment}</p>}
          <div className="attachment-summary"><FileImage /><span><strong>{plan?.attachments?.length ?? 0}</strong> ảnh đã lưu trên backend</span></div>
        </fieldset>
      </section>

      <div className="form-footer">
        <div><Info /><span>Khi gửi duyệt, backend tạo version và round bất biến rồi chạy evaluation.</span></div>
        <div className="button-row"><button type="button" className="button button-secondary" disabled={busy || locked || failedLoad} onClick={() => void save(false)}><Save /> {busy ? 'Đang lưu...' : 'Lưu draft'}</button><button className="button button-primary" type="submit" disabled={busy || locked || failedLoad}><Send /> {busy ? 'Đang xử lý...' : 'Gửi duyệt'}</button></div>
      </div>
    </form>
  </section>
}

function TextField({ label, name, value, error, required, helper, readOnly, placeholder, type = 'text', inputMode, icon, onChange }: { label: string; name: keyof FormValues; value: string; error?: string; required?: boolean; helper?: string; readOnly?: boolean; placeholder?: string; type?: string; inputMode?: 'numeric'; icon?: React.ReactNode; onChange: (key: keyof FormValues, value: string) => void }) {
  return <label className={`field ${error ? 'field-invalid' : ''}`} htmlFor={name}><span>{label}{required && <em> *</em>}</span><div className="input-wrap">{icon}{<input id={name} name={name} type={type} inputMode={inputMode} value={value} readOnly={readOnly} placeholder={placeholder} aria-invalid={Boolean(error)} aria-describedby={`${name}-help`} onChange={event => onChange(name, event.target.value)} />}</div><small id={`${name}-help`} className={error ? 'field-error' : ''}>{error || helper || (required ? 'Bắt buộc khi gửi duyệt.' : 'Tùy chọn.')}</small></label>
}

function TextArea({ label, name, value, error, required, helper, rows = 5, onChange }: { label: string; name: keyof FormValues; value: string; error?: string; required?: boolean; helper?: string; rows?: number; onChange: (key: keyof FormValues, value: string) => void }) {
  return <label className={`field field-full ${error ? 'field-invalid' : ''}`} htmlFor={name}><span>{label}{required && <em> *</em>}</span><textarea id={name} name={name} rows={rows} value={value} aria-invalid={Boolean(error)} aria-describedby={`${name}-help`} onChange={event => onChange(name, event.target.value)} /><small id={`${name}-help`} className={error ? 'field-error' : ''}>{error || helper || (required ? 'Bắt buộc khi gửi duyệt.' : 'Tùy chọn.')}</small></label>
}

function toFormValues(plan: PlanView): FormValues {
  const payload = plan.payload ?? {}
  const value = (key: keyof FormValues) => {
    const raw = payload[key]
    if (Array.isArray(raw)) return raw.join(', ')
    return raw == null ? empty[key] : String(raw)
  }
  return Object.fromEntries(Object.keys(empty).map(key => [key, value(key as keyof FormValues)])) as FormValues
}
