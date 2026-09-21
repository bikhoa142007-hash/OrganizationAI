import { Link } from 'react-router-dom'

export function LandingPage() {
  return (
    <div className="landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="hero-copy">
          <span className="section-kicker">Judge Demo Mode</span>
          <h2 id="landing-title">Kiểm tra kế hoạch marketing trong một luồng rõ ràng.</h2>
          <p className="hero-description">
            OrganizationAI hỗ trợ xem xét kế hoạch marketing qua một quy trình có thể theo dõi,
            từ hồ sơ mới đến kết quả, Verify, Policy và lịch sử audit.
          </p>
          <div className="hero-actions">
            <Link className="button button-primary" to="/plans/new">
              Hồ sơ mới
            </Link>
            <Link className="button button-secondary" to="/verify">
              Verify
            </Link>
          </div>
          <p className="demo-status">
            <span className="status-dot" aria-hidden="true" />
            Chọn actor demo trên thanh điều hướng. Quyền được kiểm tra ở backend.
          </p>
        </div>
        <aside className="demo-panel" aria-label="Thông tin phiên demo">
          <div className="panel-heading">
            <span className="panel-icon" aria-hidden="true">◎</span>
            <div>
              <p className="panel-label">Phiên hiện tại</p>
              <h3>Judge Demo Mode</h3>
            </div>
          </div>
          <dl className="demo-facts">
            <div>
              <dt>Truy cập</dt>
              <dd>Không đăng nhập</dd>
            </div>
            <div>
              <dt>Dữ liệu</dt>
              <dd>Mô phỏng</dd>
            </div>
            <div>
              <dt>Điểm vào</dt>
              <dd>Hồ sơ mới hoặc Verify</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className="landing-links" aria-labelledby="landing-links-title">
        <div className="section-heading">
          <span className="section-kicker">Điều hướng</span>
          <h2 id="landing-links-title">Các điểm kiểm tra chính</h2>
        </div>
        <div className="link-grid">
          <Link className="link-card link-card-primary" to="/plans/new">
            <span className="card-index">01</span>
            <span>
              <strong>Hồ sơ mới</strong>
              <small>Tải lên kế hoạch để bắt đầu luồng xử lý.</small>
            </span>
            <span className="card-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="link-card" to="/verify">
            <span className="card-index">02</span>
            <span>
              <strong>Verify</strong>
              <small>Mở khu vực kiểm tra các luồng đã được chuẩn bị.</small>
            </span>
            <span className="card-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="link-card" to="/policy">
            <span className="card-index">03</span>
            <span>
              <strong>Policy</strong>
              <small>Xem bộ quy định ở chế độ chỉ đọc.</small>
            </span>
            <span className="card-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="link-card" to="/audit">
            <span className="card-index">04</span>
            <span>
              <strong>Audit history</strong>
              <small>Tra lại lịch sử hành động của hồ sơ và lần chạy.</small>
            </span>
            <span className="card-arrow" aria-hidden="true">→</span>
          </Link>
        </div>
      </section>

      <section className="limitations" aria-labelledby="limitations-title">
        <div>
          <span className="section-kicker">Giới hạn hiện tại</span>
          <h2 id="limitations-title">Phiên này tập trung vào khả năng kiểm tra luồng.</h2>
        </div>
        <ul>
          <li>Giao diện dùng backend FastAPI và SQLite thật; đánh giá AI dùng MockVLMProvider trong demo.</li>
          <li>Thông tin trong phiên demo là dữ liệu mô phỏng và không đại diện cho quyết định thực tế.</li>
          <li>Policy là cấu hình tổng hợp; audit và phiên bản được lưu trên backend.</li>
        </ul>
      </section>
    </div>
  )
}
