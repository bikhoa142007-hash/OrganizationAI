export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public correlationId?: string) { super(message) }
}

export class ApiClient {
  private pending = new Map<string, string>()
  constructor(private baseUrl: string, private actor: () => string, private transport: typeof fetch = (...args) => fetch(...args)) {}

  async request<T>(path: string, method = 'GET', body?: unknown, key?: string): Promise<T> {
    const multipart = body instanceof FormData
    const fingerprint = `${this.actor()}:${method}:${path}:${multipart ? Array.from(body.entries()).map(([k, v]) => `${k}:${v instanceof File ? `${v.name}:${v.size}:${v.lastModified}` : v}`).join('|') : JSON.stringify(body)}`
    const headers: Record<string, string> = { 'X-Demo-Actor': this.actor() }
    if (method !== 'GET') {
      const stableKey = key ?? this.pending.get(fingerprint) ?? crypto.randomUUID()
      this.pending.set(fingerprint, stableKey)
      headers['Idempotency-Key'] = stableKey
    }
    if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json'
    let response: Response
    try {
      response = await this.transport(this.baseUrl.replace(/\/$/, '') + path, {
        method, headers, body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
      })
    } catch {
      throw new ApiError('NETWORK_ERROR', 'Không kết nối được backend. Thử lại sẽ giữ cùng idempotency key.', 0)
    }
    const data = await response.json()
    if (!response.ok) {
      if (response.status < 500) this.pending.delete(fingerprint)
      const guidance: Record<number, string> = {
        401: 'Phiên demo không hợp lệ. Chọn lại actor demo.',
        403: 'Actor này không có quyền thực hiện hành động trên hồ sơ.',
        409: 'Hồ sơ đã thay đổi hoặc đã được xử lý. Tải lại trước khi tiếp tục.',
        422: 'Kiểm tra dữ liệu và các trường bắt buộc trước khi gửi lại.',
      }
      throw new ApiError(data.code ?? 'HTTP_ERROR', `${guidance[response.status] ?? 'Yêu cầu thất bại.'} ${data.message ?? ''}`.trim(), response.status, data.correlation_id)
    }
    this.pending.delete(fingerprint)
    return data as T
  }

  async attachment(path: string): Promise<Blob> {
    const response = await this.transport(this.baseUrl.replace(/\/$/, '') + path, { headers: { 'X-Demo-Actor': this.actor() } })
    if (!response.ok) throw new ApiError('ATTACHMENT_ERROR', 'Không tải được ảnh riêng tư.', response.status)
    return response.blob()
  }
}

export const demoActor = () => sessionStorage.getItem('organization-demo-actor') ?? 'DEMO-MAKER-01'
export const api = new ApiClient(import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api', demoActor)
