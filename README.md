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
- **Background sessions**: nothing, by design. See below.

`TABCOLOR_TTY` redirects the bytes to a given tty or file; the tests use it so
they cannot repaint the pane they run in.

## Background sessions paint nothing

Interactive sessions inherit `$TMUX_PANE` and colour their own tab with no
guesswork. Background jobs do not inherit it, and there is no dependable way to
recover which tab they belong to. Two approaches were built and both shipped
the same bug — colouring an unrelated tab:

- **Process lineage.** Claude Code runs background jobs under a host process
  whose ancestry leads to whichever session parented the host pool, not the
  session you launched the job from. In testing, a job started from one tab
  resolved to a completely different project's tab.
- **Working directory.** Two sessions open on the same directory are
  indistinguishable, and a job's `cwd` is often a subdirectory of both.

Also ruled out: `ps -E` cannot read ancestor environments reliably on macOS —
it reports a process's environment as of `exec`, and misses `TMUX` entirely on
a tmux pane's own login shell.

If you want a specific background job to signal, point it at a tab explicitly:

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
