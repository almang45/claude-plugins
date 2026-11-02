import type { Register } from 'claude-code'

const isApplied = { plugin: 'opus-start', key: 'isApplied' } as const

// Only the forced default is replaced, so `claude --model haiku` keeps its choice.
export const shouldSwitch = (model: string, isInteractive: boolean): boolean =>
  isInteractive && /sonnet/i.test(model)

export const register: Register = on => {
  on('session.start', ($, e, next) => {
    // Not awaited: $.command.run waits for an idle session, and session.start holds the first prompt.
    void (async () => {
      try {
        // A reload runs session.start again; it must not undo a later manual /model.
        const { value: wasApplied } = await $.state.get(isApplied)
        if (wasApplied) return
        await $.state.set(isApplied, true)

        if (!shouldSwitch(await $.session.model(), e.isInteractive)) return
        await $.command.run({ command: 'model', args: 'opus' })

        const model = await $.session.model()
        if (!/opus/i.test(model)) $.ui.toast(`opus-start: still on ${model}`)
      } catch (error) {
        $.ui.toast(`opus-start: /model opus failed: ${String(error)}`)
      }
    })()

    return next(e)
  })
}
