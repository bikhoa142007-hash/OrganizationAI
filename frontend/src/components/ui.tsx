import type { LucideIcon } from 'lucide-react'
import { AlertCircle, CheckCircle2, Inbox, LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'

export function StatusBadge({ value }: { value?: string | null }) {
  const text = value || 'Không xác định'
  return <span className={`status-badge status-${statusTone(text)}`}>{statusLabel(text)}</span>
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="page-eyebrow">{eyebrow}</p>}<h2>{title}</h2>{description && <p className="page-description">{description}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</header>
}

export function StatePanel({ kind, title, description, action }: { kind: 'loading' | 'empty' | 'error' | 'success'; title: string; description?: string; action?: ReactNode }) {
  const icons: Record<typeof kind, LucideIcon> = { loading: LoaderCircle, empty: Inbox, error: AlertCircle, success: CheckCircle2 }
  const Icon = icons[kind]
  return <div className={`state-panel state-${kind}`} role={kind === 'error' ? 'alert' : 'status'}><Icon aria-hidden="true" className={kind === 'loading' ? 'spin' : ''} /><div><h3>{title}</h3>{description && <p>{description}</p>}</div>{action && <div className="state-action">{action}</div>}</div>
}

export function formatDateTime(value?: string) {
  if (!value) return 'Chưa có dữ liệu'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('vi-VN', { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatMoney(value?: string, currency = 'VND') {
  if (value == null || value === '') return 'Chưa có dữ liệu'
  try { return new Intl.NumberFormat('vi-VN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(BigInt(value)) } catch { return `${value} ${currency}` }
}

export function statusLabel(value: string) {
  const labels: Record<string, string> = { DRAFT: 'Bản nháp', PENDING: 'Chờ xử lý', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối', CHANGES_REQUESTED: 'Yêu cầu chỉnh sửa', HUMAN_REVIEW_REQUIRED: 'Cần người duyệt', AI_PENDING: 'Đang chờ đánh giá', AI_PROCESSING: 'Đang đánh giá', AI_PROCESSING_FAILED: 'Đánh giá lỗi', AI_AUTO_APPROVED: 'Tự động duyệt', ACTIVE: 'Đang hoạt động', CLOSED: 'Đã đóng', PASS: 'Đạt', FAIL: 'Không đạt', ERROR: 'Lỗi', RUNNING: 'Đang chạy', COMPLETED: 'Hoàn tất' }
  return labels[value] ?? value.replaceAll('_', ' ')
}

function statusTone(value: string) {
  if (['APPROVED', 'AI_AUTO_APPROVED', 'PASS', 'COMPLETED', 'UPDATED'].includes(value)) return 'success'
  if (['PENDING', 'PENDING_APPROVAL', 'CHANGES_REQUESTED', 'HUMAN_REVIEW_REQUIRED', 'AI_PENDING', 'RUNNING', 'ACTIVE'].includes(value)) return 'warning'
  if (['REJECTED', 'FAIL', 'ERROR', 'AI_PROCESSING_FAILED', 'STALE'].includes(value)) return 'danger'
  if (['AI_PROCESSING', 'PROCESSING'].includes(value)) return 'info'
  return 'neutral'
}
