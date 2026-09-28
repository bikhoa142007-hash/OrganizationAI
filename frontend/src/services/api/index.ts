import type { FrontendServices } from '../interfaces'
import type { AuditEvent, PlanState, PlanView, ResultView, ReviewDetail, VerifyRun, RuntimeOutcome } from '../../types'
import { api, ApiClient, ApiError, demoActor } from './client'

type Json = Record<string, unknown>
export interface WirePlan {
  plan_id: string; maker_id: string; payload: Json; attachments: Array<{ attachment_id: string; media_type: string; byte_size: number }>
  revision: number; current_round: number; state: { plan_status: PlanState['planStatus']; processing_stage: PlanState['processingStage']; approval_round_status: PlanState['approvalRoundStatus'] }
}
interface Evaluation {
  feasibility_score: number | null; feasibility_confidence: number | null; media_confidence: number | null
  proposed_action?: string; media_result: string | null; model_version: string; evidence: Array<{ evidence_id: string; source_ref: string; observation: string }>; missing_facts: string[]
  evidence_conflicts: Array<{ conflict_id: string; description: string }>
}
interface Decision {
  outcome: RuntimeOutcome; escalation_category: string | null; reason: string; policy_version: string
  applied_rule_ids: string[]; budget_validation: { budget_minor_units: string; limit_minor_units: string }
}
export interface History {
  plan: WirePlan; versions: Array<{ plan_version: number; approval_round: number; payload: Json }>
  rounds: Array<{ number: number; revision: number; decision_id: string | null; configuration: { policy: { policy_version: string } } }>
  records: Array<{ kind: string; body: Json }>; audit: Array<Json>
}
interface Config {
  policy: {
    policy: {
      policy_version: string
      rule_ids: string[]
      auto_approval_policy_enabled: boolean
      mandatory_fields: string[]
      known_model_versions: string[]
      allowed_media_types: string[]
      max_attachment_bytes: number
      feasibility_threshold: number
      media_confidence_threshold: number
      feasibility_confidence_threshold: number
    }
    budgets: Array<{ configuration_id: string; currency: string; limit_minor_units: string; department: string; active: boolean }>
    authority: { snapshot_id: string; auto_limit_minor_units: string; checker_id: string | null; active: boolean } | null
  }
  checker_id: string
  department: string
  currency: string
}
const state = (v: WirePlan['state']): PlanState => ({ planStatus: v.plan_status, processingStage: v.processing_stage, approvalRoundStatus: v.approval_round_status })
export const mapPlan = (p: WirePlan): PlanView => ({ planId: p.plan_id, title: String(p.payload.title ?? ''), payload: p.payload,
  makerId: p.maker_id, revision: p.revision, planVersion: p.current_round || undefined, approvalRound: p.current_round || undefined, state: state(p.state),
  attachments: p.attachments.map(a => ({ attachmentId: a.attachment_id, mediaType: a.media_type, byteSize: a.byte_size })) })
const currentRecords = (h: History) => h.records.filter(r => r.body.approval_round === h.plan.current_round)
const record = <T,>(h: History, kind: string) => currentRecords(h).find(r => r.kind === kind)?.body as T | undefined

export function mapResult(h: History): ResultView {
  const d = record<Decision>(h, 'engine_decision'), e = record<Evaluation>(h, 'evaluation')
  const human = record<{ action: string; reason: string; override_reason: string }>(h, 'human_decision')
  const questions = currentRecords(h).filter(r => r.kind === 'escalation').map(r => String(r.body.question))
  const evidence = (e?.evidence ?? []).map(v => ({ id: v.evidence_id, label: v.source_ref, value: v.observation }))
  evidence.push(...(e?.evidence_conflicts ?? []).map(v => ({ id: v.conflict_id, label: 'Factual conflict', value: v.description })))
  evidence.push(...(e?.missing_facts ?? []).map((value, i) => ({ id: `missing-${i}`, label: 'Chưa xác minh', value })))
  if (e) evidence.push({ id: 'ai-recommendation', label: 'Khuyến nghị AI (không phải quyết định cuối)', value: String(e.proposed_action ?? 'Chưa có khuyến nghị') })
  if (e) evidence.push({ id: 'media-confidence', label: 'Media confidence', value: String(e.media_confidence) })
  const actions = [{ id: 'history', label: 'Version / round / history', href: `/plans/${h.plan.plan_id}` },
    { id: 'audit', label: 'Audit', href: `/audit?planId=${encodeURIComponent(h.plan.plan_id)}` }]
  if (h.plan.state.plan_status === 'REJECTED' && h.plan.maker_id === demoActor()) actions.push({ id: 'revise', label: 'Sửa và gửi lại', href: `/plans/${h.plan.plan_id}/edit` })
  return { planId: h.plan.plan_id, title: String(h.plan.payload.title ?? h.plan.plan_id),
    variant: human ? 'HUMAN_DECISION' : d?.outcome === 'AUTO_APPROVED' ? 'SYSTEM_DECISION' : d ? 'HUMAN_REVIEW' : 'ERROR',
    statusLabel: `${h.plan.state.plan_status} · ${d?.escalation_category ?? d?.outcome ?? 'Chưa đánh giá'}`,
    decisionSource: human ? 'CHECKER' : d?.outcome === 'AUTO_APPROVED' ? 'SYSTEM · Policy bật tự duyệt · MOCK_VLM (kịch bản seed)' : undefined,
    score: e?.feasibility_score, confidence: e?.feasibility_confidence,
    media: { status: e?.media_result ?? 'Chưa có', attachments: h.plan.attachments.map(a => a.attachment_id) },
    budget: { value: d?.budget_validation.budget_minor_units, limit: d?.budget_validation.limit_minor_units },
    ruleIds: d?.applied_rule_ids, evidence, reason: human ? human.reason || human.override_reason : d?.reason,
    policyVersion: d?.policy_version, modelVersion: e?.model_version,
    reviewDetails: questions.length ? { question: questions.join('\n'), authority: String(h.plan.payload.checker_id) } : undefined, actions }
}

export function mapReview(h: History): ReviewDetail {
  const result = mapResult(h)
  return { ...mapPlan(h.plan), revision: h.rounds.at(-1)?.revision, status: 'PENDING',
    escalationCategory: record<Decision>(h, 'engine_decision')?.escalation_category ?? undefined,
    reason: result.reason, authority: String(h.plan.payload.checker_id), createdAt: String(h.audit.at(-1)?.timestamp ?? ''),
    originalInput: Object.fromEntries(Object.entries(h.plan.payload).map(([k, v]) => [k, typeof v === 'string' ? v : JSON.stringify(v)])),
    attachments: h.plan.attachments.map(a => a.attachment_id), evidence: result.evidence,
    appliedRuleIds: result.ruleIds, handoffQuestions: currentRecords(h).filter(r => r.kind === 'escalation').map(r => String(r.body.question)),
    currentDecision: result.statusLabel }
}

export const history = (id: string) => api.request<History>(`/plans/${encodeURIComponent(id)}`)
export function createApiServices(client: ApiClient = api): FrontendServices {
  const revisions = new Map<string, number>(), histories = new Map<string, History>(), runs = new Map<string, VerifyRun>()
  const remember = (p: WirePlan) => { revisions.set(p.plan_id, p.revision); return mapPlan(p) }
  const read = async (id: string) => { const h = await client.request<History>(`/plans/${encodeURIComponent(id)}`); histories.set(id, h); remember(h.plan); return h }
  const list = async () => (await client.request<WirePlan[]>('/plans')).map(remember)
  const audit = (h: History): AuditEvent[] => h.audit.map(e => ({ eventId: String(e.event_id), action: String(e.action), actorId: String(e.actor_id),
    timestamp: String(e.timestamp), inputVersion: `${e.plan_version ?? 'draft'} / round ${e.approval_round ?? '—'}`,
    policyVersion: e.policy_version as string | undefined, modelVersion: e.model_version as string | undefined, reason: String(e.reason),
    correlationId: e.correlation_id as string | undefined, runId: e.run_id as string | undefined,
    decisionId: (e.human_decision_id ?? e.decision_id) as string | undefined,
    outcome: e.outcome as string | undefined, humanAction: e.human_action as string | undefined,
    overrideReason: e.override_reason as string | undefined,
    appliedRuleIds: Array.isArray(e.applied_rule_ids) ? e.applied_rule_ids.map(String) : undefined,
    previousState: e.previous_state ? state(e.previous_state as WirePlan['state']) : null,
    newState: e.new_state ? state(e.new_state as WirePlan['state']) : null }))
  return {
    plan: {
      listPlans: list, getPlan: async id => remember((await read(id)).plan),
      saveDraft: async (id, payload, meta) => {
        const planId = id || `DEMO-${crypto.randomUUID()}`
        return remember(await client.request<WirePlan>(`/plans/${encodeURIComponent(planId)}/draft`, 'PUT',
          { payload, expected_revision: meta.expectedRevision ?? revisions.get(planId) ?? 0 }, meta.idempotencyKey))
      },
      uploadAttachment: async (id, file, meta) => {
        const form = new FormData(); form.set('file', file); form.set('expected_revision', String(meta.expectedRevision ?? revisions.get(id)))
        const p = await client.request<WirePlan>(`/plans/${encodeURIComponent(id)}/attachments`, 'POST', form, meta.idempotencyKey)
        remember(p); return mapPlan(p).attachments!.at(-1)!
      },
      submitPlan: async (id, meta) => {
        const config = await client.request<Config>('/config')
        const submission = await client.request<{ round: { number: number; revision: number } }>(`/plans/${encodeURIComponent(id)}/submit`, 'POST',
          { expected_revision: meta.expectedRevision ?? revisions.get(id), expected_policy_version: config.policy.policy.policy_version }, meta.idempotencyKey)
        await client.request(`/plans/${encodeURIComponent(id)}/rounds/${submission.round.number}/evaluate`, 'POST',
          { expected_revision: submission.round.revision }, meta.idempotencyKey ? `${meta.idempotencyKey}:evaluate` : undefined)
        return remember((await read(id)).plan)
      },
      getProcessingStatus: async id => { const h = await read(id); return { status: record(h, 'engine_decision') ? 'COMPLETED' : 'PROCESSING', message: h.plan.state.processing_stage ?? h.plan.state.plan_status } },
      getResult: async id => mapResult(await read(id)),
      stopProcessing: async () => { throw new ApiError('UNAVAILABLE', 'Stop không thuộc contract Sprint 1.', 409) },
      retryProcessing: async id => {
        const h = await read(id), round = h.rounds.at(-1)
        if (!round || round.decision_id) throw new ApiError('CONFLICT', 'Chỉ tiếp tục evaluation chưa được ghi nhận.', 409)
        await client.request(`/plans/${encodeURIComponent(id)}/rounds/${round.number}/evaluate`, 'POST', { expected_revision: round.revision }, `continue:${id}:${round.number}`)
        return { status: 'COMPLETED' }
      },
    },
    review: {
      listPendingReviews: async () => Promise.all((await client.request<WirePlan[]>('/reviews')).map(async p => mapReview(await read(p.plan_id)))),
      getReview: async id => mapReview(await read(id)),
      decide: async (id, input, meta) => {
        try {
          const h = histories.get(id) ?? await read(id)
          await client.request(`/plans/${encodeURIComponent(id)}/rounds/${h.plan.current_round}/decision`, 'POST',
            { action: input.action, reason: input.reason || null, override_reason: input.overrideReason || null, expected_revision: meta.expectedRevision }, meta.idempotencyKey)
          return { status: 'UPDATED', message: 'Quyết định đã được lưu cùng audit.' }
        } catch (error) {
          if (error instanceof ApiError) return { status: error.status === 409 ? 'STALE' : 'ERROR', message: error.message }
          throw error
        }
      },
    },
    audit: { listByPlan: async id => audit(await read(id)), listByRun: async () => { throw new Error('Chọn hồ sơ từ danh sách để xem audit.') } },
    policy: {
      getCurrentPolicy: async () => {
        const c = await client.request<Config>('/config'), policy = c.policy.policy, budget = c.policy.budgets.find(item => item.active)
        return {
          policyVersion: policy.policy_version,
          policyName: 'Marketing auto-approval policy',
          status: policy.auto_approval_policy_enabled ? 'ENABLED' : 'DISABLED',
          dataSource: 'API',
          settings: [
            { label: 'Điểm khả thi', value: `> ${policy.feasibility_threshold}` },
            { label: 'Media confidence', value: `>= ${policy.media_confidence_threshold}` },
            { label: 'Feasibility confidence', value: `>= ${policy.feasibility_confidence_threshold}` },
            { label: 'Hạn mức tự động', value: budget ? `${budget.limit_minor_units} ${budget.currency}` : 'Backend không cung cấp' },
            { label: 'Định dạng tệp', value: policy.allowed_media_types.join(', ') },
            { label: 'Dung lượng tối đa', value: `${Math.round(policy.max_attachment_bytes / 1_000_000)} MB` },
            { label: 'Model được biết', value: policy.known_model_versions.join(', ') },
            { label: 'Trường bắt buộc', value: policy.mandatory_fields.join(', ') },
          ],
          rules: policy.rule_ids.map(ruleId => ({ ruleId })),
        }
      },
      getPolicy: async version => {
        const c = await client.request<Config>('/config'), policy = c.policy.policy
        if (policy.policy_version !== version) return null
        const budget = c.policy.budgets.find(item => item.active)
        return {
          policyVersion: version, policyName: 'Marketing auto-approval policy',
          status: policy.auto_approval_policy_enabled ? 'ENABLED' : 'DISABLED', dataSource: 'API',
          settings: [
            { label: 'Điểm khả thi', value: `> ${policy.feasibility_threshold}` },
            { label: 'Hạn mức tự động', value: budget ? `${budget.limit_minor_units} ${budget.currency}` : 'Backend không cung cấp' },
          ],
          rules: policy.rule_ids.map(ruleId => ({ ruleId })),
        }
      },
    },
    verify: {
      startRun: async suite => {
        const start = new Date().toISOString()
        type Row = {
          case_id: string; passed: boolean; error: string | null; differences: string[]
          started_at: string; completed_at: string; duration_ms: number
          expected: { route: RuntimeOutcome; primary_category: string | null }
          actual: { decision: Decision; questions: unknown[] } | null
        }
        const response = await client.request<{ run_id: string; rows: Row[] }>(`/verify/${suite}`, 'POST', {}, crypto.randomUUID())
        const rows = response.rows.map(r => ({ caseId: r.case_id, expectedAction: r.expected.route, expectedCategory: r.expected.primary_category,
          actualAction: r.actual?.decision.outcome, actualCategory: r.actual?.decision.escalation_category,
          status: r.error ? 'ERROR' as const : r.passed ? 'PASS' as const : 'FAIL' as const,
          reason: r.error ?? (r.differences.join('; ') || r.actual?.decision.reason),
          appliedRuleIds: r.actual?.decision.applied_rule_ids, generatedQuestion: r.actual?.questions,
          startedAt: r.started_at, completedAt: r.completed_at, durationMs: r.duration_ms, pass: r.passed,
          error: r.error ? { code: 'VERIFY_FAILED', message: r.error } : null }))
        const run: VerifyRun = { runId: response.run_id, suite, status: 'COMPLETED', rows, startedAt: start, completedAt: new Date().toISOString(), dataSource: 'API',
          summary: { totalCases: rows.length, completedCases: rows.length, passedCases: rows.filter(r => r.pass).length,
            failedCases: rows.filter(r => r.status === 'FAIL').length, errorCases: rows.filter(r => r.status === 'ERROR').length, progressPercent: 100 } }
        runs.set(run.runId, run); return run
      },
      getRun: async id => runs.get(id) ?? null,
    },
  }
}
