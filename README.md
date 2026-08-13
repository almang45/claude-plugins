# tabcolor

Claude Code plugin. Paints the iTerm2 tab with the session's current state, so a
wall of tabs tells you which one wants you without reading any of them.

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

## How it reaches the tab

Everything ends in iTerm2's OSC 6 tab-color sequence. What differs is how it
gets there.

- **Outside tmux**: written straight to `/dev/tty`. Hook stdout is consumed by
  Claude Code and never reaches the terminal, so the tty is the only route.
- **Inside tmux `-CC`**: written to the pane's tty, unwrapped. iTerm2's
  control-mode integration renders each tmux window as its own native tab and
  applies a pane's control sequences to that pane's tab, so this lands exactly
  where it should.
- **Background sessions**, where neither `$TMUX_PANE` nor a controlling terminal
  exists: Claude Code runs these under a host process that strips `TMUX` from the
  environment and gives the hook no tty, so nothing above would fire. The
  launching pane is still recoverable — an ancestor owns the terminal, and
  `tmux list-panes` maps a terminal back to a pane. A background job therefore
  colors the tab of the session that **launched** it, which is where you go to
  deal with it, not whichever tab you happen to be looking at.

Adoption assumes tmux's default socket; export `TMUX` yourself if you run
`tmux -S`. `TABCOLOR_NO_ADOPT=1` disables it and `TABCOLOR_TTY` redirects the
bytes elsewhere; the tests use both so they cannot repaint the pane they run in.

### Control mode only

This targets `tmux -CC`. Plain tmux discards escape sequences it does not
understand, so there the same bytes vanish — it would need
`set -g allow-passthrough on` plus a DCS wrapper (`ESC P tmux; … ESC \`) with
every `ESC` in the payload doubled. That branch is deliberately absent.

Two earlier mechanisms were tried against a live tab and rejected:

- `window-status-style`, which colors a cell in tmux's status bar. Correct in
  plain tmux, and invisible under `-CC`, which never draws a status line.
- The DCS passthrough wrapper. It reaches *a* tab, but not the pane's own, so
  under `-CC` it colored the wrong tab while the working tab stayed blank.

## Customizing

Edit the `case` block in `hooks/tabcolor.sh`. Three hex values, one place.

## Test

```bash
./test.sh
```

Asserts the exact bytes for every state, in and out of tmux. Needs no tmux
server and no pty, and cannot repaint the pane it runs in.

One failure worth keeping a guard for, seen for real: `/dev/tty` is
world-writable even with no controlling terminal, so a `[[ -w /dev/tty ]]` guard
passes and the open then fails `ENXIO`. Hooks running headless printed
`Device not configured` on every invocation.
