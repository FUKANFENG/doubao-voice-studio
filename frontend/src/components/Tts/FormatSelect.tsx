import { useTtsStore } from '../../state/ttsStore'
import type { AudioFormat } from '../../types'

const FORMATS: { value: AudioFormat; label: string; mime: string }[] = [
  { value: 'aac', label: 'AAC (推荐)', mime: 'audio/aac' },
  { value: 'mp3', label: 'MP3', mime: 'audio/mpeg' },
  { value: 'opus', label: 'Opus', mime: 'audio/ogg' },
  { value: 'pcm', label: 'PCM (原始)', mime: 'audio/wav' },
]

export function FormatSelect() {
  const format = useTtsStore((s) => s.format)
  const setFormat = useTtsStore((s) => s.setFormat)
  return (
    <div>
      <label className="label" htmlFor="audio-format">音频格式</label>
      <select
        id="audio-format"
        className="input"
        value={format}
        onChange={(e) => setFormat(e.target.value as AudioFormat)}
      >
        {FORMATS.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>
    </div>
  )
}
