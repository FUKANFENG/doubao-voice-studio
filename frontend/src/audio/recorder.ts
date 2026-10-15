// 浏览器录音 + 16kHz AudioContext + AudioWorklet
// 输出 4096 字节/帧的 Int16-LE PCM（与豆包 SDK 完全一致）

export class PcmRecorder {
  private stream: MediaStream | null = null
  private audioCtx: AudioContext | null = null
  private workletNode: AudioWorkletNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private onFrameCb: ((buf: ArrayBuffer) => void) | null = null
  private sampleRate = 16000

  /**
   * 启动录音
   * @param onFrame 收到一帧 PCM 时回调（4096 字节 Int16-LE）
   */
  async start(onFrame: (buf: ArrayBuffer) => void): Promise<void> {
    this.onFrameCb = onFrame

    // 1. getUserMedia（单声道、回声消除、噪声抑制）
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })

    // 2. 16kHz AudioContext（让浏览器原生降采样，省去手写降采样）
    //    Chrome/Edge/Firefox 都支持 sampleRate 选项
    this.audioCtx = new AudioContext({ sampleRate: this.sampleRate })

    // 3. 加载 AudioWorklet 模块
    await this.audioCtx.audioWorklet.addModule('/resampler-worklet.js')

    // 4. 创建处理节点
    this.workletNode = new AudioWorkletNode(this.audioCtx, 'pcm16-framer')
    this.workletNode.port.onmessage = (ev) => {
      const pcm16 = ev.data.pcm16 as Int16Array
      this.onFrameCb?.(pcm16.buffer as ArrayBuffer)
    }

    // 5. 接通：麦克风 -> AudioWorklet
    this.sourceNode = this.audioCtx.createMediaStreamSource(this.stream)
    this.sourceNode.connect(this.workletNode)

    // 注意：worklet 节点不能 connect 到 destination，否则会回放！
  }

  /** 停止录音，释放资源 */
  async stop(): Promise<void> {
    try { this.workletNode?.disconnect() } catch {}
    try { this.sourceNode?.disconnect() } catch {}
    try { await this.audioCtx?.close() } catch {}
    try { this.stream?.getTracks().forEach(t => t.stop()) } catch {}
    this.workletNode = null
    this.sourceNode = null
    this.audioCtx = null
    this.stream = null
    this.onFrameCb = null
  }

  get actualSampleRate(): number {
    return this.audioCtx?.sampleRate ?? this.sampleRate
  }
}
