"""Tests for agy_review.py against a stub agy and gh, in throwaway git repos.

Run: python3 -I plugins/antigravity-agents/tests/test_agy_review.py
Nothing reaches the real agy, GitHub or your git config.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "skills" / "agy-review" / "scripts" / "agy_review.py"
SCHEMA = HERE.parent / "skills" / "agy-review" / "findings.schema.json"

AGY_STUB = r'''#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
if args[:1] == ["models"]:
    print("Fetching available models...")
    for line in os.environ["STUB_MODELS"].split(";"):
        print(line.replace(",", "\t"))
    sys.exit(0)
stdin = sys.stdin.read()  # hangs here if the caller left stdin open
mode = os.environ.get("STUB_MODE", "ok")
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps({"argv": args, "cwd": os.getcwd(), "stdin": len(stdin), "mode": mode}) + "\n")
if mode == "hang":
    time.sleep(60)
if mode == "edit":
    with open("app.py", "a") as f:
        f.write("# touched by a reviewer\n")
conv = os.environ.get("STUB_CONV", "conv-1")
if mode == "timeout":
    print("[agy] print timeout after 1s with turn in progress; returning partial output", file=sys.stderr)
    print(json.dumps({"conversation_id": conv, "status": "SUCCESS", "response": ""}))
    sys.exit(0)
if mode == "prose":
    print(json.dumps({"conversation_id": conv, "status": "SUCCESS", "response": "app.py:3 divides by zero"}))
    sys.exit(0)
if mode == "neterror":
    print("network timeout", file=sys.stderr)
    print(json.dumps({"conversation_id": conv, "status": "ERROR", "response": "app.py:3 div", "error": "network"}))
    sys.exit(3)
findings = json.loads(os.environ.get("STUB_FINDINGS", "[]"))
print(json.dumps({"conversation_id": conv, "status": "SUCCESS", "response": "done",
                  "structured_output": {"summary": "checked", "findings": findings}}))
'''

GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
print(json.dumps({"number": 7, "title": "Add division", "url": "https://github.com/o/r/pull/7",
                  "headRefOid": os.environ["STUB_PR_HEAD"], "baseRefName": "main"}))
'''

MODELS = ";".join([
    "gemini-3.8-flash-high,Gemini 3.8 Flash (High)",
    "gemini-3.8-flash-medium,Gemini 3.8 Flash (Medium)",
    "gemini-3.10-flash-high,Gemini 3.10 Flash (High)",
    "gemini-3.10-flash-low,Gemini 3.10 Flash (Low)",
    "gemini-3.10-pro-medium,Gemini 3.10 Pro (Medium)",
    "claude-opus-5-5-high,Claude Opus 5.5 (High)",
    "gpt-oss-120b-medium,GPT-OSS 120B (Medium)",
])


def finding(file: str, line: int, severity: str, title: str, confidence: float = 0.9) -> Dict[str, Any]:
    return {
        "file": file, "line": line, "severity": severity, "category": "test", "title": title,
        "failure_scenario": "b == 0", "evidence": f"{file}:{line}", "suggested_fix": "guard",
        "confidence": confidence,
    }


def load_module() -> Any:
    # A __pycache__ next to the script would ship: the marketplace copies plugin folders verbatim.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("agy_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


class Sandbox:
    """A clone of a bare origin, a feature branch with committed, uncommitted and untracked work."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agy-review-test-")).resolve()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("agy", AGY_STUB), ("gh", GH_STUB)):
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text(textwrap.dedent("""\
            [user]
                name = Test
                email = test@example.invalid
            [commit]
                gpgsign = false
            [init]
                defaultBranch = main
            [advice]
                detachedHead = false
            """))
        self.log = self.tmp / "agy.log"
        self.home = self.tmp / "jobs"
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "STUB_LOG": str(self.log),
            "STUB_MODELS": MODELS,
            "AGY_REVIEW_HOME": str(self.home),
        }
        for key in ("AGY_BIN", "AGY_REVIEW_MODEL", "AGY_REVIEW_EFFORT", "AGY_REVIEW_GRACE_S"):
            self.env.pop(key, None)
        self.origin = self.tmp / "origin.git"
        self.repo = self.tmp / "repo"
        self.git(self.tmp, "init", "--quiet", "--bare", str(self.origin))
        self.git(self.tmp, "clone", "--quiet", str(self.origin), str(self.repo))
        (self.repo / "app.py").write_text("def div(a, b):\n    return a // b\n")
        self.git(self.repo, "add", "app.py")
        self.git(self.repo, "commit", "--quiet", "-m", "init")
        self.git(self.repo, "push", "--quiet", "origin", "HEAD:main")
        self.git(self.repo, "remote", "set-head", "origin", "main")
        self.git(self.repo, "switch", "--quiet", "-c", "feature")
        (self.repo / "app.py").write_text("def div(a, b):\n    return a / b\n")
        (self.repo / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
        self.git(self.repo, "add", "app.py", "package-lock.json")
        self.git(self.repo, "commit", "--quiet", "-m", "true division")
        self.feature = self.git(self.repo, "rev-parse", "HEAD").strip()

    def dirty(self) -> None:
        with (self.repo / "app.py").open("a") as handle:
            handle.write("\ndef mul(a, b):\n    return a * b\n")
        (self.repo / "new.py").write_text("print('new content')\n")
        (self.repo / ".DS_Store").write_bytes(b"\x00\x01junk")

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True, text=True
        ).stdout

    def cli(self, *args: str, timeout: float = 60, **env: str) -> Tuple[int, Dict[str, Any]]:
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), *args], cwd=self.repo, env={**self.env, **env},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
        )
        stream = proc.stdout if proc.stdout.strip() else proc.stderr
        try:
            return proc.returncode, json.loads(stream)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"not JSON (exit {proc.returncode}): {proc.stdout!r} {proc.stderr!r}") from exc

    def calls(self) -> List[Dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


class ScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.close)

    def test_branch_scope_covers_commits_uncommitted_and_untracked_work(self) -> None:
        self.box.dirty()
        code, out = self.box.cli("scope")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["mode"], "branch")
        self.assertEqual(sorted(out["files"]), ["app.py", "new.py"])
        self.assertEqual(out["untracked"], ["new.py"])
        self.assertEqual(out["root"], str(self.box.repo))
        self.assertEqual(out["lenses"], ["all"])
        self.assertEqual((out["model"], out["effort"]), ("gemini-3.10-flash", "high"))
        patch = (Path(out["job_dir"]) / "input" / "diff.patch").read_text()
        self.assertIn("+    return a / b", patch)
        self.assertIn("+def mul(a, b):", patch)
        self.assertIn("+print('new content')", patch)
        self.assertNotIn("lockfileVersion", patch)
        self.assertEqual(len(out["run_commands"]), 1)
        self.assertTrue(out["run_commands"][0].endswith(f"run {out['job_dir']} all"))

    def test_large_change_fans_out_to_four_lenses(self) -> None:
        (self.box.repo / "big.py").write_text("x = 1\n" * 200)
        code, out = self.box.cli("scope")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["lenses"], ["correctness", "security", "reliability", "conventions"])

    def test_explicit_lenses_are_validated(self) -> None:
        code, out = self.box.cli("scope", "--lenses", "security,bogus")
        self.assertEqual(code, 1)
        self.assertIn("unknown lens bogus", out["error"])

    def test_nothing_to_review_leaves_no_job_behind(self) -> None:
        self.box.git(self.box.repo, "switch", "--quiet", "main")
        code, out = self.box.cli("scope")
        self.assertEqual(code, 1)
        self.assertIn("nothing to review", out["error"])
        self.assertEqual(list(self.box.home.iterdir()), [])

    def test_default_job_dir_sits_directly_in_the_temp_dir(self) -> None:
        self.box.dirty()
        tmpdir = self.box.tmp / "t"
        tmpdir.mkdir()
        env = {k: v for k, v in self.box.env.items() if k != "AGY_REVIEW_HOME"}
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "scope"], cwd=self.box.repo, env={**env, "TMPDIR": str(tmpdir)},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        job = Path(json.loads(proc.stdout)["job_dir"])
        self.assertEqual(job.parent, tmpdir.resolve())
        self.assertTrue(job.name.startswith("agy-review-repo-"))
        self.assertEqual(job.stat().st_mode & 0o777, 0o700)

    def test_untracked_files_that_vanish_or_cannot_be_read_are_skipped(self) -> None:
        module = load_module()
        module.untracked_files = lambda repo: ["gone.py", "locked.py", "ok.py"]
        locked = self.box.repo / "locked.py"
        locked.write_text("secret = 1\n")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o644)
        (self.box.repo / "ok.py").write_text("ok = 1\n")
        change = module.Change(mode="branch", description="", root=self.box.repo, patch=b"", files=[], added=0, deleted=0)
        module.add_untracked(self.box.repo, change, False)
        self.assertEqual((change.files, change.added), (["ok.py"], 1))
        [skipped] = change.skipped
        self.assertTrue(skipped.startswith("locked.py (untracked, unreadable:"), skipped)

    def test_range_on_another_head_reviews_a_worktree_that_cleanup_removes(self) -> None:
        self.box.dirty()
        code, out = self.box.cli("scope", "main...feature")
        self.assertEqual(code, 0, out)
        root = Path(out["root"])
        self.assertEqual(root, Path(out["job_dir"]) / "src")
        self.assertEqual(self.box.git(root, "rev-parse", "HEAD").strip(), self.box.feature)
        self.assertEqual(out["files"], ["app.py"])
        code, cleaned = self.box.cli("cleanup", out["job_dir"])
        self.assertEqual(code, 0, cleaned)
        self.assertEqual(cleaned["worktree_removed"], str(root))
        self.assertFalse(root.exists())
        self.assertNotIn(str(root), self.box.git(self.box.repo, "worktree", "list"))

    def test_range_at_a_clean_head_reuses_the_checkout(self) -> None:
        code, out = self.box.cli("scope", "main..HEAD")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["root"], str(self.box.repo))

    def test_pr_is_fetched_from_origin(self) -> None:
        self.box.git(self.box.repo, "push", "--quiet", "origin", f"{self.box.feature}:refs/pull/7/head")
        self.box.git(self.box.repo, "switch", "--quiet", "main")
        code, out = self.box.cli("scope", "#7", STUB_PR_HEAD=self.box.feature)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["mode"], "pr")
        self.assertIn('PR #7 "Add division" into main', out["description"])
        self.assertEqual(self.box.git(Path(out["root"]), "rev-parse", "HEAD").strip(), self.box.feature)
        self.box.cli("cleanup", out["job_dir"])

    def test_pr_head_that_does_not_match_github_is_refused(self) -> None:
        self.box.git(self.box.repo, "push", "--quiet", "origin", f"{self.box.feature}:refs/pull/7/head")
        code, out = self.box.cli("scope", "pr:7", STUB_PR_HEAD="0" * 40)
        self.assertEqual(code, 1)
        self.assertIn("but GitHub reports 000000000000", out["error"])
        self.assertEqual(list(self.box.home.iterdir()), [])

    def test_paths_review_whole_files(self) -> None:
        code, out = self.box.cli("scope", "--paths", "app.py")
        self.assertEqual(code, 0, out)
        self.assertEqual((out["mode"], out["files"]), ("paths", ["app.py"]))

    def test_effort_picks_a_gemini_that_offers_it(self) -> None:
        self.box.dirty()
        code, out = self.box.cli("scope", "--effort", "medium")
        self.assertEqual((code, out["model"], out["effort"]), (0, "gemini-3.10-pro", "medium"), out)
        code, out = self.box.cli("scope", "--effort", "max")
        self.assertEqual(code, 1)
        self.assertIn("no Gemini model with max effort", out["error"])

    def test_explicit_model_with_effort_suffix_is_split(self) -> None:
        self.box.dirty()
        code, out = self.box.cli("scope", "--model", "gemini-3.8-flash-medium")
        self.assertEqual((code, out["model"], out["effort"]), (0, "gemini-3.8-flash", "medium"), out)
        code, out = self.box.cli("scope", "--model", "gemini-9-ultra")
        self.assertEqual(code, 1)
        self.assertIn("agy has no model 'gemini-9-ultra'", out["error"])


class RunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.close)
        self.box.dirty()
        code, self.scope = self.box.cli("scope")
        self.assertEqual(code, 0, self.scope)
        self.job = self.scope["job_dir"]

    def test_ok_run_passes_the_flags_print_mode_needs(self) -> None:
        findings = json.dumps([finding("app.py", 2, "HIGH", "division by zero")])
        code, out = self.box.cli("run", self.job, "all", STUB_FINDINGS=findings)
        self.assertEqual(code, 0, out)
        self.assertEqual((out["status"], out["finding_count"], out["tree_changed"]), ("ok", 1, False))
        self.assertEqual(out["findings"][0]["severity"], "high")
        self.assertEqual(out["findings"][0]["lens"], "all")
        self.assertNotIn("response", out)
        [call] = self.box.calls()
        argv = call["argv"]
        self.assertEqual(call["stdin"], 0)
        self.assertEqual(call["cwd"], self.scope["root"])
        for flag in ("--dangerously-skip-permissions", "--sandbox", "--disable-slash-commands"):
            self.assertIn(flag, argv)
        pairs = dict(zip(argv, argv[1:]))
        self.assertEqual(pairs["--model"], "gemini-3.10-flash")
        self.assertEqual(pairs["--effort"], "high")
        self.assertEqual(pairs["--output-format"], "json")
        self.assertEqual(pairs["--json-schema"], str(SCHEMA))
        self.assertEqual(pairs["--print-timeout"], "1200s")
        self.assertEqual(pairs["--add-dir"], str(Path(self.job) / "input"))
        prompt = pairs["-p"]
        self.assertIn("Your lens is **all**", prompt)
        self.assertIn(str(Path(self.job) / "input" / "diff.patch"), prompt)
        self.assertIn("### security", prompt)
        self.assertNotIn("$", prompt.split("## Lens")[0])

    def test_timeout_then_resume_continues_the_same_conversation(self) -> None:
        code, out = self.box.cli("run", self.job, "all", STUB_MODE="timeout", STUB_CONV="conv-42")
        self.assertEqual((code, out["status"], out["conversation_id"]), (2, "timeout", "conv-42"), out)
        code, out = self.box.cli("run", self.job, "all", "--resume", STUB_FINDINGS="[]")
        self.assertEqual((code, out["status"], out["attempt"]), (0, "ok", 2), out)
        argv = self.box.calls()[-1]["argv"]
        self.assertEqual(dict(zip(argv, argv[1:]))["--conversation"], "conv-42")
        self.assertIn("without starting over", dict(zip(argv, argv[1:]))["-p"])
        self.assertTrue((Path(self.job) / "out" / "all.result.json.1").exists())

    def test_resume_without_an_earlier_run_is_an_error(self) -> None:
        code, out = self.box.cli("run", self.job, "security", "--resume")
        self.assertEqual(code, 1)
        self.assertIn("no earlier agy conversation", out["error"])

    def test_watchdog_kills_a_stalled_job(self) -> None:
        started = time.monotonic()
        code, out = self.box.cli(
            "run", self.job, "all", "--timeout", "0.01", STUB_MODE="hang", AGY_REVIEW_GRACE_S="1"
        )
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual((code, out["status"], out["watchdog_killed"]), (2, "timeout", True), out)

    def test_an_edit_in_the_review_root_is_reported(self) -> None:
        code, out = self.box.cli("run", self.job, "all", STUB_MODE="edit")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["tree_changed"])

    def test_prose_answer_is_returned_for_the_caller_to_read(self) -> None:
        code, out = self.box.cli("run", self.job, "all", STUB_MODE="prose")
        self.assertEqual((code, out["status"]), (2, "unstructured"), out)
        self.assertEqual(out["response"], "app.py:3 divides by zero")

    def test_network_error_with_partial_prose_is_an_error_to_resume(self) -> None:
        code, out = self.box.cli("run", self.job, "all", STUB_MODE="neterror")
        self.assertEqual((code, out["status"], out["agy_exit"]), (2, "error", 3), out)
        self.assertEqual(out["error"], "network")


class ReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()
        self.addCleanup(self.box.close)
        self.box.dirty()
        code, scope = self.box.cli("scope", "--lenses", "correctness,security,reliability")
        self.assertEqual(code, 0, scope)
        self.job = scope["job_dir"]

    def test_report_ranks_folds_twins_and_lists_missing_lenses(self) -> None:
        self.box.cli("run", self.job, "correctness", STUB_FINDINGS=json.dumps([
            finding("app.py", 2, "medium", "divide by zero"),
            finding("app.py", 40, "low", "naming", confidence=0.2),
        ]))
        self.box.cli("run", self.job, "security", STUB_FINDINGS=json.dumps([
            finding("app.py", 3, "critical", "attacker-controlled divisor crashes worker"),
        ]))
        code, report = self.box.cli("report", self.job, "--min-confidence", "0.5")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["total"], 1)
        [top] = report["findings"]
        self.assertEqual((top["severity"], top["lens"]), ("critical", "security"))
        self.assertEqual(top["also_reported_by"], [{"lens": "correctness", "title": "divide by zero"}])
        self.assertEqual(report["lenses"]["reliability"], {"status": "not-run"})
        self.assertTrue((Path(self.job) / "report.json").exists())


class RankTest(unittest.TestCase):
    def test_newer_version_beats_older_and_pro_beats_flash(self) -> None:
        module = load_module()
        ranked = sorted(
            ["gemini-3.8-flash", "gemini-3.10-flash", "gemini-3.10-pro", "gemini-3.10-flash-lite"],
            key=module.gemini_rank,
        )
        self.assertEqual(ranked[-1], "gemini-3.10-pro")
        self.assertEqual(ranked[0], "gemini-3.8-flash")


if __name__ == "__main__":
    unittest.main(verbosity=1)
