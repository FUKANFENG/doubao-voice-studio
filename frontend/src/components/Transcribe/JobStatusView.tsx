import { useEffect, useState } from 'react'
import { useTranscribeStore, STATUS_LABEL } from '../../state/transcribeStore'
import { isTerminal, formatDuration } from '../../api/transcribe'
import { Icon, Waveform } from '../Icons'
export function JobStatusView() {
  const job = useTranscribeStore(s => s.job)
  const loading = useTranscribeStore(s => s.loading)
  const selectedId = useTranscribeStore(s => s.selectedId)
  const [now, setNow] = useState(performance.now())
  useEffect(() => {
    if (!job || isTerminal(job.status)) return
    const timer = setInterval(() => setNow(performance.now()), 1000)
    return () => clearInterval(timer)
  }, [job?.id, job?.status])
  if (!job) return <section className="card transcription-empty"><span className="empty-label">你的下一份学习笔记，从这里开始</span><div className="empty-illustration"><div className="paper-sheet"><Icon name="book" size={28} /><i /><i /><i /><i /><span><Icon name="check" size={16} />学习笔记</span></div><span className="floating-spark"><Icon name="spark" size={26} /></span><Waveform /></div><h2>{loading || selectedId ? '正在加载任务…' : '把好内容，变成自己的知识。'}</h2><p>添加一个 YouTube 链接或本地文件，<br />文字稿、字幕和 AI 笔记都会在这里等你。</p><div className="output-chips"><span>TXT 文字稿</span><span>SRT 字幕</span><span>AI 学习笔记</span></div></section>
  const terminal = isTerminal(job.status)
  const tick = terminal ? 0 : Math.max(0, now - job.received_at) / 1000
  const elapsed = job.elapsed_sec + tick
  const wait = job.wait_sec + (!job.started_at ? tick : 0)
  const process = job.processing_sec + (job.started_at ? tick : 0)
  const steps = ['准备音频', '逐段转录', '生成文字稿', 'AI 整理']
  const stage = ['error', 'cancelled'].includes(job.status)
    ? job.total_chunks && job.done_chunks < job.total_chunks ? 1 : job.result_text ? 2 : 0
    : ['pending', 'downloading', 'extracting', 'chunking'].includes(job.status) ? 0 : ['recognizing', 'waiting_asr'].includes(job.status) ? 1 : job.status === 'merging' ? 2 : 3
  return <section className="card job-detail">
    <div className="section-heading compact"><span className={'state-pill ' + job.status}><span className="status-dot" />{STATUS_LABEL[job.status]}</span><span className="job-id">#{job.id.slice(0, 6)}</span></div>
    <h2 className="job-title">{job.title || '准备好，开始记录这段内容。'}</h2>
    <p className="job-source">{job.source}</p>
    <div className="time-grid"><div className="total-time"><span>总耗时</span><strong>{formatDuration(elapsed)}</strong></div><div><span>排队耗时</span><strong>{formatDuration(wait)}</strong></div><div><span>处理耗时</span><strong>{formatDuration(process)}</strong></div></div>
    <div className="progress-caption"><span>{job.status === 'pending' ? '等待开始 · 队列第 ' + job.queue_position + ' 位' : job.current_step}</span><strong>{job.progress_pct}%</strong></div>
    <progress className={'job-progress ' + job.status} value={job.progress_pct} max={100} aria-label="转录整体进度" />
    <ol className="stage-list">{steps.filter((_, index) => index < 3 || job.summary_requested).map((step, index) => <li key={step} className={index === 3 && job.summary_status === 'error' ? 'failed' : job.status === 'done' || index < stage ? 'complete' : index === stage && !terminal ? 'current' : ''}><span>{job.status === 'done' || index < stage ? <Icon name="check" size={12} /> : index + 1}</span>{index === 3 && job.summary_status === 'error' ? 'AI 整理未完成' : step}</li>)}</ol>
    <div className="job-meta"><span><Icon name="play" size={13} />视频 / 音频时长 <b>{job.duration_sec ? formatDuration(job.duration_sec) : '待解析'}</b></span><span>{job.total_chunks ? job.done_chunks + ' / ' + job.total_chunks + ' 段已识别' : '自动切分音频'}</span></div>
    {job.error && <div className="notice error" role="alert">{job.error}</div>}
    {job.summary_error && <div className="notice warning" role="status">文字稿已保留。{job.summary_error}</div>}
  </section>
}
