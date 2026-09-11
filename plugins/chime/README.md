# chime

Claude Code plugin. Gives a session an audible state, so a terminal you are not
looking at can still tell you it finished or that it is stuck.

Same three states as [tabcolor](../tmux-iterm2-tabcolor), so the ear and the eye
never disagree. Each state is a *pool*, and the sound is drawn at random per
fire — one fixed ding stops registering after a day, the way a fixed spinner
verb would.

| State | Default sounds | Volume | Fired by |
|-------|----------------|--------|----------|
| working | `Tink` `Pop` `Morse` `Bottle` `Purr` | 0.2 | `UserPromptSubmit`, `PostToolUse` |
| your turn | `Glass` `Hero` `Ping` `Blow` | 0.6 | `Stop` |
| needs you | `Submarine` `Sosumi` `Funk` `Basso` | 1.0 | `Notification` (filtered) |

Volume is the point of the tiering: the working ticks fire once per tool call
and are meant to sit under whatever you are listening to, while "needs you" is
the only state allowed to interrupt. Defaults are macOS's own
`/System/Library/Sounds`, so nothing ships audio and there is nothing to install.

## Your own sounds

Drop audio files in a directory per state and they replace that state's pool.
Anything CoreAudio opens works — `aiff`, `wav`, `mp3`, `m4a`, `caf`.

```
~/.claude/chime/busy/*        # or $CLAUDE_CONFIG_DIR/chime/...
~/.claude/chime/idle/*
~/.claude/chime/attention/*
```

Set `CHIME_DIR` to put them somewhere else. Multiple files in a state = a pool,
picked at random, same as the defaults. An empty or missing directory falls back
to the system sounds, so you can override one state and leave the rest alone.

The directory deliberately lives *outside* the plugin: installs land in a
versioned cache directory that a reinstall replaces, and your recordings would
go with it.

## Speech instead

```
export CHIME_SAY=1              # speak instead of chiming
export CHIME_VOICE=Samantha     # optional, defaults to the system voice
```

Uses macOS `say`, so again nothing to install. Phrases rotate per fire:

| State | Says |
|-------|------|
| your turn | "your turn" / "all done" / "ready when you are" / "finished" |
| needs you | "needs you" / "waiting on you" / "permission needed" / "stuck" |

**Working has no phrases on purpose** — a voice narrating every tool call is
unlivable. It stays a quiet tick even in speech mode. Add a `phrases=(...)` to
the `busy` case in `hooks/chime.sh` if you disagree.

Precedence is: your recordings, then speech, then the built-in sounds. A file
you bothered to record outranks a synthesised voice.

`say` is also the quickest way to *make* the recordings, if you want fixed
phrases without the synthesiser running every time:

```
say -o ~/.claude/chime/attention/stuck.aiff -v Daniel "oi, I need you"
```

## Phrase packs

`packs/anime-ja.sh` renders a Japanese phrase pack into the recordings
directory. It needs no plugin change at all — it is just recordings, which also
means no synthesiser latency at chime time.

```
./packs/anime-ja.sh                 # Kyoko, standard
./packs/anime-ja.sh Otoya           # any voice from: say -v '?' | grep ja_JP
./packs/anime-ja.sh Kyoko --ecchi   # tsundere register for the loud state
./packs/anime-ja.sh --clean         # remove it again
```

Files are namespaced `anime-*.aiff`, so `--clean` and re-runs never touch
recordings you made yourself, and a pack can coexist with them in the same pool.
The voice name is validated before anything is deleted.

macOS ships 9 `ja_JP` voices. Enhanced tiers exist for **Kyoko** and **Otoya**
only, via System Settings → Accessibility → Spoken Content → Manage Voices; the
script picks `Kyoko (Enhanced)` automatically when it is installed. Siri voices
such as O-Ren are *not* reachable from `say` at all. Compare `id_ID`, which has
exactly one voice, Damayanti.

`[[pbas]]` and `-r` were verified to work on the Enhanced model too, so the
timbre presets survive the upgrade.

Copy the script and swap the phrase lists for any other language — the states
are the only contract.

### Timbre

A line reads as a different character depending on pitch and pace, so phrases
are tagged with a preset and rendered separately:

| Preset | pbas | rate | Reads as |
|--------|------|------|----------|
| `oneesan` | 28 | 125 | lower and unhurried — あらあら, あら、ダメですよ先輩 |
| `kouhai` | 68 | 190 | higher and eager — 先輩〜, 助けて、先輩！, もう、変態！ |
| plain | 45 | 165 | the voice as shipped |

Measured on Kyoko: `[[pbas]]` shifts pitch without changing duration, `-r` is
words per minute, and `[[pmod]]` is **ignored** by the modern voices, so there
is no vibrato knob to reach for.

Those numbers are calibration knobs, not constants — ears and voices differ:

```
KOUHAI_PBAS=80 KOUHAI_RATE=205 ./packs/anime-ja.sh Kyoko --ecchi
ONEESAN_VOICE='Grandma (Japanese (Japan))' ./packs/anime-ja.sh
```

### Clips from real audio

Synthesis only goes so far. `packs/clip.sh` cuts any audio or video file into a
pool, which beats approximating a delivery you already have a recording of:

```
./packs/clip.sh attention araara.mp4 3.2 1.4        # state, file, start, seconds
```

Needs ffmpeg. Output is mono 22kHz, loudness-normalised to -18 LUFS so a phone
recording does not blow past the volume tiering. Files are namespaced `clip-*`,
so `anime-ja.sh --clean` leaves them alone.

## Notification is filtered

`Notification` also fires on `idle_prompt`, `agent_completed`, `auth_success`
and more. An unmatched hook there means a session that wants nothing shouts
anyway, so the matcher is an allowlist of the types that genuinely block on you:
`permission_prompt`, `worker_permission_prompt`, `agent_needs_input`,
`elicitation_dialog`, `elicitation_url_dialog`. An unrecognised type stays quiet
rather than crying wolf.

## Install

```
/plugin marketplace add ~/Workspaces/opensource/almang45-pro/claude-chime
/plugin install chime@chime
```

Installs are copied to a cache keyed by version, so after editing the source
**bump `version` in `.claude-plugin/plugin.json`** before `/reload-plugins`, or
the old copy keeps running.

## Test

```
./test.sh
```

Stubs `afplay` and `say` on `PATH` and asserts the exact command each state
would run — pool membership, volume tiering, randomness, and the precedence
between recordings, speech and defaults. Runs under `/bin/bash` 3.2, the one
macOS actually has, and never makes a sound.

## Not done

- **No rate limit.** A tool-call storm chimes per call. Marked `ponytail:` in
  `hooks/chime.sh`; add an mtime gate on a state file if the ticks become a drum
  roll.
- **macOS only.** `afplay` and `say` are absent elsewhere and the hook exits
  quietly, no error. Add a `paplay`/`spd-say` branch when there is a Linux box
  to hear it.
