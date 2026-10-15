import { AuthApiError } from './auth'
import { resolveApiBaseUrl } from './apiBaseUrl'

export const configurationKinds = [
  'approval_policy', 'budget', 'media_policy', 'strategy_rubric', 'authority', 'checker_assignment',
] as const

export type ConfigurationKind = typeof configurationKinds[number]
export type ConfigurationState = 'UNCONFIGURED' | 'DISABLED' | 'EFFECTIVE' | 'SCHEDULED' | 'SUPERSEDED'

export type ConfigurationRevision = {
  revision_id: string
  kind: ConfigurationKind
  revision: number
  status: ConfigurationState
  effective_at: string
  change_reason: string
  value: Record<string, unknown>
  configuration_hash: string
  changed_by: string
  created_at: string
  signoff?: {
    candidate_revision_id: string
    approval_policy_revision_id: string
    approved_configuration_hash: string
    policy_owner_id: string
    signed_at: string
    authority_revision_id: string
    authority_configuration_hash: string
    configuration_revisions: Record<string, { revision_id: string; configuration_hash: string }>
  } | null
}

export type ConfigurationItem = {
  kind: ConfigurationKind
  status: 'UNCONFIGURED' | 'DISABLED' | 'EFFECTIVE'
  current_revision: ConfigurationRevision | null
  next_scheduled_revision: ConfigurationRevision | null
}

export type ConfigurationCurrent = { as_of: string; items: ConfigurationItem[] }
export type ConfigurationHistory = {
  kind: ConfigurationKind
  as_of: string
  items: ConfigurationRevision[]
  offset: number
  limit: number
  total: number
}

const criteria = new Set(['objective', 'audience', 'channel', 'timeline', 'kpi', 'budget_efficiency', 'risk_control'])
const evidenceKinds = new Set(['OCR_TEXT', 'OBSERVATION', 'OBJECT_DETECTION', 'VISUAL_QUALITY', 'VISUAL_INSPECTION'])

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function hasKeys(value: Record<string, unknown>, expected: string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every(key => key in value)
}

function nonblank(value: unknown, max = 160): value is string {
  return typeof value === 'string' && value.trim() === value && value.length > 0 && value.length <= max
}

function minorUnits(value: unknown): value is string {
  return typeof value === 'string' && /^(0|[1-9][0-9]{0,23})$/.test(value)
}

function validUserId(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

export function validateConfigurationValue(kind: ConfigurationKind, value: unknown): string | null {
  if (!record(value)) return 'Giá trị phải là một đối tượng JSON.'
  if (kind === 'approval_policy') {
    if (!hasKeys(value, ['enabled', 'media_confidence_threshold', 'feasibility_score_threshold_exclusive', 'feasibility_confidence_threshold'])) return 'Thiếu hoặc có trường policy không được hỗ trợ.'
    if (value.enabled !== false) return 'Chỉ được lưu auto-approval đang tắt cho tới khi PO phê duyệt.'
    if (typeof value.media_confidence_threshold !== 'number' || value.media_confidence_threshold < 0 || value.media_confidence_threshold > 1) return 'Ngưỡng media confidence phải nằm trong 0..1.'
    if (typeof value.feasibility_score_threshold_exclusive !== 'number' || !Number.isInteger(value.feasibility_score_threshold_exclusive) || value.feasibility_score_threshold_exclusive < 0 || value.feasibility_score_threshold_exclusive >= 100) return 'Ngưỡng feasibility phải là số nguyên từ 0 đến 99.'
    if (typeof value.feasibility_confidence_threshold !== 'number' || value.feasibility_confidence_threshold < 0 || value.feasibility_confidence_threshold > 1) return 'Ngưỡng feasibility confidence phải nằm trong 0..1.'
    return null
  }
  if (kind === 'budget') {
    if (!hasKeys(value, ['currency', 'limits']) || value.currency !== 'VND' || !Array.isArray(value.limits)) return 'Budget phải có currency VND và limits dạng danh sách.'
    const seen = new Set<string>()
    for (const item of value.limits) {
      if (!record(item) || !hasKeys(item, ['department', 'limit_minor_units', 'active']) || !nonblank(item.department, 120) || !minorUnits(item.limit_minor_units) || typeof item.active !== 'boolean') return 'Mỗi budget limit cần department, số VND nguyên không âm và active.'
      if (seen.has(item.department)) return `Bộ phận ${item.department} có limit chồng lấn.`
      seen.add(item.department)
    }
    return null
  }
  if (kind === 'strategy_rubric') {
    if (!hasKeys(value, ['rubric_id', 'rubric_version', 'status', 'criteria']) || !nonblank(value.rubric_id) || !nonblank(value.rubric_version) || !['ACTIVE', 'DISABLED'].includes(String(value.status)) || !Array.isArray(value.criteria)) return 'Strategy rubric không đúng schema.'
    const seen = new Set<string>()
    let weight = 0
    for (const item of value.criteria) {
      if (!record(item) || !hasKeys(item, ['criterion_id', 'label', 'weight']) || !nonblank(item.criterion_id, 80) || !nonblank(item.label) || typeof item.weight !== 'number' || !Number.isInteger(item.weight) || item.weight < 1 || item.weight > 100) return 'Mỗi tiêu chí cần mã, nhãn và trọng số nguyên 1..100.'
      if (!criteria.has(item.criterion_id) || seen.has(item.criterion_id)) return 'Rubric phải dùng đủ tiêu chí đã hỗ trợ, mỗi tiêu chí một lần.'
      seen.add(item.criterion_id)
      weight += item.weight
    }
    return seen.size === criteria.size && weight === 100 ? null : 'Rubric phải có đủ bảy tiêu chí và tổng trọng số bằng 100.'
  }
  if (kind === 'checker_assignment') {
    if (!hasKeys(value, ['maker_may_select_other', 'defaults']) || typeof value.maker_may_select_other !== 'boolean' || !Array.isArray(value.defaults)) return 'Checker assignment không đúng schema.'
    const departments = new Set<string>()
    for (const item of value.defaults) {
      if (!record(item) || !hasKeys(item, ['department', 'checker_id']) || !nonblank(item.department, 120) || !validUserId(item.checker_id)) return 'Mỗi default cần bộ phận và UUID của một Checker.'
      if (departments.has(item.department)) return `Bộ phận ${item.department} có nhiều Checker mặc định.`
      departments.add(item.department)
    }
    return null
  }
  if (kind === 'authority') {
    if (!hasKeys(value, ['currency', 'auto_limit_minor_units', 'allowed_departments', 'checker_id', 'policy_owner_id', 'budget_authority_id', 'active']) || value.currency !== 'VND' || !minorUnits(value.auto_limit_minor_units) || typeof value.active !== 'boolean' || !Array.isArray(value.allowed_departments)) return 'Authority không đúng schema VND.'
    if (!value.allowed_departments.length || value.allowed_departments.some(item => !nonblank(item, 120)) || new Set(value.allowed_departments).size !== value.allowed_departments.length) return 'allowed_departments phải có giá trị duy nhất.'
    for (const key of ['checker_id', 'policy_owner_id', 'budget_authority_id']) if (value[key] !== null && !validUserId(value[key])) return `${key} phải là UUID hoặc null.`
    return null
  }
  if (kind === 'media_policy') {
    if (!hasKeys(value, ['policy_id', 'policy_version', 'status', 'scope_departments', 'scope_channels', 'rules']) || !nonblank(value.policy_id) || !nonblank(value.policy_version) || !['ACTIVE', 'DISABLED'].includes(String(value.status)) || !Array.isArray(value.scope_departments) || !Array.isArray(value.scope_channels) || !Array.isArray(value.rules)) return 'Media policy không đúng schema.'
    if (!value.scope_departments.length || !value.scope_channels.length || value.scope_departments.some(item => !nonblank(item, 120)) || value.scope_channels.some(item => !nonblank(item, 120))) return 'Media policy cần scope bộ phận và kênh rõ ràng.'
    for (const item of value.rules) {
      if (!record(item) || !['rule_id', 'severity', 'description', 'required_evidence_kinds', 'forbidden_literals'].every(key => key in item) || !nonblank(item.rule_id) || !nonblank(item.description, 1000) || !['HARD_VIOLATION', 'WARNING'].includes(String(item.severity)) || !Array.isArray(item.required_evidence_kinds) || !item.required_evidence_kinds.length || item.required_evidence_kinds.some(kind => typeof kind !== 'string' || !evidenceKinds.has(kind)) || !Array.isArray(item.forbidden_literals) || item.forbidden_literals.some(text => !nonblank(text, 500))) return 'Media policy chứa rule không hợp lệ.'
      if (item.forbidden_literals.length && !item.required_evidence_kinds.includes('OCR_TEXT')) return 'Rule dùng forbidden_literals cần OCR_TEXT.'
    }
    return value.rules.length ? null : 'Media policy cần ít nhất một rule.'
  }
  return 'Configuration kind không được hỗ trợ.'
}

async function request<T>(path: string, method: 'GET' | 'POST', body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${resolveApiBaseUrl()}${path}`, {
      method,
      credentials: 'include',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new AuthApiError(0, 'Không thể kết nối dịch vụ cấu hình workflow.', 'NETWORK_ERROR')
  }
  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (response.status === 401 || response.status === 403) {
    window.dispatchEvent(new Event(response.status === 401 ? 'organizationai:auth-expired' : 'organizationai:access-denied'))
  }
  if (!response.ok) {
    const message = record(data) && typeof data.message === 'string' ? data.message : 'Yêu cầu cấu hình workflow thất bại.'
    const code = record(data) && typeof data.code === 'string' ? data.code : 'HTTP_ERROR'
    throw new AuthApiError(response.status, message, code)
  }
  return data as T
}

function isRevision(value: unknown): value is ConfigurationRevision {
  return record(value)
    && typeof value.revision_id === 'string'
    && configurationKinds.includes(value.kind as ConfigurationKind)
    && Number.isInteger(value.revision)
    && ['UNCONFIGURED', 'DISABLED', 'EFFECTIVE', 'SCHEDULED', 'SUPERSEDED'].includes(String(value.status))
    && typeof value.effective_at === 'string'
    && typeof value.change_reason === 'string'
    && record(value.value)
    && typeof value.configuration_hash === 'string'
    && typeof value.changed_by === 'string'
    && typeof value.created_at === 'string'
    && (value.signoff === undefined || value.signoff === null || record(value.signoff))
}

export const approvalConfigurationService = {
  validateDraft: validateConfigurationValue,

  async current(): Promise<ConfigurationCurrent> {
    const result = await request<unknown>('/workflow/configuration', 'GET')
    if (!record(result) || typeof result.as_of !== 'string' || !Array.isArray(result.items)) throw new AuthApiError(502, 'Dịch vụ cấu hình trả về dữ liệu không hợp lệ.', 'INVALID_RESPONSE')
    for (const item of result.items) {
      if (!record(item) || !configurationKinds.includes(item.kind as ConfigurationKind) || !['UNCONFIGURED', 'DISABLED', 'EFFECTIVE'].includes(String(item.status)) || (item.current_revision !== null && !isRevision(item.current_revision)) || (item.next_scheduled_revision !== null && !isRevision(item.next_scheduled_revision))) throw new AuthApiError(502, 'Dịch vụ cấu hình trả về dữ liệu không hợp lệ.', 'INVALID_RESPONSE')
    }
    return result as ConfigurationCurrent
  },

  async history(kind: ConfigurationKind, offset = 0, limit = 50): Promise<ConfigurationHistory> {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    const result = await request<unknown>(`/workflow/configuration/${encodeURIComponent(kind)}/history?${query}`, 'GET')
    if (!record(result) || result.kind !== kind || typeof result.as_of !== 'string' || !Array.isArray(result.items) || !result.items.every(isRevision) || !Number.isInteger(result.total)) throw new AuthApiError(502, 'Dịch vụ cấu hình trả về lịch sử không hợp lệ.', 'INVALID_RESPONSE')
    return result as ConfigurationHistory
  },

  createRevision(kind: ConfigurationKind, body: { expected_revision: number | null; effective_at: string; change_reason: string; value: Record<string, unknown> }): Promise<ConfigurationRevision> {
    const validationError = validateConfigurationValue(kind, body.value)
    if (validationError) return Promise.reject(new AuthApiError(422, validationError, 'VALIDATION_ERROR'))
    return request<unknown>(`/workflow/configuration/${encodeURIComponent(kind)}/revisions`, 'POST', body).then(result => {
      if (!isRevision(result) || result.kind !== kind) throw new AuthApiError(502, 'Dịch vụ cấu hình trả về revision không hợp lệ.', 'INVALID_RESPONSE')
      return result
    })
  },

  async signOffPolicy(expectedRevisions: Record<ConfigurationKind, { revision_id: string; configuration_hash: string }>): Promise<{ revision: ConfigurationRevision; replayed: boolean }> {
    const result = await request<unknown>('/workflow/configuration/approval-policy/signoff', 'POST', {
      expected_revisions: expectedRevisions,
    })
    if (!record(result) || !isRevision(result.revision) || result.revision.kind !== 'approval_policy' || typeof result.replayed !== 'boolean') {
      throw new AuthApiError(502, 'Dịch vụ sign-off trả về dữ liệu không hợp lệ.', 'INVALID_RESPONSE')
    }
    return result as { revision: ConfigurationRevision; replayed: boolean }
  },
}
