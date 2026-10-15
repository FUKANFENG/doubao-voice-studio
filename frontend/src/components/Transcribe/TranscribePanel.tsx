import { useEffect } from 'react'
import { useTranscribeStore } from '../../state/transcribeStore'
import { SubmitForm } from './SubmitForm'
import { QueueView } from './QueueView'
import { JobStatusView } from './JobStatusView'
import { ResultView } from './ResultView'
import { Icon } from '../Icons'
export function TranscribePanel() {
  const selectedId = useTranscribeStore(s => s.selectedId)
  const error = useTranscribeStore(s => s.connectionError)
  useEffect(() => {
    let active = true, timer: ReturnType<typeof setTimeout>
    async function tick() {
      await useTranscribeStore.getState().refresh()
      if (active) timer = setTimeout(tick, 2000)
    }
    void tick()
    return () => { active = false; clearTimeout(timer) }
  }, [selectedId])
  return <>
    <div className="workflow-strip"><span><b>01</b> 添加视频或音频</span><Icon name="arrow" size={16} /><span><b>02</b> 自动排队转录</span><Icon name="arrow" size={16} /><span><b>03</b> 收获文字与笔记</span></div>
    {error && <div className="notice warning" role="status">连接暂时中断，任务仍会在服务端继续。{error}</div>}
    <div className="transcribe-layout"><div className="transcribe-input"><SubmitForm /><QueueView /></div><div className="transcribe-output"><JobStatusView /><ResultView key={selectedId} /></div></div>
  </>
}
