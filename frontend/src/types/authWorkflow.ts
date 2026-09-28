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
  actor_id: string
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
  submitted_by: string
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
  history: WorkflowEvent[]
  created_at: string
  updated_at: string
}

export interface WorkflowChecker {
  id: string
  display_name: string
}
