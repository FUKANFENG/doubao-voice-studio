export interface AccountStatus {
  loaded: boolean
  auth_ok: boolean
  cookie_chars: number
  can_manage: boolean
  local_available: boolean
  tool_available: boolean
}

async function request(path: string, body?: unknown, signal?: AbortSignal): Promise<AccountStatus> {
  const response = await fetch('/api/auth/' + path, {
    method: body === undefined ? 'GET' : 'POST', cache: 'no-store',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Doubao-Local': '1' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal || AbortSignal.timeout(25000),
  })
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null)
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null
    throw new Error(typeof detail === 'string' ? detail : '操作未完成，请检查服务连接后重试。')
  }
  return response.json()
}

export const fetchAccountStatus = (signal?: AbortSignal) => request('status', undefined, signal)
export const readLocalAccount = (requestUrl: string) => request('local', { request_url: requestUrl.trim() })
export const importAccount = (config: unknown) => request('import', { config })
