# antigravity-agents

Two skills that make Claude Code an orchestrator for [Google Antigravity CLI](https://antigravity.google/docs/cli/getting-started) (`agy`) sub-agents:

- **antigravity-agents** delegates any job. Claude writes a self-contained brief, launches `agy -p` in the background and keeps working. When the job finishes, Claude checks the result (`git diff`, typecheck, build) before trusting any of it. It suits audits, research sweeps, refactors and second opinions from a different model. It loads when you ask Claude to delegate, offload or spin up a sub-agent, or when you name Antigravity, agy or Gemini.
- **review** does one job, code review, with the workflow built in. It splits a review into lenses, runs each lens as a parallel read-only agy job on the newest Gemini at `high` effort, and Claude verifies every finding before showing it to you. It loads when you ask for an agy, Antigravity or Gemini review, or a second-opinion review from another model.

## Changes from upstream

Fork of [markfulton/claude-antigravity-agents](https://github.com/markfulton/claude-antigravity-agents) at `f1911e4` (MIT), checked against agy 1.3.5:

- The launch example now passes `--dangerously-skip-permissions`. Upstream's own flag notes call it required for any job that uses tools, but the example left it out, so a copied job froze on its first tool call.
- `--model` no longer names `Gemini 3.5 Flash`, which agy 1.3.3 rejects at launch. The skill picks from `agy models` instead.
- `--print-timeout` defaults to `0s` (no limit), not 5m. A timeout still exits 0 with status `SUCCESS`, so the skill checks stderr for it.
- Jobs run with `--output-format json`, with stdout and stderr in separate files. Follow-ups resume the exact job with `--conversation <id>` instead of the ambiguous `--continue`.
- `--print-timeout` doesn't stop a stalled model stream, so the skill caps wall-clock itself. A dropped connection exits 3 with status `ERROR`, but `response` can still hold the whole report.
- Added the `review` skill (`skills/review/`, `tests/`), which this repo owns and upstream doesn't have. The `antigravity-agents` skill sends code reviews to it. An upstream sync has to keep both.

## Install

Install `agy` 1.3.5 or later with the [getting-started guide](https://antigravity.google/docs/cli/getting-started), then run `agy` once in a terminal and finish the Google sign-in in the browser. Claude can't do that step for you. The review skill also needs `python3` 3.9 or later (the macOS system one works), `git`, and `gh` for PR targets.

```bash
claude plugin install antigravity-agents@alm-plugins
```

Don't also copy upstream's `antigravity-agents` folder into `~/.claude/skills/`, or two copies of the skill will compete for the same prompts.

## review

```text
scope ──► run correctness ─┐
      ├─► run security ────┤  each finishes ──► Claude verifies its findings
      ├─► run reliability ─┤
      └─► run conventions ─┘──► report (ranked, merged) ──► cleanup
```

Ask for it by name, for example "agy review this branch", "get a Gemini review of PR 12" or "agy review src/auth with the security lens". You can also run the skill directly:

```text
/antigravity-agents:review                      # this branch + uncommitted + untracked, vs the default branch
/antigravity-agents:review develop              # the same, against develop
/antigravity-agents:review main...feature/x     # a commit range
/antigravity-agents:review pr:12                # a GitHub PR, reviewed in a detached worktree
/antigravity-agents:review --paths src/auth.py  # whole files instead of a diff
/antigravity-agents:review --lenses security --effort xhigh
```

A change under 150 lines gets one job that covers every lens. A larger one gets four jobs: correctness, security, reliability and conventions. Each job takes 5 to 20 minutes at high effort and prints nothing until it finishes. Reviewing this skill's own 1,600-line first commit took four jobs about 8 minutes each, run in parallel.

You get a verdict and the findings Claude confirmed or found plausible, ranked by severity, with `file:line`, the failure scenario and a fix. You also get the number of findings it rejected and why. Claude fixes nothing and posts nothing to a PR unless you ask.

### How it works

`skills/review/scripts/agy_review.py` does the mechanical work, and every subcommand prints JSON:

| Step | What it does |
|---|---|
| `scope [target]` | Resolves the target and writes `input/diff.patch` and `input/files.txt` to a new private job directory, `$TMPDIR/agy-review-<repo>-*`. Lockfiles, minified and map files stay out unless you pass `--all-files`. For a PR, it refuses to go on if the head it fetched from `origin` doesn't match the head GitHub reports, as happens when `origin` is a fork. Picks the newest Gemini that offers the effort from `agy models`, which also checks that you are signed in. |
| `run <job> <lens>` | Runs `agy -p` with `--model`, `--effort`, `--json-schema findings.schema.json`, `--sandbox`, `--dangerously-skip-permissions`, `--disable-slash-commands`, a print timeout and stdin closed. A watchdog kills the job's process group 2 minutes after the print timeout, because agy's own timeout misses a stalled model stream. It also fingerprints the review root before and after, so an edit made by a job shows up as `tree_changed`. |
| `run ... --resume` | Continues the lens's agy conversation after a timeout or network error. |
| `report <job>` | Merges the lenses, ranks the findings by severity and confidence, and folds findings that sit at the same spot. |
| `cleanup <job>` | Removes the detached worktree made for a PR or for a range whose head isn't checked out. |

The job prompt is `brief.md`, plus the lens text from `lenses/<lens>.md`. To add a lens, drop a file into `lenses/` and pass `--lenses <name>`.

Environment overrides: `AGY_BIN`, `AGY_REVIEW_MODEL`, `AGY_REVIEW_EFFORT`, `AGY_REVIEW_HOME` (where job directories go) and `AGY_REVIEW_GRACE_S` (watchdog grace).

```bash
python3 -I plugins/antigravity-agents/tests/test_agy_review.py
```

The tests use stub `agy` and `gh` binaries and throwaway git repositories, so nothing reaches Google or GitHub, and they ignore your git config.

## What it reaches

| Skill | Network | Runs processes | Files | Calls a model | Sends data anywhere |
| --- | --- | --- | --- | --- | --- |
| antigravity-agents | Through `agy` | `agy` | Write jobs edit the worktree they run in | Gemini, or whatever `--model` names, via Antigravity | Job prompts and the files a job reads go to Google |
| review | Through `agy`, plus `gh` and `git fetch` for PRs | `python3`, `agy`, `git`, `gh` | Job directories in `$TMPDIR`; a detached worktree for PRs and ranges; reads the reviewed tree, never writes it | Gemini at `high` effort unless you pick another | The diff, the brief and the files a job reads go to Google |

`antigravity-agents` is instructions only: everything in its row happens when Claude follows it and runs `agy`. `review` puts every agy flag in its Python helper.

Every job that uses tools needs `--dangerously-skip-permissions`, because print mode can't answer agy's permission prompts. Read-only jobs pair it with `--sandbox`, and write jobs run only in an isolated git worktree or a repo Claude isn't editing. The review skill's brief also forbids running the project's code, tests and builds, and Claude shows you any edit a job made before reverting it.

- In Claude Code's auto mode, the permission classifier may stop these launches because they start agents with permissions skipped. Approve them, or add an allow rule.
- A PR from someone you don't trust can carry instructions aimed at the reviewing agent. The sandbox limits the commands it can run, but don't review such PRs on a machine that holds credentials you care about. Read the findings as claims to check, not as instructions.
- Never put secrets in a job prompt, and don't send code to Google that you may not share with it.

The antigravity-agents skill is by [Mark Fulton](https://markfulton.com), MIT licensed. The review skill was added in this repo.
