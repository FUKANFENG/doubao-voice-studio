import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../Icons'
import { CopyButton } from './CopyButton'
import { Markdown, sectionsFromMarkdown } from './Markdown'
import './developer.css'

const baseUrl = window.location.origin
const agentInstructions = `请为当前项目接入豆包语音工作室。
Base URL: ${baseUrl}
先读取 ${baseUrl}/llms.txt、${baseUrl}/api/docs/markdown 和 ${baseUrl}/openapi.json。
从业务后端调用，不读取或复制服务器 auth.json 或豆包 Cookie。
按文档选择 TTS / WebSocket ASR / URL 或文件转录；AI 整理在提交时传 summarize=true。
多轮对话先 POST /api/chat/sessions，再向该会话 messages 接口提交 text 和唯一 request_id；SSE 的 text 是回复全文快照，done 后核对最后一条消息的 status/error。
转录保存任务 id，每 2 秒查询；done/error/cancelled 是终态，AI 成功另看 summary_status。
POST 超时后不要盲目重发；先查询历史。不要增加 worker 或绕过现有串行队列。
兼容 detail 字符串、对象、数组及代理非 JSON 错误。
WebSocket partial 是当前文本快照；final 没有文本。发送 finish 后等待 final 再断开。
请遵循当前项目的配置和代码风格完成接入，并验证实际响应。`

export function DeveloperPanel() {
  const [markdown, setMarkdown] = useState('')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState(0)
  const [query, setQuery] = useState('')
  const contentHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 15000)
    let disposed = false
    setError('')
    async function load() {
      try {
        const response = await fetch('/api/docs/markdown', { signal: controller.signal, cache: 'no-cache' })
        if (!response.ok) throw new Error('文档暂时无法加载（HTTP ' + response.status + '）')
        const text = await response.text()
        if (!sectionsFromMarkdown(text).length) throw new Error('文档内容不完整，请刷新后重试')
        if (!disposed) setMarkdown(text)
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error && reason.name !== 'AbortError' ? reason.message : '文档加载超时，请重试')
      } finally { clearTimeout(timer) }
    }
    void load()
    return () => { disposed = true; clearTimeout(timer); controller.abort() }
  }, [attempt])
  const sections = useMemo(() => sectionsFromMarkdown(markdown), [markdown])
  const filtered = sections.map((section, index) => ({ ...section, index })).filter(section =>
    (section.title + section.content).toLowerCase().includes(query.trim().toLowerCase()))
  const current = sections[selected] || sections[0]

  function choose(index: number) {
    setSelected(index)
    // The heading remains mounted; move keyboard focus without changing the URL hash.
    requestAnimationFrame(() => contentHeading.current?.focus())
  }
  return <section className="developer-panel" aria-label="API 开发文档">
    <div className="dev-intro card">
      <div className="dev-intro-copy">
        <span className="dev-kicker"><span className="status-dot" /> API v1.4 · HTTP + WebSocket + SSE</span>
        <h2>一次接入，让每个项目<br className="dev-title-break" />都有声音。</h2>
        <p>参数、示例和接口契约都在这里。复制一份说明，交给你的开发 Agent。</p>
        <div className="dev-actions"><CopyButton text={agentInstructions} label="复制 Agent 接入说明" primary />
          <a className="dev-inline-link" href="/api/docs/markdown" target="_blank" rel="noreferrer">阅读 Markdown <Icon name="arrow" size={14} /></a></div>
      </div>
      <div className="dev-connection">
        <div className="dev-connection-heading"><Icon name="code" size={18} /><span>你的服务入口</span><span className="dev-api-label">BASE URL</span></div>
        <code>{baseUrl}</code>
        <CopyButton text={baseUrl} label="复制地址" />
        <div className="dev-connection-footer">语音合成 / 实时听写 / 转录与 AI 笔记</div>
      </div>
    </div>
    <div className="dev-resources" aria-label="开发资源">
      <a href="/openapi.json" target="_blank" rel="noreferrer"><Icon name="code" size={17} /><span>OpenAPI <small>机器可读契约</small></span><Icon name="arrow" size={14} /></a>
      <a href="/docs" target="_blank" rel="noreferrer"><Icon name="play" size={17} /><span>交互式文档 <small>查看与调试 HTTP</small></span><Icon name="arrow" size={14} /></a>
      <a href="/api/docs/examples/python" download><Icon name="download" size={17} /><span>Python <small>下载接入示例</small></span></a>
      <a href="/api/docs/examples/node" download><Icon name="download" size={17} /><span>Node.js <small>下载接入示例</small></span></a>
    </div>
    {error ? <div className="card dev-load-error" role="alert"><p>{error}</p><button className="btn-ghost" onClick={() => setAttempt(value => value + 1)}>重新加载</button></div>
      : !current ? <div className="card dev-loading" role="status" aria-busy="true"><span />正在加载接口文档…</div>
      : <div className="dev-docs-layout">
        <aside className="dev-toc">
          <label className="label" htmlFor="dev-search">查找文档</label>
          <input className="input" id="dev-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="接口、参数或关键词" />
          <nav aria-label="文档章节">{filtered.map(section => <button key={section.title} aria-current={selected === section.index ? 'location' : undefined}
            className={selected === section.index ? 'selected' : ''} onClick={() => choose(section.index)}>
            <span>{String(section.index + 1).padStart(2, '0')}</span>{section.title}
          </button>)}</nav>
          {!filtered.length && <p className="dev-no-results" role="status">没有匹配的章节，试试「文件」或「AI」。</p>}
          <a className="dev-agent-index" href="/llms.txt" target="_blank" rel="noreferrer"><Icon name="spark" size={15} /> Agent 索引 · llms.txt</a>
        </aside>
        <article className="card dev-article">
          <div className="dev-article-heading"><span className="dev-kicker">API REFERENCE / {String(selected + 1).padStart(2, '0')}</span>
            <h2 ref={contentHeading} tabIndex={-1}>{current.title}</h2></div>
          <Markdown text={current.content} />
          <div className="dev-pagination">
            <button className="btn-ghost" disabled={selected === 0} onClick={() => choose(selected - 1)}>上一节</button>
            <span>{selected + 1} / {sections.length}</span>
            <button className="btn-ghost" disabled={selected >= sections.length - 1} onClick={() => choose(selected + 1)}>下一节 <Icon name="arrow" size={14} /></button>
          </div>
        </article>
      </div>}
  </section>
}
