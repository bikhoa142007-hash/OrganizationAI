import type {
  AttachmentRef,
  PlanDraftPayload,
  PlanId,
  PlanView,
  ProcessingSnapshot,
  ResultVariant,
  ResultView,
  ServiceRequestMeta,
} from '../../types'
import type { PlanService } from '../interfaces'

export type MockProcessingScenario = 'success' | 'failed' | 'network-error'
export type MockResultVariant = 'system' | 'human-review' | 'human' | 'error'

export class MockPlanService implements PlanService {
  private mockPlanSequence = 0
  private processingReads = 0
  private processingScenario: MockProcessingScenario
  private resultVariant: MockResultVariant

  constructor(processingScenario: MockProcessingScenario = 'success', resultVariant: MockResultVariant = 'system') {
    this.processingScenario = processingScenario
    this.resultVariant = resultVariant
  }

  async listPlans(): Promise<PlanView[]> {
    return []
  }

  async getPlan(_planId: PlanId): Promise<PlanView | null> {
    return null
  }

  async saveDraft(
    planId: PlanId,
    payload: PlanDraftPayload,
    _meta: ServiceRequestMeta,
  ): Promise<PlanView | null> {
    const resolvedPlanId = planId || `mock-plan-${++this.mockPlanSequence}`
    return {
      planId: resolvedPlanId,
      payload,
      revision: 1,
      state: {
        planStatus: 'DRAFT',
        processingStage: null,
        approvalRoundStatus: null,
      },
    }
  }

  async uploadAttachment(
    _planId: PlanId,
    _file: File,
    _meta: ServiceRequestMeta,
  ): Promise<AttachmentRef | null> {
    return null
  }

  async submitPlan(_planId: PlanId, _meta: ServiceRequestMeta): Promise<PlanView | null> {
    this.processingReads = 0
    return null
  }

  async getProcessingStatus(_planId: PlanId): Promise<ProcessingSnapshot> {
    if (this.processingScenario === 'network-error') {
      throw new Error('MOCK_NETWORK_ERROR')
    }

    if (this.processingScenario === 'failed') {
      return {
        status: 'FAILED',
        message: 'Mock service không thể tiếp tục xử lý phiên này.',
        error: { code: 'MOCK_PROCESSING_FAILED', message: 'Mock processing failed.' },
      }
    }

    const snapshots: ProcessingSnapshot[] = [
      { status: 'PROCESSING', progress: 0, message: 'Service đã nhận hồ sơ.' },
      { status: 'PROCESSING', progress: 35, message: 'Service đang xử lý hồ sơ.' },
      { status: 'PROCESSING', progress: 70, message: 'Service đang hoàn tất quá trình xử lý.' },
      { status: 'COMPLETED', progress: 100, message: 'Service đã báo hoàn tất xử lý.' },
    ]
    const snapshot = snapshots[Math.min(this.processingReads, snapshots.length - 1)]
    this.processingReads += 1
    return snapshot
  }

  async getResult(planId: PlanId): Promise<ResultView | null> {
    const variantMap: Record<MockResultVariant, ResultVariant> = {
      system: 'SYSTEM_DECISION',
      'human-review': 'HUMAN_REVIEW',
      human: 'HUMAN_DECISION',
      error: 'ERROR',
    }
    const variant = variantMap[this.resultVariant]
    if (variant === 'ERROR') {
      return {
        planId,
        variant,
        title: 'Không thể tải kết quả',
        statusLabel: 'Lỗi kết quả',
        error: { code: 'MOCK_RESULT_ERROR', message: 'Mock service không cung cấp được snapshot kết quả.' },
        actions: [
          { id: 'retry-result', label: 'Thử tải lại', href: planId ? `/plans/${planId}/result` : '/plans/result' },
          { id: 'new-plan', label: 'Tạo hồ sơ mới', href: '/plans/new' },
        ],
      }
    }

    if (variant === 'HUMAN_REVIEW') {
      return {
        planId,
        variant,
        title: 'Đang chờ human review',
        statusLabel: 'Chờ người phụ trách xem xét',
        decisionSource: 'human review',
        reviewDetails: {
          question: 'Hồ sơ đã được chuyển tới bước xem xét của con người.',
          authority: 'Thông tin người duyệt sẽ do service cung cấp.',
        },
        evidence: [{ id: 'review-state', label: 'Trạng thái service', value: 'Đang chờ human review' }],
        actions: [{ id: 'back-home', label: 'Về Landing', href: '/' }],
      }
    }

    const isHumanDecision = variant === 'HUMAN_DECISION'
    return {
      planId,
      variant,
      title: isHumanDecision ? 'Kết quả do human quyết định' : 'Kết quả từ hệ thống',
      statusLabel: isHumanDecision ? 'Đã có quyết định của human' : 'Đã có kết quả hệ thống',
      decisionSource: isHumanDecision ? 'human' : 'system',
      score: isHumanDecision ? null : 0.82,
      confidence: isHumanDecision ? null : 0.91,
      media: { status: 'Service đã nhận media đính kèm.', attachments: ['brief.pdf'] },
      budget: { value: 'Service chưa cung cấp giá trị thực tế.', limit: 'Service chưa cung cấp giới hạn.' },
      ruleIds: ['service-rule-1', 'service-rule-2'],
      evidence: [
        { id: 'evidence-1', label: 'Nguồn dữ liệu', value: 'Snapshot do MockPlanService cung cấp.' },
        { id: 'evidence-2', label: 'Phạm vi', value: 'Chỉ hiển thị dữ liệu service trả về.' },
      ],
      reason: 'Reason được service cung cấp cho màn hình kết quả.',
      policyVersion: 'service-policy-version',
      modelVersion: 'service-model-version',
      actions: [{ id: 'back-home', label: 'Về Landing', href: '/' }],
    }
  }

  async stopProcessing(_planId: PlanId, _meta: ServiceRequestMeta): Promise<ProcessingSnapshot> {
    return { status: 'STOPPED', message: 'Service đã xác nhận hồ sơ được dừng.' }
  }

  async retryProcessing(_planId: PlanId, _meta: ServiceRequestMeta): Promise<ProcessingSnapshot> {
    this.processingScenario = 'success'
    this.processingReads = 0
    return { status: 'PROCESSING', progress: 0, message: 'Service đã bắt đầu lại quá trình xử lý.' }
  }
}
