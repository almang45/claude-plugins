---
name: review
description: Code review by Google Antigravity CLI (agy) sub-agents running Gemini Flash at high reasoning effort, run side by side with Claude Opus sub-agents on the same brief, then a comparison of what each model found. Fans the review of the current branch, a PR, a commit range or a set of files out to parallel read-only jobs, one per lens (correctness, security, reliability, conventions) and reviewer, verifies every finding against the code, and scores both reviewers. Use when the user asks for an agy, Antigravity or Gemini code review, wants to compare Gemini and Opus on a review, wants a second-opinion review from a model other than Claude, or runs /antigravity-agents:review.
argument-hint: "[<base-rev> | <a>..<b> | pr:<n> | --paths <file>...] [--lenses a,b] [--reviewers agy,opus] [--effort high]"
---

# agy and Opus code review

Review a change twice, in parallel and independently: agy sub-agents (newest Gemini Flash, `high`
effort) and Claude Opus sub-agents (`antigravity-agents:opus-reviewer`), each lens briefed
the same way. Then verify every finding and compare the two reviewers. You are the reviewer
of record: the sub-agents propose findings, you confirm them and judge who found what.

Arguments: $ARGUMENTS

Every step goes through one helper that prints a JSON object:

```bash
python3 -I ${CLAUDE_SKILL_DIR}/scripts/agy_review.py <scope|run|ingest|report|cleanup> ...
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
| a GitHub PR (needs `gh`; the reviewers read a detached worktree of the PR head) | `pr:<n>`, `#<n>` or the PR URL |
| particular files in full, not a diff | `--paths <file>...` |

Options: `--lenses correctness,security` to narrow; `--lenses all` for a single job per
reviewer; `--reviewers agy` or `--reviewers opus` when the user wants one side only (the
default is both); `--effort xhigh|max` only when the user asks for more than high, and both
reviewers get it; `--model <id>` for agy only when they name one; `--timeout <min>` for agy
(default 20). With no `--lenses`, a change under 150 lines gets one `all` job per reviewer and
anything larger gets four.

The output has `job_dir`, `description`, `file_count`, `added`/`deleted`, `lenses`,
`reviewers`, agy's `model` and `effort`, `warnings`, the exact agy `run_commands` and the
`opus_tasks`. On `{"error": ...}`, tell the user what it says. A sign-in error means the user
must run `agy` once in their own terminal; you cannot do it for them. "nothing to review" ends
the skill.

Tell the user in one line what is under review, the lenses, the reviewers with agy's model and
effort, and that the jobs take 5 to 20 minutes.

## 2. Run

Start every job in the same message:

- Each `run_commands` entry as its own background Bash call (`run_in_background: true`).
- Each `opus_tasks` entry as a background Agent call, with its `subagent_type`, `model`,
  `effort`, `description` and `prompt` exactly as given. If that agent type isn't available,
  use `general-purpose` with the same model and effort, and start the prompt with "Read-only:
  never edit, write or run anything."

Don't poll and don't sleep: each call notifies you when it finishes. Never pass one
reviewer's findings to the other; the comparison needs independent reviews.

When the scope's `root` is the user's checkout, change nothing in it until every job has
finished. The jobs read that tree, and an edit trips the `tree_changed` check.

## 3. Collect and verify each job as it finishes

**agy lens.** `run` prints the lens result and exits 0 when `status` is `ok`, or 2 otherwise.

- `unstructured`: the job answered in prose. Its `response` is in the output; verify the
  findings in it like any others, but they have no refs and stay out of the comparison.
- `timeout` or `error`: re-run once with `REVIEW run <job_dir> <lens> --resume`, which
  continues the same agy conversation. If it fails again, report the lens as failed. Offer
  `--effort medium` but don't switch on your own: the user asked for high effort.

**Opus lens.** Save the agent's final message verbatim to the task's `reply_file` with the
Write tool, then run its `ingest_command`. Add `--duration-s <s>` and `--tokens <n>` when the
agent's completion notice reports them. It exits 0 when `status` is `ok`, or 2 otherwise.

- `unstructured`: the reply held no parsable JSON. If you can message the agent, ask it once
  for only the JSON result, save that and ingest again. Otherwise treat it like an agy
  `unstructured` lens.
- `warnings`: findings that left out schema fields. Read them with that in mind.

**Either reviewer**, `tree_changed: true`: a job, or someone, changed files in the review
root. Run `git status` and `git diff` there. Show the user any change a job made and ask before
reverting it.

Every finding has a `ref`, such as `agy/security#2` or `opus/all#1`. Verify each one now,
while the other jobs run: open the file at the reported line, trace the failure scenario
through the code yourself, and mark it:

- **confirmed**: you followed the path and the defect is real.
- **plausible**: the code allows it, but it depends on runtime state you cannot see (load,
  config, data).
- **rejected**: the code prevents it, it is pre-existing and unchanged, or it is style
  dressed up as a bug. Keep a one-line reason.

Judge each finding on its merits, whichever model reported it. Correct an overstated
severity. A finding that cites a rule from the repository's AGENTS.md or CLAUDE.md needs the
rule to actually say that.

## 4. Report and compare

Once every job has finished:

1. Run `REVIEW report <job_dir>`. It groups findings at the same spot, across reviewers and
   lenses, into issues `I1`, `I2` and so on, each with `found_by` and its `refs`. The grouping
   goes by location only, so treat it as a suggestion.
2. Write `<job_dir>/verdicts.json`, a list with one entry per distinct defect that names every
   ref reporting it, from any reviewer and lens:

   ```json
   [
     {"refs": ["agy/correctness#1", "opus/correctness#3"], "verdict": "confirmed", "severity": "high", "reason": "b == 0 reaches app.py:12"},
     {"refs": ["agy/security#1"], "verdict": "rejected", "reason": "validated in parse(), line 40"}
   ]
   ```

   Put refs in one entry only when they describe the same defect: split a report group that
   holds different defects, and join refs that the report kept apart. `severity`, your
   corrected one, is optional. Cover every ref.
3. Run `REVIEW report <job_dir> --verdicts <job_dir>/verdicts.json`. It refuses unknown or
   repeated refs, so fix the file and rerun if it does. Its `scoreboard` has, for each
   reviewer, findings, confirmed, plausible and rejected counts; `precision`, the share of its
   verified findings that held up; `severity_changed`, its valid findings whose severity you
   corrected; `unique_valid`, the valid issues only it found; `recall`, its share of every
   valid issue either reviewer found; `missed`; and `slowest_lens_s`.

Then answer:

1. A one-line verdict on the change: ship, fix first, or needs discussion.
2. The valid issues (confirmed and plausible), most severe first. Give the severity,
   `file:line`, the defect, its failure scenario, the fix, and who found it: agy, Opus or both.
   If you have a findings-report tool for code reviews, report them through it, with confirmed
   or plausible as the verdict. Otherwise use a markdown table.
3. The comparison: a table with one column per reviewer and rows for findings, confirmed,
   plausible, rejected, precision, severity corrected, unique valid issues, recall and slowest
   lens. Then two or three lines on what it shows: which issues only one side caught and how
   severe they were, and what the rejected findings had in common. One change is a small
   sample, so don't generalize past it. With a single reviewer, skip the table and give its
   precision.
4. How many findings you rejected and why, in a line or two. Lenses that failed, and agy's
   model and effort.

Fix nothing and post nothing to the PR unless the user asks. Offer to fix the confirmed
findings.

## 5. Clean up

Always run `REVIEW cleanup <job_dir>`, including after failures. It removes the worktree a PR
or range review created. Keep the job directory unless the user wants it gone (`--purge`).
Its `out/agy/` and `out/opus/` folders hold each lens's brief, raw output and result, which
you need if a lens has to be debugged.
