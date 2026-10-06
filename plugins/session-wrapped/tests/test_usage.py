"""usage.py reads the active profile's transcripts. Run: python3 -I tests/test_usage.py"""
import importlib.util
import os
import pathlib
import sys

# A directory-source install copies the folder verbatim, so keep __pycache__ out of scripts/.
sys.dont_write_bytecode = True
SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "usage.py"


def root_for(env: dict[str, str]) -> str:
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location("usage", SCRIPT)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.ROOT
    finally:
        os.environ.clear()
        os.environ.update(saved)


if __name__ == "__main__":
    assert root_for({"HOME": "/h"}) == "/h/.claude/projects"
    assert root_for({"HOME": "/h", "CLAUDE_CONFIG_DIR": ""}) == "/h/.claude/projects"
    assert root_for({"HOME": "/h", "CLAUDE_CONFIG_DIR": "/h/.claude-alm"}) == "/h/.claude-alm/projects"
    assert root_for({"HOME": "/h", "CLAUDE_CONFIG_DIR": "~/.claude-alm"}) == "/h/.claude-alm/projects"
    print("ok")
