import { MicButton } from './MicButton'
import { TranscriptView } from './TranscriptView'
import { StatusBar } from './StatusBar'
import { Icon, Waveform } from '../Icons'
export function AsrPanel() {
  return <div className="voice-layout"><section className="card recording-card"><div className="section-heading"><span className="icon-tile orange"><Icon name="mic" /></span><div><h2>此刻，想说点什么？</h2><p>允许麦克风访问后，就可以开始记录</p></div></div><div className="recording-stage"><Waveform /><MicButton /></div><StatusBar /></section><div className="voice-settings"><TranscriptView /><div className="notice neutral"><Icon name="book" size={18} /><span>长课程或已有的音视频文件，可以到「课程转录」中提交，自动排队处理。</span></div></div></div>
}
