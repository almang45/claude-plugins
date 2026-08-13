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

# Interactive sessions inherit TMUX_PANE and land on their own tab. Background
# sessions do not, and there is no reliable way to recover it: Claude Code runs
# them under a host whose process lineage belongs to whichever session parented
# the host pool, not the one that launched the job, and several sessions can
# share a working directory. Both heuristics were tried and both painted an
# unrelated tab. So a background job paints nothing unless you point it
# somewhere explicitly with TABCOLOR_TTY.
#
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
