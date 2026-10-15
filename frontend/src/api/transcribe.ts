export type TranscribeStatus = 'pending' | 'downloading' | 'extracting' | 'chunking' | 'waiting_asr' | 'recognizing' | 'merging' | 'summarizing' | 'done' | 'error' | 'cancelled'
export interface JobSummary {
  id: string; status: TranscribeStatus; source: string; source_type: 'url' | 'file'; title: string
  duration_sec: number; progress_pct: number; current_step: string; total_chunks: number; done_chunks: number
  summary_requested: boolean; summary_status: string; summary_error: string; error: string
  created_at: number; started_at: number; finished_at: number; server_time: number
  elapsed_sec: number; wait_sec: number; processing_sec: number; queue_position: number
}
export interface TranscribeJob extends JobSummary {
  result_text: string; srt_text: string; structured_text: string; summary: string; received_at: number
}
export interface Capabilities {
  summary: { available: boolean; provider: string; label: string; reason: string }
  queue_concurrency: number; cooldown_sec: number
}
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: 'no-store', signal: AbortSignal.timeout(30000) })
  if (!response.ok) {
    let message = '请求失败（HTTP ' + response.status + '）'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (typeof body.detail?.message === 'string') message = body.detail.message
      else if (Array.isArray(body.detail)) message = '提交内容不正确，请检查链接或文件。'
    } catch { /* Keep the HTTP error if the gateway returned HTML. */ }
    throw new Error(message)
  }
  return response.json()
}
export const listJobs = () => request<JobSummary[]>('/api/transcribe/jobs')
export const getCapabilities = () => request<Capabilities>('/api/transcribe/capabilities')
export async function getJob(id: string): Promise<TranscribeJob> {
  const job = await request<TranscribeJob>('/api/transcribe/jobs/' + id)
  return { ...job, received_at: performance.now() }
}
export const cancelJob = (id: string) => request<JobSummary>('/api/transcribe/jobs/' + id + '/cancel', { method: 'POST' })
export const submitYoutubeUrl = (url: string, summarize: boolean) =>
  request<JobSummary>('/api/transcribe/url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, summarize }) })
export async function submitLocalFile(file: File, summarize: boolean): Promise<JobSummary> {
  const body = new FormData()
  body.append('file', file)
  body.append('summarize', String(summarize))
  // Uploads can take longer than polling requests.
  const response = await fetch('/api/transcribe/file', { method: 'POST', body })
  if (!response.ok) {
    let message = '上传失败（HTTP ' + response.status + '）。大文件可通过本机地址上传。'
    try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail } catch {}
    throw new Error(message)
  }
  return response.json()
}
export const getTextUrl = (id: string) => '/api/transcribe/jobs/' + id + '/text'
export const getSrtUrl = (id: string) => '/api/transcribe/jobs/' + id + '/srt'
export const getSummaryUrl = (id: string) => '/api/transcribe/jobs/' + id + '/summary'
export const isTerminal = (status: TranscribeStatus) => ['done', 'error', 'cancelled'].includes(status)
export function formatDuration(value: number): string {
  const seconds = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0))
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60
  return (h ? String(h).padStart(2, '0') + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0')
}
