export interface ChatMessage {
  id: string; role: 'user' | 'assistant'; content: string
  status: 'done' | 'streaming' | 'stopped' | 'error'; error: string
  created_at: number; request_id: string
}
export interface ChatSessionInfo {
  id: string; title: string; created_at: number; updated_at: number; generating: boolean
}
export interface ChatSession extends ChatSessionInfo { messages: ChatMessage[] }
export type ChatEvent = { type: 'session' | 'done'; session: ChatSession }
  | { type: 'text'; message_id: string; text: string }

async function checked(response: Response) {
  if (!response.ok) {
    let message = '请求失败，请稍后再试。'
    try {
      const body = await response.json()
      const detail = body.detail
      if (typeof detail === 'string') message = detail
      else if (detail?.message) message = detail.message
      else if (Array.isArray(detail)) message = '消息参数不正确，请检查长度后重试。'
    } catch { /* The server may have returned a non-JSON error. */ }
    throw new Error(message)
  }
  return response
}
export async function listChatSessions(): Promise<ChatSessionInfo[]> {
  return (await checked(await fetch('/api/chat/sessions'))).json()
}
export async function getChatSession(id: string): Promise<ChatSession> {
  return (await checked(await fetch('/api/chat/sessions/' + encodeURIComponent(id)))).json()
}
export async function createChatSession(): Promise<ChatSession> {
  return (await checked(await fetch('/api/chat/sessions', { method: 'POST' }))).json()
}
export async function streamChat(id: string, text: string, requestId: string,
  signal: AbortSignal, receive: (event: ChatEvent) => void) {
  const response = await checked(await fetch('/api/chat/sessions/' + encodeURIComponent(id) + '/messages', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, request_id: requestId }), signal,
  }))
  if (!response.body) throw new Error('浏览器无法接收流式回复，请刷新后再试。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', finished = false
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data:')) continue
          const event: ChatEvent = JSON.parse(line.slice(5).trim())
          receive(event)
          if (event.type === 'done') finished = true
        }
      }
      if (done) break
    }
    if (!finished) throw new Error('回复连接已中断，已收到的内容会保留。')
  } finally { reader.releaseLock() }
}
