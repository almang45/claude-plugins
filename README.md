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
- **Inside tmux**: tmux discards escape sequences it does not itself understand,
  so the payload is wrapped in a DCS passthrough (`ESC P tmux; … ESC \`) with
  every `ESC` in it doubled, then written to the pane's tty. This needs
  `allow-passthrough`, which is off by default — the hook turns it on rather than
  making you edit `tmux.conf`.
- **Background sessions**, where neither `$TMUX_PANE` nor a controlling terminal
  exists: Claude Code runs these under a host process that strips `TMUX` from the
  environment and gives the hook no tty, so nothing above would fire. The
  launching pane is still recoverable — an ancestor owns the terminal, and
  `tmux list-panes` maps a terminal back to a pane.

Adoption assumes tmux's default socket; export `TMUX` yourself if you run
`tmux -S`. `TABCOLOR_NO_ADOPT=1` disables it and `TABCOLOR_TTY` redirects the
bytes elsewhere; the tests use both so they cannot repaint the pane they run in.

### Under `tmux -CC`

iTerm2's control-mode integration renders tmux windows as native iTerm2 tabs and
never draws tmux's own status line. An earlier version of this plugin set
`window-status-style`, which works in plain tmux and is completely invisible
under `-CC`. Passthrough is the only mechanism that reaches the tab in control
mode, and it happens to be the better one in plain tmux too — it colors the real
iTerm2 tab rather than a cell in a status bar — so the status-bar path is gone.

## Customizing

Edit the `case` block in `hooks/tabcolor.sh`. Three hex values, one place.

## Test

```bash
./test.sh
```

Asserts the exact bytes for every state, raw and DCS-wrapped, plus the two
properties that make the wrapper work: `ESC` doubled, `ST` terminator. Needs no
tmux server and no pty, and cannot repaint the pane it runs in.

Two failures worth keeping guards for, both seen for real:

- `/dev/tty` is world-writable even with no controlling terminal, so a
  `[[ -w /dev/tty ]]` guard passes and the open then fails `ENXIO`. Hooks running
  headless printed `Device not configured` on every invocation.
- Flattening the `ESC` doubling in the passthrough makes tmux swallow the whole
  sequence. Nothing errors; the tab just silently never changes.
