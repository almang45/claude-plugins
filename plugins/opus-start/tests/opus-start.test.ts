import { expect, test } from 'claude-code/testing'
import { shouldSwitch } from '../hooks/register'

test('only an interactive Sonnet session switches', () => {
  expect(shouldSwitch('claude-sonnet-5-5', true)).toBe(true)
  expect(shouldSwitch('Sonnet 5.5', true)).toBe(true)
  expect(shouldSwitch('claude-sonnet-5-5', false)).toBe(false)
  expect(shouldSwitch('claude-haiku-5-5', true)).toBe(false)
  expect(shouldSwitch('claude-opus-5-5', true)).toBe(false)
})

test('a Sonnet session runs /model opus', async ($, on) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))

  const ran = new Promise<string>(resolve => {
    on('command.run', (_, e) => {
      resolve(`${e.command} ${e.args}`)
      return { text: '' }
    })
  })

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(await ran).toBe('model opus')
})
