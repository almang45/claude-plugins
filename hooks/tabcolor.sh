#!/usr/bin/env bash
# Paints the tmux window (or iTerm2 tab) with the current Claude Code state.
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

# A dead tmux server or a missing controlling tty must stay silent: this runs as
# a hook, where stray stderr surfaces as noise in the session.
if [[ -n ${TMUX:-} && -n ${TMUX_PANE:-} ]]; then
  if [[ -z $hex ]]; then
    tmux set-option -uw -t "$TMUX_PANE" window-status-style 2>/dev/null
    tmux set-option -uw -t "$TMUX_PANE" window-status-current-style 2>/dev/null
  else
    tmux set-option -w -t "$TMUX_PANE" window-status-style "bg=#$hex,fg=black" 2>/dev/null
    tmux set-option -w -t "$TMUX_PANE" window-status-current-style "bg=#$hex,fg=black,bold" 2>/dev/null
  fi
  exit 0
fi

# iTerm2 OSC 6, written to the tty because hook stdout is consumed by Claude Code
# and never reaches the terminal. Guarding with -w is not enough: /dev/tty is
# world-writable even when the process has no controlling terminal, where the
# open then fails with ENXIO. So just attempt it, with 2>/dev/null ordered ahead
# of the tty redirect so the shell's own failure message is swallowed too.
if [[ -z $hex ]]; then
  { printf '\033]6;1;bg;*;default\a'; } 2>/dev/null >/dev/tty
else
  { printf '\033]6;1;bg;red;brightness;%d\a\033]6;1;bg;green;brightness;%d\a\033]6;1;bg;blue;brightness;%d\a' \
    "$((16#${hex:0:2}))" "$((16#${hex:2:2}))" "$((16#${hex:4:2}))"; } 2>/dev/null >/dev/tty
fi
exit 0
