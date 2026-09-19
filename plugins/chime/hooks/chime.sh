#!/usr/bin/env bash
# One sound per state would go deaf after a day, so each state is a pool and the
# pick is random per fire, the way the spinner verbs rotate.
#
# Three sources, first one that has anything wins:
#   1. your own recordings in $CHIME_DIR/<state>/
#   2. spoken phrases, if CHIME_SAY is set
#   3. the macOS system sounds it ships with
#
# Written for bash 3.2, which is the one /bin/bash still is on macOS. No
# namerefs, no associative arrays.
set -euo pipefail

case "${1:-}" in
  # Plain notification dings, kept quiet: these fire once per tool call, so they
  # sit under the music. No phrases on purpose, a voice narrating every tool
  # call is unlivable.
  busy)      pool=(Glass Ping); phrases=(); vol=0.2 ;;
  # Turn finished, your move.
  idle)      pool=(Glass Hero Ping Blow); vol=0.8
             phrases=("your turn" "all done" "ready when you are" "finished") ;;
  # Stopped, wants an answer. Same level as idle: both are your own recordings,
  # and a 5.6dB gap between two voices read as a bug, not a tier.
  attention) pool=(Submarine Sosumi Funk Basso); vol=0.8
             phrases=("needs you" "waiting on you" "permission needed" "stuck") ;;
  *) exit 0 ;;
esac

# Deliberately not inside the plugin: installs land in a versioned cache
# directory that a reinstall replaces, and your recordings would go with it.
custom=("${CHIME_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/chime}/$1"/*)

# ponytail: no rate limit, a tool-call storm chimes per call. Add an mtime gate
# on a state file if the busy ticks turn into a drum roll.
# Backgrounded so a ~1s sound never sits in front of the prompt returning.
if [[ -e ${custom[0]} ]]; then
  # afplay opens anything CoreAudio does: aiff, wav, mp3, m4a, caf.
  command -v afplay >/dev/null 2>&1 || exit 0
  afplay -v "$vol" "${custom[RANDOM % ${#custom[@]}]}" >/dev/null 2>&1 &
elif [[ -n ${CHIME_SAY:-} && ${#phrases[@]} -gt 0 ]]; then
  command -v say >/dev/null 2>&1 || exit 0
  # volm is a speech-synthesis embedded command; say has no volume flag.
  say ${CHIME_VOICE:+-v "$CHIME_VOICE"} "[[volm $vol]] ${phrases[RANDOM % ${#phrases[@]}]}" >/dev/null 2>&1 &
else
  # afplay is macOS-only; elsewhere stay quiet rather than fail the hook.
  command -v afplay >/dev/null 2>&1 || exit 0
  afplay -v "$vol" "/System/Library/Sounds/${pool[RANDOM % ${#pool[@]}]}.aiff" >/dev/null 2>&1 &
fi
