# agy-review

Code review by Google Antigravity CLI (`agy`) sub-agents. Claude splits the review into
lenses and runs each one as a parallel, read-only `agy` print-mode job on the newest Gemini
at `high` reasoning effort. It then checks every finding against the code before showing it
to you.

```text
scope ──► run correctness ─┐
      ├─► run security ────┤  each finishes ──► Claude verifies its findings
      ├─► run reliability ─┤
      └─► run conventions ─┘──► report (ranked, merged) ──► cleanup
```

[antigravity-agents](../antigravity-agents) delegates any kind of job to agy. This plugin does
one job, code review, with the workflow built in: scoping, lenses, a findings schema,
timeouts, resume and verification.

## Requirements

- `agy` 1.3.5 or later, signed in. Run `agy` once in a terminal to sign in.
- `python3` 3.9 or later. The macOS system one works.
- `git`, plus `gh` for PR targets.

## Install

```bash
claude plugin marketplace add almang45/claude-plugins
claude plugin install agy-review@alm-plugins
```

## Use

Ask for it by name, for example "agy review this branch", "get a Gemini review of PR 12" or
"agy review src/auth with the security lens". You can also run the skill directly:

```text
/agy-review:agy-review                      # this branch + uncommitted + untracked, vs the default branch
/agy-review:agy-review develop              # the same, against develop
/agy-review:agy-review main...feature/x     # a commit range
/agy-review:agy-review pr:12                # a GitHub PR, reviewed in a detached worktree
/agy-review:agy-review --paths src/auth.py  # whole files instead of a diff
/agy-review:agy-review --lenses security --effort xhigh
```

A change under 150 lines gets one job that covers every lens. A larger one gets four jobs:
correctness, security, reliability and conventions. Each job takes 5 to 20 minutes at high
effort and prints nothing until it finishes.

You get a verdict and the findings Claude confirmed or found plausible, ranked by severity,
with `file:line`, the failure scenario and a fix. You also get the number of findings it
rejected and why. Claude fixes nothing and posts nothing to a PR unless you ask.

## How it works

`skills/agy-review/scripts/agy_review.py` does the mechanical work, and every subcommand prints
JSON:

| Step | What it does |
|---|---|
| `scope [target]` | Resolves the target and writes `input/diff.patch` and `input/files.txt` to a job directory under `$TMPDIR/agy-review/`. Lockfiles, minified and map files stay out unless you pass `--all-files`. Picks the newest Gemini that offers the effort from `agy models`, which also checks that you are signed in. |
| `run <job> <lens>` | Runs `agy -p` with `--model`, `--effort`, `--json-schema findings.schema.json`, `--sandbox`, `--dangerously-skip-permissions`, `--disable-slash-commands`, a print timeout and stdin closed. A watchdog kills the job's process group 2 minutes after the print timeout, because agy's own timeout misses a stalled model stream. It also fingerprints the review root before and after, so an edit made by a job shows up as `tree_changed`. |
| `run ... --resume` | Continues the lens's agy conversation after a timeout or network error. |
| `report <job>` | Merges the lenses, ranks the findings by severity and confidence, and folds findings that sit at the same spot. |
| `cleanup <job>` | Removes the detached worktree made for a PR or for a range whose head isn't checked out. |

The job prompt is `brief.md`, plus the lens text from `lenses/<lens>.md`. To add a lens, drop a
file into `lenses/` and pass `--lenses <name>`.

Environment overrides: `AGY_BIN`, `AGY_REVIEW_MODEL`, `AGY_REVIEW_EFFORT`, `AGY_REVIEW_HOME`
(where job directories go) and `AGY_REVIEW_GRACE_S` (watchdog grace).

## Safety

- Print mode can't answer agy's permission prompts, so jobs run with
  `--dangerously-skip-permissions`. `--sandbox` and a read-only brief bound what they do, and the
  brief forbids running the project's code, tests and builds. Claude checks `tree_changed`,
  shows you any edit a job made, and asks before reverting it.
- PR reviews, and ranges whose head isn't checked out, run in a throwaway detached worktree
  inside the job directory.
- In Claude Code's auto mode, the permission classifier may stop the `run` commands because they
  start agents with permissions skipped. Approve them, or add an allow rule for them.
- The diff and the brief go to Google through agy. Don't run it on code you may not send there.

## Test

```bash
python3 -I plugins/agy-review/tests/test_agy_review.py
```

The tests use stub `agy` and `gh` binaries and throwaway git repositories, so nothing reaches
Google or GitHub, and they ignore your git config.
