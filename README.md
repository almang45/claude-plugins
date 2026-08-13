# tabcolor

Claude Code plugin. Paints the iTerm2 tab with the session's current state, so a
wall of tabs tells you which one wants you without reading any of them.

Each tab is an andon light, using the palette and the state mapping of
[andon-light](../andon-light) — LED values from `firmware/code.py` (`COL`), states
from `hooks/claude-signal.sh` — so a tab and the lamp on the desk always agree.

| Color  | State | Fired by |
|--------|-------|----------|
| 🟡 yellow `#ff9600` | working | `UserPromptSubmit`, `PostToolUse` |
| 🟢 green `#00ff00` | idle / complete, your turn | `SessionStart`, `Stop` |
| 🔴 red `#ff0000` | stopped, needs you | `Notification` |
| — | color cleared | `SessionEnd` |

The one deliberate divergence is `PostToolUse` where andon-light wires
`PreToolUse`: a permission prompt fires `Notification` *after* `PreToolUse`, so
`PreToolUse` would leave the tab red until the next prompt. `PostToolUse` clears
it the moment the approved tool finishes.

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
- **Sessions hosted as background jobs**: matched to a tab by title. See below.

`TABCOLOR_TTY` redirects the bytes to a given tty or file; the tests use it so
they cannot repaint the pane they run in.

## Finding the tab for a background-hosted session

A session Claude Code runs as a background job never inherits `$TMUX_PANE`, and
its hooks have no controlling terminal either. What identifies its tab is the
**title**: Claude Code sets the terminal title to the session name, and tmux
exposes that as `pane_title`. The hook reads the name from
`$CLAUDE_JOB_DIR/state.json` and finds the pane whose title contains it.
Substring, because the title carries a leading status glyph (`◐`, `✳`).

Three other approaches were built or considered first, and every one of them
resolved to the wrong tab:

- **Process lineage.** Background jobs run under a host whose ancestry leads to
  whichever session parented the host pool, not the one displaying the session.
  In testing, this session resolved to an unrelated project's tab.
- **Working directory.** Two sessions open on the same directory are
  indistinguishable, and a job's `cwd` is often a subdirectory of both.
- **Ancestor environments.** macOS `ps -E` reports a process's environment as of
  `exec`, and misses `TMUX` entirely on a tmux pane's own login shell.

The ancestor-TTY walk is what
[claude-code-iterm2-tab-status](https://github.com/JasperSui/claude-code-iterm2-tab-status)
uses, and its README documents the same "wrong tab" symptom.

To override the target entirely, point a session at a tty yourself:

```bash
TABCOLOR_TTY=/dev/ttys017 claude ...   # tmux display-message -p '#{pane_tty}'
```

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
