# tabcolor

Claude Code plugin. Paints the tmux window (or the iTerm2 tab, outside tmux)
with the session's current state, so a wall of panes tells you which one wants
you without reading any of them.

| Color  | State | Fired by |
|--------|-------|----------|
| 🔵 blue `#4a9eff` | Claude is working | `UserPromptSubmit`, `PostToolUse` |
| 🟠 orange `#ff9f0a` | permission prompt / waiting on you | `Notification` |
| 🟢 green `#30d158` | your turn, response finished | `SessionStart`, `Stop` |
| — | color cleared | `SessionEnd` |

## Install

```bash
claude plugin marketplace add ~/Workspaces/opensource/almang45-pro/tmux-iterm2-tabcolor
claude plugin install tabcolor@tabcolor
```

Or from inside a session: `/plugin marketplace add <path>` then `/plugin install tabcolor@tabcolor`.

## How it picks a target

- **Inside tmux** (`$TMUX_PANE` set): sets `window-status-style` and
  `window-status-current-style` on the window owning `$TMUX_PANE`. Each session
  colors only its own window; nothing else is touched, and `reset` unsets the
  options rather than hardcoding your theme's defaults back.
- **Background sessions**, where neither applies: Claude Code runs these under a
  host process that strips `TMUX` from the environment and leaves the hook with
  no controlling terminal, so both branches above would no-op. The launching pane
  is still recoverable — an ancestor owns the terminal, and `tmux list-panes`
  maps a terminal back to a pane. Walking ancestor *environments* instead looks
  obvious and does not work: macOS `ps -E` reports a shell's environment as of
  exec and misses `TMUX` on the pane's own shell.
- **Outside tmux**: emits iTerm2's OSC 6 tab-color sequence to `/dev/tty` —
  hook stdout is consumed by Claude Code and never reaches the terminal.

Adoption assumes tmux's default socket; export `TMUX` yourself if you run
`tmux -S`. Set `TABCOLOR_NO_ADOPT=1` to disable it, which is what the tests do so
they cannot repaint the real pane they are running in.

Inside tmux you get the tmux window color, not the iTerm2 tab. Coloring the
outer iTerm2 tab from inside tmux needs `set -g allow-passthrough on` plus
DCS-wrapped sequences — skipped, add it if you run one Claude session per
iTerm2 tab and want the outer tab to react.

## Customizing

Edit the `case` block in `hooks/tabcolor.sh`. Three hex values, one place.

## Test

```bash
./test.sh
```

Drives the script against a throwaway tmux server and reads the options back,
checks the OSC bytes under a `pty.fork()`, and asserts that a run with no
controlling terminal stays silent and exits 0.

That last case is the one to keep: `/dev/tty` is world-writable even when the
process has no controlling terminal, so a `[[ -w /dev/tty ]]` guard passes and
the open then fails with ENXIO. Seen for real when a hook runs headless.
