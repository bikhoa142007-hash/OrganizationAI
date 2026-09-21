import type { PolicyView } from '../../types'
import type { PolicyService } from '../interfaces'
import { mockCurrentPolicy } from './mockPolicyData'

export class MockPolicyService implements PolicyService {
  async getCurrentPolicy(): Promise<PolicyView | null> {
    return clonePolicy(mockCurrentPolicy)
  }

  async getPolicy(policyVersion: string): Promise<PolicyView | null> {
    return policyVersion === mockCurrentPolicy.policyVersion ? clonePolicy(mockCurrentPolicy) : null
  }
}

function clonePolicy(policy: PolicyView): PolicyView {
  return { ...policy, rules: policy.rules.map((rule) => ({ ...rule })) }
}
