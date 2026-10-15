// ASR Zustand store
import { create } from 'zustand'

export type AsrConnState =
  | 'idle'         // 未连接
  | 'connecting'   // 正在连接
  | 'queued'       // 等待 ASR 通道
  | 'connected'    // 已连接
  | 'recording'    // 录音中
  | 'finishing'    // 接收最终结果
  | 'closed'       // 正常结束
  | 'error'        // 出错

interface AsrStore {
  // 连接态
  connState: AsrConnState
  errorMsg: string

  // 识别结果
  partialText: string  // 当前最新累计结果
  finalText: string    // 最终文本

  // 录音指标
  framesSent: number
  durationMs: number   // 录音时长
  startTimeMs: number  // 录音开始时间戳

  // actions
  setConnState: (s: AsrConnState) => void
  setError: (msg: string) => void
  startRecord: () => void
  setQueued: (position: number) => void
  setPartial: (text: string) => void
  setFinal: (text: string) => void
  incFrame: () => void
  updateDuration: () => void
  reset: () => void
}

export const useAsrStore = create<AsrStore>((set, get) => ({
  connState: 'idle',
  errorMsg: '',
  partialText: '',
  finalText: '',
  framesSent: 0,
  durationMs: 0,
  startTimeMs: 0,

  setConnState: (s) => set({ connState: s }),
  setError: (msg) => set({ connState: 'error', errorMsg: msg }),

  startRecord: () => set({
    connState: 'recording',
    partialText: '',
    finalText: '',
    framesSent: 0,
    durationMs: 0,
    startTimeMs: Date.now(),
  }),

  setQueued: (_position) => set({ connState: 'queued' }),

  setPartial: (text) => set({ partialText: text }),
  setFinal: (text) => set({ finalText: text, partialText: text }),

  incFrame: () => set((s) => ({ framesSent: s.framesSent + 1 })),
  updateDuration: () => {
    const s = get()
    if (s.startTimeMs > 0) {
      set({ durationMs: Date.now() - s.startTimeMs })
    }
  },

  reset: () => set({
    connState: 'idle',
    errorMsg: '',
    partialText: '',
    finalText: '',
    framesSent: 0,
    durationMs: 0,
    startTimeMs: 0,
  }),
}))
