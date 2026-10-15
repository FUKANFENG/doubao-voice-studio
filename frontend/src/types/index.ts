// ====== 音色 ======
export type SpeakerId = string

export interface Speaker {
  id: SpeakerId
  name: string
}

// ====== TTS ======
export type AudioFormat = 'aac' | 'mp3' | 'opus' | 'pcm'

export interface TtsRequest {
  text: string
  speaker: SpeakerId
  format: AudioFormat
  speech_rate: number  // 0.7 ~ 2.0
  pitch: number         // -10 ~ 10
}

export interface TtsSpeakersResponse {
  default: SpeakerId
  speakers: Speaker[]
}

// ====== ASR ======
export type AsrEventType = 'partial' | 'final' | 'error'

export interface AsrEvent {
  type: AsrEventType
  text?: string
  code?: string
  message?: string
}

// ====== Health ======
export interface HealthResponse {
  ok: boolean
  ts: number
  auth_loaded: boolean
  auth_ok: boolean
  auth_reason: string
  cookie_chars: number
}
