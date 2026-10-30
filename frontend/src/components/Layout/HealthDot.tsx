import { useEffect, useState } from 'react'
import { fetchHealth } from '../../api/tts'
import type { HealthResponse } from '../../types'
export function HealthDot() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let active = true, timer: ReturnType<typeof setTimeout>
    async function update() {
      try { const data = await fetchHealth(); if (active) { setHealth(data); setFailed(false) } }
      catch { if (active) setFailed(true) }
    }
    async function tick() {
      await update()
      if (active) timer = setTimeout(tick, 10000)
    }
    const changed = () => { void update() }
    window.addEventListener('doubao-auth-updated', changed)
    void tick()
    return () => { active = false; clearTimeout(timer); window.removeEventListener('doubao-auth-updated', changed) }
  }, [])
  const okay = !failed && !!health?.auth_ok
  return <span className={'health-badge ' + (okay ? 'healthy' : failed || health ? 'unhealthy' : '')} role="status">
    <span className="status-dot" />{failed ? '服务连接中断' : !health ? '连接服务中' : okay ? '服务已就绪' : '登录态需更新'}
  </span>
}
