import { create } from 'zustand'
import { getJob, listJobs, getCapabilities, type TranscribeJob, type JobSummary, type Capabilities, type TranscribeStatus } from '../api/transcribe'

let refreshVersion = 0
const SELECTED_JOB_KEY = 'doubao-voice-studio:selected-job'
function readSelectedId(): string | null {
  try { return sessionStorage.getItem(SELECTED_JOB_KEY) } catch { return null }
}
function writeSelectedId(id: string | null) {
  try { if (id) sessionStorage.setItem(SELECTED_JOB_KEY, id); else sessionStorage.removeItem(SELECTED_JOB_KEY) } catch { /* private browsing */ }
}
interface State {
  jobs: JobSummary[]; job: TranscribeJob | null; selectedId: string | null
  capabilities: Capabilities | null; loading: boolean; error: string; connectionError: string
  select: (id: string) => void
  setError: (message: string) => void
  refresh: () => Promise<void>
}
export const useTranscribeStore = create<State>((set, get) => ({
  jobs: [], job: null, selectedId: readSelectedId(), capabilities: null, loading: true, error: '', connectionError: '',
  select: (id) => { refreshVersion++; writeSelectedId(id); set({ selectedId: id, job: null }) },
  setError: (error) => set({ error }),
  refresh: async () => {
    const version = ++refreshVersion
    try {
      const [jobs, capabilities] = await Promise.all([listJobs(), getCapabilities()])
      if (version !== refreshVersion) return
      let id = get().selectedId
      if (!id || !jobs.some(job => job.id === id)) {
        id = jobs.find(job => !['done', 'error', 'cancelled'].includes(job.status))?.id || jobs[0]?.id || null
        writeSelectedId(id)
        set({ selectedId: id, job: null })
      }
      set({ jobs, capabilities, loading: false, connectionError: '' })
      if (id) {
        const job = await getJob(id)
        if (version === refreshVersion && get().selectedId === id) set({ job })
      }
    } catch (error) {
      if (version !== refreshVersion) return
      set({ loading: false, connectionError: error instanceof Error ? error.message : '连接中断，正在重试…' })
    }
  },
}))
export const STATUS_LABEL: Record<TranscribeStatus, string> = {
  pending: '排队中', downloading: '下载音频', extracting: '提取音频', chunking: '切分音频',
  waiting_asr: '等待识别通道', recognizing: '转录中', merging: '生成文字稿', summarizing: 'AI 整理中',
  done: '已完成', error: '未完成', cancelled: '已取消',
}
