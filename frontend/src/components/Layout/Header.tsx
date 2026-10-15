import { HealthDot } from './HealthDot'

export function Header() {
  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="text-2xl">🍊</span>
        <h1 className="text-lg font-semibold text-slate-800">
          豆包 ASR / TTS Demo
        </h1>
      </div>
      <HealthDot />
    </header>
  )
}
