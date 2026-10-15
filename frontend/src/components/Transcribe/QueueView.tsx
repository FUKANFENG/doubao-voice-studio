import { useState } from 'react'
import { useTranscribeStore, STATUS_LABEL } from '../../state/transcribeStore'
import { cancelJob, isTerminal, formatDuration } from '../../api/transcribe'
import { Icon } from '../Icons'
export function QueueView() {
  const { jobs, selectedId, loading, select } = useTranscribeStore()
  const [cancelling, setCancelling] = useState('')
  const waiting = jobs.filter(job => job.status === 'pending').length
  const active = jobs.filter(job => !isTerminal(job.status) && job.status !== 'pending').length
  async function cancel(id: string) {
    setCancelling(id)
    try { await cancelJob(id); await useTranscribeStore.getState().refresh() }
    catch (error) { useTranscribeStore.getState().setError(error instanceof Error ? error.message : '取消失败') }
    finally { setCancelling('') }
  }
  return <section className="card queue-card">
    <div className="section-heading compact"><h2>任务队列</h2><span className="subtle-badge">串行处理</span></div>
    <div className="queue-counts"><span><b>{active}</b> 处理中</span><span><b>{waiting}</b> 等待中</span><span><b>{jobs.filter(job => job.status === 'done').length}</b> 已完成</span></div>
    {loading ? <p className="empty-queue">正在读取任务…</p> : !jobs.length ? <p className="empty-queue">队列空空的，添加第一个任务吧。</p> :
      <ul className="queue-list">{[...jobs].sort((a, b) => Number(isTerminal(a.status)) - Number(isTerminal(b.status)) || (isTerminal(a.status) ? b.created_at - a.created_at : a.created_at - b.created_at)).map(job =>
        <li key={job.id} className={'queue-item ' + (selectedId === job.id ? 'selected' : '')}>
          <button className="queue-select" onClick={() => select(job.id)} aria-pressed={selectedId === job.id}><span className={'queue-icon ' + job.status}><Icon name={job.status === 'done' ? 'check' : job.status === 'pending' ? 'clock' : job.source_type === 'url' ? 'link' : 'file'} size={17} /></span><span className="queue-item-text"><strong>{job.title || job.source}</strong><small>{STATUS_LABEL[job.status]}{job.queue_position ? ' · 第 ' + job.queue_position + ' 位' : ' · ' + formatDuration(job.elapsed_sec)}</small></span></button>
          {job.status === 'pending' && !job.started_at && <button className="icon-button" aria-label={'取消任务 ' + (job.title || job.source)} disabled={cancelling === job.id} onClick={() => void cancel(job.id)}><Icon name="close" size={16} /></button>}
        </li>)}</ul>}
    <p className="queue-footnote">刷新页面不会中断任务，结果会保存在本机。</p>
  </section>
}
