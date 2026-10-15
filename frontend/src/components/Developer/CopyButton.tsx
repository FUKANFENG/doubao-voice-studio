import { useEffect, useState } from 'react'
import { Icon } from '../Icons'

export function CopyButton({ text, label, primary = false }: { text: string; label: string; primary?: boolean }) {
  const [message, setMessage] = useState('')
  useEffect(() => setMessage(''), [text])
  return <span className="dev-copy-control">
    <button type="button" className={primary ? 'btn-primary' : 'dev-copy-button'} aria-label={label} onClick={async () => {
      try { await navigator.clipboard.writeText(text); setMessage('已复制') }
      catch { setMessage('复制失败，请手动选择内容') }
    }}><Icon name={message === '已复制' ? 'check' : 'copy'} size={15} />{label}</button>
    {message && <span className="dev-copy-status" role="status">{message}</span>}
  </span>
}
