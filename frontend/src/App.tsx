import { useEffect, useState } from 'react'
import { HealthDot } from './components/Layout/HealthDot'
import { TtsPanel } from './components/Tts/TtsPanel'
import { AsrPanel } from './components/Asr/AsrPanel'
import { TranscribePanel } from './components/Transcribe/TranscribePanel'
import { DeveloperPanel } from './components/Developer/DeveloperPanel'
import { ChatPanel } from './components/Chat/ChatPanel'
import { Icon, type IconName } from './components/Icons'
type Tab = 'tts' | 'asr' | 'transcribe' | 'chat' | 'developer'
const tabs: { id: Tab; label: string; sub: string; icon: IconName }[] = [
  { id: 'tts', label: '语音合成', sub: '让文字有声音', icon: 'wave' },
  { id: 'asr', label: '实时听写', sub: '把想法说出来', icon: 'mic' },
  { id: 'transcribe', label: '课程转录', sub: '留下每一个知识点', icon: 'book' },
  { id: 'chat', label: '豆包对话', sub: '把灵感慢慢聊清楚', icon: 'chat' },
  { id: 'developer', label: '开发文档', sub: '把能力接入你的项目', icon: 'code' },
]
const descriptions: Record<Tab, string> = {
  tts: '选一个喜欢的声音，让你的文字自然开口。',
  asr: '打开麦克风，边说边记录。专注表达，文字交给豆包。',
  transcribe: '从一段视频，到一份可回看的学习笔记。',
  chat: '提问、写作、梳理思路，让每一次对话都有下文。',
  developer: '从这里出发，把语音与学习能力带到你的下一个项目。',
}
export default function App() {
  const [tab, setTab] = useState<Tab>(() => tabs.some(item => item.id === location.hash.slice(1)) ? location.hash.slice(1) as Tab : 'tts')
  const active = tabs.find(item => item.id === tab)!
  useEffect(() => {
    const change = () => { const value = location.hash.slice(1); if (tabs.some(item => item.id === value)) setTab(value as Tab) }
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])
  return <div className="studio-shell">
    <aside className="sidebar">
      <a aria-label="豆包语音工作室首页" className="brand" href="#tts" onClick={() => setTab('tts')}><span className="brand-mark"><Icon name="wave" size={25} /></span><span>豆包<span className="brand-sub">VOICE STUDIO</span></span></a>
      <div className="sidebar-label">我的工作台</div>
      <nav aria-label="功能导航">{tabs.map(item => <button key={item.id} aria-label={item.label} className={'nav-item ' + (tab === item.id ? 'active' : '')} aria-current={tab === item.id ? 'page' : undefined} onClick={() => { setTab(item.id); history.replaceState(null, '', '#' + item.id) }}><Icon name={item.icon} /><span><strong>{item.label}</strong><small>{item.sub}</small></span><span className="nav-indicator" /></button>)}</nav>
      <div className="sidebar-note"><span className="mini-orbit"><Icon name="spark" /></span><strong>声音里的灵感，<br />都值得被留下。</strong><p>合成 · 听写 · 学习笔记</p></div>
      <div className="sidebar-bottom"><span className="status-dot" />个人语音工作室<span>v1.4</span></div>
    </aside>
    <div className="studio-main">
      <header className="topbar"><span>工作台 <span className="breadcrumb-slash">/</span> <strong>{active.label}</strong></span><HealthDot /></header>
      <main className="workspace">
        <div className="page-heading"><div><span className="eyebrow">MAKE ROOM FOR YOUR IDEAS</span><h1>{active.label}<span className="heading-dot">.</span></h1><p>{descriptions[tab]}</p></div><div className="heading-art" aria-hidden="true"><Icon name={active.icon} size={42} /><span /><span /></div></div>
        {tab === 'tts' && <TtsPanel />}
        {tab === 'asr' && <AsrPanel />}
        {tab === 'transcribe' && <TranscribePanel />}
        {tab === 'chat' && <ChatPanel />}
        {tab === 'developer' && <DeveloperPanel />}
        <footer className="workspace-footer"><span>一点声音，无限可能。</span><span>由豆包提供语音与文字能力</span></footer>
      </main>
    </div>
  </div>
}
