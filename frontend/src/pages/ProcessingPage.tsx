import { Activity, ArrowLeft, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PageHeader, StatePanel, StatusBadge } from '../components/ui'
import { useServices } from '../services/ServiceProvider'
import type { ProcessingSnapshot } from '../types'

export function ProcessingPage() {
  const { planId = '' } = useParams()
  const services = useServices()
  const navigate = useNavigate()
  const [snapshot, setSnapshot] = useState<ProcessingSnapshot | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const value = await services.plan.getProcessingStatus(planId)
        if (cancelled) return
        setSnapshot(value); setError('')
        if (value.status === 'COMPLETED') navigate(`/plans/${planId}/result`, { replace: true })
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)) }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [navigate, planId, reload, services.plan])

  return <section className="processing-page">
    <PageHeader eyebrow={`Hồ sơ ${planId || 'không xác định'}`} title="Trạng thái xử lý" description="Màn hình chỉ hiển thị stage backend trả về. API hiện tại không cung cấp phần trăm tiến độ hoặc hành động Stop." actions={<Link className="button button-secondary" to={`/plans/${planId}`}><ArrowLeft /> Chi tiết hồ sơ</Link>} />
    {error ? <StatePanel kind="error" title="Không đọc được trạng thái" description={error} action={<button className="button button-secondary" onClick={() => setReload(value => value + 1)}><RefreshCw /> Thử lại</button>} /> : !snapshot ? <StatePanel kind="loading" title="Đang đọc trạng thái" description="Đang chờ snapshot từ backend." /> : <div className="processing-panel"><div className="processing-visual"><span className="processing-pulse"><Activity /></span><div><p className="page-eyebrow">Current status</p><h3>{snapshot.message || snapshot.status}</h3><StatusBadge value={snapshot.status} /></div></div><p>Submit và evaluation được lưu theo revision/idempotency. Nếu request đánh giá bị gián đoạn sau khi submit, mở chi tiết hồ sơ để tiếp tục round chưa có kết quả.</p><div className="button-row"><Link className="button button-secondary" to={`/audit?planId=${encodeURIComponent(planId)}`}><Activity /> Xem audit</Link><button className="button button-secondary" onClick={() => setReload(value => value + 1)}><RefreshCw /> Làm mới</button></div></div>}
  </section>
}
