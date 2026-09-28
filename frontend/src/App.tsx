import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './routes/AppRoutes'
import { ServicesProvider } from './services/ServiceProvider'
import { createApiServices } from './services/api'
import { AuthProvider } from './context/AuthContext'

const services = createApiServices()

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ServicesProvider services={services}>
          <AppRoutes />
        </ServicesProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
