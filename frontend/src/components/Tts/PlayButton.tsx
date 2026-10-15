import { useEffect, useRef, useState } from 'react'
import { useTtsStore } from '../../state/ttsStore'
import { synthesizeTts } from '../../api/tts'
import { Icon } from '../Icons'
export function PlayButton() {
  const store = useTtsStore()
  const audioRef = useRef<HTMLAudioElement>(null)
  const outputFormat = store.resultFormat
  const [playError, setPlayError] = useState('')
  useEffect(() => {
    if (store.audioUrl && outputFormat !== 'pcm') void audioRef.current?.play().catch(() => {})
  }, [store.audioUrl, outputFormat])
  async function synthesize() {
    if (store.state === 'synthesizing' || !store.text.trim()) return
    setPlayError('')
    store.startSynth()
    try {
      const blob = await synthesizeTts({ text: store.text, speaker: store.speaker, format: store.format, speech_rate: store.speechRate, pitch: store.pitch }, store.updateProgress)
      if (!blob.size) throw new Error('没有收到音频，请重新合成')
      store.finishSynth(URL.createObjectURL(blob), blob.size)
    } catch (error) { store.failSynth(error instanceof Error ? error.message : '合成失败，请重试') }
  }
  const busy = store.state === 'synthesizing'
  return <div className="playback-controls">
    <div className="flex gap-2"><button className="btn-primary flex-1" disabled={busy || !store.text.trim() || !store.speaker} onClick={() => void synthesize()}><Icon name={busy ? 'clock' : 'wave'} size={18} />{busy ? '正在合成 · ' + (store.bytesReceived / 1024).toFixed(1) + ' KB' : '生成语音'}</button><button className="btn-ghost" disabled={!store.audioUrl || outputFormat === 'pcm'} onClick={() => { if (audioRef.current) { audioRef.current.currentTime = 0; void audioRef.current.play().catch(() => setPlayError('播放未能开始，请使用音频播放器或下载试听。')) } }}><Icon name="play" size={16} />重播</button></div>
    {store.errorMsg && <p className="notice error" role="alert">{store.errorMsg}</p>}
    {store.audioUrl && <div className="audio-result">{outputFormat !== 'pcm' ? <audio ref={audioRef} src={store.audioUrl} controls className="w-full mt-4" onPlay={store.startPlay} onEnded={store.endPlay} onPause={store.endPlay} onError={() => setPlayError('浏览器无法预览此格式，可以下载音频或改用 MP3。')} /> : <p className="field-hint">PCM 为原始音频，请下载后在音频工具中使用。</p>}<div className="result-footer"><span>{playError || (store.totalBytes / 1024).toFixed(1) + ' KB · 已生成'}</span><a className="btn-ghost" href={store.audioUrl} download={'doubao-voice.' + outputFormat}><Icon name="download" size={15} />下载音频</a></div></div>}
  </div>
}
