// Node.js 18+，使用内置 fetch；默认只检查健康，不创建任务。
import { readFile } from 'node:fs/promises';
import { basename, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export class DoubaoClient {
  constructor(baseUrl = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async request(path, options = {}) {
    // 不自动重试 POST，避免网络超时后重复创建任务。
    const response = await fetch(this.baseUrl + path, {
      ...options, signal: AbortSignal.timeout(300_000),
    });
    if (!response.ok) {
      const raw = await response.text();
      let detail = raw.slice(0, 500);
      try {
        const payload = JSON.parse(raw);
        detail = typeof payload.detail === 'string'
          ? payload.detail : payload.detail?.message || JSON.stringify(payload.detail);
      } catch { /* 代理也可能返回 HTML 错误 */ }
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }
    return response;
  }

  async json(path, body) {
    const options = body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    };
    return (await this.request(path, options)).json();
  }

  health() { return this.json('/api/health'); }
  speakers() { return this.json('/api/speakers'); }
  capabilities() { return this.json('/api/transcribe/capabilities'); }
  jobs() { return this.json('/api/transcribe/jobs'); }
  job(id) { return this.json('/api/transcribe/jobs/' + encodeURIComponent(id)); }
  submitUrl(url, summarize = false) { return this.json('/api/transcribe/url', { url, summarize }); }

  async tts(text, options = {}) {
    const response = await this.request('/api/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, ...options }),
    });
    const audio = Buffer.from(await response.arrayBuffer());
    if (!audio.length) throw new Error('返回了空音频，请检查服务端上游状态。');
    return audio;
  }

  async submitFile(path, summarize = false) {
    // 示例把文件读入内存；超大文件建议用 curl.exe -F。
    const form = new FormData();
    form.append('file', new Blob([await readFile(path)]), basename(path));
    form.append('summarize', String(summarize));
    return (await this.request('/api/transcribe/file', { method: 'POST', body: form })).json();
  }

  async cancel(id) {
    return (await this.request('/api/transcribe/jobs/' + encodeURIComponent(id) + '/cancel',
      { method: 'POST' })).json();
  }

  async wait(id, timeoutMs = 3_600_000) {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      const job = await this.job(id);
      if (['done', 'error', 'cancelled'].includes(job.status)) {
        if (job.status !== 'done') throw new Error(job.error || `任务 ${id} 已取消`);
        return job; // 单独检查 summary_status。
      }
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    throw new Error(`等待任务 ${id} 超时；服务端继续执行，可使用相同 id 查询。`);
  }

  async download(id, kind = 'text') {
    if (!['text', 'srt', 'summary'].includes(kind)) throw new Error('无效的结果类型');
    return (await this.request('/api/transcribe/jobs/' + encodeURIComponent(id) + '/' + kind)).text();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const client = new DoubaoClient(process.env.DOUBAO_BASE_URL);
  console.log(await client.health());
}
