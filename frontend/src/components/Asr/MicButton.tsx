import { useEffect, useRef } from 'react'
import { useAsrStore } from '../../state/asrStore'
import { AsrClient } from '../../api/asr'
import { PcmRecorder } from '../../audio/recorder'
import { Icon } from '../Icons'
export function MicButton() {
  const store = useAsrStore()
  const session = useRef(0)
  const asrRef = useRef<AsrClient | null>(null)
  const recorderRef = useRef<PcmRecorder | null>(null)
  const finishTimer = useRef<ReturnType<typeof setTimeout>>()
  const supported = !!navigator.mediaDevices?.getUserMedia
  function cleanup() {
    clearTimeout(finishTimer.current)
    void recorderRef.current?.stop()
    recorderRef.current = null
    asrRef.current?.close()
    asrRef.current = null
  }
  useEffect(() => () => {
    session.current++
    cleanup()
    const state = useAsrStore.getState()
    if (['recording', 'connecting', 'finishing'].includes(state.connState)) {
      state.setFinal(state.partialText)
      state.setConnState('closed')
    }
  }, [])
  async function start() {
    const version = ++session.current
    cleanup()
    store.reset()
    store.setConnState('connecting')
    const asr = new AsrClient()
    asrRef.current = asr
    let ended = false
    function fail(message: string) {
      if (version !== session.current) return
      ended = true
      store.setError(message)
      cleanup()
    }
    asr.onPartial(event => { if (version === session.current && !ended) store.setPartial(event.text || '') })
    asr.onQueued(position => { if (version === session.current && !ended) store.setQueued(position) })
    asr.onFinal(() => {
      if (version !== session.current || ended) return
      ended = true
      store.setFinal(useAsrStore.getState().partialText)
      store.updateDuration()
      store.setConnState('closed')
      cleanup()
    })
    asr.onError(error => fail(error.message))
    asr.onClose(() => {
      if (version === session.current && !ended) fail('连接已断开，已识别的文字保留在右侧。请重新录音。')
    })
    try {
      await asr.connect()
      if (version !== session.current || ended) { asr.close(); return }
      store.setConnState('connected')
      const recorder = new PcmRecorder()
      recorderRef.current = recorder
      await recorder.start(frame => { if (version === session.current && !ended) { asr.sendPcmFrame(frame); store.incFrame() } })
      if (version !== session.current || ended) { await recorder.stop(); return }
      store.startRecord()
    } catch (error) { fail(error instanceof Error ? error.message : '麦克风启动失败，请检查权限') }
  }
  async function stop() {
    store.updateDuration()
    store.setConnState('finishing')
    await recorderRef.current?.stop()
    if (useAsrStore.getState().connState !== 'finishing') return
    finishTimer.current = setTimeout(() => {
      store.setFinal(useAsrStore.getState().partialText)
      store.setError('等待识别结果超时，已收到的文字已保留。')
      session.current++
      cleanup()
    }, 15000)
    asrRef.current?.finish()
  }
  const recording = store.connState === 'recording'
  const busy = ['connecting', 'queued', 'finishing'].includes(store.connState)
  return <div className="microphone-control">
    <button className={'mic-button ' + (recording ? 'recording' : '')} onClick={() => void (recording ? stop() : start())} disabled={busy || !supported} aria-label={recording ? '停止录音' : '开始录音'}>{recording ? <span className="stop-square" /> : <Icon name="mic" size={36} />}</button>
    <p className="mic-label">{!supported ? '请使用支持麦克风的浏览器，并通过 HTTPS 访问' : store.connState === 'connecting' ? '正在连接麦克风…' : store.connState === 'queued' ? 'ASR 忙，已进入等待队列…' : store.connState === 'finishing' ? '正在接收最终结果…' : recording ? '正在倾听，点击结束' : store.connState === 'closed' ? '已记录，点击开始新的一段' : '点击麦克风，开始说话'}</p>
    {store.errorMsg && <p className="notice error" role="alert">{store.errorMsg}</p>}
  </div>
}
