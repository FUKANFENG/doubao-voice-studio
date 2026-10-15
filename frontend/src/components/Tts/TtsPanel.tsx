import { TextInput } from './TextInput'
import { SpeakerSelect } from './SpeakerSelect'
import { RateSlider } from './RateSlider'
import { PitchSlider } from './PitchSlider'
import { FormatSelect } from './FormatSelect'
import { PlayButton } from './PlayButton'
import { Icon, Waveform } from '../Icons'
export function TtsPanel() {
  return <div className="voice-layout"><section className="card text-composer"><div className="section-heading"><span className="icon-tile orange"><Icon name="file" /></span><div><h2>写下你想说的</h2><p>一段开场白、一句问候，或一个新点子</p></div><span className="subtle-badge">文字 → 语音</span></div><TextInput /><div className="composer-bottom"><Icon name="spark" size={16} /><span>用标点安排停顿，让表达更自然。</span></div><PlayButton /></section><div className="voice-settings"><section className="card"><div className="section-heading"><span className="icon-tile teal"><Icon name="wave" /></span><div><h2>声音的性格</h2><p>调出你喜欢的语气</p></div></div><div className="settings-stack"><SpeakerSelect /><RateSlider /><PitchSlider /><FormatSelect /></div></section><div className="sound-card"><Waveform /><strong>每一句，都有自己的节奏。</strong><p>调节语速和音高，找到适合内容的声音。</p></div></div></div>
}
