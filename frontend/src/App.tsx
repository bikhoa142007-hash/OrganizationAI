import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './routes/AppRoutes'
import { ServicesProvider } from './services/ServiceProvider'
import { createApiServices } from './services/api'
import { SessionProvider } from './services/SessionProvider'

const services = createApiServices()

export function App() {
  return (
    <BrowserRouter>
      <ServicesProvider services={services}>
        <SessionProvider><AppRoutes /></SessionProvider>
      </ServicesProvider>
    </BrowserRouter>
  )
}
