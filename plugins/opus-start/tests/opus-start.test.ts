import { expect, test } from 'claude-code/testing'
import { shouldSwitch } from '../hooks/register'

const START = { cwd: '/', surface: 'terminal', isInteractive: true } as const

// A missing call fails the test at this bound instead of the 5 s default.
const BOUNDED = { timeoutMs: 2000 } as const

test('only an interactive Sonnet session switches', () => {
  expect(shouldSwitch('claude-sonnet-5-5', true)).toBe(true)
  expect(shouldSwitch('Sonnet 5.5', true)).toBe(true)
  expect(shouldSwitch('claude-sonnet-5-5', false)).toBe(false)
  expect(shouldSwitch('claude-haiku-5-5', true)).toBe(false)
  expect(shouldSwitch('claude-opus-5-5', true)).toBe(false)
})

test('a Sonnet session runs /model opus', BOUNDED, async ($, on) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('ui.toast', () => ({ value: undefined }))

  const ran = new Promise<string>(resolve => {
    on('command.run', (_, e) => {
      resolve(`${e.command} ${e.args}`)
      return { text: '' }
    })
  })

  await $.session.start(START)
  expect(await ran).toBe('model opus')
})

test('a second session.start, as on a reload, does not switch again', BOUNDED, async ($, on) => {
  let model = 'claude-sonnet-5-5'
  let runs = 0
  let settled = () => {}
  const firstSwitch = new Promise<void>(resolve => {
    settled = resolve
  })

  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.model', () => ({ value: model }))
  on('command.run', () => {
    runs += 1
    model = 'claude-opus-5-5'
    settled()
    return { text: '' }
  })

  await $.session.start(START)
  await firstSwitch

  // The person picked Sonnet again by hand; the reload must leave it.
  model = 'claude-sonnet-5-5'
  await $.session.start(START)
  await new Promise(resolve => setTimeout(resolve, 200))

  expect(runs).toBe(1)
})

test('a refused switch says so in a toast', BOUNDED, async ($, on) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('command.run', () => ({ text: 'Model not available' }))

  const toasted = new Promise<string>(resolve => {
    on('ui.toast', (_, e) => {
      resolve(e.text)
      return { value: undefined }
    })
  })

  await $.session.start(START)
  expect(await toasted).toBe('opus-start: still on claude-sonnet-5-5')
})
