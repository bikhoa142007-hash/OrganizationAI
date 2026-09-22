export type PlanId = string
export type RunId = string
export type AuditEventId = string

export type PlanStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
export type ProcessingStage =
  | 'AI_PENDING'
  | 'AI_PROCESSING'
  | 'HUMAN_REVIEW_REQUIRED'
  | 'AI_AUTO_APPROVED'
  | 'AI_PROCESSING_FAILED'
export type RuntimeOutcome = 'AUTO_APPROVED' | 'HUMAN_REVIEW_REQUIRED'
export type HumanAction = 'APPROVED' | 'REJECTED' | 'REQUEST_CHANGES'
export type VerifySuite = 'general' | 'escalation'
export type ProcessingStatus = 'PROCESSING' | 'STOPPED' | 'COMPLETED' | 'FAILED'

export interface AppCapabilitySet {
  stop: boolean
  retryEvaluation: boolean
  requestChanges: boolean
}

export interface AppActor {
  id: string
  roles: string[]
}

export interface AppConfig {
  environment: string
  actor: string
  roles: string[]
  actors: AppActor[]
  checkerId: string
  department: string
  currency: string
  provider: string
  mockMode: string
  allowedMediaTypes: string[]
  maxAttachmentBytes: number
  capabilities: AppCapabilitySet
}

/** UI-only input boundary. The API payload is intentionally unresolved until Role 2 confirms it. */
export type PlanDraftPayload = Record<string, unknown>

export interface AttachmentRef {
  attachmentId: string
  mediaType: string
  byteSize: number
}

export interface PlanState {
  planStatus: PlanStatus
  processingStage: ProcessingStage | null
  approvalRoundStatus: 'ACTIVE' | 'CLOSED' | null
}

export interface PlanSummary {
  planId: PlanId
  makerId?: string
  title?: string
  state?: PlanState
  revision?: number
}

export interface PlanView extends PlanSummary {
  planVersion?: number
  approvalRound?: number
  inputHash?: string
  policyVersion?: string
  payload?: PlanDraftPayload
  attachments?: AttachmentRef[]
}

export interface ProcessingSnapshot {
  status: ProcessingStatus
  progress?: number
  message?: string
  updatedAt?: string
  error?: { code: string; message: string } | null
}

export type ResultVariant = 'SYSTEM_DECISION' | 'HUMAN_REVIEW' | 'HUMAN_DECISION' | 'ERROR'

export interface ResultAction {
  id: string
  label: string
  href?: string
}

export interface ResultEvidence {
  id: string
  label: string
  value: string
}

/** UI snapshot boundary. Result values are supplied by the service and are not derived by the page. */
export interface ResultView {
  planId: PlanId
  variant: ResultVariant
  title: string
  statusLabel: string
  decisionSource?: string
  score?: number | null
  confidence?: number | null
  media?: {
    status?: string
    attachments?: string[]
  }
  budget?: {
    value?: string
    limit?: string
  }
  ruleIds?: string[]
  evidence?: ResultEvidence[]
  reason?: string
  policyVersion?: string
  modelVersion?: string
  reviewDetails?: {
    question?: string
    authority?: string
  }
  error?: { code: string; message: string }
  actions?: ResultAction[]
}

export interface ServiceRequestMeta {
  expectedRevision?: number
  idempotencyKey?: string
  correlationId?: string
}

export interface ReviewItem extends PlanSummary {
  escalationCategory?: string
  reason?: string
  createdAt?: string
  priority?: string
  authority?: string
  status?: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CHANGES_REQUESTED'
}

export interface ReviewEvidence {
  id: string
  label: string
  value: string
}

export interface ReviewDetail extends ReviewItem {
  originalInput?: Record<string, string>
  attachments?: string[]
  evidence?: ReviewEvidence[]
  appliedRuleIds?: string[]
  handoffQuestions?: string[]
  currentDecision?: string
}

export interface ReviewDecisionInput {
  action: HumanAction
  reason: string
  overrideReason?: string
}

export interface ReviewDecisionResult {
  status: 'UPDATED' | 'STALE' | 'ERROR'
  review?: ReviewDetail | null
  message?: string
}

export interface AuditEvent {
  eventId: AuditEventId
  action: string
  actorId?: string
  timestamp?: string
  inputVersion?: string
  policyVersion?: string
  modelVersion?: string
  reason?: string
  correlationId?: string
  runId?: string
  decisionId?: string
  outcome?: string
  humanAction?: string
  overrideReason?: string
  appliedRuleIds?: string[]
  previousState?: PlanState | null
  newState?: PlanState | null
}

export interface VerifyResultRow {
  caseId: string
  caseName?: string
  input?: string
  expectedAction?: RuntimeOutcome | null
  expectedCategory?: string | null
  actualAction?: RuntimeOutcome | null
  actualCategory?: string | null
  generatedQuestion?: unknown[]
  appliedRuleIds?: string[]
  status?: 'PENDING' | 'RUNNING' | 'PASS' | 'FAIL' | 'ERROR'
  reason?: string
  startedAt?: string
  completedAt?: string
  auditReference?: string
  durationMs?: number
  pass?: boolean
  error?: { code: string; message: string } | null
}

export interface VerifyRunSummary {
  totalCases: number
  completedCases: number
  passedCases: number
  failedCases: number
  errorCases: number
  progressPercent: number
}

export interface VerifyRun {
  runId: RunId
  suite: VerifySuite
  status: 'NOT_RUN' | 'RUNNING' | 'COMPLETED' | 'ERROR'
  rows: VerifyResultRow[]
  summary?: VerifyRunSummary
  startedAt?: string
  completedAt?: string
  currentCaseId?: string | null
  error?: { code: string; message: string } | null
  dataSource?: 'MOCK' | 'API'
}

export interface PolicyRuleView {
  ruleId: string
  title?: string
  description?: string
  condition?: string
  scope?: string
  action?: string
  effect?: string
  reference?: string
}

export interface PolicyView {
  policyVersion: string
  policyName?: string
  status?: string
  dataSource?: 'MOCK' | 'API'
  settings?: Array<{ label: string; value: string }>
  rules: PolicyRuleView[]
}
