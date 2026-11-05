/** Whether this session already had its one /model opus attempt. */
export type IsApplied = boolean

declare module 'claude-code' {
  interface PluginState {
    'opus-start': { isApplied: IsApplied }
  }
}
