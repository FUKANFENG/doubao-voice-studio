import { useEffect, useRef, useState } from 'react'
import { fetchAccountStatus, importAccount, readLocalAccount, type AccountStatus } from '../../api/account'
import { Icon } from '../Icons'
import './account.css'

const buildsUrl = 'https://github.com/FUKANFENG/doubao-voice-studio/actions/workflows/windows-auth-tool.yml'

export function AccountPanel() {
  const [status, setStatus] = useState<AccountStatus | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState('')
  const [config, setConfig] = useState('')
  const [requestUrl, setRequestUrl] = useState('')
  const [refresh, setRefresh] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const mounted = useRef(true)
  const pending = useRef(false)
  useEffect(() => {
    mounted.current = true
    const controller = new AbortController()
    setError('')
    fetchAccountStatus(controller.signal).then(value => { if (!controller.signal.aborted) setStatus(value) }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '状态加载失败')
    })
    return () => { mounted.current = false; controller.abort() }
  }, [refresh])

  async function apply(kind: 'local' | 'import') {
    if (!status?.can_manage || pending.current) return
    setError(''); setSuccess('')
    let parsed: unknown
    if (kind === 'import') {
      try {
        if (new Blob([config]).size > 65536) throw new Error()
        parsed = JSON.parse(config)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error()
      } catch { setError('请导入 64 KB 以内的完整 JSON 配置。'); return }
    }
    pending.current = true
    setBusy(kind)
    try {
      const next = kind === 'local' ? await readLocalAccount(requestUrl) : await importAccount(parsed)
      if (mounted.current) {
        setStatus(next); setConfig(''); setRequestUrl('')
        if (fileInput.current) fileInput.current.value = ''
        setSuccess('登录态已验证并应用。现在就可以继续合成、听写或转录。')
      }
      window.dispatchEvent(new Event('doubao-auth-updated'))
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error && reason.name !== 'TimeoutError'
        ? reason.message : '等待响应超时，请刷新状态确认是否已经生效。')
    } finally { pending.current = false; if (mounted.current) setBusy('') }
  }

  async function loadFile(file: File | undefined) {
    if (!file) return
    setError(''); setSuccess('')
    try {
      if (file.size > 65536) throw new Error('配置超过 64 KB，请选择工具导出的 JSON 文件。')
      const text = await file.text()
      if (mounted.current) setConfig(text.replace(/^\uFEFF/, ''))
    } catch (reason) { if (mounted.current) setError(reason instanceof Error ? reason.message : '无法读取文件') }
  }

  const disabled = !status?.can_manage || !!busy
  return <div className="account-panel">
    <section className="card account-overview" aria-label="当前登录态">
      <span className={'account-emblem ' + (status?.auth_ok ? 'ready' : '')}><Icon name="key" size={28} /></span>
      <div className="account-overview-copy"><span className="account-kicker">你的豆包连接</span><h2>{!status ? '正在读取连接状态…' : status.auth_ok ? '一切就绪，继续创作。' : '更新一次登录态，灵感继续。'}</h2><p>{status?.auth_ok ? '合成、听写、转录和对话，共用这一份已验证的登录态。' : '从 Windows 客户端获取，或导入你已有的配置。验证通过后立即生效。'}</p></div>
      <button className="btn-ghost" onClick={() => setRefresh(value => value + 1)} disabled={!!busy}><Icon name="refresh" size={16} />刷新状态</button>
      {status && <div className="account-facts"><span><i className={'status-dot ' + (status.auth_ok ? 'ready' : '')} />{status.auth_ok ? '会话验证通过' : '会话待更新'}</span><span>{status.loaded ? '配置已加载' : '尚未加载配置'}</span><span>生效范围：当前工作室</span></div>}
    </section>
    {status && !status.can_manage && <p className="notice warning" role="status">原生部署请在服务所在电脑用 localhost 或 127.0.0.1 打开本页。Docker 部署请更新宿主机挂载的 auth.json 后重启容器。这里仍可查看状态和下载 Windows 工具。</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    {success && <p className="notice success" role="status">{success}</p>}
    <div className="account-methods">
      <section className="card account-method">
        <div className="section-heading"><span className="icon-tile orange"><Icon name="key" /></span><div><h2>从 Windows 客户端获取</h2><p>熟悉的账号，直接接着用</p></div></div>
        <ol className="account-steps"><li><b>1</b><div><strong>在豆包客户端登录</strong><p>登录完成后，完全退出客户端与托盘进程。</p></div></li><li><b>2</b><div><strong>一键读取，自动验证</strong><p>沿用工作室现有配置，读取本机当前用户的登录态。</p></div></li><li><b>3</b><div><strong>回到工作台继续使用</strong><p>验证通过后立即应用，保留已有任务和历史。</p></div></li></ol>
        <details className="account-advanced"><summary>首次配置，缺少会话参数？</summary><label className="label" htmlFor="account-request-url">本人实际语音请求 URL</label><input id="account-request-url" type="password" autoComplete="off" spellCheck={false} className="input" value={requestUrl} onChange={event => setRequestUrl(event.target.value)} disabled={disabled} placeholder="wss://ws-samantha.doubao.com/…" /><p>已有完整配置时留空即可。</p></details>
        <button className="btn-primary account-main-action" disabled={disabled || !status?.local_available} onClick={() => void apply('local')}><Icon name={busy === 'local' ? 'clock' : 'key'} size={17} />{busy === 'local' ? '正在读取并验证…' : '获取并应用登录态'}</button>
        {status?.can_manage && !status.local_available && <p className="field-hint">自动读取需要 Windows 原生服务。其他原生部署可使用配置导入。</p>}
      </section>
      <section className="card account-method">
        <div className="section-heading"><span className="icon-tile teal"><Icon name="file" /></span><div><h2>导入已有配置</h2><p>桌面工具导出，一次导入即可</p></div></div>
        <button className="account-file" type="button" disabled={disabled} onClick={() => fileInput.current?.click()}><Icon name="upload" size={23} /><strong>选择 auth.json 文件</strong><span>也可以将完整配置粘贴到下面</span></button>
        <input ref={fileInput} id="account-file" className="file-input" type="file" accept="application/json,.json" disabled={disabled} onChange={event => void loadFile(event.target.files?.[0])} />
        <label className="label" htmlFor="account-json">登录态配置</label><textarea id="account-json" className="input account-json" autoComplete="off" autoCorrect="off" spellCheck={false} placeholder={'{\n  "cookie": "…",\n  "web_id": "…",\n  "tea_uuid": "…"\n}'} value={config} disabled={disabled} onChange={event => setConfig(event.target.value)} />
        <button className="btn-primary account-main-action" disabled={disabled || !config.trim()} onClick={() => void apply('import')}><Icon name={busy === 'import' ? 'clock' : 'check'} size={17} />{busy === 'import' ? '正在验证并应用…' : '验证并应用配置'}</button><p className="field-hint">验证失败会保留原配置。导入成功后，输入内容自动清空。</p>
      </section>
    </div>
    <section className="card account-tool"><span className="icon-tile"><Icon name="download" /></span><div><h2>把登录态工具放在手边</h2><p>Windows 独立程序 · 获取、复制、保存，也能直接应用到本机工作室。</p></div><a className="btn-ghost" href={status?.tool_available ? '/api/auth/tool' : buildsUrl} target={status?.tool_available ? undefined : '_blank'} rel="noreferrer"><Icon name="download" size={16} />{status?.tool_available ? '下载 Windows 工具' : '获取 Windows 构建'}</a></section>
  </div>
}
