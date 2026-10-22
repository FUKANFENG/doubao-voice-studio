import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../../state/chatStore'
import { Icon } from '../Icons'
import { Markdown } from '../Developer/Markdown'
import { CopyButton } from '../Developer/CopyButton'
import '../Developer/developer.css'
import './chat.css'

const suggestions = ['帮我把一个想法变成可执行的计划', '解释一个概念，并用生活中的例子说明', '帮我润色一段文字，让表达更清晰']

export function ChatPanel() {
  const state = useChatStore()
  const { refresh, select, newSession, send, stop } = state
  const session = state.selectedId ? state.details[state.selectedId] : undefined
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [query, setQuery] = useState('')
  const key = state.selectedId || 'new'
  const draft = drafts[key] || ''
  const setDraft = (text: string) => setDrafts(values => ({ ...values, [key]: text }))
  const viewport = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const composer = useRef<HTMLTextAreaElement>(null)
  const messages = session?.messages || []
  const ownStream = state.busy && state.streamingId === state.selectedId
  const waiting = state.busy || !!session?.generating || state.creating || state.loading

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => { if (!useChatStore.getState().busy) void refresh() }, 4000)
    return () => window.clearInterval(timer)
  }, [refresh])
  useEffect(() => { follow.current = true }, [state.selectedId])
  useEffect(() => {
    if (follow.current && viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight
  }, [messages, state.selectedId])

  async function submit() {
    if (!draft.trim() || waiting) return
    const text = draft
    const draftKey = key
    setDraft('')
    follow.current = true
    const accepted = await send(text)
    if (!accepted) {
      const restoreKey = draftKey === 'new' ? useChatStore.getState().selectedId || 'new' : draftKey
      setDrafts(values => ({ ...values, [restoreKey]: values[restoreKey] || text }))
    }
    composer.current?.focus()
  }

  return <div className="chat-layout">
    <aside className="card chat-history" aria-label="对话历史">
      <button className="btn-primary chat-new" onClick={() => void newSession()} disabled={state.creating || state.loading}>
        <Icon name="plus" size={17} />{state.creating ? '正在创建…' : '新建对话'}
      </button>
      <label className="sr-only" htmlFor="chat-search">搜索对话</label>
      <input id="chat-search" className="input chat-search" placeholder="搜索历史对话" type="search" value={query} onChange={e => setQuery(e.target.value)} />
      <div className="chat-history-label">最近的对话 <span>{state.sessions.length}</span></div>
      <nav className="chat-session-list" aria-label="历史会话">
        {state.sessions.filter(s => s.title.toLowerCase().includes(query.toLowerCase())).map(item =>
          <button key={item.id} className={'chat-session ' + (item.id === state.selectedId ? 'selected' : '')}
            aria-current={item.id === state.selectedId ? 'page' : undefined} onClick={() => select(item.id)}>
            <Icon name="chat" size={16} /><span><strong>{item.title}</strong><small>{item.generating ? '正在回复…' : new Date(item.updated_at * 1000).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })}</small></span>
          </button>)}
      </nav>
      {!state.sessions.length && <p className="chat-history-empty">从第一句开始，<br />把灵感慢慢聊清楚。</p>}
      {!!query && !state.sessions.some(s => s.title.toLowerCase().includes(query.toLowerCase())) && <p className="chat-history-empty">没有找到匹配的对话。</p>}
      <p className="chat-storage"><Icon name="file" size={14} />记录自动保存在本机</p>
    </aside>
    <section className="card chat-room" aria-label="豆包对话">
      <div className="chat-room-heading"><span className="icon-tile teal"><Icon name="chat" /></span>
        <div><h2>{session?.title || '和豆包聊聊'}</h2><p>豆包 · 连续对话</p></div>
        <span className="chat-connection"><span className="status-dot" />复用已有登录态</span>
      </div>
      <div ref={viewport} className="chat-messages" role="log" aria-label="对话消息" aria-live="off"
        onScroll={() => { const el = viewport.current; if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100 }}>
        {state.loading || (state.selectedId && !session) ? <div className="chat-welcome"><Icon name="chat" size={30} /><p>正在读取对话…</p></div>
          : !messages.length ? <div className="chat-welcome"><span className="chat-welcome-symbol"><Icon name="spark" size={30} /></span>
            <span className="eyebrow">A LITTLE CONVERSATION, A NEW IDEA</span><h3>想法，从一句话开始。</h3><p>提一个问题，梳理一段思路，<br />或接着上次的话题慢慢聊。</p>
            <div className="chat-suggestions">{suggestions.map(text => <button key={text} onClick={() => { setDraft(text); composer.current?.focus() }}><span>{text}</span><Icon name="arrow" size={16} /></button>)}</div>
          </div> : messages.map(message => <article key={message.id} className={'chat-message ' + message.role}>
            <div className="chat-message-label">{message.role === 'assistant' ? <><Icon name="spark" size={14} />豆包</> : '你'}</div>
            <div className="chat-bubble">{message.role === 'assistant'
              ? message.content ? <Markdown text={message.content} /> : message.status === 'streaming' ? <span className="chat-thinking">正在想一想<span>…</span></span> : <span className="chat-no-answer">{message.status === 'stopped' ? '已停止接收' : '暂未收到回复'}</span>
              : <p>{message.content}</p>}</div>
            {message.role === 'assistant' && <div className="chat-message-tools">
              {message.content && message.status !== 'streaming' && <CopyButton text={message.content} label="复制回复" />}
              {message.status === 'streaming' && <span className="chat-stream-status">正在回复…</span>}
              {message.error && <span role={message.status === 'error' ? 'alert' : 'status'} className={message.status === 'error' ? 'chat-message-error' : 'chat-stream-status'}>{message.error}</span>}
            </div>}
          </article>)}
      </div>
      {(state.error || state.connectionError) && <div className="notice error chat-error" role="alert">{state.error || state.connectionError}<button onClick={() => { useChatStore.setState({ error: '', connectionError: '' }); void refresh() }}>重新连接</button></div>}
      <form className="chat-composer" onSubmit={e => { e.preventDefault(); void submit() }}>
        <label className="sr-only" htmlFor="chat-message">输入消息</label>
        <textarea ref={composer} id="chat-message" placeholder="说说你的问题，或继续刚才的话题…" maxLength={12000} rows={3} value={draft} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); void submit() } }} />
        <div className="chat-composer-bottom"><span>Enter 发送 <span>·</span> Shift + Enter 换行</span><small>{draft.length.toLocaleString()} / 12,000</small>
          {ownStream ? <button type="button" className="btn-ghost" onClick={stop}><span className="chat-stop-icon" />停止生成</button>
            : <button className="btn-primary" type="submit" disabled={!draft.trim() || waiting}><span>{state.busy ? '其他对话回复中' : '发送'}</span><Icon name="arrow" size={17} /></button>}
        </div>
      </form>
      <p className="chat-footnote">消息通过当前豆包账号发送，可能出现在该账号的会话历史中。</p>
      <span className="sr-only" role="status">{state.busy ? '豆包正在回复' : '可以发送消息'}</span>
    </section>
  </div>
}
