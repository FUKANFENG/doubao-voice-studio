import { create } from 'zustand'
import { createChatSession, getChatSession, listChatSessions, streamChat,
  type ChatSession, type ChatSessionInfo } from '../api/chat'

const selectedKey = 'doubao-voice-studio:chat-session'
function readSelected() { try { return localStorage.getItem(selectedKey) } catch { return null } }
function remember(id: string | null) {
  try { if (id) localStorage.setItem(selectedKey, id); else localStorage.removeItem(selectedKey) } catch { /* private browsing */ }
}
let controller: AbortController | null = null
let refreshVersion = 0
function info(session: ChatSession): ChatSessionInfo {
  const { messages: _, ...summary } = session
  return summary
}
interface State {
  sessions: ChatSessionInfo[]; details: Record<string, ChatSession>; selectedId: string | null
  loading: boolean; creating: boolean; busy: boolean; streamingId: string | null; error: string; connectionError: string
  refresh: () => Promise<void>
  select: (id: string) => void
  newSession: () => Promise<void>
  send: (text: string) => Promise<boolean>
  stop: () => void
}
export const useChatStore = create<State>((set, get) => {
  const update = (session: ChatSession) => set(state => ({
    details: { ...state.details, [session.id]: session },
    sessions: [info(session), ...state.sessions.filter(s => s.id !== session.id)]
      .sort((a, b) => b.updated_at - a.updated_at),
  }))
  return {
    sessions: [], details: {}, selectedId: readSelected(), loading: true, creating: false,
    busy: false, streamingId: null, error: '', connectionError: '',
    refresh: async () => {
      const version = ++refreshVersion
      try {
        const sessions = await listChatSessions()
        if (version !== refreshVersion) return
        let id = get().selectedId
        if (!sessions.some(s => s.id === id)) {
          id = sessions[0]?.id || null
          remember(id)
        }
        set({ sessions, selectedId: id, loading: false, connectionError: '' })
        if (id && !(get().busy && get().streamingId === id)) {
          const session = await getChatSession(id)
          if (version === refreshVersion && get().selectedId === id && get().streamingId !== id) {
            update(session)
          }
        }
      } catch (error) {
        if (version === refreshVersion) set({ loading: false, connectionError: error instanceof Error ? error.message : '无法读取对话，请重试。' })
      }
    },
    select: id => {
      refreshVersion++
      remember(id)
      set({ selectedId: id, error: '' })
      void get().refresh()
    },
    newSession: async () => {
      if (get().creating) return
      set({ creating: true, error: '' })
      refreshVersion++
      try {
        const session = await createChatSession()
        update(session)
        remember(session.id)
        set({ selectedId: session.id })
      } catch (error) {
        set({ error: error instanceof Error ? error.message : '创建对话失败，请重试。' })
      } finally { set({ creating: false, loading: false }) }
    },
    send: async text => {
      if (get().busy || get().creating || !text.trim()) return false
      const abort = new AbortController()
      controller = abort
      let id = get().selectedId
      let accepted = false
      set({ busy: true, streamingId: id, error: '' })
      refreshVersion++
      try {
        if (!id) {
          const session = await createChatSession()
          id = session.id
          update(session)
          remember(id)
          set({ selectedId: id, streamingId: id })
        }
        await streamChat(id, text.trim(), crypto.randomUUID(), abort.signal, event => {
          if (event.type === 'session' || event.type === 'done') {
            accepted = true
            update(event.session)
          } else if (event.type === 'text') {
            set(state => {
              const session = state.details[id!]
              if (!session) return state
              return { details: { ...state.details, [id!]: { ...session,
                messages: session.messages.map(m => m.id === event.message_id ? { ...m, content: event.text } : m),
              } } }
            })
          }
        })
      } catch (error) {
        const stopped = abort.signal.aborted
        const message = stopped ? '已停止接收回复。' : error instanceof Error ? error.message : '对话暂时失败，请重试。'
        const session = id ? get().details[id] : undefined
        if (session && accepted) update({ ...session, generating: false, messages: session.messages.map(m =>
          m.status === 'streaming' ? { ...m, status: stopped ? 'stopped' : 'error', error: message } : m) })
        else if (!stopped) set({ error: message })
      } finally {
        if (controller === abort) controller = null
        set({ busy: false, streamingId: null })
        // Fetch the persisted terminal state. Polling handles disconnect cleanup that is still in flight.
        void get().refresh()
      }
      return accepted
    },
    stop: () => controller?.abort(),
  }
})
