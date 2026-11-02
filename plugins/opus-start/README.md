# opus-start

Claude Code mod for accounts whose organization forces Sonnet as the default model while
still allowing Opus in `availableModels`. When an interactive session starts on Sonnet, it
runs `/model opus`, the same command you would type.

- It goes through `/model`, so the organization's allowlist still decides. If Opus is
  refused, the session stays on Sonnet and a toast says so.
- It does not rewrite the `model` setting through a `settings.read` hook, which would
  override the organization's policy for every reader.
- Other models are left alone (`claude --model haiku`). An explicit `--model sonnet` looks
  the same as the forced default and is switched too; run `/model sonnet` to go back.
- `claude -p` and SDK runs are not touched.
- It runs once per session, so a plugin reload does not undo a manual `/model`.
