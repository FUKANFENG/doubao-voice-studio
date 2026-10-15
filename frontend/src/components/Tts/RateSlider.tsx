import { useTtsStore } from '../../state/ttsStore'

export function RateSlider() {
  const rate = useTtsStore((s) => s.speechRate)
  const setRate = useTtsStore((s) => s.setSpeechRate)
  return (
    <div>
      <label className="label flex justify-between" htmlFor="speech-rate">
        <span>语速</span>
        <span className="text-doubao-600 font-mono">{rate.toFixed(2)}x</span>
      </label>
      <input
        id="speech-rate"
        type="range"
        className="slider"
        min={0.7}
        max={2.0}
        step={0.05}
        value={rate}
        onChange={(e) => setRate(parseFloat(e.target.value))}
      />
      <div className="flex justify-between text-xs text-slate-400 mt-1">
        <span>0.7x 慢</span>
        <span>1.0x</span>
        <span>2.0x 快</span>
      </div>
    </div>
  )
}
