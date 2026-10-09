import { ArrowLeft, Check, FileImage, RefreshCw, Send, UploadCloud } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowChecker, WorkflowPayload, WorkflowPlan } from '../types/authWorkflow'

const emptyPayload: WorkflowPayload = {
  title: '', objective: '', summary: '', department: '', start_date: '', end_date: '',
  budget_minor_units: '', currency: 'VND', target_audience: '', channels: [], kpi_expected: '', notes: '',
}

type FormField = keyof WorkflowPayload | 'checker_user_id' | 'attachment'
type FieldErrors = Partial<Record<FormField, string>>
type BusyAction = 'saving' | 'uploading' | 'submitting' | null
type WorkflowAction = Exclude<BusyAction, null> | 'loading'

const textFieldLimits: Array<[Exclude<keyof WorkflowPayload, 'channels'>, number, string]> = [
  ['title', 200, 'Tên kế hoạch'], ['objective', 2000, 'Mục tiêu'], ['summary', 10000, 'Tóm tắt'],
  ['department', 160, 'Bộ phận'], ['start_date', 10, 'Ngày bắt đầu'], ['end_date', 10, 'Ngày kết thúc'],
  ['budget_minor_units', 24, 'Ngân sách'], ['currency', 3, 'Mã tiền tệ'],
  ['target_audience', 2000, 'Đối tượng mục tiêu'], ['kpi_expected', 2000, 'KPI kỳ vọng'], ['notes', 5000, 'Ghi chú'],
]

export function AuthenticatedWorkflowFormPage() {
  const { planId } = useParams()
  const navigate = useNavigate()
  const [plan, setPlan] = useState<WorkflowPlan | null>(null)
  const [payload, setPayload] = useState<WorkflowPayload>(emptyPayload)
  const [channelsText, setChannelsText] = useState('')
  const [checkerId, setCheckerId] = useState('')
  const [checkers, setCheckers] = useState<WorkflowChecker[]>([])
  const [checkersLoading, setCheckersLoading] = useState(true)
  const [checkerError, setCheckerError] = useState<AuthApiError | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileValidationPending, setFileValidationPending] = useState(false)
  const fileValidationRequest = useRef(0)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [planError, setPlanError] = useState<AuthApiError | null>(null)
  const [apiError, setApiError] = useState<AuthApiError | null>(null)
  const [failedAction, setFailedAction] = useState<WorkflowAction>('saving')
  const [notice, setNotice] = useState('')
  const [planLoading, setPlanLoading] = useState(Boolean(planId))
  const [busyAction, setBusyAction] = useState<BusyAction>(null)
  const [revisionConflict, setRevisionConflict] = useState(false)
  const [unknownCreate, setUnknownCreate] = useState(false)

  const loadCheckers = useCallback(async () => {
    setCheckersLoading(true)
    setCheckerError(null)
    try {
      setCheckers(await authWorkflowService.listCheckers())
    } catch (reason) {
      setCheckerError(asApiError(reason, 'Không thể tải danh sách Checker.'))
    } finally {
      setCheckersLoading(false)
    }
  }, [])

  useEffect(() => { void loadCheckers() }, [loadCheckers])

  useEffect(() => {
    let active = true
    setPlan(null)
    setPayload({ ...emptyPayload, channels: [] })
    setChannelsText('')
    setCheckerId('')
    setPlanError(null)
    setApiError(null)
    setRevisionConflict(false)
    setUnknownCreate(false)
    setPlanLoading(Boolean(planId))

    if (planId) {
      authWorkflowService.getPlan(planId)
        .then(value => { if (active) applyPlan(value) })
        .catch(reason => { if (active) setPlanError(asApiError(reason, 'Không thể tải kế hoạch.')) })
        .finally(() => { if (active) setPlanLoading(false) })
    }
    return () => { active = false }
  }, [planId])

  function applyPlan(value: WorkflowPlan) {
    setPlan(value)
    setPayload({ ...value.payload, channels: [...value.payload.channels] })
    setChannelsText(value.payload.channels.join(', '))
    setCheckerId(value.checker_id ?? '')
  }

  const locked = Boolean(plan && !['DRAFT', 'REJECTED'].includes(plan.status))
  const selectedCheckerIsAvailable = Boolean(checkerId && checkers.some(checker => checker.id === checkerId))
  const hasUnsavedChanges = !plan || JSON.stringify(payload) !== JSON.stringify(plan.payload)
    || checkerId !== (plan.checker_id ?? '') || file !== null

  function update<Key extends keyof WorkflowPayload>(key: Key, value: WorkflowPayload[Key]) {
    setPayload(current => ({ ...current, [key]: value }))
    setFieldErrors(current => ({ ...current, [key]: undefined }))
    setApiError(null)
    setNotice('')
  }

  function updateChannels(value: string) {
    setChannelsText(value)
    update('channels', value.split(',').map(item => item.trim()).filter(Boolean))
  }

  function updateChecker(value: string) {
    setCheckerId(value)
    setFieldErrors(current => ({ ...current, checker_user_id: undefined }))
    setApiError(null)
    setNotice('')
  }

  async function selectFile(nextFile: File | null) {
    const requestId = ++fileValidationRequest.current
    setFile(nextFile)
    setFileValidationPending(false)
    const basicError = nextFile ? validateAttachment(nextFile) : ''
    setFieldErrors(current => ({ ...current, attachment: basicError || undefined }))
    setApiError(null)
    setNotice('')
    if (!nextFile || basicError || typeof createImageBitmap !== 'function') return

    setFileValidationPending(true)
    try {
      const bitmap = await createImageBitmap(nextFile)
      const exceedsPixelLimit = bitmap.width * bitmap.height > 25_000_000
      bitmap.close()
      if (requestId === fileValidationRequest.current && exceedsPixelLimit) {
        setFieldErrors(current => ({ ...current, attachment: 'Ảnh vượt quá giới hạn 25 megapixel của backend.' }))
      }
    } catch {
      if (requestId === fileValidationRequest.current) {
        setFieldErrors(current => ({ ...current, attachment: 'Không đọc được ảnh. Chọn một file PNG, JPEG hoặc WebP hợp lệ.' }))
      }
    } finally {
      if (requestId === fileValidationRequest.current) setFileValidationPending(false)
    }
  }

  async function save(submit: boolean) {
    if (fileValidationPending) return
    const validation = validatePayload(payload, {
      submit,
      checkerSelected: selectedCheckerIsAvailable,
      checkerLoading: checkersLoading,
      hasAttachment: Boolean(file || plan?.attachments.length),
    })
    const fileIssue = file ? validateAttachment(file) || fieldErrors.attachment || '' : ''
    if (fileIssue) validation.attachment = fileIssue
    setFieldErrors(validation)
    setApiError(null)
    setNotice('')
    setUnknownCreate(false)
    if (Object.values(validation).some(Boolean)) return

    let currentPlan = plan
    let currentAction: WorkflowAction = 'saving'
    setBusyAction('saving')
    try {
      let saved = currentPlan
        ? hasUnsavedChanges
          ? await authWorkflowService.updatePlan(currentPlan.id, payload, checkerId || null, currentPlan.revision)
          : currentPlan
        : await authWorkflowService.createPlan(payload, checkerId || null)
      currentPlan = saved
      setPlan(saved)

      if (file) {
        currentAction = 'uploading'
        setBusyAction('uploading')
        saved = await authWorkflowService.uploadAttachment(saved.id, file, saved.revision)
        currentPlan = saved
        setPlan(saved)
        setFile(null)
      }

      if (submit) {
        currentAction = 'submitting'
        setBusyAction('submitting')
        saved = await authWorkflowService.submitPlan(saved.id, saved.revision)
        currentPlan = saved
        setPlan(saved)
        navigate(`/workflow/plans/${saved.id}`, {
          state: { workflowNotice: 'Yêu cầu đã được gửi. Trạng thái bên dưới lấy từ phản hồi của máy chủ.' },
        })
      } else {
        navigate(`/workflow/plans/${saved.id}`, {
          state: { workflowNotice: 'Bản nháp đã được lưu.' },
        })
      }
    } catch (reason) {
      const failure = asApiError(reason, 'Không thể hoàn tất thao tác với kế hoạch.')
      setApiError(failure)
      setFailedAction(currentAction)
      setRevisionConflict(failure.status === 409 || failure.code === 'CONFLICT')
      setUnknownCreate(!currentPlan && currentAction === 'saving' && failure.status === 0 && failure.code === 'NETWORK_ERROR')

      if (currentPlan) {
        try {
          const latest = await authWorkflowService.getPlan(currentPlan.id)
          currentPlan = latest
          setPlan(latest)
          if (currentAction === 'submitting' && !['DRAFT', 'REJECTED'].includes(latest.status)) {
            navigate(`/workflow/plans/${latest.id}`, {
              replace: true,
              state: { workflowNotice: 'Trạng thái mới nhất đã được tải từ máy chủ sau khi kết nối bị gián đoạn.' },
            })
          }
        } catch {
          // Keep the last confirmed plan revision and all local form values visible.
        }
      }
    } finally {
      setBusyAction(null)
    }
  }

  function useLatestPlan() {
    if (!plan) return
    applyPlan(plan)
    setFieldErrors({})
    setApiError(null)
    setRevisionConflict(false)
    setNotice('Đã thay nội dung biểu mẫu bằng phiên bản mới nhất trên máy chủ.')
  }

  if (planLoading) return <p className="auth-workflow-state" role="status">Đang tải bản nháp…</p>
  if (planId && !plan) return <section className="auth-workflow-page auth-workflow-form-page">
    <Link className="auth-back-link" to="/workflow/plans"><ArrowLeft /> Quay lại danh sách</Link>
    <div className="auth-workflow-alert is-error" role="alert">
      <div><strong>{apiFailureHeading(planError, 'loading')}</strong><p>{apiFailureText(planError, 'loading')}</p>
        {planError?.correlationId && <small>Mã tham chiếu: {planError.correlationId}</small>}
      </div>
      <button className="button button-secondary" type="button" onClick={() => {
        setPlanLoading(true)
        setPlanError(null)
        authWorkflowService.getPlan(planId)
          .then(applyPlan)
          .catch(reason => setPlanError(asApiError(reason, 'Không thể tải kế hoạch.')))
          .finally(() => setPlanLoading(false))
      }}><RefreshCw /> Thử lại</button>
    </div>
  </section>

  return <section className="auth-workflow-page auth-workflow-form-page">
    <Link className="auth-back-link" to={plan ? `/workflow/plans/${plan.id}` : '/workflow/plans'}><ArrowLeft /> Quay lại</Link>
    <div className="auth-workflow-page-heading"><div><p className="page-eyebrow">Maker · PostgreSQL</p><h1>{plan ? 'Cập nhật kế hoạch' : 'Tạo kế hoạch marketing'}</h1><p>Bản nháp có thể chưa đầy đủ. Nội dung gửi đi sẽ được chụp thành version chỉ đọc.</p></div>
      <span className={`workflow-status${hasUnsavedChanges ? ' status-draft' : ''}`}>{hasUnsavedChanges ? 'Có thay đổi chưa lưu' : `Đã lưu · revision ${plan?.revision ?? '—'}`}</span>
    </div>

    {apiError && <section className="auth-workflow-alert is-error" role="alert">
      <div><strong>{apiFailureHeading(apiError, failedAction)}</strong><p>{apiFailureText(apiError, failedAction)}</p>
        {apiError.correlationId && <small>Mã tham chiếu: {apiError.correlationId}</small>}
      </div>
    </section>}
    {unknownCreate && <section className="auth-workflow-state is-error" aria-labelledby="unknown-create-title">
      <h2 id="unknown-create-title">Chưa xác định được kết quả tạo bản nháp</h2>
      <p>Kết nối đã ngắt trước khi xác nhận phản hồi. Hãy kiểm tra danh sách trước khi thử tạo lại để tránh tạo bản nháp trùng.</p>
      <div className="button-row"><Link className="button button-secondary" to="/workflow/plans" target="_blank" rel="noreferrer">Mở danh sách trong tab mới</Link>
        <button className="button button-secondary" type="button" onClick={() => setUnknownCreate(false)}>Tôi đã kiểm tra — cho phép thử lại</button></div>
    </section>}
    {notice && <div className="auth-workflow-alert is-success" role="status"><Check /><p>{notice}</p></div>}
    {locked && <div className="auth-workflow-alert is-review" role="status"><p>Kế hoạch đã gửi hoặc đã duyệt nên biểu mẫu chỉ đọc. Trạng thái hiện tại: {plan?.status}.</p></div>}
    {revisionConflict && plan && <section className="auth-workflow-state is-conflict" role="status">
      <div><h2>Máy chủ có revision mới hơn</h2><p>Các giá trị bạn đang nhập vẫn được giữ. Bản mới nhất là revision {plan.revision}, cập nhật {new Date(plan.updated_at).toLocaleString('vi-VN')}.</p>
        <p><strong>Tiêu đề đang lưu:</strong> {plan.payload.title || 'Chưa có tên'} · <strong>Checker:</strong> {plan.checker_name || 'Chưa gán'}</p></div>
      <button className="button button-secondary" type="button" onClick={useLatestPlan}>Dùng bản mới nhất</button>
    </section>}

    <form className="auth-workflow-form" noValidate onSubmit={(event: FormEvent) => { event.preventDefault(); void save(true) }}>
      <fieldset disabled={busyAction !== null || locked}>
        <div className="auth-workflow-fields">
          <label className="auth-field" htmlFor="workflow-title">Tên kế hoạch
            <input id="workflow-title" maxLength={200} value={payload.title} aria-invalid={Boolean(fieldErrors.title)} aria-describedby={fieldErrors.title ? 'workflow-title-error' : undefined} onChange={event => update('title', event.target.value)} />
            {fieldErrors.title && <span className="auth-field-error" id="workflow-title-error">{fieldErrors.title}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-checker">Người phê duyệt
            <select id="workflow-checker" value={checkerId} disabled={checkersLoading} aria-invalid={Boolean(fieldErrors.checker_user_id)} aria-describedby={fieldErrors.checker_user_id ? 'workflow-checker-error' : 'workflow-checker-help'} onChange={event => updateChecker(event.target.value)}>
              <option value="">Chưa chọn Checker</option>
              {checkerId && plan?.checker_name && !checkers.some(checker => checker.id === checkerId) && <option value={checkerId}>{plan.checker_name} (không còn khả dụng)</option>}
              {checkers.map(checker => <option key={checker.id} value={checker.id}>{checker.display_name}</option>)}
            </select>
            {fieldErrors.checker_user_id ? <span className="auth-field-error" id="workflow-checker-error">{fieldErrors.checker_user_id}</span>
              : <small id="workflow-checker-help">{checkersLoading ? 'Đang tải danh sách Checker…' : 'Danh sách lấy từ tài khoản Checker đang hoạt động.'}</small>}
          </label>
          <label className="auth-field" htmlFor="workflow-objective">Mục tiêu
            <input id="workflow-objective" maxLength={2000} value={payload.objective} aria-invalid={Boolean(fieldErrors.objective)} aria-describedby={fieldErrors.objective ? 'workflow-objective-error' : undefined} onChange={event => update('objective', event.target.value)} />
            {fieldErrors.objective && <span className="auth-field-error" id="workflow-objective-error">{fieldErrors.objective}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-department">Bộ phận
            <input id="workflow-department" maxLength={160} value={payload.department} aria-invalid={Boolean(fieldErrors.department)} aria-describedby={fieldErrors.department ? 'workflow-department-error' : undefined} onChange={event => update('department', event.target.value)} />
            {fieldErrors.department && <span className="auth-field-error" id="workflow-department-error">{fieldErrors.department}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-start-date">Ngày bắt đầu
            <input id="workflow-start-date" type="date" value={payload.start_date} aria-invalid={Boolean(fieldErrors.start_date)} aria-describedby={fieldErrors.start_date ? 'workflow-start-date-error' : undefined} onChange={event => update('start_date', event.target.value)} />
            {fieldErrors.start_date && <span className="auth-field-error" id="workflow-start-date-error">{fieldErrors.start_date}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-end-date">Ngày kết thúc
            <input id="workflow-end-date" type="date" value={payload.end_date} aria-invalid={Boolean(fieldErrors.end_date)} aria-describedby={fieldErrors.end_date ? 'workflow-end-date-error' : undefined} onChange={event => update('end_date', event.target.value)} />
            {fieldErrors.end_date && <span className="auth-field-error" id="workflow-end-date-error">{fieldErrors.end_date}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-budget">Ngân sách (đơn vị nhỏ nhất)
            <input id="workflow-budget" inputMode="numeric" maxLength={24} value={payload.budget_minor_units} aria-invalid={Boolean(fieldErrors.budget_minor_units)} aria-describedby={fieldErrors.budget_minor_units ? 'workflow-budget-error' : 'workflow-budget-help'} onChange={event => update('budget_minor_units', event.target.value)} />
            {fieldErrors.budget_minor_units ? <span className="auth-field-error" id="workflow-budget-error">{fieldErrors.budget_minor_units}</span> : <small id="workflow-budget-help">Khi gửi: nhập số nguyên dương, không có dấu phân cách. Mã tiền tệ được lưu riêng.</small>}
          </label>
          <label className="auth-field" htmlFor="workflow-currency">Mã tiền tệ
            <input id="workflow-currency" maxLength={3} value={payload.currency} aria-invalid={Boolean(fieldErrors.currency)} aria-describedby={fieldErrors.currency ? 'workflow-currency-error' : 'workflow-currency-help'} onChange={event => update('currency', event.target.value)} />
            {fieldErrors.currency ? <span className="auth-field-error" id="workflow-currency-error">{fieldErrors.currency}</span> : <small id="workflow-currency-help">Tối đa 3 ký tự, theo mã được backend chấp nhận.</small>}
          </label>
          <label className="auth-field" htmlFor="workflow-audience">Đối tượng mục tiêu
            <input id="workflow-audience" maxLength={2000} value={payload.target_audience} aria-invalid={Boolean(fieldErrors.target_audience)} aria-describedby={fieldErrors.target_audience ? 'workflow-audience-error' : undefined} onChange={event => update('target_audience', event.target.value)} />
            {fieldErrors.target_audience && <span className="auth-field-error" id="workflow-audience-error">{fieldErrors.target_audience}</span>}
          </label>
          <label className="auth-field field-wide" htmlFor="workflow-summary">Tóm tắt chiến lược
            <textarea id="workflow-summary" rows={4} maxLength={10000} value={payload.summary} aria-invalid={Boolean(fieldErrors.summary)} aria-describedby={fieldErrors.summary ? 'workflow-summary-error' : undefined} onChange={event => update('summary', event.target.value)} />
            {fieldErrors.summary && <span className="auth-field-error" id="workflow-summary-error">{fieldErrors.summary}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-kpi">KPI kỳ vọng
            <input id="workflow-kpi" maxLength={2000} value={payload.kpi_expected} aria-invalid={Boolean(fieldErrors.kpi_expected)} aria-describedby={fieldErrors.kpi_expected ? 'workflow-kpi-error' : undefined} onChange={event => update('kpi_expected', event.target.value)} />
            {fieldErrors.kpi_expected && <span className="auth-field-error" id="workflow-kpi-error">{fieldErrors.kpi_expected}</span>}
          </label>
          <label className="auth-field" htmlFor="workflow-channels">Kênh triển khai
            <input id="workflow-channels" value={channelsText} aria-invalid={Boolean(fieldErrors.channels)} aria-describedby={fieldErrors.channels ? 'workflow-channels-error' : 'workflow-channels-help'} onChange={event => updateChannels(event.target.value)} />
            {fieldErrors.channels ? <span className="auth-field-error" id="workflow-channels-error">{fieldErrors.channels}</span> : <small id="workflow-channels-help">Phân tách bằng dấu phẩy; tối đa 20 kênh.</small>}
          </label>
          <label className="auth-field field-wide" htmlFor="workflow-notes">Ghi chú
            <textarea id="workflow-notes" rows={3} maxLength={5000} value={payload.notes} aria-invalid={Boolean(fieldErrors.notes)} aria-describedby={fieldErrors.notes ? 'workflow-notes-error' : undefined} onChange={event => update('notes', event.target.value)} />
            {fieldErrors.notes && <span className="auth-field-error" id="workflow-notes-error">{fieldErrors.notes}</span>}
          </label>
        </div>
        <div className="auth-upload-row">
          <label className="button button-secondary" htmlFor="workflow-attachment"><UploadCloud /> Chọn ảnh
            <input id="workflow-attachment" aria-label="Chọn ảnh đính kèm" type="file" accept="image/png,image/jpeg,image/webp" onChange={event => { void selectFile(event.target.files?.[0] ?? null) }} />
          </label>
          <span>{file ? `${file.name} · ${Math.ceil(file.size / 1024)} KB · chờ tải lên` : `${plan?.attachments.length ?? 0} ảnh đã lưu`}</span>
          {(file || plan?.attachments.length) ? <FileImage aria-hidden="true" /> : null}
          {file && <button className="button button-quiet" type="button" onClick={() => void selectFile(null)}>Bỏ ảnh đang chọn</button>}
          {fieldErrors.attachment && <span className="auth-field-error" role="alert">{fieldErrors.attachment}</span>}
        </div>
        <p className="auth-workflow-form-hint">Ảnh hỗ trợ PNG, JPEG hoặc WebP; tối đa 5 MiB và 25 megapixel. Backend sẽ kiểm tra lại file khi tải lên.</p>
        {!file && !plan?.attachments.length && <p className="auth-workflow-form-hint">Chưa có ảnh tải lên. Gửi duyệt yêu cầu ít nhất một ảnh.</p>}
      </fieldset>

      {checkerError && <div className="auth-workflow-alert is-error" role="alert"><div><strong>Không tải được danh sách Checker</strong><p>{apiFailureText(checkerError, 'loading')}</p>{checkerError.correlationId && <small>Mã tham chiếu: {checkerError.correlationId}</small>}</div><button className="button button-secondary" type="button" onClick={() => void loadCheckers()} disabled={checkersLoading}>Thử lại</button></div>}
      {!checkersLoading && !checkerError && checkers.length === 0 && <div className="auth-workflow-alert is-review" role="status"><p>Hiện chưa có Checker khả dụng. Bạn vẫn có thể lưu bản nháp; chưa thể gửi duyệt.</p></div>}
      {fileValidationPending && <p className="auth-workflow-operation" role="status" aria-live="polite">Đang kiểm tra kích thước ảnh…</p>}
      {busyAction && <p className="auth-workflow-operation" role="status" aria-live="polite">{operationLabel(busyAction)}</p>}
      <div className="auth-workflow-form-footer"><p>Gửi duyệt sẽ lưu snapshot và chạy đánh giá theo cấu hình backend. Giao diện không ước lượng phần trăm tiến độ.</p><div className="button-row">
        <button className="button button-secondary" type="button" disabled={busyAction !== null || fileValidationPending || locked || unknownCreate} onClick={() => void save(false)}>{busyAction === 'saving' ? 'Đang lưu…' : 'Lưu bản nháp'}</button>
        <button className="button button-primary" type="submit" disabled={busyAction !== null || fileValidationPending || locked || unknownCreate || checkersLoading || checkers.length === 0}><Send /> {busyAction === 'submitting' ? 'Đang gửi và chờ phản hồi…' : busyAction === 'uploading' ? 'Đang tải ảnh lên…' : 'Gửi duyệt'}</button>
      </div></div>
    </form>
  </section>
}

function validatePayload(payload: WorkflowPayload, options: {
  submit: boolean
  checkerSelected: boolean
  checkerLoading: boolean
  hasAttachment: boolean
}): FieldErrors {
  const errors: FieldErrors = {}
  for (const [field, maximum, label] of textFieldLimits) {
    if (payload[field].length > maximum) errors[field] = `${label} không được vượt quá ${maximum} ký tự.`
  }
  if (payload.channels.length > 20) errors.channels = 'Chỉ được gửi tối đa 20 kênh.'
  if (!options.submit) return errors

  for (const [field, label] of [['title', 'Tên kế hoạch'], ['objective', 'Mục tiêu'], ['summary', 'Tóm tắt chiến lược']] as const) {
    if (!payload[field].trim()) errors[field] = `${label} là bắt buộc khi gửi duyệt.`
  }
  if (!payload.start_date) errors.start_date = 'Chọn ngày bắt đầu trước khi gửi.'
  else if (!isCalendarDate(payload.start_date)) errors.start_date = 'Ngày bắt đầu phải là ngày ISO hợp lệ.'
  if (!payload.end_date) errors.end_date = 'Chọn ngày kết thúc trước khi gửi.'
  else if (!isCalendarDate(payload.end_date)) errors.end_date = 'Ngày kết thúc phải là ngày ISO hợp lệ.'
  if (isCalendarDate(payload.start_date) && isCalendarDate(payload.end_date) && payload.end_date < payload.start_date) {
    errors.end_date = 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.'
  }
  if (!/^[1-9][0-9]{0,23}$/.test(payload.budget_minor_units)) {
    errors.budget_minor_units = 'Ngân sách phải là số nguyên dương, tối đa 24 chữ số.'
  }
  if (options.checkerLoading) errors.checker_user_id = 'Đợi tải danh sách Checker hoàn tất rồi gửi lại.'
  else if (!options.checkerSelected) errors.checker_user_id = 'Chọn Checker đang hoạt động trước khi gửi.'
  if (!options.hasAttachment) errors.attachment = 'Thêm ít nhất một ảnh PNG, JPEG hoặc WebP trước khi gửi.'
  return errors
}

function isCalendarDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return false
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  if (year < 1) return false
  const date = new Date(0)
  date.setUTCFullYear(year, month - 1, day)
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

function validateAttachment(file: File) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) return 'Chỉ hỗ trợ ảnh PNG, JPEG hoặc WebP.'
  if (file.size > 5 * 1024 * 1024) return 'Ảnh vượt quá giới hạn 5 MiB của backend.'
  return ''
}

function asApiError(reason: unknown, fallback: string) {
  return reason instanceof AuthApiError ? reason
    : new AuthApiError(0, reason instanceof Error ? reason.message : fallback, 'CLIENT_ERROR')
}

function apiFailureHeading(error: AuthApiError | null, action: WorkflowAction) {
  if (error?.status === 404) return 'Không tìm thấy kế hoạch'
  if (error?.status === 409 || error?.code === 'CONFLICT') return 'Kế hoạch đã thay đổi trên máy chủ'
  if (error?.status === 422 || error?.code === 'VALIDATION_ERROR') return 'Dữ liệu chưa được chấp nhận'
  if (error?.status === 401) return 'Phiên đăng nhập đã hết hạn'
  if (error?.status === 403) return 'Không có quyền thực hiện thao tác này'
  if (error?.status === 0 && error.code === 'NETWORK_ERROR') return action === 'loading' ? 'Không thể kết nối workflow' : 'Không nhận được xác nhận từ máy chủ'
  return 'Không thể hoàn tất yêu cầu'
}

function apiFailureText(error: AuthApiError | null, action: WorkflowAction) {
  if (error?.status === 404) return 'Kế hoạch không còn tồn tại hoặc không thuộc phạm vi tài khoản hiện tại.'
  if (error?.status === 409 || error?.code === 'CONFLICT') return `${error.message} Các giá trị bạn đang nhập vẫn được giữ; hãy kiểm tra revision mới nhất trước khi lưu lại.`
  if (error?.status === 422 || error?.code === 'VALIDATION_ERROR') return error.message
  if (error?.status === 401) return 'Hãy đăng nhập lại để tiếp tục. Biểu mẫu không xóa các giá trị đang nhập.'
  if (error?.status === 403) return 'Quyền truy cập đã bị từ chối. Không thể tiếp tục thao tác với kế hoạch này.'
  if (error?.status === 0 && error.code === 'NETWORK_ERROR') return action === 'loading'
    ? 'Kiểm tra kết nối rồi thử tải lại.'
    : 'Dữ liệu hiện tại vẫn được giữ. Hãy tải lại trạng thái trước khi lặp lại thao tác.'
  if (error?.status === 0) return error.message
  if (error && error.status >= 500) return 'Dịch vụ workflow chưa hoàn tất yêu cầu. Dữ liệu trong biểu mẫu vẫn được giữ.'
  return error?.message || 'Thử lại sau khi kiểm tra các trường trong biểu mẫu.'
}

function operationLabel(action: Exclude<BusyAction, null>) {
  return ({
    saving: 'Đang lưu nội dung kế hoạch…',
    uploading: 'Đang tải ảnh lên…',
    submitting: 'Đang gửi kế hoạch và chờ máy chủ phản hồi…',
  })[action]
}
