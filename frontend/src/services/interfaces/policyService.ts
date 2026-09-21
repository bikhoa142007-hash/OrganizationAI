import type { PolicyView } from '../../types'

export interface PolicyService {
  getCurrentPolicy(): Promise<PolicyView | null>
  getPolicy(policyVersion: string): Promise<PolicyView | null>
}
