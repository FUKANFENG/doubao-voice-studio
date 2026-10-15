import { useState } from 'react'
import { useAsrStore } from '../../state/asrStore'
import { Icon } from '../Icons'
export function TranscriptView() {
  const store = useAsrStore()
  const [copied, setCopied] = useState('')
  const text = store.finalText || store.partialText
  return <section className="card live-transcript"><div className="section-heading compact"><h2>灵感记录</h2><Icon name="file" size={18} /></div>{text ? <p className="live-text">{text}{store.connState === 'recording' && <span className="live-caret" />}</p> : <div className="live-empty"><Icon name="mic" size={28} /><p>你说的每一句话，<br />都会慢慢出现在这里。</p></div>}<div className="result-footer"><span role="status">{copied || text.length + ' 字'}</span><button className="icon-button" disabled={!text} aria-label="复制识别文字" onClick={async () => { try { await navigator.clipboard.writeText(text); setCopied('已复制') } catch { setCopied('请手动选择文字复制') } }}><Icon name="copy" size={17} /></button></div></section>
}
