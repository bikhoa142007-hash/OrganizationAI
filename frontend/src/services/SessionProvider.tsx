import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren } from 'react'
import type { AppConfig } from '../types'
import { api, demoActor } from './api/client'

interface WireConfig {
  environment: string
  actor: string
  roles: string[]
  actors: Array<{ id: string; roles: string[] }>
  checker_id: string
  department: string
  currency: string
  provider: string
  mock_mode: string
  policy: {
    policy: {
      allowed_media_types: string[]
      max_attachment_bytes: number
    }
  }
  capabilities: { stop: boolean; retry_evaluation: boolean; request_changes: boolean }
}

interface SessionValue {
  config: AppConfig | null
  loading: boolean
  error: string
  refresh: () => Promise<void>
  switchActor: (actorId: string) => void
  hasRole: (role: string) => boolean
}

const fallbackSession: SessionValue = {
  config: null,
  loading: false,
  error: '',
  refresh: async () => undefined,
  switchActor: () => undefined,
  hasRole: () => false,
}

const SessionContext = createContext<SessionValue>(fallbackSession)

export function SessionProvider({ children }: PropsWithChildren) {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const value = await api.request<WireConfig>('/config')
      setConfig({
        environment: value.environment,
        actor: value.actor,
        roles: value.roles,
        actors: value.actors,
        checkerId: value.checker_id,
        department: value.department,
        currency: value.currency,
        provider: value.provider,
        mockMode: value.mock_mode,
        allowedMediaTypes: value.policy.policy.allowed_media_types,
        maxAttachmentBytes: value.policy.policy.max_attachment_bytes,
        capabilities: {
          stop: value.capabilities.stop,
          retryEvaluation: value.capabilities.retry_evaluation,
          requestChanges: value.capabilities.request_changes,
        },
      })
    } catch (reason) {
      setConfig(null)
      setError(reason instanceof Error ? reason.message : 'Không thể tải thông tin phiên.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const value = useMemo<SessionValue>(() => ({
    config,
    loading,
    error,
    refresh,
    switchActor: (actorId) => {
      if (!actorId || actorId === demoActor()) return
      sessionStorage.setItem('organization-demo-actor', actorId)
      window.location.assign('/')
    },
    hasRole: (role) => Boolean(config?.roles.includes(role)),
  }), [config, error, loading, refresh])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  return useContext(SessionContext)
}
