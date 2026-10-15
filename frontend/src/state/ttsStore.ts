// TTS Zustand store
import { create } from 'zustand'
import type { AudioFormat, SpeakerId } from '../types'

export type TtsState =
  | 'idle'        // 空闲
  | 'synthesizing' // 合成中
  | 'ready'        // 合成完成，待播放
  | 'playing'      // 播放中
  | 'error'        // 错误

interface TtsStore {
  // 参数
  text: string
  speaker: SpeakerId
  format: AudioFormat
  speechRate: number  // 0.7 ~ 2.0
  pitch: number       // -10 ~ 10

  // 状态
  state: TtsState
  errorMsg: string
  audioUrl: string | null   // 上次合成好的 Blob URL
  resultFormat: AudioFormat
  bytesReceived: number
  totalBytes: number

  // actions
  setText: (v: string) => void
  setSpeaker: (v: SpeakerId) => void
  setFormat: (v: AudioFormat) => void
  setSpeechRate: (v: number) => void
  setPitch: (v: number) => void
  startSynth: () => void
  updateProgress: (bytes: number) => void
  finishSynth: (audioUrl: string, totalBytes: number) => void
  failSynth: (msg: string) => void
  startPlay: () => void
  endPlay: () => void
  reset: () => void
}

export const useTtsStore = create<TtsStore>((set, get) => ({
  text: '海鸥在线，你要整点薯条吗？',
  speaker: '',  // 空 = 后端用默认
  format: 'aac',
  speechRate: 1.0,
  pitch: 0,

  state: 'idle',
  errorMsg: '',
  audioUrl: null,
  resultFormat: 'aac',
  bytesReceived: 0,
  totalBytes: 0,

  setText: (v) => set({ text: v }),
  setSpeaker: (v) => set({ speaker: v }),
  setFormat: (v) => set({ format: v }),
  setSpeechRate: (v) => set({ speechRate: v }),
  setPitch: (v) => set({ pitch: v }),

  startSynth: () => {
    const previous = get().audioUrl
    if (previous) URL.revokeObjectURL(previous)
    set({
    resultFormat: get().format,
    state: 'synthesizing',
    errorMsg: '',
    bytesReceived: 0,
    totalBytes: 0,
    audioUrl: null,  // 清理旧的
    })
  },
  updateProgress: (bytes) => set({ bytesReceived: bytes }),
  finishSynth: (audioUrl, totalBytes) => set({
    state: 'ready',
    audioUrl,
    totalBytes,
  }),
  failSynth: (msg) => set({ state: 'error', errorMsg: msg }),
  startPlay: () => set({ state: 'playing' }),
  endPlay: () => set({ state: 'ready' }),
  reset: () => {
    const previous = get().audioUrl
    if (previous) URL.revokeObjectURL(previous)
    set({ state: 'idle', errorMsg: '', audioUrl: null })
  },
}))
