#!/usr/bin/env bash
# Paints the iTerm2 tab with the current Claude Code state.
# Invoked by hooks with exactly one argument: busy | attention | idle | reset.
set -uo pipefail

# ponytail: fixed palette, edit here. A config layer buys nothing for 3 colors.
case "${1:-}" in
  busy)      hex=4a9eff ;;  # Claude is working
  attention) hex=ff9f0a ;;  # permission prompt / waiting on you
  idle)      hex=30d158 ;;  # your turn
  reset)     hex=       ;;
  *) exit 0 ;;
esac

# iTerm2's tab-color control sequence. Set per channel, or restore the default.
osc() {
  if [[ -z $hex ]]; then
    printf '\033]6;1;bg;*;default\a'
  else
    printf '\033]6;1;bg;red;brightness;%d\a\033]6;1;bg;green;brightness;%d\a\033]6;1;bg;blue;brightness;%d\a' \
      "$((16#${hex:0:2}))" "$((16#${hex:2:2}))" "$((16#${hex:4:2}))"
  fi
}

# Background sessions run under a host that strips TMUX from the environment and
# leaves the hook no controlling tty, so without this they could paint nothing at
# all. The launching pane is still reachable: some ancestor owns the terminal,
# and tmux maps a terminal back to a pane. Reading ancestor environments would be
# the obvious route but is not dependable, macOS ps(1) reports a shell's env as
# of exec and misses TMUX entirely on the pane's own shell.
# TABCOLOR_NO_ADOPT exists so the test suite can exercise the plain-terminal path
# without adopting, and repainting, the real pane the tests run in.
if [[ -z ${TMUX_PANE:-} && -z ${TABCOLOR_NO_ADOPT:-} ]]; then
  pid=$PPID
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    [[ -n $pid && $pid -gt 1 ]] || break
    term=$(ps -o tty= -p "$pid" 2>/dev/null | tr -d '[:space:]')
    if [[ -n $term && $term != '??' ]]; then
      # ponytail: default socket only. Export TMUX yourself if you run tmux -S.
      TMUX_PANE=$(tmux list-panes -a -F '#{pane_id} #{pane_tty}' 2>/dev/null |
        awk -v tty="/dev/$term" '$2 == tty { print $1; exit }')
      break
    fi
    pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d '[:space:]')
  done
fi

# TABCOLOR_TTY overrides where the bytes go. The tests assert on a plain file;
# it also makes this debuggable without guessing which pty is involved.
# Under tmux -CC, iTerm2 renders each tmux window as its own native tab and
# applies a pane's control sequences to that pane's tab, so writing to the pane's
# tty lands on the right tab with no wrapping at all.
# ponytail: -CC only. Plain tmux swallows sequences it does not understand and
# would need `set -g allow-passthrough on` plus a DCS wrapper with every ESC
# doubled; add that branch if this ever has to run outside control mode.
target=${TABCOLOR_TTY:-}
if [[ -n ${TMUX_PANE:-} ]]; then
  [[ -n $target ]] || target=$(tmux display-message -p -t "$TMUX_PANE" '#{pane_tty}' 2>/dev/null)
else
  [[ -n $target ]] || target=/dev/tty
fi
sequence=$(osc)

# Stay silent when the target is gone: this runs as a hook, where stray stderr
# surfaces as noise. Testing /dev/tty with -w would not be enough, it is
# world-writable even with no controlling terminal, where the open fails ENXIO.
# 2>/dev/null is ordered first so the shell's own redirect error is swallowed.
[[ -n $target ]] || exit 0
{ printf '%s' "$sequence"; } 2>/dev/null >"$target"
exit 0
