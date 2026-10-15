import { useTtsStore } from '../../state/ttsStore'

export function PitchSlider() {
  const pitch = useTtsStore((s) => s.pitch)
  const setPitch = useTtsStore((s) => s.setPitch)
  return (
    <div>
      <label className="label flex justify-between" htmlFor="pitch">
        <span>音高</span>
        <span className="text-doubao-600 font-mono">
          {pitch > 0 ? `+${pitch}` : pitch}
        </span>
      </label>
      <input
        id="pitch"
        type="range"
        className="slider"
        min={-10}
        max={10}
        step={1}
        value={pitch}
        onChange={(e) => setPitch(parseInt(e.target.value, 10))}
      />
      <div className="flex justify-between text-xs text-slate-400 mt-1">
        <span>-10 低</span>
        <span>0</span>
        <span>+10 高</span>
      </div>
    </div>
  )
}
