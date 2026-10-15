---
name: agy-review
description: Code review by Google Antigravity CLI (agy) sub-agents running Gemini at high reasoning effort. Fans the review of the current branch, a PR, a commit range or a set of files out to parallel read-only agy jobs, one per lens (correctness, security, reliability, conventions), then verifies every finding against the code before reporting. Use when the user asks for an agy, Antigravity or Gemini code review, wants a second-opinion review from a model other than Claude, or runs /antigravity-agents:agy-review.
argument-hint: "[<base-rev> | <a>..<b> | pr:<n> | --paths <file>...] [--lenses a,b] [--effort high]"
---

# agy code review

Review a change with agy sub-agents (newest Gemini, `high` effort), one background job per
lens, then verify what they report before the user sees it. You are the reviewer of record:
the jobs propose findings, you confirm them.

Arguments: $ARGUMENTS

Every step goes through one helper that prints a JSON object:

```bash
python3 -I ${CLAUDE_SKILL_DIR}/scripts/agy_review.py <scope|run|report|cleanup> ...
```

`REVIEW` below stands for that command.

## 1. Scope

Map the arguments onto a target, then run `REVIEW scope [target] [options]` from the
repository:

| The user wants | Target |
|---|---|
| this branch, including uncommitted and untracked work (default) | none |
| the same, against a branch other than the default | `<base-rev>`, e.g. `develop` |
| a commit range | `<a>..<b>`, or `<a>...<b>` to diff from their merge base |
| a GitHub PR (needs `gh`; agy reads a detached worktree of the PR head) | `pr:<n>`, `#<n>` or the PR URL |
| particular files in full, not a diff | `--paths <file>...` |

Options: `--lenses correctness,security` to narrow; `--lenses all` for a single job;
`--effort xhigh|max` only when the user asks for more than high; `--model <id>` only when they
name one; `--timeout <min>` (default 20). With no `--lenses`, a change under 150 lines gets
one `all` job and anything larger gets four.

The output has `job_dir`, `description`, `file_count`, `added`/`deleted`, `lenses`, `model`,
`effort`, `warnings` and the exact `run_commands`. On `{"error": ...}`, tell the user what it
says. A sign-in error means the user must run `agy` once in their own terminal; you cannot do
it for them. "nothing to review" ends the skill.

Tell the user in one line what is under review, the lenses, the model and effort, and that
the jobs take 5 to 20 minutes and print nothing until they finish.

## 2. Run

Start every command in `run_commands` in the same message, each as its own background Bash
call (`run_in_background: true`). Don't poll and don't sleep: each call notifies you when its
lens finishes.

When the scope's `root` is the user's checkout, change nothing in it until every lens has
finished. The jobs read that tree, and an edit trips the `tree_changed` check.

## 3. Verify each lens as it finishes

`run` prints the lens result and exits 0 when `status` is `ok`, or 2 otherwise.

- `ok`: verify its findings now, while the other lenses run.
- `unstructured`: the job answered in prose. Its `response` is in the output; treat the
  findings in it like any others.
- `timeout` or `error`: re-run once with `REVIEW run <job_dir> <lens> --resume`, which
  continues the same agy conversation. If it fails again, report the lens as failed. Offer
  `--effort medium` but don't switch on your own: the user asked for high effort.
- `tree_changed: true`: a job, or someone, changed files in the review root. Run
  `git status` and `git diff` there. Show the user any change a job made and ask before
  reverting it.

To verify a finding, open the file at the reported line and trace the failure scenario through
the code yourself. Mark it:

- **confirmed**: you followed the path and the defect is real.
- **plausible**: the code allows it, but it depends on runtime state you cannot see (load,
  config, data).
- **rejected**: the code prevents it, it is pre-existing and unchanged, or it is style
  dressed up as a bug. Keep a one-line reason.

Correct an overstated severity, and merge duplicates across lenses. Findings that cite a rule
from the repository's AGENTS.md or CLAUDE.md need the rule to actually say that.

## 4. Report

Once every lens has finished, run `REVIEW report <job_dir>` to merge and rank the results.
Findings from different lenses at the same spot are folded together under `also_reported_by`.
Then answer:

1. A one-line verdict: ship, fix first, or needs discussion.
2. The confirmed and plausible findings, most severe first. Give the severity, `file:line`,
   the defect, its failure scenario, the fix, and which lenses found it. If you have a
   findings-report tool for code reviews, report them through it, with confirmed or plausible
   as the verdict. Otherwise use a markdown table.
3. How many findings you rejected and why, in a line or two.
4. Lenses that failed, plus model, effort and the slowest lens's duration.

Fix nothing and post nothing to the PR unless the user asks. Offer to fix the confirmed
findings.

## 5. Clean up

Always run `REVIEW cleanup <job_dir>`, including after failures. It removes the worktree a PR
or range review created. Keep the job directory unless the user wants it gone (`--purge`).
Its `out/` folder holds each lens's prompt, raw agy output and stderr, which you need if a
lens has to be debugged.
