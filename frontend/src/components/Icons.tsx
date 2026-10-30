import type { CSSProperties } from 'react'
export type IconName = 'chat' | 'wave' | 'mic' | 'book' | 'arrow' | 'plus' | 'link' | 'upload' | 'check' | 'clock' | 'spark' | 'file' | 'download' | 'copy' | 'close' | 'play' | 'code' | 'key' | 'refresh'
const paths: Record<IconName, React.ReactNode> = {
  key: <><circle cx="8" cy="9" r="5" /><path d="m12 13 8 8m-4-4 3-3m-6 0 3-3" /></>,
  refresh: <><path d="M20 7V3l-4 4a8 8 0 1 0 4 8M20 3h-5" /></>,
  chat: <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z" />,
  code: <><path d="m7 6-5 6 5 6m10-12 5 6-5 6M14 3l-4 18" /></>,
  wave: <><path d="M4 10v4m4-8v12m4-15v18m4-15v12m4-8v4" /></>,
  mic: <><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" /></>,
  book: <><path d="M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3zM12 6v15" /><path d="M6 8h3m-3 4h3m6-4h3m-3 4h3" /></>,
  arrow: <><path d="M4 12h16m-6-6 6 6-6 6" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  link: <><path d="m10 13 4-4m-6 7-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 12a4 4 0 0 0 6 0l5-5a4 4 0 0 0-6-6l-1 1" /></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /><path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5z" /></>,
  file: <><path d="M14 2H5v20h14V7zM14 2v6h5M8 12h8m-8 4h6" /></>,
  download: <><path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4" /></>,
  copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M15 8V3H3v12h5" /></>,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  play: <path d="m8 4 12 8-12 8z" />,
}
export function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name]}</svg>
}
export function Waveform() {
  return <div className="waveform" aria-hidden="true">{[18, 30, 45, 26, 56, 76, 42, 62, 88, 54, 34, 68, 44, 26, 52, 32, 18].map((height, i) => <span key={i} style={{ height, animationDelay: i * 0.08 + 's' }} />)}</div>
}
