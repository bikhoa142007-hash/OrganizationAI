import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  approvalConfigurationService,
  approvalPolicySignoffKinds,
  configurationKinds,
  type ApprovalPolicySignoffKind,
  type ConfigurationCurrent,
  type ConfigurationHistory,
  type ConfigurationKind,
  type ConfigurationRevision,
} from '../services/approvalConfiguration'

const kindLabels: Record<ConfigurationKind, string> = {
  approval_policy: 'Policy phê duyệt',
  budget: 'Hạn mức ngân sách',
  media_policy: 'Policy truyền thông',
  strategy_rubric: 'Rubric chiến lược',
  authority: 'Authority',
  checker_assignment: 'Checker mặc định',
  auto_reject_policy: 'Policy auto-reject',
}

const stateLabels: Record<string, string> = {
  UNCONFIGURED: 'Chưa cấu hình hiệu lực',
  DISABLED: 'Đang tắt',
  EFFECTIVE: 'Đang hiệu lực',
  SCHEDULED: 'Đã lên lịch hiệu lực',
  SUPERSEDED: 'Đã được revision mới thay thế',
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })
}

function RevisionSummary({ revision }: { revision: ConfigurationRevision }) {
  return <article className="auth-workflow-state">
    <h3>Revision {revision.revision} · {stateLabels[revision.status]}</h3>
    <p>Hiệu lực từ {formatDate(revision.effective_at)} · tạo lúc {formatDate(revision.created_at)}</p>
    <p>{revision.change_reason}</p>
    <details><summary>Giá trị đã lưu · hash cấu hình</summary>
      <pre>{JSON.stringify(revision.value, null, 2)}</pre>
      <code>{revision.configuration_hash}</code>
    </details>
  </article>
}

export function AuthenticatedApprovalConfigurationPage() {
  const [kind, setKind] = useState<ConfigurationKind>('approval_policy')
  const [current, setCurrent] = useState<ConfigurationCurrent | null>(null)
  const [history, setHistory] = useState<ConfigurationHistory | null>(null)
  const [valueText, setValueText] = useState('{}')
  const [effectiveAt, setEffectiveAt] = useState('')
  const [changeReason, setChangeReason] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const loadRequestId = useRef(0)

  const load = useCallback(async (selectedKind: ConfigurationKind) => {
    const requestId = ++loadRequestId.current
    setLoading(true)
    setError('')
    setCurrent(null)
    setHistory(null)
    try {
      const [currentResult, historyResult] = await Promise.all([
        approvalConfigurationService.current(),
        approvalConfigurationService.history(selectedKind),
      ])
      if (requestId !== loadRequestId.current) return
      setCurrent(currentResult)
      setHistory(historyResult)
    } catch (failure) {
      if (requestId === loadRequestId.current) {
        setError(failure instanceof Error ? failure.message : String(failure))
        setCurrent(null)
        setHistory(null)
      }
    } finally {
      if (requestId === loadRequestId.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(kind)
    return () => { loadRequestId.current += 1 }
  }, [kind, load])

  const currentItem = useMemo(() => current?.items.find(item => item.kind === kind) ?? null, [current, kind])
  const latestRevision = useMemo(() => history?.items.reduce<ConfigurationRevision | null>(
    (latest, item) => !latest || item.revision > latest.revision ? item : latest,
    null,
  ) ?? null, [history])

  function parseDraft(): Record<string, unknown> | null {
    try {
      const parsed: unknown = JSON.parse(valueText)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setError('Bản nháp phải là một object JSON.')
        return null
      }
      return parsed as Record<string, unknown>
    } catch {
      setError('Bản nháp không phải JSON hợp lệ.')
      return null
    }
  }

  function validateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    setError('')
    const parsed = parseDraft()
    if (!parsed) return
    const validationError = approvalConfigurationService.validateDraft(kind, parsed)
    if (validationError) setError(validationError)
    else setMessage('Bản nháp hợp lệ. Chưa có revision nào được ghi.')
  }

  async function saveRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setMessage('')
    const parsed = parseDraft()
    if (!parsed) return
    const validationError = approvalConfigurationService.validateDraft(kind, parsed)
    if (validationError) {
      setError(validationError)
      return
    }
    if (!effectiveAt || !changeReason.trim()) {
      setError('Cần nhập thời điểm hiệu lực và lý do thay đổi.')
      return
    }
    const parsedEffectiveAt = new Date(effectiveAt)
    if (Number.isNaN(parsedEffectiveAt.getTime())) {
      setError('Thời điểm hiệu lực không hợp lệ.')
      return
    }
    setSaving(true)
    try {
      const revision = await approvalConfigurationService.createRevision(kind, {
        expected_revision: latestRevision?.revision ?? null,
        effective_at: parsedEffectiveAt.toISOString(),
        change_reason: changeReason.trim(),
        value: parsed,
      })
      setMessage(`Đã tạo revision ${revision.revision}. Revision được giữ bất biến trong lịch sử.`)
      setValueText('{}')
      setEffectiveAt('')
      setChangeReason('')
      await load(kind)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setSaving(false)
    }
  }

  async function signOffPolicy() {
    setError('')
    setMessage('')
    if (!current || kind !== 'approval_policy') return
    const expectedRevisions = Object.fromEntries(approvalPolicySignoffKinds.map(configurationKind => {
      const item = current.items.find(candidate => candidate.kind === configurationKind)
      return [configurationKind, item?.current_revision && {
        revision_id: item.current_revision.revision_id,
        configuration_hash: item.current_revision.configuration_hash,
      }]
    }))
    if (approvalPolicySignoffKinds.some(configurationKind => !expectedRevisions[configurationKind])) {
      setError('Chưa đủ sáu revision approval hiện hành để ký.')
      return
    }
    setSaving(true)
    try {
      const result = await approvalConfigurationService.signOffPolicy(
        expectedRevisions as Record<ApprovalPolicySignoffKind, { revision_id: string; configuration_hash: string }>,
      )
      const signedAt = result.revision.signoff?.signed_at
      setMessage(`Đã ghi sign-off của Policy Owner cho revision ${result.revision.revision}${signedAt ? ` lúc ${formatDate(signedAt)}` : ''}.${result.replayed ? ' Đây là phản hồi lặp lại của cùng sign-off.' : ''}`)
      await load('approval_policy')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setSaving(false)
    }
  }

  async function signOffAutoRejectPolicy() {
    setError('')
    setMessage('')
    if (!current || kind !== 'auto_reject_policy') return
    const expectedRevisions = Object.fromEntries(current.items.map(item => [
      item.kind,
      item.current_revision && {
        revision_id: item.current_revision.revision_id,
        configuration_hash: item.current_revision.configuration_hash,
      },
    ]))
    if (configurationKinds.some(configurationKind => !expectedRevisions[configurationKind])) {
      setError('Chưa đủ revision hiệu lực để ký. Cần cấu hình đầy đủ cả bảy loại trước.')
      return
    }
    setSaving(true)
    try {
      const result = await approvalConfigurationService.signOffAutoRejectPolicy(
        expectedRevisions as Record<ConfigurationKind, { revision_id: string; configuration_hash: string }>,
      )
      const signedAt = result.revision.signoff?.signed_at
      setMessage(`Đã ghi sign-off của Policy Owner cho auto-reject revision ${result.revision.revision}${signedAt ? ` lúc ${formatDate(signedAt)}` : ''}.${result.replayed ? ' Đây là phản hồi lặp lại của cùng sign-off.' : ''}`)
      await load('auto_reject_policy')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setSaving(false)
    }
  }

  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading">
      <div><p className="page-eyebrow">Workflow PostgreSQL · Administrator</p><h1>Cấu hình phê duyệt</h1>
        <p>Revision đã tạo là bất biến. Bản nháp dưới đây chỉ nằm trên trang cho tới khi tạo revision.</p></div>
      <button className="button button-secondary" type="button" disabled={loading} onClick={() => void load(kind)}>Tải lại</button>
    </div>

    {error && <p className="auth-workflow-state is-error" role="alert">{error}</p>}
    {message && <p className="auth-workflow-state" role="status">{message}</p>}

    {kind === 'strategy_rubric' && <p className="auth-workflow-state" role="note">
      Rubric hợp lệ theo schema có thể được lưu, nhưng evaluator hiện chỉ hỗ trợ bộ trọng số baseline
      15/15/15/15/15/15/10 (Objective, Audience, Channel, Timeline, KPI, Budget efficiency, Risk control).
      Rubric dùng trọng số khác sẽ fail-closed với EVALUATOR_RUBRIC_UNSUPPORTED và yêu cầu Checker xem xét;
      việc lưu rubric không có nghĩa mọi bộ trọng số đều được evaluator hỗ trợ.
    </p>}

    <label htmlFor="approval-configuration-kind">Loại cấu hình
      <select id="approval-configuration-kind" value={kind} onChange={event => {
        setLoading(true)
        setCurrent(null)
        setHistory(null)
        setKind(event.target.value as ConfigurationKind)
        setValueText('{}')
        setError('')
        setMessage('')
      }}>
        {configurationKinds.map(item => <option key={item} value={item}>{kindLabels[item]}</option>)}
      </select>
    </label>

    {loading && <p role="status">Đang tải cấu hình…</p>}
    {!loading && currentItem && <section aria-label="Trạng thái cấu hình hiện tại">
      <h2>{stateLabels[currentItem.status]}</h2>
      {currentItem.current_revision ? <RevisionSummary revision={currentItem.current_revision} /> : <p>Không có giá trị hiệu lực; hệ thống phải xử lý fail-closed và yêu cầu Checker.</p>}
      {currentItem.next_scheduled_revision && <>
        <h3>Revision kế tiếp đã lên lịch</h3>
        <RevisionSummary revision={currentItem.next_scheduled_revision} />
      </>}
    </section>}

    {!loading && kind === 'approval_policy' && currentItem?.current_revision?.value.enabled === false && <section className="auth-workflow-state" aria-label="Policy Owner sign-off">
      <h2>Policy Owner sign-off</h2>
      <p>Thao tác này ký revision Policy phê duyệt đang hiển thị và tạo revision kế tiếp bật auto-approve. Backend chỉ chấp nhận phiên đăng nhập của bkhoa, xác minh sáu revision approval hiện hành, danh tính và trạng thái tài khoản, scope Marketing/social, ngân sách, authority và hạn mức đã duyệt.</p>
      <p>Policy auto-reject là luồng sign-off riêng và không được kích hoạt bởi thao tác này.</p>
      <p>Người ký cần kiểm tra các revision cụ thể và hash bên dưới. Sign-off được ghi bất biến cùng actor, thời điểm và authority snapshot.</p>
      <div aria-label="Các revision sẽ được sign-off">
        {approvalPolicySignoffKinds.map(signoffKind => {
          const item = current?.items.find(candidate => candidate.kind === signoffKind)
          return item?.current_revision
            ? <RevisionSummary key={item.kind} revision={item.current_revision} />
            : <p key={signoffKind}>{kindLabels[signoffKind]}: chưa cấu hình hiệu lực.</p>
        })}
      </div>
      {currentItem.current_revision.signoff && <p role="status">
        Đã ký bởi {currentItem.current_revision.signoff.policy_owner_id} lúc {formatDate(currentItem.current_revision.signoff.signed_at)} · hash {currentItem.current_revision.signoff.approved_configuration_hash}
      </p>}
      <button className="button button-primary" type="button" disabled={saving || loading} onClick={() => void signOffPolicy()}>
        {saving ? 'Đang xác minh và ghi sign-off…' : 'Policy Owner ký và bật auto-approve'}
      </button>
    </section>}

    {!loading && kind === 'auto_reject_policy' && currentItem?.current_revision?.value.enabled === false && <section className="auth-workflow-state" aria-label="Policy Owner auto-reject sign-off">
      <h2>Policy Owner sign-off · auto-reject</h2>
      <p>Ký sẽ kích hoạt đúng rule, scope và hash đang hiển thị. Chỉ ký sau khi đã duyệt nội dung literal, ngoại lệ, reason code và bằng chứng bắt buộc. Backend yêu cầu tài khoản ADMIN bkhoa đang hoạt động, Media/Strategy Marketing/social, Checker lekhoi và các revision hiện hành.</p>
      <p>Rule không có sign-off luôn tắt. Sau khi ký, mọi lần đổi revision hỗ trợ làm policy cũ fail-closed; hồ sơ đã gửi giữ snapshot cũ của mình.</p>
      <div aria-label="Các revision sẽ được sign-off">
        {current?.items.map(item => item.current_revision
          ? <RevisionSummary key={item.kind} revision={item.current_revision} />
          : <p key={item.kind}>{kindLabels[item.kind]}: chưa cấu hình hiệu lực.</p>)}
      </div>
      {currentItem.current_revision.signoff && <p role="status">
        Đã ký bởi {currentItem.current_revision.signoff.policy_owner_id} lúc {formatDate(currentItem.current_revision.signoff.signed_at)} · hash {currentItem.current_revision.signoff.approved_configuration_hash}
      </p>}
      <button className="button button-primary" type="button" disabled={saving || loading} onClick={() => void signOffAutoRejectPolicy()}>
        {saving ? 'Đang xác minh và ghi sign-off…' : 'Policy Owner ký và bật auto-reject'}
      </button>
    </section>}

    <form className="auth-plan-filters" onSubmit={validateDraft} aria-label="Soạn bản nháp cấu hình">
      <h2>Bản nháp trên trang</h2>
      <label htmlFor="approval-configuration-json">Giá trị JSON
        <textarea id="approval-configuration-json" rows={12} value={valueText} onChange={event => setValueText(event.target.value)} spellCheck={false} />
      </label>
      <button className="button button-secondary" type="submit">Kiểm tra bản nháp</button>
    </form>

    <form className="auth-plan-filters" onSubmit={event => void saveRevision(event)} aria-label="Tạo revision cấu hình">
      <label htmlFor="approval-configuration-effective-at">Hiệu lực từ thời điểm (giờ địa phương, gửi UTC)
        <input id="approval-configuration-effective-at" type="datetime-local" value={effectiveAt} onChange={event => setEffectiveAt(event.target.value)} required />
      </label>
      <label htmlFor="approval-configuration-reason">Lý do thay đổi
        <input id="approval-configuration-reason" maxLength={1000} value={changeReason} onChange={event => setChangeReason(event.target.value)} required />
      </label>
      <button className="button button-primary" type="submit" disabled={saving || loading}>{saving ? 'Đang tạo revision…' : 'Tạo revision bất biến'}</button>
    </form>

    <section aria-label="Lịch sử revision cấu hình">
      <h2>Lịch sử {kindLabels[kind]}</h2>
      {history?.items.length
        ? history.items.map(revision => <RevisionSummary key={revision.revision_id} revision={revision} />)
        : !loading && <p>Chưa có revision được lưu.</p>}
    </section>
  </section>
}
