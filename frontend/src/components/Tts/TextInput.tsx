import { useTtsStore } from '../../state/ttsStore'
export function TextInput() {
  const text = useTtsStore(s => s.text), setText = useTtsStore(s => s.setText)
  return <div className="text-input-wrap"><label className="sr-only" htmlFor="synthesis-text">合成文本</label><textarea id="synthesis-text" className="composer-textarea" maxLength={2000} value={text} onChange={e => setText(e.target.value)} placeholder="把你的文字放在这里，让声音赋予它温度…" /><div className="text-counter"><span>中文、英文都可以</span><span>{text.length.toLocaleString()} <span>/ 2,000</span></span></div></div>
}
