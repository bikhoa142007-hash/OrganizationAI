import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useServices } from '../services/ServiceProvider'

export function ProcessingPage() {
  const { planId = '' } = useParams(), services = useServices(), navigate = useNavigate()
  const [message, setMessage] = useState('Đang tải trạng thái…'), [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const snapshot = await services.plan.getProcessingStatus(planId)
        if (cancelled) return
        setMessage(snapshot.message ?? snapshot.status)
        if (snapshot.status === 'COMPLETED') navigate(`/plans/${planId}/result`, { replace: true })
      } catch (e) { if (!cancelled) setError(String(e)) }
    }
    void poll(); const timer = window.setInterval(() => void poll(), 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [planId, services.plan, navigate])
  return <section className="processing-page"><h2>Trạng thái xử lý</h2><p role="status">{message}</p>{error && <p role="alert">{error}</p>}<Link to={`/plans/${planId}`}>Mở chi tiết / tiếp tục evaluation</Link></section>
}
