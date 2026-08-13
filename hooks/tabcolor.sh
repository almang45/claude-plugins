#!/usr/bin/env bash
# Paints the iTerm2 tab with the current Claude Code state.
# Invoked by hooks with exactly one argument: busy | attention | idle | reset.
set -uo pipefail

# An andon light, with andon-light's state mapping (hooks/claude-signal.sh):
# yellow is work in progress, green is a finished run, red wants you.
# The hues are the lamp's (firmware/code.py COL) darkened to roughly a fifth
# brightness: a tab sits behind its own title text for hours, where the LED
# values are a wall of colour. Same signal, readable at a glance, not shouting.
# ponytail: fixed palette, edit here. A config layer buys nothing for 3 colors.
case "${1:-}" in
  busy)      hex=4a3f1e ;;  # dark amber: working
  idle)      hex=3a4a30 ;;  # dark moss: idle / complete, your turn
  attention) hex=5a2a26 ;;  # dark oxblood: stopped, needs you
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

# Sessions Claude Code hosts as background jobs never inherit TMUX_PANE, and the
# obvious ways to recover it all point at the wrong tab: process lineage leads to
# whichever session parented the host pool, and several sessions can share a
# working directory. What does identify the tab is its title — Claude Code sets
# it to the session name, and tmux exposes that as pane_title.
if [[ -z ${TMUX_PANE:-} && -r "${CLAUDE_JOB_DIR:-}/state.json" ]]; then
  # "nameSource" also lives in this file; the space after the colon excludes it.
  name=$(sed -n 's/.*"name": "\([^"]*\)".*/\1/p' "$CLAUDE_JOB_DIR/state.json" | head -1)
  if [[ -n $name ]]; then
    # index() is a literal substring match, so a name with regex metacharacters
    # is safe. The title carries a leading status glyph, hence substring.
    TMUX_PANE=$(tmux list-panes -a -F '#{pane_id}	#{pane_title}' 2>/dev/null |
      awk -F'\t' -v n="$name" 'index($2, n) { print $1; exit }')
  fi
fi
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
