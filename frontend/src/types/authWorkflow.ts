export interface WorkflowPayload {
  title: string
  objective: string
  summary: string
  department: string
  start_date: string
  end_date: string
  budget_minor_units: string
  currency: string
  target_audience: string
  channels: string[]
  kpi_expected: string
  notes: string
}

export interface WorkflowAttachment {
  id: string
  filename: string
  media_type: string
  byte_size: number
  content_hash: string
  created_at: string
}

export interface WorkflowEvent {
  id: string
  actor_id: string | null
  actor_type: 'HUMAN' | 'SYSTEM'
  actor_name: string
  action: string
  status_before: string | null
  status_after: string
  details: Record<string, unknown>
  created_at: string
}

export interface WorkflowVersion {
  version_number: number
  round_number: number
  payload: WorkflowPayload
  attachments: Array<Pick<WorkflowAttachment, 'id' | 'filename' | 'media_type' | 'byte_size' | 'content_hash'>>
  snapshot_hash: string | null
  submitted_by: string
  created_at: string
}

export interface WorkflowEvaluation {
  evaluation_id: string
  plan_id: string
  plan_version: number
  approval_round: number
  run_id: string
  status: 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT'
  provider: 'LOCAL_VLM' | 'MOCK_VLM'
  model_version: string | null
  policy_version: string
  input_hash: string
  media_result: 'PASS' | 'REVIEW_REQUIRED' | null
  media_confidence: number | null
  feasibility_score: number | null
  feasibility_confidence: number | null
  proposed_action: 'RECOMMEND_AUTO_APPROVAL' | 'RECOMMEND_HUMAN_REVIEW' | null
  reason: string
  media_findings: Array<{ finding_id: string; severity: 'HARD_VIOLATION' | 'WARNING'; description: string; rule_id: string | null; evidence_refs: string[] }>
  evidence: Array<{ evidence_id: string; source_type: string; source_ref: string; observation: string; content_hash: string | null }>
  evidence_conflicts: Array<{ conflict_id: string; description: string; evidence_refs: string[] }>
  missing_facts: string[]
  agent_errors: Array<{ component: string; code: string; message: string }>
  criterion_scores: Array<{ criterion_id: string; score: number; maximum_score: number; rationale: string; evidence_refs: string[] }>
  assumptions: string[]
}

export interface WorkflowAiEvaluation {
  id: string
  version_number: number
  round_number: number
  run_id: string
  evaluation_id: string
  correlation_id: string
  input_hash: string
  provider: 'LOCAL_VLM' | 'MOCK_VLM'
  model_id: string | null
  model_version: string | null
  policy_version: string
  policy_snapshot_id: string
  policy_snapshot_hash: string
  status: 'PENDING' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT'
  attempts: number
  retried: boolean
  evaluation: WorkflowEvaluation | null
  visual_extraction: WorkflowVlmExtraction | null
  failure_reason: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface WorkflowVlmEvidence {
  evidence_id: string
  kind: 'OCR_TEXT' | 'OBSERVATION'
  text: string
  source_attachment_id: string
  source_content_hash: string
}

export interface WorkflowVlmUncertainty {
  text: string
  source_attachment_id: string
  source_content_hash: string
}

export interface WorkflowVlmAttachmentExtraction {
  attachment_id: string
  content_hash: string
  media_type: string
  status: 'COMPLETE' | 'PARTIAL' | 'UNREADABLE' | 'FAILED'
  ocr_text: string
  evidence: WorkflowVlmEvidence[]
  uncertainties: WorkflowVlmUncertainty[]
  error_code?: string
}

export interface WorkflowVlmExtraction {
  status: 'SUCCEEDED' | 'PARTIAL' | 'UNREADABLE' | 'FAILED'
  error_code?: string
  provider: 'LOCAL_VLM'
  model_id: string | null
  model_revision: string | null
  reported_model_id: string | null
  prompt_version: string
  schema_version: string
  run_id: string
  plan_id: string
  plan_version: number
  approval_round: number
  input_hash: string
  raw_output_hash: string | null
  started_at: string
  completed_at: string
  attachments: WorkflowVlmAttachmentExtraction[]
}

export interface WorkflowEngineDecision {
  id: string
  version_number: number
  round_number: number
  decision_id: string
  outcome: 'AUTO_APPROVED' | 'HUMAN_REVIEW_REQUIRED'
  decision: {
    reason: string
    applied_rule_ids: string[]
    rule_checks: Array<{ rule_id: string; result: 'PASS' | 'FAIL' | 'UNKNOWN'; observed_value: unknown; applicable_rule_or_limit: string; evidence_refs: string[] }>
    budget_validation: { result: 'PASS' | 'FAIL' | 'UNKNOWN'; budget_minor_units: string | null; limit_minor_units: string | null; currency: string | null }
    escalation_category: string | null
  }
  created_at: string
}

export interface WorkflowPlan {
  id: string
  code: string
  payload: WorkflowPayload
  status: 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
  processing_stage: string
  maker_id: string
  maker_name: string
  checker_id: string | null
  checker_name: string | null
  current_version: number
  current_round: number
  revision: number
  decision_reason: string | null
  attachments: WorkflowAttachment[]
  versions: WorkflowVersion[]
  ai_evaluations: WorkflowAiEvaluation[]
  engine_decisions: WorkflowEngineDecision[]
  history: WorkflowEvent[]
  created_at: string
  updated_at: string
}

export interface WorkflowChecker {
  id: string
  display_name: string
}
