import { FilePlus2, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { WorkflowPlanFilters } from '../components/auth/workflow/WorkflowPlanFilters'
import { useAuth } from '../context/AuthContext'
import { AuthApiError } from '../services/auth'
import { authWorkflowService } from '../services/authWorkflow'
import {
  backendCalendarDate,
  EMPTY_WORKFLOW_PLAN_FILTERS,
  filterWorkflowPlans,
  parseWorkflowPlanFilters,
  workflowPlanDepartments,
  writeWorkflowPlanFilters,
} from '../services/workflowPlanFilters'
import type { WorkflowPlan } from '../types/authWorkflow'

const PAGE_SIZE = 100
type ListMode = 'plans' | 'reviews'
type ListFailure = { error: AuthApiError; kind: 'first' | 'more'; offset: number }

export function AuthenticatedPlansPage({ reviews = false }: { reviews?: boolean }) {
  const { roles } = useAuth()
  const mode: ListMode = reviews ? 'reviews' : 'plans'
  const [searchParams, setSearchParams] = useSearchParams()
  const queryString = searchParams.toString()
  const parsedFilters = useMemo(
    () => parseWorkflowPlanFilters(new URLSearchParams(queryString)),
    [queryString],
  )
  const filters = parsedFilters.filters
  const [invalidUrlNotice, setInvalidUrlNotice] = useState('')

  const [plans, setPlans] = useState<WorkflowPlan[]>([])
  const plansRef = useRef<WorkflowPlan[]>([])
  const [dataMode, setDataMode] = useState<ListMode | null>(null)
  const loadedModeRef = useRef<ListMode | null>(null)
  const requestGeneration = useRef(0)
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [nextOffset, setNextOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [failure, setFailure] = useState<ListFailure | null>(null)
  const [reloadCount, setReloadCount] = useState(0)

  const replacePlans = useCallback((next: WorkflowPlan[]) => {
    plansRef.current = next
    setPlans(next)
  }, [])

  useEffect(() => {
    if (!parsedFilters.invalid) return
    setInvalidUrlNotice('Một số bộ lọc trên địa chỉ trang không hợp lệ nên đã được chuẩn hóa hoặc bỏ qua.')
    setSearchParams(
      writeWorkflowPlanFilters(filters, new URLSearchParams(queryString)),
      { replace: true },
    )
  }, [filters, parsedFilters.invalid, queryString, setSearchParams])

  const updateFilters = useCallback((next: typeof filters) => {
    setInvalidUrlNotice('')
    setSearchParams(current => writeWorkflowPlanFilters(next, current), { replace: true })
  }, [setSearchParams])

  const clearFilters = useCallback(() => {
    updateFilters(EMPTY_WORKFLOW_PLAN_FILTERS)
  }, [updateFilters])

  useEffect(() => {
    let active = true
    const generation = ++requestGeneration.current
    const sameMode = loadedModeRef.current === mode
    const keepRows = sameMode && plansRef.current.length > 0

    if (!sameMode) {
      replacePlans([])
      loadedModeRef.current = null
      setDataMode(null)
      setNextOffset(0)
      setHasMore(false)
    }
    setFailure(null)
    setLoadingMore(false)
    setInitialLoading(!keepRows)
    setRefreshing(keepRows)

    const loadFirstPage = mode === 'reviews'
      ? authWorkflowService.listReviews(0, PAGE_SIZE)
      : authWorkflowService.listPlans(0, PAGE_SIZE)

    loadFirstPage.then(result => {
      if (!active || requestGeneration.current !== generation) return
      replacePlans(mergeWorkflowPlans([], result))
      loadedModeRef.current = mode
      setDataMode(mode)
      setNextOffset(result.length)
      setHasMore(result.length === PAGE_SIZE)
    }).catch(reason => {
      if (!active || requestGeneration.current !== generation) return
      const error = asListError(reason, 'Không thể tải danh sách kế hoạch.')
      setFailure({ error, kind: 'first', offset: 0 })
      if (shouldClearLoadedList(error)) {
        replacePlans([])
        loadedModeRef.current = null
        setDataMode(null)
        setNextOffset(0)
        setHasMore(false)
      }
    }).finally(() => {
      if (!active || requestGeneration.current !== generation) return
      setInitialLoading(false)
      setRefreshing(false)
    })

    return () => {
      active = false
      if (requestGeneration.current === generation) requestGeneration.current += 1
    }
  }, [mode, reloadCount, replacePlans])

  const visiblePlans = dataMode === mode ? plans : []
  const filteredPlans = useMemo(
    () => filterWorkflowPlans(visiblePlans, filters),
    [visiblePlans, filters],
  )
  const departments = useMemo(() => workflowPlanDepartments(visiblePlans), [visiblePlans])

  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || dataMode !== mode) return
    const offset = nextOffset
    const generation = requestGeneration.current
    setFailure(null)
    setLoadingMore(true)
    try {
      const result = mode === 'reviews'
        ? await authWorkflowService.listReviews(offset, PAGE_SIZE)
        : await authWorkflowService.listPlans(offset, PAGE_SIZE)
      if (requestGeneration.current !== generation) return
      replacePlans(mergeWorkflowPlans(plansRef.current, result))
      setNextOffset(offset + result.length)
      setHasMore(result.length === PAGE_SIZE)
    } catch (reason) {
      if (requestGeneration.current !== generation) return
      const error = asListError(reason, 'Không thể tải thêm hồ sơ.')
      setFailure({ error, kind: 'more', offset })
      if (shouldClearLoadedList(error)) {
        setFailure({ error, kind: 'first', offset: 0 })
        replacePlans([])
        loadedModeRef.current = null
        setDataMode(null)
        setNextOffset(0)
        setHasMore(false)
      }
    } finally {
      if (requestGeneration.current === generation) setLoadingMore(false)
    }
  }, [dataMode, hasMore, loadingMore, mode, nextOffset, replacePlans])

  const isAdmin = roles.includes('ADMIN')
  const title = reviews ? 'Kế hoạch chờ tôi duyệt' : isAdmin ? 'Toàn bộ kế hoạch' : 'Kế hoạch của tôi'
  const description = reviews
    ? 'Hồ sơ đang chờ và được giao cho tài khoản Checker hiện tại.'
    : isAdmin && !roles.includes('MAKER')
      ? 'Chế độ chỉ đọc cho kế hoạch trong phạm vi marketing.'
      : isAdmin
        ? 'Tài khoản quản trị xem kế hoạch và chỉ tạo bản nháp theo quyền Maker.'
        : 'Các bản nháp, hồ sơ đã gửi và lịch sử do tài khoản hiện tại tạo.'
  const isInitialLoading = initialLoading || (dataMode !== mode && !failure)
  const pageError = failure?.error

  function retryFailure() {
    if (failure?.kind === 'more') void loadMore()
    else setReloadCount(value => value + 1)
  }

  return <section className="auth-workflow-page">
    <div className="auth-workflow-page-heading">
      <div>
        <p className="page-eyebrow">Workflow PostgreSQL · {reviews ? 'Checker' : isAdmin ? 'Administrator' : 'Maker'}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="button-row">
        <button className="button button-secondary" type="button" onClick={() => setReloadCount(value => value + 1)} disabled={isInitialLoading || refreshing || loadingMore}>
          <RefreshCw aria-hidden="true" /> {refreshing ? 'Đang tải…' : 'Tải lại'}
        </button>
        {!reviews && roles.includes('MAKER') && <Link className="button button-primary" to="/workflow/plans/new"><FilePlus2 aria-hidden="true" /> Tạo kế hoạch</Link>}
      </div>
    </div>

    {isInitialLoading && <p className="auth-workflow-state" role="status">Đang tải danh sách kế hoạch…</p>}
    {refreshing && visiblePlans.length > 0 && <p className="auth-plan-refresh-status" role="status">Đang đồng bộ danh sách. Các yêu cầu đã tải vẫn được giữ.</p>}

    {!isInitialLoading && pageError && visiblePlans.length === 0 && <section className="auth-workflow-state is-error" role="alert">
      <h2>Không tải được danh sách</h2><p>{listErrorText(pageError)}</p>
      {pageError.correlationId && <p className="auth-workflow-error-reference">Mã tham chiếu: {pageError.correlationId}</p>}
      <button className="button button-secondary" type="button" onClick={retryFailure}>Thử lại</button>
    </section>}

    {!isInitialLoading && pageError && visiblePlans.length > 0 && failure?.kind === 'first' && <div className="auth-workflow-alert is-error" role="alert">
      <div><p>{listErrorText(pageError)}</p>{pageError.correlationId && <small className="auth-workflow-error-reference">Mã tham chiếu: {pageError.correlationId}</small>}</div>
      <button className="button button-secondary" type="button" onClick={retryFailure} disabled={refreshing}>Thử tải lại</button>
    </div>}

    {!isInitialLoading && !pageError && visiblePlans.length === 0 && <section className="auth-workflow-state">
      <h2>{reviews ? 'Không có hồ sơ chờ duyệt được giao cho bạn.' : 'Chưa có kế hoạch'}</h2>
      <p>{reviews ? 'Hồ sơ sẽ xuất hiện tại đây khi được giao cho tài khoản Checker hiện tại.' : 'Tạo bản nháp đầu tiên để bắt đầu workflow Auth.'}</p>
    </section>}

    {visiblePlans.length > 0 && <>
      <WorkflowPlanFilters
        filters={filters}
        departments={departments}
        urlNotice={invalidUrlNotice}
        onChange={updateFilters}
        onClear={clearFilters}
      />
      <div className="auth-plan-result-count" aria-live="polite">
        <strong>{filteredPlans.length} kết quả trong {visiblePlans.length} yêu cầu đã tải</strong>
        <span>{hasMore ? 'Kết quả chỉ áp dụng cho dữ liệu đã tải; có thể tải thêm để mở rộng phạm vi.' : 'Đã tải hết các yêu cầu được trả về trong phạm vi quyền truy cập của bạn.'}</span>
      </div>

      {filteredPlans.length > 0 ? <div className={`auth-workflow-table-wrap auth-plan-results-wrap${reviews ? ' auth-review-queue-wrap' : ''}`}>
        <table className={`auth-workflow-table auth-plan-results-table${reviews ? ' auth-review-queue-table' : ''}`}>
          <thead><tr>
            <th scope="col">Yêu cầu / Mã</th><th scope="col">Bộ phận</th><th scope="col">Trạng thái</th>
            <th scope="col">Người lập</th><th scope="col">Checker</th><th scope="col">Ngày tạo</th>
            <th scope="col">Cập nhật</th><th scope="col">Vòng duyệt</th>
          </tr></thead>
          <tbody>{filteredPlans.map(plan => <WorkflowPlanRow key={plan.id} plan={plan} />)}</tbody>
        </table>
      </div> : <section className="auth-workflow-state auth-plan-no-results" aria-live="polite">
        <h2>Không có yêu cầu khớp với bộ lọc.</h2>
        <p>{hasMore ? 'Chưa có kết quả phù hợp trong dữ liệu đã tải. Tải thêm hồ sơ để tiếp tục tìm trong phạm vi tài khoản.' : 'Đã tìm hết dữ liệu hiện có trong phạm vi tài khoản.'}</p>
        <button className="button button-secondary" type="button" onClick={clearFilters} disabled={!Object.values(filters).some(Boolean)}>Xóa bộ lọc</button>
      </section>}

      <div className="auth-plan-pagination" aria-live="polite">
        {failure?.kind === 'more' && <div className="auth-workflow-alert is-error" role="alert">
          <div><p>{listErrorText(failure.error)}</p>{failure.error.correlationId && <small className="auth-workflow-error-reference">Mã tham chiếu: {failure.error.correlationId}</small>}</div>
            <button className="button button-secondary" type="button" onClick={retryFailure} disabled={loadingMore}>Thử lại</button>
        </div>}
        {loadingMore && <p className="auth-workflow-state" role="status">Đang tải thêm hồ sơ…</p>}
        {!failure && hasMore && !loadingMore && <button className="button button-secondary" type="button" onClick={() => void loadMore()}>Tải thêm hồ sơ</button>}
        {!hasMore && !loadingMore && !failure && <p role="status">{reviews ? 'Đã tải hết hồ sơ được giao.' : isAdmin ? 'Đã tải hết kế hoạch trong phạm vi quản trị.' : 'Đã tải hết kế hoạch do bạn tạo.'}</p>}
      </div>
    </>}
  </section>
}

function WorkflowPlanRow({ plan }: { plan: WorkflowPlan }) {
  const title = readText(plan?.payload?.title).trim() || readText(plan?.code).trim() || 'Kế hoạch không có tên'
  const code = readText(plan?.code)
  const status = readText(plan?.status)
  const createdDate = backendCalendarDate(plan?.created_at)
  const updatedDate = backendCalendarDate(plan?.updated_at)
  const stage = readText(plan?.processing_stage)
  const round = typeof plan?.current_round === 'number' && Number.isFinite(plan.current_round) && plan.current_round > 0
    ? plan.current_round : '—'

  return <tr>
    <td data-label="Yêu cầu / Mã"><Link aria-label={code ? `${title} (${code})` : title} to={`/workflow/plans/${encodeURIComponent(plan.id)}`}><strong>{title}</strong><small>{code || 'Không có mã'}</small></Link></td>
    <td data-label="Bộ phận">{readText(plan?.payload?.department).trim() || 'Chưa cung cấp'}</td>
    <td data-label="Trạng thái"><span className={`workflow-status status-${status.toLowerCase()}`}>{statusLabel(status)}</span>{['AI_PENDING', 'AI_PROCESSING'].includes(stage) && <small className="auth-stage-note">AI đang đánh giá</small>}{stage === 'HUMAN_REVIEW_REQUIRED' && <small className="auth-stage-note">Chờ Checker xem xét</small>}</td>
    <td data-label="Người lập">{readText(plan?.maker_name).trim() || 'Không rõ'}</td>
    <td data-label="Checker">{readText(plan?.checker_name).trim() || 'Chưa gán'}</td>
    <td data-label="Ngày tạo">{createdDate || '—'}</td>
    <td data-label="Cập nhật">{updatedDate || '—'}</td>
    <td data-label="Vòng duyệt">{round}</td>
  </tr>
}

function mergeWorkflowPlans(current: WorkflowPlan[], incoming: WorkflowPlan[]) {
  const merged = [...current]
  const indexById = new Map(merged.map((plan, index) => [plan.id, index]))
  for (const plan of incoming) {
    const existingIndex = indexById.get(plan.id)
    if (existingIndex === undefined) {
      indexById.set(plan.id, merged.length)
      merged.push(plan)
    } else {
      merged[existingIndex] = plan
    }
  }
  return merged
}

function readText(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function statusLabel(status: string) {
  return ({ DRAFT: 'Bản nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối' } as Record<string, string>)[status]
    ?? (status ? status.replaceAll('_', ' ') : 'Không xác định')
}

function asListError(reason: unknown, fallback: string) {
  return reason instanceof AuthApiError
    ? reason
    : new AuthApiError(0, reason instanceof Error ? reason.message : fallback, 'CLIENT_ERROR')
}

function shouldClearLoadedList(error: AuthApiError) {
  return [401, 403, 404].includes(error.status)
    || ['UNAUTHENTICATED', 'FORBIDDEN', 'NOT_FOUND'].includes(error.code || '')
}

function listErrorText(error: AuthApiError) {
  if (error.code === 'INVALID_RESPONSE') return 'Dịch vụ workflow trả về danh sách không hợp lệ. Hãy thử tải lại.'
  if (error.status === 0 || error.code === 'NETWORK_ERROR') return 'Không kết nối được dịch vụ workflow. Kiểm tra kết nối rồi thử lại.'
  if (error.status === 401 || error.code === 'UNAUTHENTICATED') return 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để xem danh sách.'
  if (error.status === 403 || error.code === 'FORBIDDEN') return 'Tài khoản hiện tại không có quyền xem danh sách này.'
  if (error.status === 404 || error.code === 'NOT_FOUND') return 'Danh sách hoặc hồ sơ này hiện không khả dụng.'
  if (error.status === 409 || error.code === 'CONFLICT') return 'Dữ liệu hàng chờ đã thay đổi. Tải lại danh sách để đồng bộ.'
  if (error.status === 422 || error.code === 'VALIDATION_ERROR') return 'Dịch vụ không chấp nhận yêu cầu tải danh sách. Hãy tải lại.'
  if (error.status >= 500) return 'Dịch vụ workflow đang gặp sự cố. Hãy thử lại sau.'
  return error.message || 'Không thể tải danh sách kế hoạch.'
}
