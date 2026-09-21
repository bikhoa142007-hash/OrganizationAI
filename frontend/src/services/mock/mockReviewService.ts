import type {
  PlanId,
  ReviewDecisionInput,
  ReviewDecisionResult,
  ReviewDetail,
  ReviewItem,
  ServiceRequestMeta,
} from '../../types'
import type { ReviewService } from '../interfaces'
import type { MockAuditService } from './mockAuditService'

export type MockReviewScenario = 'normal' | 'stale' | 'error'

export class MockReviewService implements ReviewService {
  private readonly scenario: MockReviewScenario
  private readonly reviews: ReviewDetail[]
  private readonly auditService?: MockAuditService

  constructor(scenario: MockReviewScenario = 'normal', auditService?: MockAuditService) {
    this.scenario = scenario
    this.auditService = auditService
    this.reviews = [
      {
        planId: 'mock-review-1',
        title: 'Chiến dịch ra mắt sản phẩm',
        revision: 4,
        status: 'PENDING',
        escalationCategory: 'Cần con người',
        reason: 'Service chuyển tiếp hồ sơ để người có thẩm quyền xem xét.',
        priority: 'Service cung cấp',
        authority: 'Service cung cấp',
        createdAt: '2026-09-21T08:30:00Z',
        originalInput: { Campaign: 'Chiến dịch ra mắt sản phẩm', Audience: 'Service cung cấp', Channel: 'Service cung cấp' },
        attachments: ['campaign-brief.pdf', 'key-visual.png'],
        evidence: [
          { id: 'evidence-1', label: 'VLM evidence', value: 'Service cung cấp vùng thông tin cần người xem xét.' },
          { id: 'evidence-2', label: 'Nguồn', value: 'Snapshot mock của ReviewService.' },
        ],
        appliedRuleIds: ['service-rule-1', 'service-rule-2'],
        handoffQuestions: ['Service yêu cầu người có thẩm quyền xác nhận nội dung hồ sơ.'],
        currentDecision: 'Đang chờ human review',
      },
      {
        planId: 'mock-review-2',
        title: 'Kế hoạch truyền thông quý IV',
        revision: 2,
        status: 'PENDING',
        escalationCategory: 'Service cung cấp',
        reason: 'Lý do chuyển tiếp do service trả về.',
        priority: 'Service cung cấp',
        authority: 'Service cung cấp',
        createdAt: '2026-09-21T09:15:00Z',
        originalInput: { Campaign: 'Kế hoạch truyền thông quý IV', Objective: 'Service cung cấp' },
        attachments: [],
        evidence: [{ id: 'evidence-3', label: 'Evidence', value: 'Service chưa cung cấp thêm bằng chứng.' }],
        appliedRuleIds: [],
        handoffQuestions: [],
        currentDecision: 'Đang chờ human review',
      },
    ]
  }

  async listPendingReviews(): Promise<ReviewItem[]> {
    if (this.scenario === 'error') throw new Error('MOCK_REVIEW_QUEUE_ERROR')
    return this.reviews.filter((review) => review.status === 'PENDING')
  }

  async getReview(planId: PlanId): Promise<ReviewDetail | null> {
    if (this.scenario === 'error') throw new Error('MOCK_REVIEW_DETAIL_ERROR')
    return this.reviews.find((review) => review.planId === planId) ?? null
  }

  async decide(
    planId: PlanId,
    input: ReviewDecisionInput,
    _meta: ServiceRequestMeta,
  ): Promise<ReviewDecisionResult> {
    if (!input.reason.trim()) return { status: 'ERROR', message: 'Reason là bắt buộc để hoàn tất action.' }
    if (this.scenario === 'error') return { status: 'ERROR', message: 'Mock service không thể ghi nhận action.' }
    if (this.scenario === 'stale' || planId === 'mock-review-stale') {
      return { status: 'STALE', message: 'Hồ sơ đã được xử lý trước đó. Vui lòng tải lại queue.' }
    }

    const review = this.reviews.find((item) => item.planId === planId)
    if (!review || review.status !== 'PENDING') {
      return { status: 'STALE', message: 'Trạng thái hồ sơ đã thay đổi. Vui lòng tải lại queue.' }
    }

    const previousState = { planStatus: 'PENDING_APPROVAL' as const, processingStage: 'HUMAN_REVIEW_REQUIRED' as const, approvalRoundStatus: 'ACTIVE' as const }
    const nextStatus = input.action === 'APPROVED' ? 'APPROVED' : input.action === 'REJECTED' ? 'REJECTED' : 'CHANGES_REQUESTED'
    review.status = nextStatus
    review.currentDecision = input.action
    review.reason = input.reason
    this.auditService?.appendReviewDecision(planId, input.action, input.reason, previousState, { planStatus: nextStatus === 'APPROVED' ? 'APPROVED' : nextStatus === 'REJECTED' ? 'REJECTED' : 'PENDING_APPROVAL', processingStage: null, approvalRoundStatus: 'CLOSED' })
    return { status: 'UPDATED', review, message: 'Service đã cập nhật trạng thái hồ sơ.' }
  }
}
