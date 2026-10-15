import { useTtsStore } from '../../state/ttsStore'

interface Props {
  enabled: boolean
  isTts: boolean
}

export function TtsPageHint({ enabled, isTts }: Props) {
  const text = useTtsStore((s) => s.text)
  const speaker = useTtsStore((s) => s.speaker)
  const speechRate = useTtsStore((s) => s.speechRate)
  const pitch = useTtsStore((s) => s.pitch)
  const format = useTtsStore((s) => s.format)

  if (!isTts) return null
  return (
    <div className="card bg-slate-50 border-dashed">
      <div className="text-xs text-slate-500 space-y-1">
        <div>
          <strong className="text-slate-700">当前请求：</strong>
          POST /api/tts
        </div>
        <div>
          <strong>text：</strong>
          <span className="font-mono">{text.slice(0, 30)}{text.length > 30 ? '...' : ''}</span>
        </div>
        <div>
          <strong>speaker：</strong>
          <span className="font-mono">{speaker || '(默认)'}</span>
        </div>
        <div>
          <strong>speech_rate：</strong>
          <span className="font-mono">{speechRate.toFixed(2)}</span> &nbsp;
          <strong>pitch：</strong>
          <span className="font-mono">{pitch}</span> &nbsp;
          <strong>format：</strong>
          <span className="font-mono">{format}</span>
        </div>
      </div>
    </div>
  )
}
