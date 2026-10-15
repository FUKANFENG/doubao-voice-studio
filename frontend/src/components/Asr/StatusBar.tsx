import { useEffect } from 'react'
import { useAsrStore } from '../../state/asrStore'
import { formatDuration } from '../../api/transcribe'
export function StatusBar() {
  const { connState, durationMs, updateDuration } = useAsrStore()
  useEffect(() => {
    if (connState !== 'recording') return
    const timer = setInterval(updateDuration, 500)
    return () => clearInterval(timer)
  }, [connState, updateDuration])
  const labels = { idle: '准备就绪', connecting: '连接中', queued: '等待 ASR', connected: '已连接', recording: '录音中', finishing: '接收结果中', closed: '录音已结束', error: '请检查连接' }
  return <div className="record-status"><span><span className="status-dot" />{labels[connState]}</span><span>录音时长 <b>{formatDuration(durationMs / 1000)}</b></span></div>
}
