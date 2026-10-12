# session-wrapped

Spotify Wrapped for a Claude Code session: an animated stat reveal and a shareable PNG card.

`/wrapped` plays an animated stat reveal (session length, tool calls, MVP tool, red-to-green test runs, longest turn, cost) and writes a 1200px PNG card to your Desktop. `/wrapped demo` does the same with sample numbers. Week and month totals come from `scripts/usage.py`, which reads your local transcripts in `$CLAUDE_CONFIG_DIR/projects` (default `~/.claude/projects`) and caches the rollups. Needs `python3`. Nothing leaves your machine.

## Install

Vendored from [OneWave-AI/claude-code-mods](https://github.com/OneWave-AI/claude-code-mods/tree/main/session-wrapped) (MIT), with one change (`-alm.1`): `scripts/usage.py` follows `$CLAUDE_CONFIG_DIR` instead of a hardcoded `~/.claude`, so a non-default profile's week and month cards read that profile's transcripts. Needs Claude Code 2.1.287 or later.

```bash
claude plugin install session-wrapped@alm-plugins
```

Or load this folder for one session, from the repo root: `claude --plugin-dir ./plugins/session-wrapped`

## What it reaches

| Mod | Network | Runs processes | Files | Calls a model | Sends data anywhere |
| --- | --- | --- | --- | --- | --- |
| session-wrapped | No | `python3` (reads local transcripts, and writes the PNG where `base64` has no `-o`), `base64` (writes the PNG) | Writes one PNG to `~/Desktop`, a cache in `~/.cache/session-wrapped` | No | No |

Run `claude plugin validate plugins/session-wrapped` to list every event it hooks and every call it makes. Tests: `claude plugin test plugins/session-wrapped` and `python3 -I plugins/session-wrapped/tests/test_usage.py`. See the [upstream README](https://github.com/OneWave-AI/claude-code-mods#security) for the full security notes.

Part of [claude-code-mods](https://github.com/OneWave-AI/claude-code-mods) by [OneWave AI](https://www.onewave-ai.com). MIT licensed.
