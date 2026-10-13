import { Clock3, RefreshCw, Save } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { SlaConfiguration, SlaConfigurationHistory } from '../types/authWorkflow'

const HISTORY_PAGE_SIZE = 25

type Parts = { hours: string; minutes: string }

export function AuthenticatedSlaPage() {
  const [configuration, setConfiguration] = useState<SlaConfiguration | null>(null)
  const [history, setHistory] = useState<SlaConfigurationHistory | null>(null)
  const [duration, setDuration] = useState<Parts>({ hours: '', minutes: '' })
  const [warning, setWarning] = useState<Parts>({ hours: '', minutes: '' })
  const [enabled, setEnabled] = useState(false)
  const [reason, setReason] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const loadSequence = useRef(0)

  const load = useCallback(async (nextOffset = 0) => {
    const requestSequence = ++loadSequence.current
    setLoading(true)
    setError('')
    try {
      const [nextConfiguration, nextHistory] = await Promise.all([
        authWorkflowService.getSlaConfiguration(),
        authWorkflowService.listSlaConfigurationHistory(nextOffset, HISTORY_PAGE_SIZE),
      ])
      if (requestSequence !== loadSequence.current) return
      setConfiguration(nextConfiguration)
      setHistory(nextHistory)
      setOffset(nextOffset)
      setEnabled(nextConfiguration.enabled)
      setDuration(toParts(nextConfiguration.duration_minutes))
      setWarning(toParts(nextConfiguration.warning_before_minutes))
    } catch (failure) {
      if (requestSequence === loadSequence.current) setError(slaError(failure))
    } finally {
      if (requestSequence === loadSequence.current) setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const durationMinutes = fromParts(duration)
  const warningMinutes = fromParts(warning)
  const invalidDuration = durationMinutes === null || durationMinutes <= 0
  const invalidWarning = warningMinutes === null || warningMinutes <= 0
    || durationMinutes === null || warningMinutes >= durationMinutes
  const invalidReason = !reason.trim() || reason.trim().length > 1000
  const canSave = !loading && !saving && configuration !== null
    && !invalidDuration && !invalidWarning && !invalidReason

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSave || durationMinutes === null || warningMinutes === null || !configuration) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const updated = await authWorkflowService.updateSlaConfiguration({
        enabled,
        duration_minutes: durationMinutes,
        warning_before_minutes: warningMinutes,
        expected_revision: configuration.revision,
        change_reason: reason.trim(),
      })
      setReason('')
      setSuccess(`Đã lưu cấu hình revision ${updated.revision}. Cấu hình này chỉ áp dụng cho các vòng duyệt được gửi sau thời điểm lưu.`)
      await load(offset)
    } catch (failure) {
      setError(slaError(failure))
    } finally {
      setSaving(false)
    }
  }

  const page = history
  const rows = page?.items ?? []

  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading">
      <div>
        <p className="page-eyebrow">Workflow PostgreSQL · Administrator</p>
        <h1>Cấu hình SLA duyệt</h1>
        <p>Thiết lập thời hạn liên tục theo giờ cho từng vòng duyệt mới. Cấu hình lưu thành revision bất biến và có hiệu lực từ lần gửi duyệt tiếp theo.</p>
      </div>
      <button className="button button-secondary" type="button" disabled={loading} onClick={() => void load(offset)}><RefreshCw aria-hidden="true" /> Tải lại</button>
    </div>

    {error && <div className="auth-workflow-alert is-error" role="alert"><p>{error}</p>{error.includes('revision') && <button className="button button-secondary" type="button" disabled={loading} onClick={() => void load(offset)}>Tải cấu hình mới nhất</button>}</div>}
    {success && <div className="auth-workflow-alert is-success" role="status"><p>{success}</p></div>}
    {loading && !configuration && <p className="auth-workflow-state" role="status">Đang tải cấu hình SLA…</p>}

    <div className="auth-workflow-detail-grid sla-admin-grid">
      <form className="auth-workflow-form" onSubmit={save}>
        <div className="auth-workflow-card-heading"><Clock3 aria-hidden="true" /><h2>Thiết lập đang lưu</h2></div>
        <p className="sla-config-state">{configuration?.configured
          ? `Revision ${configuration.revision} · ${configuration.enabled ? 'Đang bật' : 'Đang tắt'}`
          : 'Chưa có cấu hình được lưu · SLA đang tắt'}</p>
        <label className="sla-toggle-row">
          <input type="checkbox" checked={enabled} onChange={event => setEnabled(event.currentTarget.checked)} disabled={loading || saving} />
          <span><strong>Bật SLA cho vòng duyệt mới</strong><small>Các vòng đang hoạt động giữ nguyên snapshot và hạn cũ.</small></span>
        </label>
        <div className="sla-period-grid">
          <fieldset className="sla-period-fieldset" disabled={loading || saving}>
            <legend>Thời hạn</legend>
            <label className="auth-field"><span>Giờ</span><input inputMode="numeric" type="number" min="0" step="1" value={duration.hours} onChange={event => { const hours = event.currentTarget.value; setDuration(current => ({ ...current, hours })) }} aria-invalid={invalidDuration} /></label>
            <label className="auth-field"><span>Phút</span><input inputMode="numeric" type="number" min="0" max="59" step="1" value={duration.minutes} onChange={event => { const minutes = event.currentTarget.value; setDuration(current => ({ ...current, minutes })) }} aria-invalid={invalidDuration} /></label>
          </fieldset>
          <fieldset className="sla-period-fieldset" disabled={loading || saving}>
            <legend>Cảnh báo trước hạn</legend>
            <label className="auth-field"><span>Giờ</span><input inputMode="numeric" type="number" min="0" step="1" value={warning.hours} onChange={event => { const hours = event.currentTarget.value; setWarning(current => ({ ...current, hours })) }} aria-invalid={invalidWarning} /></label>
            <label className="auth-field"><span>Phút</span><input inputMode="numeric" type="number" min="0" max="59" step="1" value={warning.minutes} onChange={event => { const minutes = event.currentTarget.value; setWarning(current => ({ ...current, minutes })) }} aria-invalid={invalidWarning} /></label>
          </fieldset>
        </div>
        {(invalidDuration || invalidWarning) && <p className="auth-field-error" role="status">Nhập thời hạn dương và thời điểm cảnh báo dương, nhỏ hơn thời hạn.</p>}
        <label className="auth-field sla-reason-field"><span>Lý do thay đổi</span><textarea value={reason} maxLength={1000} rows={3} onChange={event => setReason(event.currentTarget.value)} disabled={loading || saving} aria-invalid={invalidReason} required /></label>
        {invalidReason && <small className="auth-field-error">Lý do bắt buộc, tối đa 1.000 ký tự.</small>}
        <div className="auth-workflow-form-footer"><p>{configuration?.configured ? `Lưu sẽ tạo revision ${configuration.revision + 1}.` : 'Lưu lần đầu sẽ tạo revision 1.'} Không thay đổi hạn của vòng đã gửi.</p><button className="button button-primary" type="submit" disabled={!canSave}><Save aria-hidden="true" /> {saving ? 'Đang lưu…' : 'Lưu revision'}</button></div>
      </form>

      <aside className="auth-workflow-card sla-preview-card" aria-labelledby="sla-preview-title">
        <div className="auth-workflow-card-heading"><Clock3 aria-hidden="true" /><h2 id="sla-preview-title">Mô phỏng giao diện</h2></div>
        <span className="sla-preview-label">Giá trị kiểm thử tổng hợp · không được lưu</span>
        <strong className="sla-preview-duration">24 giờ</strong>
        <p>Cảnh báo khi còn 4 giờ. Thời hạn này chỉ minh họa giao diện; không phải SLA đã được duyệt.</p>
        <div className="sla-preview-timeline"><span><i /> Bắt đầu</span><span><i /> Cảnh báo sau 20 giờ</span><span><i /> Quá hạn sau 24 giờ</span></div>
      </aside>
    </div>

    <section className="auth-workflow-card" aria-labelledby="sla-history-title">
      <div className="auth-workflow-card-heading"><h2 id="sla-history-title">Lịch sử cấu hình</h2><span className="auth-workflow-history-count">{page?.total ?? 0} revision</span></div>
      {loading && !page ? <p role="status">Đang tải lịch sử…</p> : rows.length === 0
        ? <p>Chưa có revision cấu hình. Hệ thống không áp dụng thời hạn mặc định.</p>
        : <div className="auth-workflow-table-wrap"><table className="auth-workflow-table"><thead><tr><th>Revision</th><th>Trạng thái</th><th>Thời hạn</th><th>Cảnh báo trước</th><th>Người lưu</th><th>Thời điểm</th><th>Lý do</th></tr></thead><tbody>
          {rows.map(item => <tr key={item.revision}><td>{item.revision}</td><td>{item.enabled ? 'Đang bật' : 'Đang tắt'}</td><td>{formatMinutes(item.duration_minutes)}</td><td>{formatMinutes(item.warning_before_minutes)}</td><td>{item.changed_by_name ?? '—'}</td><td>{formatHcm(item.updated_at)}</td><td className="sla-reason-cell">{item.change_reason ?? '—'}</td></tr>)}
        </tbody></table></div>}
      {page && page.total > HISTORY_PAGE_SIZE && <div className="button-row sla-history-pagination"><button className="button button-secondary" type="button" disabled={loading || offset === 0} onClick={() => void load(Math.max(0, offset - HISTORY_PAGE_SIZE))}>Trước</button><span>{offset + 1}–{Math.min(offset + rows.length, page.total)} / {page.total}</span><button className="button button-secondary" type="button" disabled={loading || offset + rows.length >= page.total} onClick={() => void load(offset + HISTORY_PAGE_SIZE)}>Tiếp</button></div>}
    </section>
  </section>
}

function toParts(total: number | null): Parts {
  return total === null ? { hours: '', minutes: '' } : { hours: String(Math.floor(total / 60)), minutes: String(total % 60) }
}

function fromParts(value: Parts): number | null {
  if (!/^\d+$/.test(value.hours) || !/^\d+$/.test(value.minutes)) return null
  const hours = Number(value.hours)
  const minutes = Number(value.minutes)
  if (!Number.isSafeInteger(hours) || !Number.isSafeInteger(minutes) || minutes > 59) return null
  const total = hours * 60 + minutes
  return Number.isSafeInteger(total) ? total : null
}

function formatMinutes(value: number | null) {
  if (value === null) return '—'
  const hours = Math.floor(value / 60)
  const minutes = value % 60
  return [hours ? `${hours} giờ` : '', minutes ? `${minutes} phút` : ''].filter(Boolean).join(' ') || '0 phút'
}

function formatHcm(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh',
  }).format(date)
}

function slaError(failure: unknown) {
  if (failure instanceof AuthApiError && (failure.status === 409 || failure.code === 'CONFLICT')) {
    return 'Cấu hình SLA đã được cập nhật ở revision khác. Tải cấu hình mới nhất rồi áp dụng thay đổi của bạn.'
  }
  return failure instanceof Error ? failure.message : 'Không thể tải hoặc lưu cấu hình SLA.'
}
