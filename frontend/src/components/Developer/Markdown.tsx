import { Fragment, type ReactNode } from 'react'
import { CopyButton } from './CopyButton'

// Deliberately small Markdown subset for the maintained API.md; HTML is always text.
function inline(text: string): ReactNode[] {
  const pattern = /(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g
  return text.split(pattern).filter(Boolean).map((part, index) => {
    if (part.startsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    if (part.startsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link && (/^\/(?!\/)/.test(link[2]) || /^https?:\/\//.test(link[2])))
      return <a key={index} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>
    return <Fragment key={index}>{part}</Fragment>
  })
}
function cells(line: string) { return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim()) }

export function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    const key = index
    if (!line.trim()) { index++; continue }
    if (line.startsWith('```')) {
      const language = line.slice(3).trim() || 'text'
      const code: string[] = []
      index++
      while (index < lines.length && !lines[index].startsWith('```')) code.push(lines[index++])
      index++
      blocks.push(<div className="dev-code" key={key}>
        <div className="dev-code-heading"><span>{language}</span><CopyButton text={code.join('\n')} label="复制代码" /></div>
        <pre tabIndex={0} aria-label={language + ' 代码示例'}><code>{code.join('\n')}</code></pre>
      </div>)
      continue
    }
    if (line.startsWith('### ')) {
      blocks.push(<h3 key={key}>{inline(line.slice(4))}</h3>); index++; continue
    }
    if (line.startsWith('|') && /^\|[\s:|-]+\|$/.test(lines[index + 1] || '')) {
      const headers = cells(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && lines[index].startsWith('|')) rows.push(cells(lines[index++]))
      blocks.push(<div className="dev-table-scroll" tabIndex={0} role="region" aria-label="参数与接口表格，可横向滚动" key={key}>
        <table><thead><tr>{headers.map((header, i) => <th scope="col" key={i}>{inline(header)}</th>)}</tr></thead>
          <tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{inline(cell)}</td>)}</tr>)}</tbody>
        </table></div>)
      continue
    }
    if (line.startsWith('- ')) {
      const items: string[] = []
      while (index < lines.length && lines[index].startsWith('- ')) items.push(lines[index++].slice(2))
      blocks.push(<ul key={key}>{items.map((item, i) => <li key={i}>{inline(item)}</li>)}</ul>); continue
    }
    blocks.push(<p key={key}>{inline(line)}</p>); index++
  }
  return <div className="dev-prose">{blocks}</div>
}

export function sectionsFromMarkdown(markdown: string) {
  // Ignore headings inside fenced examples.
  const sections: { title: string; content: string }[] = []
  let inCode = false
  for (const line of markdown.split(/\r?\n/)) {
    if (line.startsWith('```')) inCode = !inCode
    if (!inCode && line.startsWith('## ')) sections.push({ title: line.slice(3), content: '' })
    else if (sections.length) sections[sections.length - 1].content += line + '\n'
  }
  return sections
}
