#!/usr/bin/env python3
"""Code review by Google Antigravity CLI (agy) sub-agents, compared with Claude Opus reviewers.

  scope    resolve what to review into a job directory, pick the agy model, write the Opus briefs
  run      run one lens as an agy job and normalise its result
  ingest   normalise one Opus reviewer agent's reply
  report   merge every reviewer's findings; with --verdicts, score the reviewers against each other
  cleanup  remove the worktree that scope created for a PR or range

Every subcommand prints one JSON object on stdout. Errors print {"error": ...} on
stderr and exit 1; `run` and `ingest` exit 2 when a lens finished without structured findings.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import string
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SKILL_DIR = Path(__file__).resolve().parent.parent
LENS_DIR = SKILL_DIR / "lenses"
BRIEF_PATH = SKILL_DIR / "brief.md"
SCHEMA_PATH = SKILL_DIR / "findings.schema.json"

REVIEWERS = ("agy", "opus")
OPUS_AGENT = "antigravity-agents:opus-reviewer"
OPUS_MODEL = "opus"
VERDICTS = ("confirmed", "plausible", "rejected")
VALID_VERDICTS = ("confirmed", "plausible")
DEFAULT_LENSES = ("correctness", "security", "reliability", "conventions")
ALL_LENS = "all"
# Below this many changed lines, one job covering every lens beats four narrow ones.
SMALL_CHANGE_LINES = 150
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_EFFORT = "high"
DEFAULT_TIMEOUT_MIN = 20.0
# agy's --print-timeout does not end a stalled model stream, so the job is killed after this.
WATCHDOG_GRACE_S = float(os.environ.get("AGY_REVIEW_GRACE_S", "120"))
UNTRACKED_MAX_BYTES = 256 * 1024
# gh and git fetch talk to GitHub; a stalled connection must not hang scope forever.
NETWORK_TIMEOUT_S = 180.0
LARGE_DIFF_BYTES = 1_500_000
NOISE = (
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "go.sum", "Cargo.lock", "poetry.lock", "uv.lock", "Pipfile.lock", "Gemfile.lock",
    "composer.lock", "*.min.js", "*.min.css", "*.map", ".DS_Store",
)
DIFF_OPTS = ("--no-color", "--no-ext-diff", "--find-renames", "--unified=5")
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PR_TARGET = re.compile(r"^(?:pr:|#)(\d+)$|^https://github\.com/[^/]+/[^/]+/pull/(\d+)/?$")
RANGE_TARGET = re.compile(r"^(.+?)(\.\.\.?)(.+)$")
EFFORT_SUFFIX = re.compile(r"^(.+)-(" + "|".join(EFFORTS) + r")$")
RESUME_PROMPT = string.Template(
    "Your previous turn stopped before you returned the result. Finish the $lens review of "
    "the same change now, without starting over, and return the result through the "
    "structured output."
)
# agy enforces the schema through --json-schema; an Opus agent only has these words and a parser.
OUTPUT_RULES = {
    "agy": (
        "Return the result through the structured output: `summary`, one or two sentences on this lens,\n"
        "and `findings`, which may be empty."
    ),
    "opus": (
        "Your final message is the result and nothing else: one JSON object in a ```json fence, which a\n"
        "script parses. It has `summary`, one or two sentences on this lens, and `findings`, which may be\n"
        "empty. Each finding has exactly these fields: `file` (path relative to the repository root),\n"
        "`line` (integer), `severity` (critical, high, medium or low), `category` (a kebab-case slug such\n"
        "as missing-timeout), `title` (at most 80 characters), `failure_scenario`, `evidence` (the code\n"
        "and call path, with file:line references), `suggested_fix` and `confidence` (0.0 to 1.0).\n"
        f"The JSON Schema is {SCHEMA_PATH}."
    ),
}
REPO_NOTES = {
    "agy": "It is your working directory.",
    "opus": "Read it by absolute path: your own working directory can be another checkout.",
}


class ReviewError(Exception):
    """A failure the caller can act on; main() prints it as JSON and exits 1."""


class Interrupted(BaseException):
    """SIGTERM or SIGHUP while an agy job runs, so the job's process group is not orphaned."""


@dataclass
class Change:
    mode: str
    description: str
    root: Path
    patch: bytes
    files: List[str]
    added: int
    deleted: int
    base: Optional[str] = None
    head: Optional[str] = None
    worktree: Optional[Path] = None
    untracked: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


@dataclass
class Scope:
    job_dir: str
    repo: str
    root: str
    mode: str
    description: str
    base: Optional[str]
    head: Optional[str]
    worktree: Optional[str]
    files: List[str]
    untracked: List[str]
    skipped: List[str]
    added: int
    deleted: int
    diff_bytes: int
    lenses: List[str]
    reviewers: List[str]
    model: Optional[str]
    effort: str
    timeout_min: float
    fingerprint: str
    created_at: str


# --- processes -------------------------------------------------------------------------


def run_proc(
    argv: Sequence[str],
    cwd: Optional[Path] = None,
    ok_codes: Sequence[int] = (0,),
    timeout: Optional[float] = None,
) -> "subprocess.CompletedProcess[bytes]":
    try:
        proc = subprocess.run(
            list(argv), cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise ReviewError(f"{argv[0]} not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReviewError(f"{' '.join(argv[:3])} timed out after {timeout:.0f}s") from exc
    if proc.returncode not in ok_codes:
        detail = proc.stderr.decode(errors="replace").strip() or proc.stdout.decode(errors="replace").strip()
        raise ReviewError(f"{' '.join(argv[:4])} exited {proc.returncode}: {detail[:800]}")
    return proc


def git_bytes(
    repo: Path, *args: str, ok_codes: Sequence[int] = (0,), timeout: Optional[float] = None
) -> bytes:
    # No optional locks: concurrent agy jobs may run git in the same tree.
    return run_proc(
        ["git", "--no-optional-locks", "-C", str(repo), *args], ok_codes=ok_codes, timeout=timeout
    ).stdout


def git(repo: Path, *args: str, ok_codes: Sequence[int] = (0,), timeout: Optional[float] = None) -> str:
    return git_bytes(repo, *args, ok_codes=ok_codes, timeout=timeout).decode(errors="replace")


def rev_parse(repo: Path, rev: str) -> Optional[str]:
    sha = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", ok_codes=(0, 1, 128)).strip()
    return sha or None


def require_rev(repo: Path, rev: str) -> str:
    sha = rev_parse(repo, rev)
    if sha is None:
        raise ReviewError(f"unknown revision {rev!r}")
    return sha


def agy_bin() -> str:
    found = os.environ.get("AGY_BIN") or shutil.which("agy")
    if not found:
        raise ReviewError("agy not found on PATH; install the Antigravity CLI or set AGY_BIN")
    return found


# --- what to review -------------------------------------------------------------------------


def pathspec(all_files: bool) -> List[str]:
    if all_files:
        return ["--", "."]
    return ["--", ".", *(f":(exclude,glob)**/{pattern}" for pattern in NOISE)]


def is_noise(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in NOISE)


def shortstat(text: str) -> Tuple[int, int]:
    added = re.search(r"(\d+) insertion", text)
    deleted = re.search(r"(\d+) deletion", text)
    return (int(added.group(1)) if added else 0, int(deleted.group(1)) if deleted else 0)


def untracked_files(repo: Path) -> List[str]:
    raw = git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
    return [p for p in raw.decode(errors="replace").split("\0") if p]


def tracked_diff(repo: Path, base: str, head: Optional[str], all_files: bool) -> Tuple[bytes, List[str], int, int]:
    revs = [base] if head is None else [base, head]
    spec = pathspec(all_files)
    patch = git_bytes(repo, "diff", *DIFF_OPTS, *revs, *spec)
    names = git_bytes(repo, "diff", "--name-only", "-z", "--find-renames", *revs, *spec)
    added, deleted = shortstat(git(repo, "diff", "--shortstat", "--find-renames", *revs, *spec))
    return patch, [n for n in names.decode(errors="replace").split("\0") if n], added, deleted


def default_base(repo: Path) -> str:
    origin_head = git(
        repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", ok_codes=(0, 1, 128)
    ).strip()
    for candidate in ([origin_head] if origin_head else []) + ["origin/main", "origin/master", "main", "master"]:
        if rev_parse(repo, candidate):
            return candidate
    raise ReviewError("no default branch found (origin/HEAD, main or master); pass a base revision or a range")


def worktree_clean(repo: Path) -> bool:
    return not git(repo, "status", "--porcelain", "--untracked-files=no").strip()


def checkout_for(repo: Path, head: str, job_dir: Path) -> Tuple[Path, Optional[Path]]:
    """The tree agy reads: the user's checkout when it is exactly `head`, else a detached worktree."""
    if rev_parse(repo, "HEAD") == head and worktree_clean(repo):
        return repo, None
    path = job_dir / "src"
    git(repo, "worktree", "add", "--detach", "--quiet", str(path), head)
    return path, path


def change_for_branch(repo: Path, base_rev: Optional[str], untracked: bool, all_files: bool) -> Change:
    base_name = base_rev or default_base(repo)
    merge_base = git(repo, "merge-base", require_rev(repo, base_name), "HEAD").strip()
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    patch, files, added, deleted = tracked_diff(repo, merge_base, None, all_files)
    change = Change(
        mode="branch",
        description=f"{branch} plus uncommitted changes, against {base_name} (merge base {merge_base[:12]})",
        root=repo, patch=patch, files=files, added=added, deleted=deleted,
        base=merge_base, head=rev_parse(repo, "HEAD"),
    )
    if untracked:
        add_untracked(repo, change, all_files)
    return change


def add_untracked(repo: Path, change: Change, all_files: bool) -> None:
    for rel in untracked_files(repo):
        path = repo / rel
        if not all_files and is_noise(rel):
            continue
        try:
            if not path.is_file():
                continue
            if path.stat().st_size > UNTRACKED_MAX_BYTES:
                change.skipped.append(f"{rel} (untracked, over {UNTRACKED_MAX_BYTES // 1024} KiB)")
                continue
            with path.open("rb") as handle:
                lines = sum(1 for _ in handle)
            patch = run_proc(
                ["git", "-C", str(repo), "diff", *DIFF_OPTS, "--no-index", "--", "/dev/null", rel], ok_codes=(0, 1)
            ).stdout
        except (OSError, ReviewError) as exc:
            # A build or watcher can delete an untracked file between ls-files and here.
            change.skipped.append(f"{rel} (untracked, unreadable: {exc})")
            continue
        change.patch += patch
        change.untracked.append(rel)
        change.files.append(rel)
        change.added += lines


def change_for_range(repo: Path, target: str, job_dir: Path, all_files: bool) -> Change:
    match = RANGE_TARGET.match(target)
    if match is None:
        raise ReviewError(f"not a range: {target!r}")
    base_name, dots, head_name = match.groups()
    base_sha, head_sha = require_rev(repo, base_name), require_rev(repo, head_name)
    diff_base = git(repo, "merge-base", base_sha, head_sha).strip() if dots == "..." else base_sha
    patch, files, added, deleted = tracked_diff(repo, diff_base, head_sha, all_files)
    root, worktree = checkout_for(repo, head_sha, job_dir)
    return Change(
        mode="range", description=f"commits {target} ({diff_base[:12]}..{head_sha[:12]})",
        root=root, worktree=worktree, patch=patch, files=files, added=added, deleted=deleted,
        base=diff_base, head=head_sha,
    )


def change_for_pr(repo: Path, number: int, job_dir: Path, all_files: bool) -> Change:
    view = run_proc(
        ["gh", "pr", "view", str(number), "--json", "number,title,url,headRefOid,baseRefName"],
        cwd=repo, timeout=NETWORK_TIMEOUT_S,
    ).stdout
    info: Dict[str, Any] = json.loads(view)
    git(repo, "fetch", "--quiet", "--no-tags", "origin", f"pull/{number}/head", timeout=NETWORK_TIMEOUT_S)
    head_sha = require_rev(repo, "FETCH_HEAD")
    if head_sha != info.get("headRefOid"):
        # gh can resolve the number against an upstream while origin is a fork, which would review the wrong code.
        raise ReviewError(
            f"origin's pull/{number}/head is {head_sha[:12]} but GitHub reports {str(info.get('headRefOid'))[:12]}; "
            "if origin is not the PR's repository, fetch the PR yourself and review a <base>...<head> range"
        )
    git(repo, "fetch", "--quiet", "--no-tags", "origin", str(info["baseRefName"]), timeout=NETWORK_TIMEOUT_S)
    merge_base = git(repo, "merge-base", require_rev(repo, "FETCH_HEAD"), head_sha).strip()
    patch, files, added, deleted = tracked_diff(repo, merge_base, head_sha, all_files)
    root, worktree = checkout_for(repo, head_sha, job_dir)
    return Change(
        mode="pr",
        description=f"PR #{number} \"{info.get('title', '')}\" into {info['baseRefName']}, {info.get('url', '')}",
        root=root, worktree=worktree, patch=patch, files=files, added=added, deleted=deleted,
        base=merge_base, head=head_sha,
    )


def change_for_paths(repo: Path, paths: Sequence[str]) -> Change:
    files: List[str] = []
    lines = 0
    for raw in paths:
        path = Path(raw).resolve()
        if not path.is_file():
            raise ReviewError(f"not a file: {raw}")
        try:
            files.append(str(path.relative_to(repo)))
        except ValueError as exc:
            raise ReviewError(f"{raw} is outside the repository {repo}") from exc
        with path.open("rb") as handle:
            lines += sum(1 for _ in handle)
    return Change(
        mode="paths", description=f"{len(files)} file(s) reviewed in full", root=repo,
        patch=b"", files=files, added=lines, deleted=0, head=rev_parse(repo, "HEAD"),
    )


def resolve_change(repo: Path, args: argparse.Namespace, job_dir: Path) -> Change:
    if args.paths:
        if args.target:
            raise ReviewError("pass either a target or --paths, not both")
        return change_for_paths(repo, args.paths)
    target: Optional[str] = args.target
    if target:
        pr = PR_TARGET.match(target)
        if pr:
            return change_for_pr(repo, int(pr.group(1) or pr.group(2)), job_dir, args.all_files)
        if RANGE_TARGET.match(target):
            return change_for_range(repo, target, job_dir, args.all_files)
    return change_for_branch(repo, target, not args.no_untracked, args.all_files)


# --- model ---------------------------------------------------------------------------------


def gemini_rank(base: str) -> Tuple[Tuple[int, ...], int]:
    match = re.match(r"^gemini-(\d+(?:\.\d+)*)-?(.*)$", base)
    if match is None:
        return (), 0
    tier = match.group(2)
    tier_rank = 2 if "pro" in tier else 1 if "flash" in tier and "lite" not in tier else 0
    return tuple(int(part) for part in match.group(1).split(".")), tier_rank


def list_models(agy: str) -> Dict[str, List[str]]:
    """Base model name -> efforts it offers, from `agy models` (which also proves agy is signed in)."""
    try:
        listing = run_proc([agy, "models"], timeout=90).stdout.decode(errors="replace")
    except ReviewError as exc:
        raise ReviewError(f"`agy models` failed; run `agy` once in a terminal to sign in. {exc}") from exc
    variants: Dict[str, List[str]] = {}
    for line in listing.splitlines():
        model_id = line.split("\t", 1)[0].strip()
        if "\t" not in line or not model_id:
            continue
        match = EFFORT_SUFFIX.match(model_id)
        base, effort = (match.group(1), match.group(2)) if match else (model_id, None)
        efforts = variants.setdefault(base, [])
        if effort:
            efforts.append(effort)
    if not variants:
        raise ReviewError(f"`agy models` listed no models; run `agy` once in a terminal to sign in. Output: {listing[:400]}")
    return variants


def pick_effort(requested: Optional[str]) -> str:
    effort = requested or os.environ.get("AGY_REVIEW_EFFORT") or DEFAULT_EFFORT
    if effort not in EFFORTS:
        raise ReviewError(f"effort must be one of {', '.join(EFFORTS)}, not {effort!r}")
    return effort


def resolve_model(agy: str, requested_model: Optional[str], requested_effort: Optional[str]) -> Tuple[str, str]:
    effort = pick_effort(requested_effort)
    variants = list_models(agy)
    model = requested_model or os.environ.get("AGY_REVIEW_MODEL")
    if model:
        suffixed = EFFORT_SUFFIX.match(model)
        if model not in variants and suffixed and suffixed.group(1) in variants:
            model, effort = suffixed.group(1), suffixed.group(2)
        if model not in variants:
            raise ReviewError(f"agy has no model {model!r}; it lists: {', '.join(sorted(variants))}")
    else:
        candidates = [b for b in variants if b.startswith("gemini-") and effort in variants[b]]
        if not candidates:
            raise ReviewError(f"`agy models` lists no Gemini model with {effort} effort: {', '.join(sorted(variants))}")
        # Flash is the model this review compares with Opus; a newer heavier tier (Argon, Pro) needs --model.
        flash = [b for b in candidates if gemini_rank(b)[1] == 1]
        model = max(flash or candidates, key=gemini_rank)
    if variants[model] and effort not in variants[model]:
        raise ReviewError(f"{model} offers {', '.join(variants[model])} effort, not {effort}")
    return model, effort


# --- lenses and prompts ------------------------------------------------------------------


def available_lenses() -> List[str]:
    return sorted(p.stem for p in LENS_DIR.glob("*.md"))


def pick_lenses(requested: Optional[str], changed_lines: int) -> List[str]:
    if not requested or requested == "auto":
        return [ALL_LENS] if changed_lines < SMALL_CHANGE_LINES else list(DEFAULT_LENSES)
    names = [n.strip() for n in requested.split(",") if n.strip()]
    known = available_lenses() + [ALL_LENS]
    unknown = [n for n in names if n not in known]
    if unknown or not names:
        bad = ", ".join(unknown) if unknown else repr(requested)
        raise ReviewError(f"unknown lens {bad}; available: {', '.join(known)}")
    return names


def pick_reviewers(requested: Optional[str]) -> List[str]:
    raw = requested or os.environ.get("AGY_REVIEW_REVIEWERS") or ",".join(REVIEWERS)
    names = list(dict.fromkeys(n.strip() for n in raw.split(",") if n.strip()))
    unknown = [n for n in names if n not in REVIEWERS]
    if unknown or not names:
        bad = ", ".join(unknown) if unknown else repr(raw)
        raise ReviewError(f"unknown reviewer {bad}; available: {', '.join(REVIEWERS)}")
    return names


def require_reviewer(scope: Scope, reviewer: str) -> None:
    if reviewer not in scope.reviewers:
        raise ReviewError(f"this job's reviewers are {', '.join(scope.reviewers)}, not {reviewer}")


def lens_brief(lens: str) -> str:
    if lens != ALL_LENS:
        return (LENS_DIR / f"{lens}.md").read_text(encoding="utf-8").strip()
    parts = [f"### {name}\n\n{(LENS_DIR / f'{name}.md').read_text(encoding='utf-8').strip()}" for name in DEFAULT_LENSES]
    return "This job covers every lens below; correctness and security first.\n\n" + "\n\n".join(parts)


def build_prompt(scope: Scope, lens: str, reviewer: str) -> str:
    inputs = Path(scope.job_dir) / "input"
    if scope.mode == "paths":
        listed = "\n".join(f"  - {f}" for f in scope.files)
        change = (
            f"- Repository: {scope.root}. {REPO_NOTES[reviewer]}\n"
            f"- What: these files, reviewed in full rather than as a diff:\n{listed}"
        )
        read_rule = "Read each listed file in full first."
        scope_rule = "Report defects in the listed files. Touch other files only to prove a finding in them."
    else:
        untracked = "\n- Untracked new files are in the diff as additions." if scope.untracked else ""
        change = (
            f"- Repository: {scope.root}, checked out at the reviewed revision. {REPO_NOTES[reviewer]}\n"
            f"- What: {scope.description}\n"
            f"- Diff: {inputs / 'diff.patch'} ({len(scope.files)} files, +{scope.added} -{scope.deleted})\n"
            f"- Changed files, one per line: {inputs / 'files.txt'}{untracked}"
        )
        read_rule = "Read the whole diff first."
        scope_rule = (
            "Report defects this change introduces or makes reachable. Leave pre-existing problems "
            "out unless the change makes them worse."
        )
    return string.Template(BRIEF_PATH.read_text(encoding="utf-8")).substitute(
        lens=lens, change=change, read_rule=read_rule, scope_rule=scope_rule, lens_brief=lens_brief(lens),
        output_rule=OUTPUT_RULES[reviewer],
    )


# --- tree fingerprint ---------------------------------------------------------------------


def tree_fingerprint(root: Path) -> str:
    """Changes when any tracked or untracked file in the review root changes, so a job that edits is caught."""
    digest = hashlib.sha256()
    digest.update(git_bytes(root, "rev-parse", "HEAD"))
    digest.update(git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    digest.update(git_bytes(root, "diff", "--no-ext-diff", "--binary", "HEAD"))
    for rel in untracked_files(root):
        try:
            stat = (root / rel).stat()
        except OSError:
            continue
        digest.update(f"{rel}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode())
    return digest.hexdigest()


# --- job files -------------------------------------------------------------------------------


def load_scope(job_dir: Path) -> Scope:
    path = job_dir / "scope.json"
    try:
        return Scope(**json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError as exc:
        raise ReviewError(f"{job_dir} has no scope.json; run `scope` first") from exc
    except (json.JSONDecodeError, TypeError) as exc:
        raise ReviewError(f"{path} is not a scope written by this version: {exc}") from exc


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise ReviewError(f"{path} is not valid JSON: {exc}") from exc
    return data if isinstance(data, dict) else None


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def new_job_dir(requested: Optional[str], repo: Path) -> Path:
    if requested:
        path = Path(requested).resolve()
        if path.exists() and any(path.iterdir()):
            raise ReviewError(f"job dir {path} is not empty")
        path.mkdir(parents=True, exist_ok=True)
        return path
    home = os.environ.get("AGY_REVIEW_HOME")
    if home:
        parent, prefix = Path(home), f"{repo.name}-"
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    else:
        # Not a shared /tmp/agy-review parent: another local user could pre-create it and block or swap job dirs.
        parent, prefix = Path(tempfile.gettempdir()), f"agy-review-{repo.name}-"
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent)).resolve()


# --- subcommands -----------------------------------------------------------------------------


def cmd_scope(args: argparse.Namespace) -> Dict[str, Any]:
    cwd = Path.cwd()
    top = git(cwd, "rev-parse", "--show-toplevel", ok_codes=(0, 128)).strip()
    if not top:
        raise ReviewError(f"{cwd} is not inside a git repository")
    repo = Path(top).resolve()
    reviewers = pick_reviewers(args.reviewers)
    model: Optional[str] = None
    if "agy" in reviewers:
        model, effort = resolve_model(agy_bin(), args.model, args.effort)
    elif args.model:
        raise ReviewError("--model picks the agy model, and this review has no agy reviewer")
    else:
        effort = pick_effort(args.effort)
    job_dir = new_job_dir(args.job_dir, repo)
    try:
        change = resolve_change(repo, args, job_dir)
        if change.mode != "paths" and not change.files:
            raise ReviewError(f"nothing to review: {change.description} has no changes")
        lenses = pick_lenses(args.lenses, change.added + change.deleted)
        inputs = job_dir / "input"
        inputs.mkdir()
        (inputs / "diff.patch").write_bytes(change.patch)
        (inputs / "files.txt").write_text("".join(f"{f}\n" for f in change.files), encoding="utf-8")
        for reviewer in reviewers:
            (job_dir / "out" / reviewer).mkdir(parents=True)
        scope = Scope(
            job_dir=str(job_dir), repo=str(repo), root=str(change.root), mode=change.mode,
            description=change.description, base=change.base, head=change.head,
            worktree=str(change.worktree) if change.worktree else None,
            files=change.files, untracked=change.untracked, skipped=change.skipped,
            added=change.added, deleted=change.deleted, diff_bytes=len(change.patch),
            lenses=lenses, reviewers=reviewers, model=model, effort=effort, timeout_min=args.timeout,
            fingerprint=tree_fingerprint(change.root),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        write_json(job_dir / "scope.json", asdict(scope))
        if "opus" in reviewers:
            for lens in lenses:
                (job_dir / "out" / "opus" / f"{lens}.prompt.md").write_text(
                    build_prompt(scope, lens, "opus"), encoding="utf-8"
                )
    except BaseException:
        discard_job(repo, job_dir)
        raise
    warnings = []
    if scope.diff_bytes > LARGE_DIFF_BYTES:
        warnings.append(f"diff is {scope.diff_bytes // 1024} KiB; consider a narrower range or --paths")
    if scope.worktree is None and scope.root == scope.repo:
        warnings.append("the reviewers read your checkout: make no edits there until every lens has finished")
    helper = f"python3 -I {shlex.quote(str(Path(__file__).resolve()))}"
    job = shlex.quote(scope.job_dir)
    opus_out = job_dir / "out" / "opus"
    return {
        "job_dir": scope.job_dir,
        "mode": scope.mode,
        "description": scope.description,
        "root": scope.root,
        "files": scope.files[:60],
        "file_count": len(scope.files),
        "untracked": scope.untracked,
        "skipped": scope.skipped,
        "added": scope.added,
        "deleted": scope.deleted,
        "lenses": scope.lenses,
        "reviewers": scope.reviewers,
        "model": scope.model,
        "effort": scope.effort,
        "timeout_min": scope.timeout_min,
        "warnings": warnings,
        "run_commands": [f"{helper} run {job} {lens}" for lens in scope.lenses] if "agy" in reviewers else [],
        "opus_tasks": [
            {
                "lens": lens,
                "subagent_type": OPUS_AGENT,
                "model": OPUS_MODEL,
                "effort": scope.effort,
                "description": f"Opus review: {lens}",
                "prompt": f"Brief: {opus_out / f'{lens}.prompt.md'}\nRead it first and follow it exactly.",
                "reply_file": str(opus_out / f"{lens}.response.md"),
                "ingest_command": f"{helper} ingest {job} {lens}",
            }
            for lens in scope.lenses
        ] if "opus" in reviewers else [],
    }


def discard_job(repo: Path, job_dir: Path) -> None:
    src = job_dir / "src"
    if src.exists():
        git(repo, "worktree", "remove", "--force", str(src), ok_codes=(0, 128))
    shutil.rmtree(job_dir, ignore_errors=True)


def launch(argv: Sequence[str], cwd: str, stdout: Path, stderr: Path, deadline_s: float) -> Tuple[int, bool]:
    """Runs agy with stdin closed (an open pipe hangs it) and kills its process group past the deadline."""
    with stdout.open("wb") as out, stderr.open("wb") as err:
        proc = subprocess.Popen(
            list(argv), cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True
        )
        try:
            return proc.wait(timeout=deadline_s), False
        except subprocess.TimeoutExpired:
            stop_group(proc)
            return (proc.returncode if proc.returncode is not None else -signal.SIGKILL), True
        except BaseException:
            stop_group(proc)
            raise


def stop_group(proc: "subprocess.Popen[bytes]") -> None:
    for sig, grace in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def parse_agy_json(raw: bytes) -> Dict[str, Any]:
    text = raw.decode(errors="replace").strip()
    for candidate in (text, *reversed(text.splitlines())):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def parse_reply(text: str) -> Optional[Dict[str, Any]]:
    """The result object in an agent's reply: the last ```json fence that holds one, else the first object."""
    decoder = json.JSONDecoder()
    # raw_decode, not a fence regex: a finding's evidence can itself quote a ``` block.
    for start in [m.end() for m in re.finditer(r"```json", text)][::-1] + [0]:
        brace = text.find("{", start)
        if brace < 0:
            continue
        try:
            data, _ = decoder.raw_decode(text, brace)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("findings"), list):
            return data
    return None


def required_fields() -> List[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(schema["properties"]["findings"]["items"]["required"])


def clean_findings(raw: Any, lens: str, reviewer: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        finding = dict(item)
        finding["file"] = str(finding.get("file") or "")
        severity = str(finding.get("severity", "")).lower()
        finding["severity"] = severity if severity in SEVERITY_RANK else "medium"
        try:
            finding["line"] = int(finding.get("line", 0))
        except (TypeError, ValueError):
            finding["line"] = 0
        try:
            finding["confidence"] = max(0.0, min(1.0, float(finding.get("confidence", 0.5))))
        except (TypeError, ValueError):
            finding["confidence"] = 0.5
        finding["lens"] = lens
        finding["reviewer"] = reviewer
        finding["ref"] = f"{reviewer}/{lens}#{len(findings) + 1}"
        findings.append(finding)
    return findings


def incomplete(findings: List[Dict[str, Any]], raw: Any) -> List[str]:
    """Findings whose reply left out schema fields; clean_findings filled them with defaults."""
    required = required_fields()
    items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    warnings = []
    for finding, item in zip(findings, items):
        missing = [name for name in required if name not in item]
        if missing:
            warnings.append(f"{finding['ref']} lacks {', '.join(missing)}")
    return warnings


def classify(structured: Any, data: Dict[str, Any], timed_out: bool) -> str:
    if isinstance(structured, dict) and isinstance(structured.get("findings"), list):
        return "ok"
    if timed_out:
        return "timeout"
    # A network error can leave partial prose behind; only a finished turn counts as an answer.
    if data.get("status") == "SUCCESS" and str(data.get("response") or "").strip():
        return "unstructured"
    return "error"


def archive_attempt(out: Path, lens: str, attempt: int, suffixes: Sequence[str]) -> None:
    for suffix in suffixes:
        current = out / f"{lens}.{suffix}"
        if current.exists():
            current.replace(out / f"{lens}.{suffix}.{attempt}")


def cmd_run(args: argparse.Namespace) -> Dict[str, Any]:
    job_dir = Path(args.job_dir).resolve()
    scope = load_scope(job_dir)
    require_reviewer(scope, "agy")
    lens: str = args.lens
    pick_lenses(lens, 0)
    out = job_dir / "out" / "agy"
    previous = read_json(out / f"{lens}.result.json")
    attempt = int(previous.get("attempt", 0)) + 1 if previous else 1
    conversation: Optional[str] = None
    if args.resume:
        conversation = previous.get("conversation_id") if previous else None
        if not conversation:
            raise ReviewError(f"lens {lens} has no earlier agy conversation to resume")
        prompt = RESUME_PROMPT.substitute(lens=lens)
    else:
        prompt = build_prompt(scope, lens, "agy")
    if previous:
        archive_attempt(out, lens, attempt - 1, ("result.json", "json", "err", "prompt.md"))
    (out / f"{lens}.prompt.md").write_text(prompt, encoding="utf-8")

    timeout_min: float = args.timeout or scope.timeout_min
    timeout_s = max(1, round(timeout_min * 60))
    argv = [
        agy_bin(), "-p", prompt,
        "--model", scope.model, "--effort", scope.effort,
        "--output-format", "json", "--json-schema", str(SCHEMA_PATH),
        "--print-timeout", f"{timeout_s}s",
        # Print mode cannot answer permission prompts; --sandbox and the read-only brief bound it.
        "--dangerously-skip-permissions", "--sandbox", "--disable-slash-commands",
        "--add-dir", str(job_dir / "input"),
    ]
    if conversation:
        argv += ["--conversation", conversation]
    started = time.monotonic()
    exit_code, killed = launch(argv, scope.root, out / f"{lens}.json", out / f"{lens}.err", timeout_s + WATCHDOG_GRACE_S)
    elapsed = time.monotonic() - started

    data = parse_agy_json((out / f"{lens}.json").read_bytes())
    stderr_text = (out / f"{lens}.err").read_bytes().decode(errors="replace")
    structured = data.get("structured_output")
    status = classify(structured, data, killed or "print timeout" in stderr_text)
    findings = clean_findings(structured.get("findings") if isinstance(structured, dict) else None, lens, "agy")
    result: Dict[str, Any] = {
        "lens": lens,
        "reviewer": "agy",
        "status": status,
        "attempt": attempt,
        "summary": structured.get("summary") if isinstance(structured, dict) else None,
        "finding_count": len(findings),
        "findings": findings,
        "tree_changed": tree_fingerprint(Path(scope.root)) != scope.fingerprint,
        "model": scope.model,
        "effort": scope.effort,
        "duration_s": round(elapsed, 1),
        "agy_exit": exit_code,
        "agy_status": data.get("status"),
        "watchdog_killed": killed,
        "conversation_id": data.get("conversation_id") or conversation,
        "error": data.get("error"),
        "stderr_tail": stderr_text.strip().splitlines()[-15:],
        "response": data.get("response"),
        "usage": data.get("usage"),
    }
    write_json(out / f"{lens}.result.json", result)
    shown = {k: v for k, v in result.items() if k not in ("usage", "response")}
    if status != "ok":
        shown["response"] = result["response"]
    shown["result_file"] = str(out / f"{lens}.result.json")
    return shown


def cmd_ingest(args: argparse.Namespace) -> Dict[str, Any]:
    job_dir = Path(args.job_dir).resolve()
    scope = load_scope(job_dir)
    require_reviewer(scope, "opus")
    lens: str = args.lens
    if lens not in scope.lenses:
        raise ReviewError(f"lens {lens} is not in this job; its lenses are {', '.join(scope.lenses)}")
    out = job_dir / "out" / "opus"
    reply_path = out / f"{lens}.response.md"
    try:
        reply = reply_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReviewError(f"no reply at {reply_path}; write the agent's final message there first") from exc
    previous = read_json(out / f"{lens}.result.json")
    attempt = int(previous.get("attempt", 0)) + 1 if previous else 1
    if previous:
        archive_attempt(out, lens, attempt - 1, ("result.json",))
    # Moved aside: Claude's Write tool won't overwrite a file it hasn't read, so a retry needs a free path.
    kept = out / f"{lens}.response.md.{attempt}"
    reply_path.replace(kept)

    data = parse_reply(reply)
    raw = data.get("findings") if data else None
    findings = clean_findings(raw, lens, "opus")
    status = "ok" if data is not None else "unstructured" if reply.strip() else "error"
    result: Dict[str, Any] = {
        "lens": lens,
        "reviewer": "opus",
        "status": status,
        "attempt": attempt,
        "summary": data.get("summary") if data else None,
        "finding_count": len(findings),
        "findings": findings,
        "warnings": incomplete(findings, raw),
        "tree_changed": tree_fingerprint(Path(scope.root)) != scope.fingerprint,
        "model": OPUS_MODEL,
        "effort": scope.effort,
        "duration_s": args.duration_s,
        "tokens": args.tokens,
        "reply_file": str(kept),
        "response": None if data else reply,
    }
    write_json(out / f"{lens}.result.json", result)
    shown = {k: v for k, v in result.items() if k != "response" or status != "ok"}
    shown["result_file"] = str(out / f"{lens}.result.json")
    return shown


def rank_key(finding: Dict[str, Any]) -> Tuple[int, float, str, int]:
    return SEVERITY_RANK[finding["severity"]], -finding["confidence"], finding["file"], finding["line"]


def group_findings(findings: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Groups findings at the same spot from different reviewers or lenses; each group starts with its most severe."""
    groups: List[List[Dict[str, Any]]] = []
    for finding in sorted(findings, key=rank_key):
        source = (finding["reviewer"], finding["lens"])
        group = next(
            (g for g in groups
             if g[0]["file"] == finding["file"]
             and any(abs(m["line"] - finding["line"]) <= 3 for m in g)
             and all((m["reviewer"], m["lens"]) != source for m in g)),
            None,
        )
        if group is None:
            groups.append([finding])
        else:
            group.append(finding)
    return groups


def make_issue(
    issue_id: str,
    members: List[Dict[str, Any]],
    verdict: Optional[str] = None,
    severity: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    lead = min(members, key=rank_key)
    issue: Dict[str, Any] = {"id": issue_id}
    if verdict:
        issue["verdict"] = verdict
    issue["severity"] = severity or lead["severity"]
    issue.update(
        {key: lead.get(key) for key in ("file", "line", "category", "title", "failure_scenario", "evidence", "suggested_fix")}
    )
    if verdict:
        issue["reason"] = reason or ""
    issue["found_by"] = sorted({m["reviewer"] for m in members})
    issue["refs"] = [{key: m.get(key) for key in ("ref", "severity", "line", "title", "confidence")} for m in members]
    return issue


def entry_problems(n: int, entry: Any, by_ref: Dict[str, Any], owner: Dict[str, int]) -> List[str]:
    if not isinstance(entry, dict):
        return [f"entry {n} is not an object"]
    problems = []
    refs = entry.get("refs")
    if not isinstance(refs, list) or not refs or not all(isinstance(r, str) for r in refs):
        problems.append(f"entry {n}: refs must be a non-empty list of finding refs")
        refs = []
    if entry.get("verdict") not in VERDICTS:
        problems.append(f"entry {n}: verdict must be one of {', '.join(VERDICTS)}")
    if entry.get("severity") is not None and entry["severity"] not in SEVERITY_RANK:
        problems.append(f"entry {n}: severity must be one of {', '.join(SEVERITY_RANK)}")
    for ref in refs:
        if ref not in by_ref:
            problems.append(f"entry {n}: unknown ref {ref}")
        elif ref in owner:
            problems.append(f"entry {n}: {ref} is already in entry {owner[ref]}")
        else:
            owner[ref] = n
    return problems


def load_verdicts(path: Path, by_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Claude's verdicts: one entry per distinct defect, listing the ref of every finding that reports it."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReviewError(f"no verdicts file at {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReviewError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(entries, list):
        raise ReviewError(f"{path} must hold a JSON list of {{refs, verdict, reason, severity}} entries")
    owner: Dict[str, int] = {}
    problems = [p for n, entry in enumerate(entries, 1) for p in entry_problems(n, entry, by_ref, owner)]
    if problems:
        raise ReviewError(f"{path}: " + "; ".join(problems))
    return entries


def verified_issues(entries: List[Dict[str, Any]], by_ref: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    issues = [
        make_issue("", [by_ref[r] for r in e["refs"]], e["verdict"], e.get("severity"), e.get("reason"))
        for e in entries
    ]
    issues.sort(key=lambda i: (
        VERDICTS.index(i["verdict"]), SEVERITY_RANK[i["severity"]], -max(r["confidence"] for r in i["refs"])
    ))
    for n, issue in enumerate(issues, 1):
        issue["id"] = f"I{n}"
    return issues


def scoreboard(
    findings: List[Dict[str, Any]], issues: List[Dict[str, Any]], reviewers: Dict[str, Any]
) -> Dict[str, Any]:
    """Per reviewer: how many of its findings held up, and its share of every valid issue any reviewer found."""
    verdict_of = {ref["ref"]: issue["verdict"] for issue in issues for ref in issue["refs"]}
    severity_of = {ref["ref"]: issue["severity"] for issue in issues for ref in issue["refs"]}
    valid = [i for i in issues if i["verdict"] in VALID_VERDICTS]
    board: Dict[str, Any] = {}
    for reviewer, info in reviewers.items():
        own = [f for f in findings if f["reviewer"] == reviewer]
        counts = {v: sum(1 for f in own if verdict_of.get(f["ref"]) == v) for v in VERDICTS}
        verified = sum(counts.values())
        found = [i for i in valid if reviewer in i["found_by"]]
        durations = [lens["duration_s"] for lens in info["lenses"].values() if lens.get("duration_s") is not None]
        board[reviewer] = {
            "findings": len(own),
            **counts,
            "unverified": len(own) - verified,
            "precision": round((counts["confirmed"] + counts["plausible"]) / verified, 2) if verified else None,
            "severity_changed": sum(
                1 for f in own if verdict_of.get(f["ref"]) in VALID_VERDICTS and f["severity"] != severity_of[f["ref"]]
            ),
            "valid_issues": len(found),
            "unique_valid": sum(1 for i in found if i["found_by"] == [reviewer]),
            "recall": round(len(found) / len(valid), 2) if valid else None,
            "missed": [i["id"] for i in valid if reviewer not in i["found_by"]],
            "valid_by_severity": {s: sum(1 for i in found if i["severity"] == s) for s in SEVERITY_RANK},
            "lenses_failed": [name for name, lens in info["lenses"].items() if lens.get("status") != "ok"],
            "slowest_lens_s": max(durations) if durations else None,
        }
    return board


def collect_results(job_dir: Path, scope: Scope) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    reviewers: Dict[str, Any] = {}
    findings: List[Dict[str, Any]] = []
    for reviewer in scope.reviewers:
        out = job_dir / "out" / reviewer
        found = sorted(p.name[: -len(".result.json")] for p in out.glob("*.result.json"))
        lenses: Dict[str, Any] = {}
        for lens in dict.fromkeys([*scope.lenses, *found]):
            result = read_json(out / f"{lens}.result.json")
            if result is None:
                lenses[lens] = {"status": "not-run"}
                continue
            keys = ("status", "summary", "finding_count", "attempt", "duration_s", "tree_changed", "conversation_id")
            lenses[lens] = {key: result[key] for key in keys if key in result}
            findings.extend(result.get("findings", []))
        reviewers[reviewer] = {
            "model": scope.model if reviewer == "agy" else OPUS_MODEL,
            "effort": scope.effort,
            "lenses": lenses,
        }
    return reviewers, findings


def cmd_report(args: argparse.Namespace) -> Dict[str, Any]:
    job_dir = Path(args.job_dir).resolve()
    scope = load_scope(job_dir)
    reviewers, findings = collect_results(job_dir, scope)
    report: Dict[str, Any] = {
        "job_dir": str(job_dir),
        "description": scope.description,
        "root": scope.root,
        "reviewers": reviewers,
        "tree_changed": any(
            lens.get("tree_changed") for info in reviewers.values() for lens in info["lenses"].values()
        ),
        "verified": bool(args.verdicts),
    }
    if args.verdicts:
        by_ref = {f["ref"]: f for f in findings}
        entries = load_verdicts(Path(args.verdicts).resolve(), by_ref)
        issues = verified_issues(entries, by_ref)
        counted = [i for i in issues if i["verdict"] in VALID_VERDICTS]
        covered = {ref for entry in entries for ref in entry["refs"]}
        report.update(
            valid=len(counted),
            rejected=len(issues) - len(counted),
            unverified_refs=[f["ref"] for f in findings if f["ref"] not in covered],
            scoreboard=scoreboard(findings, issues, reviewers),
        )
    else:
        kept = [f for f in findings if f["confidence"] >= args.min_confidence]
        issues = [make_issue(f"I{n}", group) for n, group in enumerate(group_findings(kept), 1)]
        counted = issues
        report["total"] = len(issues)
    report.update(
        by_severity={s: sum(1 for i in counted if i["severity"] == s) for s in SEVERITY_RANK},
        found_by=dict(Counter("+".join(i["found_by"]) for i in counted)),
        issues=issues,
    )
    write_json(job_dir / ("report.verified.json" if args.verdicts else "report.json"), report)
    return report


def cmd_cleanup(args: argparse.Namespace) -> Dict[str, Any]:
    job_dir = Path(args.job_dir).resolve()
    scope = load_scope(job_dir)
    repo = Path(scope.repo)
    removed: Optional[str] = None
    if scope.worktree and Path(scope.worktree).exists():
        git(repo, "worktree", "remove", "--force", scope.worktree)
        removed = scope.worktree
    git(repo, "worktree", "prune")
    if args.purge:
        shutil.rmtree(job_dir)
    return {"job_dir": str(job_dir), "worktree_removed": removed, "purged": bool(args.purge)}


# --- entry point ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agy_review.py", description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    scope = sub.add_parser("scope", help="resolve what to review into a new job directory")
    scope.add_argument(
        "target", nargs="?",
        help="none: this branch plus uncommitted work against the default branch; <rev>: the same "
             "against <rev>; <a>..<b> or <a>...<b>: a commit range; pr:<n>, #<n> or a PR URL",
    )
    scope.add_argument("--paths", nargs="+", metavar="FILE", help="review these files in full instead of a diff")
    scope.add_argument("--lenses", default="auto", help="comma-separated lenses, 'all', or auto (default)")
    scope.add_argument(
        "--reviewers", help=f"comma-separated, from {', '.join(REVIEWERS)} (default: all of them, or $AGY_REVIEW_REVIEWERS)"
    )
    scope.add_argument("--model", help="agy model; default: the newest Gemini Flash offering the effort")
    scope.add_argument("--effort", choices=EFFORTS, help=f"reasoning effort (default {DEFAULT_EFFORT})")
    scope.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_MIN, help="minutes per lens job")
    scope.add_argument("--job-dir", help="where to keep the job (default: a new agy-review-<repo>-* folder in $TMPDIR)")
    scope.add_argument("--no-untracked", action="store_true", help="leave untracked files out of a branch review")
    scope.add_argument("--all-files", action="store_true", help="keep lockfiles, minified and map files in the diff")
    scope.set_defaults(func=cmd_scope)

    run = sub.add_parser("run", help="run one lens as an agy job")
    run.add_argument("job_dir")
    run.add_argument("lens")
    run.add_argument("--resume", action="store_true", help="continue the lens's last agy conversation")
    run.add_argument("--timeout", type=float, help="minutes; default: the scope's timeout")
    run.set_defaults(func=cmd_run)

    ingest = sub.add_parser("ingest", help="normalise one Opus reviewer's reply, saved to its reply_file")
    ingest.add_argument("job_dir")
    ingest.add_argument("lens")
    ingest.add_argument("--duration-s", type=float, help="the agent's run time, if its notification gave one")
    ingest.add_argument("--tokens", type=int, help="the agent's token count, if its notification gave one")
    ingest.set_defaults(func=cmd_ingest)

    report = sub.add_parser("report", help="merge every reviewer's findings into ranked issues")
    report.add_argument("job_dir")
    report.add_argument("--min-confidence", type=float, default=0.0, help="ignored with --verdicts")
    report.add_argument("--verdicts", metavar="FILE", help="Claude's verdicts; adds the reviewer scoreboard")
    report.set_defaults(func=cmd_report)

    cleanup = sub.add_parser("cleanup", help="remove the PR or range worktree")
    cleanup.add_argument("job_dir")
    cleanup.add_argument("--purge", action="store_true", help="also delete the job directory")
    cleanup.set_defaults(func=cmd_cleanup)
    return parser


def _interrupt(signum: int, _frame: Any) -> None:
    raise Interrupted(signum)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _interrupt)
    handler: Callable[[argparse.Namespace], Dict[str, Any]] = args.func
    try:
        payload = handler(args)
    except ReviewError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except Interrupted as exc:
        print(json.dumps({"error": f"interrupted by signal {exc.args[0]}; the agy job was stopped"}), file=sys.stderr)
        return 130
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if args.command not in ("run", "ingest") or payload.get("status") == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
