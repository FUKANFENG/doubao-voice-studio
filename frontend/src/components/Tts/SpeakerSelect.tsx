import { useEffect, useState } from 'react'
import { useTtsStore } from '../../state/ttsStore'
import { fetchSpeakers } from '../../api/tts'
import type { Speaker } from '../../types'

export function SpeakerSelect() {
  const speaker = useTtsStore((s) => s.speaker)
  const setSpeaker = useTtsStore((s) => s.setSpeaker)
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [defaultId, setDefaultId] = useState<string>('')
  const [err, setErr] = useState('')

  useEffect(() => {
    fetchSpeakers()
      .then((r) => {
        setSpeakers(r.speakers)
        setDefaultId(r.default)
        if (!speaker && r.default) setSpeaker(r.default)
      })
      .catch((e) => setErr(String(e)))
  }, [])

  return (
    <div>
      <label className="label" htmlFor="speaker">音色</label>
      <select
        id="speaker"
        className="input"
        value={speaker}
        onChange={(e) => setSpeaker(e.target.value)}
        disabled={!speakers.length}
      >
        {!speakers.length && <option value="">加载中...</option>}
        {speakers.map((sp) => (
          <option key={sp.id} value={sp.id}>
            {sp.name}
          </option>
        ))}
      </select>
      {err && <div className="mt-1 text-xs text-red-500">{err}</div>}
      {defaultId && !speaker && (
        <div className="mt-1 text-xs text-slate-400">默认使用「温柔桃子」</div>
      )}
    </div>
  )
}
