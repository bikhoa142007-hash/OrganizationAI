export interface AuthUser {
  id: string
  user_code: string
  username: string
  email: string | null
  phone: string | null
  display_name: string
  status: 'ACTIVE' | 'DISABLED'
  roles: string[]
}
