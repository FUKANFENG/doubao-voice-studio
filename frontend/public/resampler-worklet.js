// AudioWorklet 处理器：把麦克风 Float32 采样转成 Int16-LE，按 2048 采样切帧
// 2048 采样 * 2 字节 = 4096 字节 / 帧（匹配豆包 SDK 的 FRAME_SAMPLES/FRAME_BYTES）

class PCM16Framer extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Float32Array(2048)
    this.idx = 0
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || input.length === 0) return true
    const channel = input[0]
    if (!channel) return true

    for (let i = 0; i < channel.length; i++) {
      this.buffer[this.idx++] = channel[i]
      if (this.idx >= this.buffer.length) {
        // Float32 -> Int16-LE
        const out = new Int16Array(this.buffer.length)
        for (let j = 0; j < this.buffer.length; j++) {
          let s = this.buffer[j]
          if (s > 1) s = 1
          if (s < -1) s = -1
          // 跟 SDK 同步：s < 0 用 0x8000，s >= 0 用 0x7FFF
          out[j] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7FFF)
        }
        // transferable 发出去
        this.port.postMessage({ pcm16: out }, [out.buffer])
        this.idx = 0
      }
    }
    return true
  }
}

registerProcessor('pcm16-framer', PCM16Framer)
