import { FilePlus2 } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { AuthApiError } from '../../services/auth'
import {
  workflowCompletionService,
  type WorkflowInternalNote,
} from '../../services/workflowCompletion'

interface InternalNotesPanelProps {
  planId: string
  approvalRound: number | null
}

function messageFor(error: unknown): string {
  if (error instanceof AuthApiError) {
    if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
    if (error.status === 403) return 'Chỉ Checker đang được giao cho kế hoạch này mới có thể xem hoặc thêm ghi chú nội bộ.'
    if (error.status === 404) return 'Không tìm thấy kế hoạch.'
    if (error.status === 409) return 'Yêu cầu ghi chú đã xung đột. Tải lại rồi thử lại.'
  }
  return 'Không thể tải hoặc lưu ghi chú nội bộ. Hãy thử lại.'
}

function formatUtc(value: string): string {
  return `${new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value))} UTC`
}

export function InternalNotesPanel({ planId, approvalRound }: InternalNotesPanelProps) {
  const headingId = useId()
  const inputId = useId()
  const helpId = useId()
  const [notes, setNotes] = useState<WorkflowInternalNote[]>([])
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const pendingRequest = useRef<{ fingerprint: string; key: string } | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoaded(false)
    setNotes([])
    setError('')
    workflowCompletionService.getInternalNotes(planId)
      .then(result => {
        if (!active) return
        setNotes(result)
        setLoaded(true)
      })
      .catch(reason => { if (active) setError(messageFor(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [planId, reloadKey])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = content.trim()
    if (!normalized || normalized.length > 4000 || saving) return

    const fingerprint = JSON.stringify([approvalRound, normalized])
    if (pendingRequest.current?.fingerprint !== fingerprint) {
      pendingRequest.current = { fingerprint, key: crypto.randomUUID() }
    }
    setSaving(true)
    setError('')
    try {
      const saved = await workflowCompletionService.addInternalNote(planId, {
        approval_round: approvalRound,
        content: normalized,
      }, pendingRequest.current.key)
      setNotes(current => current.some(note => note.note_id === saved.note_id) ? current : [...current, saved])
      setContent('')
      pendingRequest.current = null
    } catch (reason) {
      if (reason instanceof AuthApiError && reason.status === 403) {
        setLoaded(false)
        setNotes([])
      }
      setError(messageFor(reason))
    } finally {
      setSaving(false)
    }
  }

  return <section className="auth-workflow-card" aria-labelledby={headingId} aria-busy={loading || saving}>
    <div className="auth-workflow-card-heading">
      <FilePlus2 aria-hidden="true" />
      <h2 id={headingId}>Ghi chú nội bộ</h2>
    </div>

    {loading && <p role="status">Đang tải ghi chú nội bộ…</p>}
    {error && <div className="auth-workflow-alert is-error" role="alert">
      <p>{error}</p>
      {!loaded && <button
        className="button button-secondary"
        type="button"
        disabled={loading}
        onClick={() => setReloadKey(value => value + 1)}
      >Thử lại</button>}
    </div>}

    {loaded && <>
      {notes.length === 0
        ? <p className="auth-workflow-history-empty">Chưa có ghi chú nội bộ.</p>
        : <ol className="auth-workflow-history" aria-label="Ghi chú nội bộ">
          {notes.map(note => <li key={note.note_id}>
            <p>{note.content}</p>
            <time dateTime={note.created_at}>{formatUtc(note.created_at)}</time>
          </li>)}
        </ol>}
      <form className="auth-workflow-form" onSubmit={submit}>
        <label className="field" htmlFor={inputId}>
          <span>Thêm ghi chú cho Checker</span>
          <textarea
            id={inputId}
            rows={3}
            maxLength={4000}
            aria-describedby={helpId}
            value={content}
            onChange={event => setContent(event.currentTarget.value)}
            disabled={saving}
          />
          <small id={helpId}>{content.trim().length}/4000 ký tự. Ghi chú chỉ Checker được giao mới đọc được.</small>
        </label>
        <button
          className="button button-primary"
          type="submit"
          disabled={saving || !content.trim() || content.trim().length > 4000}
        >{saving ? 'Đang lưu…' : 'Thêm ghi chú'}</button>
      </form>
    </>}
  </section>
}
