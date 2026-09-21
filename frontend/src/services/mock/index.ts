import type { FrontendServices } from '../interfaces'
import { MockAuditService } from './mockAuditService'
import { MockPlanService } from './mockPlanService'
import { MockPolicyService } from './mockPolicyService'
import { MockReviewService } from './mockReviewService'
import { MockVerifyService } from './mockVerifyService'
import type { MockProcessingScenario, MockResultVariant } from './mockPlanService'
import type { MockReviewScenario } from './mockReviewService'

export function createMockServices(options?: { processingScenario?: MockProcessingScenario; resultVariant?: MockResultVariant; reviewScenario?: MockReviewScenario }): FrontendServices {
  const audit = new MockAuditService()
  return {
    plan: new MockPlanService(options?.processingScenario, options?.resultVariant),
    review: new MockReviewService(options?.reviewScenario, audit),
    audit,
    verify: new MockVerifyService(),
    policy: new MockPolicyService(),
  }
}
