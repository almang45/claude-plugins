// Finds the tables and fenced code in a reply so they can be drawn as cards; the rest
// stays markdown.

export type Align = 'left' | 'right' | 'center'

export type Table = { kind: 'table'; header: string[]; align: Align[]; rows: string[][] }

// `raw` is the fence as written, for the surfaces that keep Claude Code's own drawing.
export type Code = { kind: 'code'; lang: string; code: string; raw: string }

export type Segment = { kind: 'text'; text: string } | Table | Code

const SEPARATOR = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/
const FENCE = /^\s*(```|~~~)\s*([\w+#.-]*)/

// Inline emphasis and code ticks read as noise in a padded cell.
const clean = (cell: string): string =>
  cell.replace(/\*\*|__|`/g, '').replace(/\\\|/g, '|').trim()

export function cellsOf(line: string): string[] {
  const inner = line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '')

  return inner.split(/(?<!\\)\|/).map(clean)
}

const alignOf = (cell: string): Align => {
  const spec = cell.trim()

  if (spec.startsWith(':') && spec.endsWith(':')) {
    return 'center'
  }

  return spec.endsWith(':') ? 'right' : 'left'
}

const fit = (cells: string[], width: number): string[] =>
  Array.from({ length: width }, (_, i) => cells[i] ?? '')

export function splitReply(markdown: string): Segment[] {
  const lines = markdown.split('\n')
  const segments: Segment[] = []
  let text: string[] = []
  let inFence = false

  const flush = () => {
    if (text.join('\n').trim() !== '') {
      segments.push({ kind: 'text', text: text.join('\n') })
    }

    text = []
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? ''
    const next = lines[i + 1] ?? ''

    const fence = FENCE.exec(line)

    // A closed fence becomes a code segment; one still streaming stays text.
    if (fence !== null && !inFence) {
      const close = lines.findIndex((other, j) => j > i && FENCE.test(other) && other.trim().replace(/[`~]/g, '') === '')

      if (close !== -1) {
        flush()
        segments.push({
          kind: 'code',
          lang: (fence[2] ?? '').toLowerCase(),
          code: lines.slice(i + 1, close).join('\n'),
          raw: lines.slice(i, close + 1).join('\n'),
        })
        i = close
        continue
      }

      inFence = true
    } else if (fence !== null) {
      inFence = false
    }

    const header = cellsOf(line)
    const isTable =
      !inFence &&
      line.includes('|') &&
      SEPARATOR.test(next) &&
      header.length > 1 &&
      cellsOf(next).length === header.length

    if (!isTable) {
      text.push(line)
      continue
    }

    flush()

    const rows: string[][] = []
    i += 2

    while (i < lines.length && (lines[i] ?? '').includes('|') && (lines[i] ?? '').trim() !== '') {
      rows.push(fit(cellsOf(lines[i] ?? ''), header.length))
      i++
    }

    i--
    segments.push({ kind: 'table', header, align: cellsOf(next).map(alignOf), rows })
  }

  flush()

  return segments
}

// Terminal cells a character takes: wide East Asian characters and emoji take two,
// combining marks, zero-width joiners and skin-tone modifiers none.
const WIDE: readonly (readonly [number, number])[] = [
  [0x1100, 0x115f],
  [0x2e80, 0x303e],
  [0x3041, 0x33ff],
  [0x3400, 0x4dbf],
  [0x4e00, 0x9fff],
  [0xa000, 0xa4cf],
  [0xa960, 0xa97f],
  [0xac00, 0xd7a3],
  [0xf900, 0xfaff],
  [0xfe10, 0xfe19],
  [0xfe30, 0xfe6f],
  [0xff00, 0xff60],
  [0xffe0, 0xffe6],
  [0x1f300, 0x1f64f],
  [0x1f680, 0x1f6ff],
  [0x1f900, 0x1f9ff],
  [0x1fa70, 0x1faff],
  [0x20000, 0x3fffd],
]

const charWidth = (char: string): number => {
  const code = char.codePointAt(0) ?? 0

  if (/\p{Mn}|\p{Me}|\u200d|[\ufe00-\ufe0f]|\p{Emoji_Modifier}/u.test(char)) {
    return 0
  }

  return WIDE.some(([from, to]) => code >= from && code <= to) ? 2 : 1
}

export const widthOf = (text: string): number => [...text].reduce((sum, char) => sum + charWidth(char), 0)

// `text` cut to `width` cells, marked with an ellipsis where it lost text.
const cutTo = (text: string, width: number): string => {
  if (widthOf(text) <= width) {
    return text
  }

  let kept = ''
  let used = 0

  for (const char of text) {
    const next = charWidth(char)

    if (used + next > width - 1) {
      break
    }

    kept += char
    used += next
  }

  return `${kept}…`
}

// Each column's widest cell, header included, in terminal cells.
export function naturalWidths(table: Table): number[] {
  return table.header.map((cell, col) => Math.max(widthOf(cell), ...table.rows.map(row => widthOf(row[col] ?? ''))))
}

// The narrowest a column that wraps may get.
const MIN_WRAP = 3

// Column widths that fit `maxWidth`. Columns narrower than an even share keep their natural
// width; the rest split what is left by the square root of their natural width, so a long
// prose column gets more room than a medium one without starving it, and wrap inside it.
export function columnWidths(table: Table, maxWidth: number, gap: number): number[] {
  const natural = naturalWidths(table)
  const widths = [...natural]
  let budget = maxWidth - gap * (natural.length - 1)
  let open = natural.map((_, col) => col)

  for (;;) {
    const share = budget / Math.max(1, open.length)
    const fitting = open.filter(col => (natural[col] ?? 0) <= share)

    if (fitting.length === 0 || fitting.length === open.length) {
      break
    }

    budget -= fitting.reduce((sum, col) => sum + (natural[col] ?? 0), 0)
    open = open.filter(col => !fitting.includes(col))
  }

  if (open.reduce((sum, col) => sum + (natural[col] ?? 0), 0) <= budget) {
    return widths
  }

  const weight = (col: number) => Math.sqrt(natural[col] ?? 0)
  const total = open.reduce((sum, col) => sum + weight(col), 0)

  for (const col of open) {
    widths[col] = Math.max(MIN_WRAP, Math.min(natural[col] ?? 0, Math.floor((budget * weight(col)) / total)))
  }

  // Rounding leaves a few cells over; the widest open column takes them.
  const spare = budget - open.reduce((sum, col) => sum + (widths[col] ?? 0), 0)
  const widest = open.reduce((best, col) => ((natural[col] ?? 0) > (natural[best] ?? 0) ? col : best), open[0] ?? 0)

  if (spare > 0) {
    widths[widest] = Math.min(natural[widest] ?? 0, (widths[widest] ?? 0) + spare)
  }

  return widths
}

// A cell cut to its column, marked with an ellipsis where it lost text.
export function cutCell(text: string, width: number): string {
  return cutTo(text, width)
}

export function padCell(text: string, width: number, align: Align): string {
  const cut = cutTo(text, width)
  const room = width - widthOf(cut)

  if (align === 'right') {
    return ' '.repeat(room) + cut
  }

  if (align === 'center') {
    const left = Math.floor(room / 2)

    return ' '.repeat(left) + cut + ' '.repeat(room - left)
  }

  return cut + ' '.repeat(room)
}
