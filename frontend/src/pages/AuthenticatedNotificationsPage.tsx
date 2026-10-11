import { Bell, Check, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { StatePanel } from '../components/ui'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import type { WorkflowNotification, WorkflowNotificationPage } from '../types/authWorkflow'

const PAGE_SIZE = 20

export function AuthenticatedNotificationsPage() {
  const [offset, setOffset] = useState(0)
  const [reload, setReload] = useState(0)
  const [page, setPage] = useState<WorkflowNotificationPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mutationError, setMutationError] = useState('')
  const [pendingId, setPendingId] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    authWorkflowService.listNotifications(offset, PAGE_SIZE)
      .then(result => { if (active) setPage(result) })
      .catch(reason => {
        if (active) setError(reason instanceof Error ? reason.message : 'Không thể tải hộp thư thông báo.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [offset, reload])

  async function markRead(notification: WorkflowNotification) {
    setPendingId(notification.id)
    setMutationError('')
    try {
      const updated = await authWorkflowService.markNotificationRead(notification.id)
      setPage(current => current === null ? current : {
        ...current,
        unread_count: Math.max(0, current.unread_count - (notification.read_at === null ? 1 : 0)),
        items: current.items.map(item => item.id === updated.id ? updated : item),
      })
    } catch (reason) {
      setMutationError(reason instanceof AuthApiError ? reason.message : 'Không thể cập nhật thông báo.')
    } finally {
      setPendingId('')
    }
  }

  return <section className="auth-workflow-page" aria-labelledby="notifications-title">
    <header className="auth-workflow-page-heading">
      <div>
        <p className="page-eyebrow">Hộp thư</p>
        <h1 id="notifications-title">Thông báo</h1>
        <p>Thông tin gửi duyệt và kết quả phê duyệt kế hoạch được giao cho bạn.</p>
      </div>
      {page && <span className="auth-notification-unread-count" aria-live="polite">{page.unread_count} chưa đọc</span>}
    </header>

    {loading && page === null && <StatePanel kind="loading" title="Đang tải thông báo" />}
    {error && page === null && <StatePanel kind="error" title="Không thể tải hộp thư" description={error} action={<button className="button button-secondary" type="button" onClick={() => setReload(current => current + 1)}>Thử lại</button>} />}
    {error && page !== null && <p className="auth-notification-error" role="alert">{error}</p>}
    {mutationError && <p className="auth-notification-error" role="alert">{mutationError}</p>}

    {page && page.items.length === 0 && !loading && <div className="auth-notification-empty">
      <Bell aria-hidden="true" />
      <h2>Hộp thư đang trống</h2>
      <p>Khi kế hoạch được gửi hoặc có quyết định, thông báo sẽ xuất hiện tại đây.</p>
    </div>}

    {page && page.items.length > 0 && <>
      <div className="auth-notification-list" aria-label="Danh sách thông báo">
        {page.items.map(notification => <article
          className={`auth-notification-card${notification.read_at === null ? ' is-unread' : ''}`}
          key={notification.id}
        >
          <div className="auth-notification-content">
            <div className="auth-notification-heading">
              <h2>{notification.title}</h2>
              {notification.read_at === null && <span className="auth-notification-new">Mới</span>}
            </div>
            <p>{notification.message}</p>
            <small>
              {notification.plan_code} · Phiên bản {notification.version_number} · Vòng {notification.round_number}
              {' · '}{new Date(notification.created_at).toLocaleString('vi-VN')}
            </small>
          </div>
          <div className="auth-notification-actions">
            <Link to={`/workflow/plans/${notification.plan_id}`}>
              Mở kế hoạch <ExternalLink aria-hidden="true" />
            </Link>
            {notification.read_at === null && <button
              type="button"
              className="button button-secondary"
              disabled={pendingId === notification.id}
              onClick={() => void markRead(notification)}
            >
              <Check aria-hidden="true" /> {pendingId === notification.id ? 'Đang lưu…' : 'Đánh dấu đã đọc'}
            </button>}
          </div>
        </article>)}
      </div>
      <nav className="auth-notification-pagination" aria-label="Trang thông báo">
        <button className="button button-secondary" type="button" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          <ChevronLeft aria-hidden="true" /> Trước
        </button>
        <span role="status">
          {offset + 1}–{Math.min(offset + page.items.length, page.total)} / {page.total}
        </span>
        <button className="button button-secondary" type="button" disabled={loading || offset + page.items.length >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Tiếp <ChevronRight aria-hidden="true" />
        </button>
      </nav>
    </>}
  </section>
}
