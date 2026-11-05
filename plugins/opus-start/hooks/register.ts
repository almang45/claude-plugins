import type { Register } from 'claude-code'

const isApplied = { plugin: 'opus-start', key: 'isApplied' } as const

// Only the forced default is replaced, so `claude --model haiku` keeps its choice.
export const shouldSwitch = (model: string, isInteractive: boolean): boolean =>
  isInteractive && /sonnet/i.test(model)

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const toast = (text: string) => $.ui.toast(`opus-start: ${text}`)

    try {
      // A reload runs session.start again; it must not undo a later manual /model.
      const { value: wasApplied } = await $.state.get(isApplied)

      if (!wasApplied) {
        await $.state.set(isApplied, true)

        if (shouldSwitch(await $.session.model(), e.isInteractive)) {
          // Called before next(e) so it is queued ahead of an initial prompt; not awaited,
          // since it runs once the session is idle and this hook holds the session back.
          void (async () => {
            try {
              await $.command.run({ command: 'model', args: 'opus' })
              const model = await $.session.model()
              if (!/opus/i.test(model)) toast(`still on ${model}`)
            } catch (error) {
              toast(`/model opus failed: ${String(error)}`)
            }
          })()
        }
      }
    } catch (error) {
      toast(`could not check the model: ${String(error)}`)
    }

    return next(e)
  })
}
