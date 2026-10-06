// Warframe themes: a Void Fissure run, and the frames the spinner verbs name
// (Titania, Khora, Dante, Gyre, Qorvex). Same contract as the stock themes in
// themes.ts; kept apart so the upstream files stay easy to sync.
import { canvas, cells, draw, frame, mod, noise, plot, put } from './cells'
import type { Canvas, Grid } from './cells'
import { SCENE_ROWS, clouds, glyphStars, ground, ridge } from './scenes'
import type { PetArt } from './pets'
import type { Act, Theme } from './themes'

export const WARFRAME = ['fissure', 'titania', 'khora', 'dante', 'gyre', 'qorvex'] as const
type WarframeName = (typeof WARFRAME)[number]

// ---- foes ------------------------------------------------------------------------

const GRUNT = [
  ['.HH.', 'HVVH', '.BB.', 'BBBB', '.BB.', '.B.B'],
  ['.HH.', 'HVVH', '.BB.', 'BBBB', '.BB.', 'B..B'],
]
const GRINEER = { H: '#a68a64', V: '#ff595e', B: '#656d4a' }
const CORRUPTED = { H: '#2b2d42', V: '#ffd60a', B: '#8d99ae' }
/** Ticks a fallen foe's effect plays. */
const FALL = 8

type Foe = { x: number; age: number }

/**
 * Foe k walks in from the right at tick k * gap and falls `at` across the
 * width: `age` is negative while it walks, then the ticks since it fell.
 * Thicker and faster while a tool runs, slow while the turn asks.
 */
function march(t: number, w: number, act: Act, at: number): { foes: Foe[]; falls: number; spot: number } {
  const gap = act === 'tool' ? 12 : 22
  const speed = act === 'ask' ? 0.3 : 0.9
  const spot = Math.floor(w * at)
  const travel = (w + 2 - spot) / speed
  const foes: Foe[] = []
  for (let k = Math.max(0, Math.floor((t - travel - FALL) / gap)); k * gap <= t; k++) {
    const since = t - k * gap
    const age = Math.floor(since - travel)
    if (age < FALL) foes.push({ x: age < 0 ? Math.round(w + 2 - since * speed) : spot, age })
  }
  const falls = t < travel ? 0 : Math.floor((t - travel) / gap) + 1
  return { foes, falls, spot }
}

/** Where shots stop: the nearest foe still walking, else the edge. */
function reach(foes: Foe[], w: number): number {
  return Math.min(w, ...foes.filter(f => f.age < 0).map(f => f.x))
}

/** Shots leaving `x0` every `every` ticks at `speed` px a tick, gone where they meet `stop`. */
function shots(t: number, x0: number, stop: number, every: number, speed: number, at: (x: number, i: number) => void): void {
  for (let i = 0, x = x0 + mod(t, every) * speed; x < stop; i++, x += every * speed) at(x, i)
}

function walk(cv: Canvas, foe: Foe, t: number, colors: Record<string, string>): void {
  draw(cv, foe.x, 1, frame(GRUNT, t >> 1), colors)
}

function askMark(g: Grid, act: Act, t: number, x: number): void {
  if (act === 'ask' && mod(t, 8) < 6) put(g, x, 0, '?', { c: '#ffd166', b: true })
}

// ---- fissure: Excalibur cracking a relic on Corrupted ---------------------------

const EXCALIBUR = {
  stand: ['..C..', '.WWW.', '.WGW.', 'WWWWW', '.WGW.', '.W.W.', '.W.W.'],
  swing: ['..C...', '.WWW..', '.WGW..', 'WWWWBB', '.WGW..', '.W.W..', 'W...W.'],
}
const RELIC = ['.GGGG.', 'GLGGLG', 'GGCCGG', 'GLGGLG', '.GGGG.']
const WAVE = ['W.', '.B', '.B', 'W.']
/** The relic's shell, brighter with each Reactant. */
const GLOW = ['#b08d2a', '#c9a227', '#d4a017', '#e9c46a', '#ffd60a']

function fissureScene(t: number, w: number, act: Act): Grid {
  const cv = canvas(w, SCENE_ROWS)
  ground(cv, t, 7, 0.4, ['#c9a227', '#f5e6d3', '#f5e6d3', '#8d6e3f'])
  const { foes, falls } = march(t, w, act, 0.5)
  // Exalted Blade: crescent waves out to the nearest foe.
  if (act !== 'ask') shots(t, 13, reach(foes, w), 4, 3, x => draw(cv, x, 2, WAVE, { W: '#e0fbfc', B: '#4cc9f0' }))
  for (const f of foes) {
    if (f.age < 0) {
      walk(cv, f, t, CORRUPTED)
      continue
    }
    // Void light bursting out, and its Reactant flying up to the count.
    const c = frame(['#ffffff', '#fff3b0', '#ffd60a', '#ff9f1c', '#c9a227'], f.age)
    for (let a = 0; a < 8; a++) plot(cv, f.x + 2 + Math.cos(a * 0.785) * f.age, 4 + Math.sin(a * 0.785) * f.age * 0.5, c)
    plot(cv, f.x + 2 + ((w - 6 - f.x) * f.age) / FALL, 3 - f.age / 2, '#ff9f1c')
  }
  const count = falls % 10
  const isRadiant = falls > 0 && count === 0
  const glow = isRadiant ? '#ffffff' : frame(GLOW, Math.floor(count / 2))
  draw(cv, 7, mod(t, 8) < 4 ? 0 : 1, RELIC, { G: glow, L: '#fff3b0', C: isRadiant || mod(t, 6) < 3 ? '#ffffff' : '#ff9f1c' })
  const isSwing = act !== 'ask' && mod(t, 4) < 2
  draw(cv, 1, 0, isSwing ? EXCALIBUR.swing : EXCALIBUR.stand, { C: '#ffd60a', W: '#f8f9fa', G: '#ffd60a', B: '#4cc9f0' })
  const g = cells(cv)
  glyphStars(g, t, Math.floor(w / 5), 0.2, ['·', '✦'], ['#c9a227', '#fff3b0', '#8d6e3f'], 11)
  const label = isRadiant ? '✶ RADIANT ✶' : `◈ ${count}/10`
  put(g, w - label.length - 1, 0, label, { c: isRadiant ? '#fff3b0' : '#ffd60a', b: true })
  askMark(g, act, t, 6)
  return g
}

// ---- titania: Razorwing, her Razorflies and Dex Pixia --------------------------

const FAIRY = [
  ['P.....P', 'PP.H.PP', '.PPBPP.', '..PBP..', '...B...'],
  ['...H...', '.PPBPP.', 'PPPBPPP', 'P..B..P', '...B...'],
]
const PETALS = ['✿', '❀', '❁']

function titaniaScene(t: number, w: number, act: Act): Grid {
  const cv = canvas(w, SCENE_ROWS)
  ridge(cv, t, 7, 3, 0.15, '#1b4332', 7)
  ground(cv, t, 7, 0.6, ['#2d6a4f', '#40916c', '#2d6a4f', '#ff8fab', '#40916c'])
  const { foes } = march(t, w, act, 0.6)
  const x = Math.floor(w * 0.15) + Math.round(Math.sin(t * 0.06) * w * 0.06)
  const y = 1 + Math.round(Math.sin(t * 0.3))
  if (act === 'tool' || act === 'say') {
    shots(t, x + 8, reach(foes, w), 3, 4, sx => {
      plot(cv, sx, y + 2, '#ff4d6d')
      plot(cv, sx + 1, y + 2, '#ffccd5')
    })
  }
  for (const f of foes) {
    if (f.age < 0) walk(cv, f, t, GRINEER)
    // Spellbind: lifted off its feet, then gone in petals.
    else if (f.age < 4) draw(cv, f.x, 1 - f.age, GRUNT[0]!, { H: '#ffc2d1', V: '#ff8fab', B: '#ffc2d1' })
  }
  for (let i = 0; i < 4; i++) {
    const a = t * 0.35 + (i * Math.PI) / 2
    plot(cv, x + 3 + Math.cos(a) * 6, y + 2 + Math.sin(a) * 2.5, i % 2 ? '#ffd60a' : '#80ffdb')
  }
  draw(cv, x, y, frame(FAIRY, t >> 1), { P: '#ff8fab', H: '#ffd166', B: '#80b918' })
  const g = cells(cv)
  glyphStars(g, t, Math.floor(w / 5), 0.15, ['·', '✧'], ['#ffd166', '#80ffdb', '#ff8fab'], 5)
  for (const f of foes) if (f.age >= 4) put(g, f.x + 1, f.age < 6 ? 1 : 0, frame(PETALS, f.age), { c: '#ff8fab' })
  askMark(g, act, t, x + 8)
  return g
}

// ---- khora: the whip, Venari and Strangledome ----------------------------------

const KHORA = {
  stand: ['C...C', '.WWW.', '.WGW.', 'WWWWW', '.WWW.', '.W.W.', '.W.W.'],
  lash: ['C...C.', '.WWW..', '.WGW..', 'WWWWWG', '.WWW..', '.W.W..', 'W...W.'],
}
const VENARI = [
  ['....T.T', 'T...TTT', '.TTTTT.', '.T...T.'],
  ['....T.T', '.T..TTT', '.TTTTT.', 'T.....T'],
]

function khoraScene(t: number, w: number, act: Act): Grid {
  const cv = canvas(w, SCENE_ROWS)
  ground(cv, t, 7, 0.5, ['#3d405b', '#6c757d', '#3d405b', '#b08968'])
  const { foes, spot } = march(t, w, act, 0.6)
  const isLash = act !== 'ask' && mod(t, 6) < 3
  if (isLash) {
    const end = Math.min(reach(foes, w), 6 + (mod(t, 6) + 1) * 8)
    for (let x = 6; x < end; x++) plot(cv, x, 3 + Math.round(Math.sin(x * 0.7 - t)), '#e9c46a')
  }
  for (const f of foes) {
    if (f.age < 0) {
      walk(cv, f, t, GRINEER)
      continue
    }
    // Strangledome: a dome of chain closing over the foe, who hangs inside it.
    const r = Math.min(6, 2 + f.age)
    for (let a = 0; a <= 12; a++) {
      const ang = (a * Math.PI) / 12
      plot(cv, f.x + 2 + Math.cos(ang) * r, 7 - Math.sin(ang) * r, a % 2 ? '#e9c46a' : '#2a9d8f')
    }
    draw(cv, f.x, 0, GRUNT[0]!, { H: '#6c757d', V: '#ff595e', B: '#495057' })
  }
  const vx = 8 + Math.round(((Math.sin(t * 0.1) + 1) / 2) * Math.max(0, spot - 16))
  draw(cv, vx, 3, frame(VENARI, t >> 1), { T: '#80ffdb' })
  draw(cv, 1, 0, isLash ? KHORA.lash : KHORA.stand, { C: '#e9c46a', W: '#2a9d8f', G: '#e9c46a' })
  const g = cells(cv)
  glyphStars(g, t, Math.floor(w / 6), 0.1, ['·', '✦'], ['#6c757d', '#2a9d8f'], 19)
  // Pilfering Swarm: the loot it shakes out.
  for (const f of foes) if (f.age >= 4) put(g, f.x + 2, f.age - 4, '◆', { c: '#80ffdb', b: true })
  askMark(g, act, t, 6)
  return g
}

// ---- dante: Noctua, Pageflight and the Final Verse -----------------------------

const DANTE = ['.CCC.', '.WWW.', '.WGW.', 'WWWWW', 'WWGWW', '.WWW.', '.W.W.']
const NOCTUA = [
  ['PPP.PPP', 'PPPSPPP', '.CCSCC.'],
  ['.PP.PP.', 'PPPSPPP', '.CCSCC.'],
]

function danteScene(t: number, w: number, act: Act): Grid {
  const cv = canvas(w, SCENE_ROWS)
  ground(cv, t, 7, 0.4, ['#3c096c', '#5a189a', '#3c096c', '#ffd166'])
  const { foes } = march(t, w, act, 0.6)
  if (act !== 'ask') shots(t, 15, reach(foes, w), 3, 3, (x, i) => draw(cv, x, 2 + Math.round(Math.sin(x * 0.5 + i)), ['PP'], { P: '#f5e6d3' }))
  for (const f of foes) {
    if (f.age < 0) walk(cv, f, t, GRINEER)
    // Ink: the foe running down into the floor.
    else for (let i = 0; i < 6; i++) plot(cv, f.x + noise(i + f.x) * 4, 1 + f.age * 0.7 + noise(i * 3) * 3, i % 2 ? '#9d4edd' : '#3c096c')
  }
  draw(cv, 8, mod(t, 10) < 5 ? 1 : 2, frame(NOCTUA, t >> 2), { P: '#f5e6d3', S: '#9d4edd', C: '#3c096c' })
  draw(cv, 1, 0, DANTE, { C: '#ffd166', W: '#7b2cbf', G: '#ffd166' })
  const g = cells(cv)
  glyphStars(g, t, Math.floor(w / 6), 0.1, ['·', '✦'], ['#9d4edd', '#ffd166'], 13)
  // Three verses to a Final Verse: Tragedy when the dark ones lead, else Elegy.
  const beat = act === 'tool' ? 8 : 12
  const round = Math.floor(t / (beat * 4))
  const n = Math.floor(mod(t, beat * 4) / beat)
  const isDark = [0, 1, 2].map(i => noise(round * 3 + i) < 0.5)
  if (n < 3) {
    for (let i = 0; i <= n; i++) put(g, w - 6 + i * 2, 0, isDark[i] ? '◐' : '◑', { c: isDark[i] ? '#9d4edd' : '#ffd166', b: true })
  } else {
    const isTragedy = isDark.filter(Boolean).length >= 2
    const label = isTragedy ? '✠ TRAGEDY' : '✠ ELEGY'
    put(g, w - label.length - 1, 0, label, { c: isTragedy ? '#e63946' : '#ffd166', b: true })
    if (isTragedy) {
      for (const f of foes) if (f.age < 0) put(g, f.x + 1, 1 + mod(t, 2), '╱', { c: '#e63946', b: true })
    } else {
      put(g, 2 + mod(t >> 1, 3), 2 - mod(t >> 1, 3), '♥', { c: '#ffd166', b: true })
    }
  }
  askMark(g, act, t, 6)
  return g
}

// ---- gyre: the Arcsphere, Coil Horizon and its lightning -----------------------

const GYRE = ['C...C', '.WWW.', '.WGW.', 'WWWWW', '.WGW.', '..W..']
const BOLT = ['.W', 'W.', '.W', 'W.', '.W', 'W.']

function gyreScene(t: number, w: number, act: Act): Grid {
  const cv = canvas(w, SCENE_ROWS)
  clouds(cv, t, Math.max(2, Math.floor(w / 18)), 0.2, '#1b263b', 2, 17)
  ground(cv, t, 7, 0.6, ['#14213d', '#1b263b', '#14213d', '#4cc9f0'])
  const { foes, spot } = march(t, w, act, 0.55)
  if (act === 'tool' || foes.some(f => f.age >= 0)) {
    for (let i = 0; i < 10; i++) {
      const a = t * 0.5 + (i * Math.PI) / 5
      const r = 2 + (i % 3)
      plot(cv, spot + 2 + Math.cos(a) * r * 1.5, 4 + Math.sin(a) * r * 0.6, i % 2 ? '#7209b7' : '#4cc9f0')
    }
  }
  for (const f of foes) {
    if (f.age < 0) walk(cv, f, t, GRINEER)
    else if (f.age < 5) {
      draw(cv, f.x, 1, GRUNT[0]!, { H: '#e0fbfc', V: '#ffd60a', B: '#4cc9f0' })
      draw(cv, f.x + 1, 0, BOLT, { W: f.age < 2 ? '#ffffff' : '#ffd60a' })
    }
  }
  const a = t * 0.3
  draw(cv, 3 + Math.round(Math.cos(a) * 6), 3 + Math.round(Math.sin(a) * 2), ['EE', 'EE'], { E: mod(t, 4) < 2 ? '#4cc9f0' : '#e0fbfc' })
  draw(cv, 1, mod(t, 12) < 6 ? 0 : 1, GYRE, { C: '#ffd60a', W: '#e0fbfc', G: '#4cc9f0' })
  const g = cells(cv)
  if (act === 'tool' && mod(t, 3) === 0) put(g, 7 + mod(t, 5), 1, 'ϟ', { c: '#ffd60a', b: true })
  const charge = `ϟ ${String(mod(t >> 1, 101)).padStart(3)}%`
  put(g, w - charge.length - 1, 0, charge, { c: '#4cc9f0', b: true })
  askMark(g, act, t, 6)
  return g
}

// ---- qorvex: Chyrinka Pillar, Containment Wall, Crucible Blast -----------------

const QORVEX = ['.WWW.', 'WWGWW', 'WWWWW', 'WOOOW', 'WWWWW', 'WW.WW', 'WW.WW']
const PILLAR_X = 9

function qorvexScene(t: number, w: number, act: Act): Grid {
  const cv = canvas(w, SCENE_ROWS)
  ground(cv, t, 7, 0.5, ['#ffd60a', '#ffd60a', '#212529', '#212529'])
  const { foes } = march(t, w, act, 0.55)
  const height = Math.min(6, 1 + Math.floor(mod(t, 60) / 4))
  for (let y = 7 - height; y < 7; y++) {
    plot(cv, PILLAR_X, y, '#70e000')
    plot(cv, PILLAR_X + 1, y, '#ccff33')
  }
  if (height === 6) {
    const r = mod(t, 10)
    for (let a = 0; a < 12; a++) plot(cv, PILLAR_X + 1 + Math.cos(a * 0.524) * r, 4 + Math.sin(a * 0.524) * r * 0.5, '#38b000')
  }
  if (act === 'say' && mod(t, 6) < 4) {
    for (let x = 6; x < reach(foes, w); x++) {
      plot(cv, x, 3, '#ff9f1c')
      plot(cv, x, 4, mod(x + t, 3) ? '#ffd60a' : '#ffffff')
    }
  }
  for (const f of foes) {
    if (f.age < 0) {
      walk(cv, f, t, GRINEER)
      continue
    }
    // Containment Wall: two slabs closing on the foe, then a green flash.
    const gap = Math.max(0, 6 - f.age * 2)
    for (let y = 1; y < 7; y++) {
      plot(cv, f.x - gap - 1, y, '#70e000')
      plot(cv, f.x - gap, y, '#adb5bd')
      plot(cv, f.x + 4 + gap, y, '#adb5bd')
      plot(cv, f.x + 5 + gap, y, '#70e000')
    }
    if (gap > 0) draw(cv, f.x, 1, GRUNT[0]!, GRINEER)
    else draw(cv, f.x, 2, ['GGGG', 'GWWG', 'GGGG'], { G: '#70e000', W: '#ccff33' })
  }
  draw(cv, 1, 0, QORVEX, { W: '#6c757d', G: '#70e000', O: '#ff9f1c' })
  const g = cells(cv)
  if (height === 6) put(g, PILLAR_X + 3, 0, '☢', { c: '#70e000', b: true })
  askMark(g, act, t, 6)
  return g
}

// ---- themes ----------------------------------------------------------------------

export const WARFRAME_THEMES: Record<WarframeName, Theme> = {
  fissure: {
    name: 'fissure',
    rows: SCENE_ROWS,
    color: '#ffd60a',
    accent: '#f5e6d3',
    sprite: {
      think: ['⟨◇⟩ ·  ', '⟨◈⟩ ·· ', '⟨◆⟩ ···', '⟨◈⟩ ·· '],
      tool: ['⟨◈⟩   ✧', '⟨◈⟩  ✧ ', '⟨◈⟩ ✧  ', '⟨◆⟩✧   ', '⟨✦⟩    '],
      say: ['⟨◈⟩ ▸  ', '⟨◈⟩ ▸▸ ', '⟨◈⟩ ▸▸▸'],
      wait: ['⟨◈⟩ .  ', '⟨◈⟩ .. ', '⟨◈⟩ ...'],
    },
    happy: '⟨✶⟩ ✧✧',
    sad: '⟨◇⟩ ...',
    dead: '⟨✕⟩',
    sleep: '⟨◇⟩ zZ',
    confetti: ['◆', '✦', '✧', '·', '◈'],
    palette: ['#ffd60a', '#f5e6d3', '#ff9f1c', '#c9a227'],
    scene: fissureScene,
  },
  titania: {
    name: 'titania',
    rows: SCENE_ROWS,
    color: '#ff8fab',
    accent: '#80b918',
    sprite: {
      think: ['ƸӜƷ ·  ', ')Ӝ( ·· ', 'ƸӜƷ ···', ')Ӝ( ·· '],
      tool: ['ƸӜƷ⁍    ', ')Ӝ( ⁍⁍  ', 'ƸӜƷ  ⁍⁍⁍', ')Ӝ(    ✧'],
      say: ['ƸӜƷ ✿', ')Ӝ( ❀', 'ƸӜƷ ❁'],
      wait: ['ƸӜƷ .  ', ')Ӝ( .. ', 'ƸӜƷ ...'],
    },
    happy: 'ƸӜƷ ✧✧',
    sad: ')Ӝ( ...',
    dead: '×Ӝ×',
    sleep: ')Ӝ( zZ',
    confetti: ['✿', '❀', '❁', '✧', '·'],
    palette: ['#ff8fab', '#80b918', '#ffd166', '#80ffdb'],
    scene: titaniaScene,
  },
  khora: {
    name: 'khora',
    rows: SCENE_ROWS,
    color: '#2ec4b6',
    accent: '#e9c46a',
    sprite: {
      think: ['ᓚᘏᗢ ·  ', 'ᓚᘏᗢ ·· ', 'ᓚᘏᗢ ···'],
      tool: ['ᓚᘏᗢ ∿    ', 'ᓚᘏᗢ ∿∿   ', 'ᓚᘏᗢ ∿∿∿  ', 'ᓚᘏᗢ ∿∿∿∿◆'],
      say: ['ᓚᘏᗢ ⌒  ', 'ᓚᘏᗢ ⌒⌒ ', 'ᓚᘏᗢ ⌒⌒⌒'],
      wait: ['ᓚᘏᗢ .  ', 'ᓚᘏᗢ .. ', 'ᓚᘏᗢ ...'],
    },
    happy: 'ᓚᘏᗢ ◆◆',
    sad: 'ᓚᘏᗢ ...',
    dead: 'ᓚᘏᗢ ✕',
    sleep: 'ᓚᘏᗢ zZ',
    confetti: ['◆', '∿', '✦', '·', '⌒'],
    palette: ['#2ec4b6', '#e9c46a', '#80ffdb', '#b08968'],
    scene: khoraScene,
  },
  dante: {
    name: 'dante',
    rows: SCENE_ROWS,
    color: '#c77dff',
    accent: '#ffd166',
    sprite: {
      think: ['✎ ◐    ', '✎ ◐◑   ', '✎ ◐◑◐  ', '✎ ◐◑◐ ✠'],
      tool: ['▤ ≈    ', '▤  ≈≈  ', '▤   ≈≈≈', '▤     ✶'],
      say: ['✎ ✠  ', '✎ ✠✠ ', '✎ ✠✠✠'],
      wait: ['▤ .  ', '▤ .. ', '▤ ...'],
    },
    happy: '✎ ✠ ♥',
    sad: '▤ ...',
    dead: '▤ ✕',
    sleep: '▤ zZ',
    confetti: ['◐', '◑', '✠', '·', '♥'],
    palette: ['#c77dff', '#ffd166', '#f5e6d3', '#e63946'],
    scene: danteScene,
  },
  gyre: {
    name: 'gyre',
    rows: SCENE_ROWS,
    color: '#4cc9f0',
    accent: '#ffd60a',
    sprite: {
      think: ['◎ ·  ', '◎  · ', '◎   ·', '◎  · '],
      tool: ['◎ϟ    ', '◎ϟϟ   ', '◎ϟϟϟ  ', '◎ϟϟϟϟ✶'],
      say: ['◎ ≋ϟ', '◎ ϟ≋'],
      wait: ['◎ .  ', '◎ .. ', '◎ ...'],
    },
    happy: '◎ ϟϟ',
    sad: '◎ ...',
    dead: '◎ ✕',
    sleep: '◎ zZ',
    confetti: ['ϟ', '✦', '◎', '·', '+'],
    palette: ['#4cc9f0', '#ffd60a', '#7209b7', '#e0fbfc'],
    scene: gyreScene,
  },
  qorvex: {
    name: 'qorvex',
    rows: SCENE_ROWS,
    color: '#70e000',
    accent: '#ff9f1c',
    sprite: {
      think: ['▐▓▌ ▁', '▐▓▌ ▃', '▐▓▌ ▅', '▐▓▌ ▇', '▐▓▌ █'],
      tool: ['▐▓▌ █    █', '▐▓▌  █  █ ', '▐▓▌   ██  ', '▐▓▌   ✶   '],
      say: ['▐▓▌═   ', '▐▓▌══  ', '▐▓▌═══ ', '▐▓▌════'],
      wait: ['▐▓▌ .  ', '▐▓▌ .. ', '▐▓▌ ...'],
    },
    happy: '▐▓▌ ☢',
    sad: '▐▓▌ ...',
    dead: '▐▓▌ ✕',
    sleep: '▐▓▌ zZ',
    confetti: ['☢', '▪', '✦', '·', '+'],
    palette: ['#70e000', '#ff9f1c', '#adb5bd', '#ccff33'],
    scene: qorvexScene,
  },
}

// ---- pets --------------------------------------------------------------------------

export const WARFRAME_PETS: Record<WarframeName, PetArt> = {
  /** A Radiant relic, Void light in its seams. */
  fissure: {
    body: ['...GGGGGG...', '..GLGGGGLG..', '.GGGGGGGGGG.', '.GLGGGGGGLG.', '...GGGGGG...'],
    colors: { G: '#d4a017', L: '#fff3b0' },
    eyes: [4, 7],
    eyeRow: 1,
    eye: '#2b2d42',
    lid: '#d4a017',
    mouth: [5, 3],
    blush: '#ff9f1c',
    spark: '#ffd60a',
  },
  /** Titania in Razorwing, wings beating. */
  titania: {
    body: ['PP........PP', 'PPP.HHHH.PPP', '.PPPHHHHPPP.', 'PPP.GGGG.PPP', 'PP...GG...PP'],
    step: ['............', 'PPPPHHHHPPPP', 'PPPPHHHHPPPP', '.PP.GGGG.PP.', '.....GG.....'],
    colors: { P: '#ff8fab', H: '#ffe8d6', G: '#80b918' },
    eyes: [4, 7],
    eyeRow: 1,
    eye: '#2b2d42',
    lid: '#ffe8d6',
    blush: '#ff4d6d',
    spark: '#80ffdb',
  },
  /** Venari, Khora's kavat: pointed ears, glowing cheeks, tail up. */
  khora: {
    body: ['.T.....T....', 'TTT...TTT.G.', 'TTTTTTTTT.T.', 'TGTTTTTGT.T.', '.TTTTTTTTTT.'],
    step: ['.T.....T....', 'TTT...TTT..G', 'TTTTTTTTT.T.', 'TGTTTTTGT.T.', '.TTTTTTTTTT.'],
    colors: { T: '#2a9d8f', G: '#80ffdb' },
    eyes: [2, 6],
    eyeRow: 2,
    eye: '#d8f3dc',
    lid: '#2a9d8f',
    spark: '#80ffdb',
  },
  /** Noctua, Dante's book, open. */
  dante: {
    body: ['.PPPP..PPPP.', 'PPPPPPPPPPPP', 'PPPPPSSPPPPP', 'CPPPPSSPPPPC', '.CCCCCCCCCC.'],
    step: ['PPPP....PPPP', 'PPPPPPPPPPPP', 'PPPPPSSPPPPP', 'CPPPPSSPPPPC', '.CCCCCCCCCC.'],
    colors: { P: '#f5e6d3', S: '#9d4edd', C: '#3c096c' },
    eyes: [2, 9],
    eyeRow: 1,
    eye: '#5a189a',
    lid: '#f5e6d3',
    spark: '#c77dff',
  },
  /** Gyre's Arcsphere, crackling. */
  gyre: {
    body: ['...REEEER...', '.REEWWWWEER.', 'REEWWWWWWEER', '.REEWWWWEER.', '...REEEER...'],
    step: ['..R.EEEE.R..', '.EEEWWWWEEE.', 'EREWWWWWWERE', '.EEEWWWWEEE.', '..R.EEEE.R..'],
    colors: { R: '#7209b7', E: '#4cc9f0', W: '#e0fbfc' },
    eyes: [4, 7],
    eyeRow: 1,
    eye: '#14213d',
    lid: '#e0fbfc',
    mouth: [5, 3],
    spark: '#ffd60a',
  },
  /** Qorvex's helm, its core running hot. */
  qorvex: {
    body: ['..MMMMMMMM..', '.MMMMMMMMMM.', 'MMMMMMMMMMMM', 'MMGGGOOGGGMM', '.MMM....MMM.'],
    step: ['..MMMMMMMM..', '.MMMMMMMMMM.', 'MMMMMMMMMMMM', 'MMGGGOOGGGMM', '..MMM..MMM..'],
    colors: { M: '#495057', G: '#70e000', O: '#ff9f1c' },
    eyes: [3, 8],
    eyeRow: 1,
    eye: '#70e000',
    lid: '#495057',
    spark: '#ccff33',
  },
}
