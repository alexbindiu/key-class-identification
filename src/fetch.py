"""Clones the repos from config/systems.yaml and checks out the chosen commits.
Repos that are already cloned are only checked, not cloned again.

Usage: python src/fetch.py [system ...]
"""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "systems.yaml"
REPOS = ROOT / "data" / "repos"


def git(*args, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def fetch(name, system):
    target = REPOS / name
    if (target / ".git").exists():
        head = git("rev-parse", "HEAD", cwd=target)
        status = "ok (already cloned)" if head == system["commit"] else f"WRONG COMMIT {head}"
        return status
    # full clone, we need the history
    git("clone", "--quiet", "-c", "core.longpaths=true", system["repo"], str(target))
    git("-c", "advice.detachedHead=false", "checkout", "--quiet", system["commit"], cwd=target)
    return "cloned"


def main():
    systems = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(systems)
    REPOS.mkdir(parents=True, exist_ok=True)
    for name in names:
        print(f"{name:24} ", end="", flush=True)
        try:
            print(fetch(name, systems[name]))
        except RuntimeError as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
