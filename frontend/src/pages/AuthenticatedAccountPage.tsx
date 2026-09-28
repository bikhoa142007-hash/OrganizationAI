import { useAuth } from '../context/AuthContext'
import { Link } from 'react-router-dom'

export function AuthenticatedAccountPage() {
  const { user, roles, logout } = useAuth()

  return <main className="auth-account">
    <h1>OrganizationAI</h1>
    <h2>Tài khoản đã đăng nhập</h2>
    <p>Tên hiển thị: {user?.display_name}</p>
    <p>Tên đăng nhập: {user?.username}</p>
    <p>Mã người dùng: {user?.user_code}</p>
    <p>Liên hệ: {user?.email ?? user?.phone}</p>
    <p>Vai trò: {roles.length ? roles.join(', ') : 'Chưa có vai trò'}</p>
    <p>Trạng thái: {user?.status === 'ACTIVE' ? 'Đang hoạt động' : 'Đã vô hiệu hóa'}</p>
    <button type="button" onClick={() => { void logout() }}>Đăng xuất</button>
    {roles.includes('MAKER') && <p><Link to="/workflow/plans">Mở workflow PostgreSQL của Maker</Link></p>}
    {roles.includes('CHECKER') && <p><Link to="/workflow/reviews">Mở hàng chờ Checker</Link></p>}
    <p>Workflow Auth lưu dữ liệu trong PostgreSQL. Judge Demo bên dưới giữ actor tổng hợp riêng.</p>
    <p><Link to="/">Mở luồng marketing demo</Link></p>
  </main>
}
