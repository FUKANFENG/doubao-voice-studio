import { useRef, useState } from 'react'
import { submitYoutubeUrl, submitLocalFile } from '../../api/transcribe'
import { useTranscribeStore } from '../../state/transcribeStore'
import { Icon } from '../Icons'
export function SubmitForm() {
  const [type, setType] = useState<'url' | 'file'>('url')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [summarize, setSummarize] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const capabilities = useTranscribeStore(s => s.capabilities)
  const error = useTranscribeStore(s => s.error)
  const canSummarize = capabilities?.summary.available ?? false
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (submitting) return
    const store = useTranscribeStore.getState()
    store.setError(''); setSuccess('')
    if (type === 'url') {
      try {
        const parsed = new URL(url.trim())
        if (!['http:', 'https:'].includes(parsed.protocol) || !['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'].includes(parsed.hostname)) throw new Error()
      } catch { store.setError('请粘贴有效的 YouTube 视频链接'); return }
    } else if (!file) { store.setError('请先选择音频或视频文件'); return }
    setSubmitting(true)
    try {
      const job = type === 'url' ? await submitYoutubeUrl(url.trim(), summarize && canSummarize) : await submitLocalFile(file!, summarize && canSummarize)
      store.select(job.id)
      setUrl(''); setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      setSuccess('已加入队列，可以继续添加下一个任务。')
      await store.refresh()
    } catch (error) { store.setError(error instanceof Error ? error.message : '提交失败，请重试') }
    finally { setSubmitting(false) }
  }
  return <section className="card source-card">
    <div className="section-heading"><span className="icon-tile orange"><Icon name="plus" /></span><div><h2>添加转录任务</h2><p>让好内容留得住</p></div></div>
    <form onSubmit={submit}>
      <div className="segmented" aria-label="选择来源"><button type="button" aria-pressed={type === 'url'} className={type === 'url' ? 'selected' : ''} onClick={() => setType('url')}><Icon name="link" size={16} />YouTube 链接</button><button type="button" aria-pressed={type === 'file'} className={type === 'file' ? 'selected' : ''} onClick={() => setType('file')}><Icon name="upload" size={16} />本地文件</button></div>
      {type === 'url' ? <div className="source-field"><label className="label" htmlFor="video-url">视频链接</label><input id="video-url" type="url" className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" required disabled={submitting} /><p className="field-hint">支持普通视频与 Shorts，每个链接创建一个任务。</p></div> :
        <div className="source-field"><label className="file-drop" htmlFor="media-file"><span className="icon-tile"><Icon name="upload" size={24} /></span><strong>{file?.name || '选择音频或视频文件'}</strong><span>{file ? (file.size / 1024 / 1024).toFixed(1) + ' MB · 点击重新选择' : 'MP4、MP3、WAV、M4A 等格式'}</span></label><input ref={inputRef} id="media-file" className="file-input" type="file" accept="audio/*,video/*,.mkv,.flac" onChange={e => setFile(e.target.files?.[0] || null)} disabled={submitting} /><p className="field-hint">上传速度取决于网络；大文件建议在本机打开后上传。</p></div>}
      <label className={'ai-option ' + (!canSummarize ? 'unavailable' : '')}><span className="ai-symbol"><Icon name="spark" /></span><span><strong>转录后，顺便整理成笔记</strong><small>{canSummarize ? '豆包对话 · 复用现有登录态' : capabilities?.summary.reason || '正在检查豆包连接…'}</small></span><input type="checkbox" checked={summarize && canSummarize} onChange={e => setSummarize(e.target.checked)} disabled={!canSummarize || submitting} aria-label="启用 AI 整理" /></label>
      {error && <p className="notice error" role="alert">{error}</p>}
      {success && <p className="notice success" role="status">{success}</p>}
      <button className="btn-primary submit-button" disabled={submitting} type="submit"><Icon name={submitting ? 'clock' : 'plus'} size={18} />{submitting ? type === 'file' ? '正在上传，请稍候…' : '正在加入…' : '加入转录队列'}{!submitting && <Icon name="arrow" size={18} />}</button>
      <p className="submit-note"><Icon name="check" size={13} />一次处理一个任务，完成后自动继续</p>
    </form>
  </section>
}
