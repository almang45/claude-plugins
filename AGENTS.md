# alm-plugins

Claude Code plugin marketplace `alm-plugins`, published as `almang45/claude-plugins`.
`.claude-plugin/marketplace.json` lists every plugin under `plugins/<name>/`.

These are the instructions for every coding agent in this repo (Claude Code, agy and
others). `CLAUDE.md` only imports this file, so edit here.

## Commands

Run from the repo root.

```bash
claude plugin validate .                     # marketplace manifest
claude plugin validate plugins/<name>        # one plugin
claude plugin test plugins/<name>            # TS mods: spinner, swarm, session-wrapped, skins
./plugins/chime/test.sh                      # stubs afplay/say, never makes a sound
./plugins/tabcolor/test.sh                   # writes to a temp file, never repaints a tab
python3 -I plugins/session-wrapped/tests/test_usage.py
claude --plugin-dir ./plugins/<name>         # load the working copy for one session
```

## Plugin kinds

- **Command hooks** (chime, tabcolor): `hooks/hooks.json` runs `hooks/<name>.sh <state>`
  with `busy` / `idle` / `attention` (tabcolor also `reset`).
- **TS mods** (spinner, swarm, session-wrapped, skins): `hooks/hooks.json` is
  `{"modules": ["./register.tsx"]}`. Tests in `tests/*.test.ts(x)` import `claude-code/testing`.
  There is no package.json; `claude plugin test` is the runner.
- **Skill** (antigravity-agents): `skills/antigravity-agents/SKILL.md` only.

## Rules

- A change reaches installed users only when `version` in
  `plugins/<name>/.claude-plugin/plugin.json` is bumped. README-only edits need no bump;
  SKILL.md, hooks and manifests do.
- Keep a plugin's `description` in `marketplace.json` in step with its `plugin.json`.
- Upstream code (spinner, swarm, session-wrapped, skins, antigravity-agents): change only
  what this repo needs, and record it in that plugin's README so an upstream sync can
  re-apply it. A diverged copy gets a version suffix (`-alm.N`, `-warframe.N`); swarm is
  unmodified and has none.
- Bash hooks and tests must run on macOS `/bin/bash` 3.2: no associative arrays, namerefs,
  `${var,,}` or `mapfile`.
- Hooks fail silently: exit 0, nothing on stderr. Hook stderr surfaces in the session.
- `Notification` matchers stay plain `a|b|c` allowlists. A `.` or `*` turns the whole
  pattern into a regex, where `permission_prompt` also matches `worker_permission_prompt`.

## Gotchas

- A directory-source marketplace copies plugin folders verbatim, untracked files included,
  so keep `__pycache__`, `.DS_Store` and generated types out of `plugins/<name>/`.
- Mod `tsconfig.json` files extend or include generated type paths (`.claude-plugin/types/`,
  `.claude/types/`) that are not committed. Editor type errors there are not test failures.
- These plugins target Claude Code only. agy reads this file but cannot load them: its
  plugin manifest, `hooks.json` format and hook events differ, and it has no mod engine.
