import { createContext, useContext, type PropsWithChildren } from 'react'
import type { FrontendServices } from './interfaces'

const ServicesContext = createContext<FrontendServices | null>(null)

export function ServicesProvider({ services, children }: PropsWithChildren<{ services: FrontendServices }>) {
  return <ServicesContext.Provider value={services}>{children}</ServicesContext.Provider>
}

export function useServices(): FrontendServices {
  const services = useContext(ServicesContext)
  if (!services) {
    throw new Error('ServicesProvider is required before using frontend services.')
  }
  return services
}
