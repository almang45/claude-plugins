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

if [[ -n ${TMUX:-} && -n ${TMUX_PANE:-} ]]; then
  if [[ -z $hex ]]; then
    tmux set-option -uw -t "$TMUX_PANE" window-status-style
    tmux set-option -uw -t "$TMUX_PANE" window-status-current-style
  else
    tmux set-option -w -t "$TMUX_PANE" window-status-style "bg=#$hex,fg=black"
    tmux set-option -w -t "$TMUX_PANE" window-status-current-style "bg=#$hex,fg=black,bold"
  fi
  exit 0
fi

# iTerm2 OSC 6. Written to the tty because hook stdout is consumed by Claude
# Code and never reaches the terminal.
[[ -w /dev/tty ]] || exit 0
if [[ -z $hex ]]; then
  printf '\033]6;1;bg;*;default\a' >/dev/tty
else
  printf '\033]6;1;bg;red;brightness;%d\a\033]6;1;bg;green;brightness;%d\a\033]6;1;bg;blue;brightness;%d\a' \
    "$((16#${hex:0:2}))" "$((16#${hex:2:2}))" "$((16#${hex:4:2}))" >/dev/tty
fi
exit 0
