# antigravity-agents

A skill that makes Claude Code an orchestrator for [Google Antigravity CLI](https://antigravity.google/docs/cli/getting-started) (`agy`) sub-agents. Claude writes a self-contained brief, launches `agy -p` in the background and keeps working. When the job finishes, Claude checks the result (`git diff`, typecheck, build) before trusting any of it. It suits full-repo reviews, audits, research sweeps and second opinions from a different model.

It loads when you ask Claude to delegate, offload or spin up a sub-agent, or when you name Antigravity, agy or Gemini.

## Changes from upstream

Fork of [markfulton/claude-antigravity-agents](https://github.com/markfulton/claude-antigravity-agents) at `f1911e4` (MIT), checked against agy 1.3.3:

- The launch example now passes `--dangerously-skip-permissions`. Upstream's own flag notes call it required for any job that uses tools, but the example left it out, so a copied job froze on its first tool call.
- `--model` no longer names `Gemini 3.5 Flash`, which agy 1.3.3 rejects at launch. The skill picks from `agy models` instead.
- `--print-timeout` defaults to `0s` (no limit), not 5m. A timeout still exits 0 with status `SUCCESS`, so the skill checks stderr for it.
- Jobs run with `--output-format json`, with stdout and stderr in separate files. Follow-ups resume the exact job with `--conversation <id>` instead of the ambiguous `--continue`.
- `--print-timeout` doesn't stop a stalled model stream, so the skill caps wall-clock itself. A dropped connection exits 3 with status `ERROR`, but `response` can still hold the whole report.

## Install

Install `agy` with the [getting-started guide](https://antigravity.google/docs/cli/getting-started), then run `agy` once in a terminal and finish the Google sign-in in the browser. Claude can't do that step for you.

```bash
claude plugin install antigravity-agents@alm-plugins
```

Don't also copy upstream's `antigravity-agents` folder into `~/.claude/skills/`, or two copies of the skill will compete for the same prompts.

## What it reaches

| Plugin | Network | Runs processes | Files | Calls a model | Sends data anywhere |
| --- | --- | --- | --- | --- | --- |
| antigravity-agents | Through `agy` | `agy` | Write jobs edit the worktree they run in | Gemini, or whatever `--model` names, via Antigravity | Job prompts and the files a job reads go to Google |

The plugin is only a skill, a page of instructions with no hooks or code. Everything in the table happens when Claude follows it and runs `agy`. Every job that uses tools needs `--dangerously-skip-permissions`; read-only jobs pair it with `--sandbox`, and write jobs run only in an isolated git worktree or a repo Claude isn't editing. Never put secrets in a job prompt.

Skill by [Mark Fulton](https://markfulton.com). MIT licensed.
