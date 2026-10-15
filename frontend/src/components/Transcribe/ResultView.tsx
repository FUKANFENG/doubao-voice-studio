import { useState } from 'react'
import { useTranscribeStore } from '../../state/transcribeStore'
import { getTextUrl, getSrtUrl, getSummaryUrl } from '../../api/transcribe'
import { Icon } from '../Icons'
function Notes({ text }: { text: string }) {
  // Render Markdown structure as React text nodes; never interpret untrusted HTML.
  return <article className="notes">{text.split('\n').map((line, index) => {
    const content = line.replace(/^#{1,6}\s+/, '').replace(/\*\*(.*?)\*\*/g, '$1')
    if (/^#{1,6}\s/.test(line)) return <h3 key={index}>{content}</h3>
    if (/^[-*]\s/.test(line)) return <p className="note-bullet" key={index}>{content.slice(2)}</p>
    if (/^---+$/.test(line)) return <hr key={index} />
    return line.trim() ? <p key={index}>{content}</p> : <br key={index} />
  })}</article>
}
export function ResultView() {
  const job = useTranscribeStore(s => s.job)
  const [tab, setTab] = useState<'text' | 'srt' | 'summary'>('text')
  const [copyMessage, setCopyMessage] = useState('')
  if (!job || (!job.result_text && job.status !== 'done')) return null
  const content = tab === 'text' ? job.result_text : tab === 'srt' ? job.srt_text : job.summary
  const url = tab === 'text' ? getTextUrl(job.id) : tab === 'srt' ? getSrtUrl(job.id) : getSummaryUrl(job.id)
  const tabs = [{ id: 'text' as const, label: '文字稿' }, { id: 'srt' as const, label: 'SRT 字幕' }, ...(job.summary ? [{ id: 'summary' as const, label: 'AI 笔记' }] : [])]
  return <section className="card result-card">
    <div className="section-heading compact"><h2>你的转录成果</h2><span className="result-count">{job.result_text.length.toLocaleString()} 字 · {job.total_chunks} 个片段</span></div>
    <div className="result-toolbar"><div className="result-tabs">{tabs.map(item => <button key={item.id} aria-pressed={tab === item.id} className={tab === item.id ? 'active' : ''} onClick={() => { setTab(item.id); setCopyMessage('') }}>{item.id === 'summary' && <Icon name="spark" size={14} />}{item.label}</button>)}</div><button className="icon-button" aria-label="复制当前结果" disabled={!content} onClick={async () => { try { await navigator.clipboard.writeText(content); setCopyMessage('已复制') } catch { setCopyMessage('复制失败，请手动选择文字') } }}><Icon name="copy" size={17} /></button></div>
    <div className="result-content">{tab === 'summary' ? <Notes text={content} /> : <pre className={tab === 'srt' ? 'subtitle-text' : ''}>{content || '这段音频没有识别到可用文字。'}</pre>}</div>
    <div className="result-footer"><span role="status">{copyMessage || '已保存到本机，随时可以回来查看。'}</span>{content && <a href={url} className="btn-ghost" download><Icon name="download" size={15} />下载 {tab === 'text' ? 'TXT' : tab === 'srt' ? 'SRT' : 'Markdown'}</a>}</div>
  </section>
}
