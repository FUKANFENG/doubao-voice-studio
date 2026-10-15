// TTS API client
import type { TtsRequest, TtsSpeakersResponse, AudioFormat, HealthResponse } from '../types'

// format → 浏览器认识的 MIME
const FORMAT_MIME: Record<AudioFormat, string> = {
  aac: 'audio/aac',
  mp3: 'audio/mpeg',
  opus: 'audio/ogg; codecs=opus',
  pcm: 'audio/wave',  // 浏览器不太认 raw pcm，wave 兜底（带头的）
}

export class TtsApiError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

/**
 * 流式 TTS 合成：POST /api/tts → ReadableStream<Uint8Array> → Blob
 * 边收边返回，调用方可以实时拼 Blob
 */
export async function synthesizeTts(
  req: TtsRequest,
  onProgress?: (bytes: number) => void
): Promise<Blob> {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

  if (!res.ok) {
    let detail: any = null
    try { detail = await res.json() } catch {}
    const code = detail?.detail?.code ?? 'unknown'
    const msg = detail?.detail?.message ?? `HTTP ${res.status}`
    throw new TtsApiError(code, msg, res.status)
  }

  if (!res.body) {
    throw new TtsApiError('no_body', 'Response body is empty', 500)
  }

  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    chunks.push(value)
    total += value.byteLength
    onProgress?.(total)
  }

  return new Blob(chunks as BlobPart[], { type: FORMAT_MIME[req.format] })
}

export async function fetchSpeakers(): Promise<TtsSpeakersResponse> {
  const res = await fetch('/api/speakers')
  if (!res.ok) throw new Error(`fetchSpeakers HTTP ${res.status}`)
  return res.json()
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health', { cache: 'no-store', signal: AbortSignal.timeout(8000) })
  if (!res.ok) throw new Error(`fetchHealth HTTP ${res.status}`)
  return res.json()
}
