// ASR 流式识别 WebSocket 客户端
// 上行：二进制 ArrayBuffer（4096 字节 PCM 帧） + 文本 {"type":"finish"}
// 下行：文本 {"type":"partial|final|error", ...}

import type { AsrEvent } from '../types'

type Handler = (e: AsrEvent) => void

export class AsrClient {
  private ws: WebSocket | null = null
  private partialHandler: Handler | null = null
  private finalHandler: Handler | null = null
  private errorHandler: ((e: Error) => void) | null = null
  private closeHandler: ((code: number) => void) | null = null
  private openedHandler: (() => void) | null = null
  private queuedHandler: ((position: number) => void) | null = null

  /** 打开 WebSocket */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/asr`
      const ws = new WebSocket(url)
      // 必须 arraybuffer，否则浏览器不会把二进制帧当 ArrayBuffer 处理
      ws.binaryType = 'arraybuffer'
      this.ws = ws

      let settled = false
      const resolveReady = () => {
        if (!settled) {
          settled = true
          resolve()
        }
      }
      const rejectBeforeReady = (error: Error) => {
        if (!settled) {
          settled = true
          reject(error)
        }
      }
      ws.onopen = () => {
        this.openedHandler?.()
      }
      ws.onerror = (ev) => {
        const error = new Error('WebSocket error')
        this.errorHandler?.(error)
        rejectBeforeReady(error)
      }
      ws.onclose = (ev) => {
        this.closeHandler?.(ev.code)
        rejectBeforeReady(new Error('ASR 连接已关闭'))
      }
      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) return
        try {
          const data = JSON.parse(ev.data) as AsrEvent
          if (data.type === 'queued') this.queuedHandler?.(Number(data.position) || 1)
          else if (data.type === 'ready') resolveReady()
          else if (data.type === 'partial') this.partialHandler?.(data)
          else if (data.type === 'final') this.finalHandler?.(data)
          else if (data.type === 'error') {
            const error = new Error(`[${data.code}] ${data.message}`)
            this.errorHandler?.(error)
            rejectBeforeReady(error)
          }
        } catch (e) {
          // ignore non-JSON
        }
      }
    })
  }

  onPartial(h: Handler) { this.partialHandler = h }
  onFinal(h: Handler) { this.finalHandler = h }
  onError(h: (e: Error) => void) { this.errorHandler = h }
  onClose(h: (code: number) => void) { this.closeHandler = h }
  onQueued(h: (position: number) => void) { this.queuedHandler = h }

  /** 发送一帧 PCM（4096 字节 Int16-LE） */
  sendPcmFrame(buf: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(buf)
    }
  }

  /** 通知后端"采集结束" */
  finish(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'finish' }))
    }
  }

  /** 关闭 WebSocket */
  close(): void {
    try {
      this.ws?.close()
    } catch { /* ignore */ }
    this.ws = null
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
