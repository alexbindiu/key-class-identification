"""Git history of every class, using only the commits up to the chosen commit (snapshot).
Renamed files keep their older history; merge commits are not counted.

Output: data/history/<system>.csv
Usage: python src/history.py [system ...]
"""
import csv
import re
import subprocess
import sys

from sources import REPOS, ROOT, load_systems

GRAPH = ROOT / "data" / "graph"
OUTPUT = ROOT / "data" / "history"
BRACE = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")


def rename_paths(path):
    """'a/{old => new}/F.java' -> ('a/old/F.java', 'a/new/F.java')"""
    m = BRACE.match(path)
    if m:
        pre, old, new, post = m.groups()
        join = lambda middle: re.sub(r"/+", "/", f"{pre}{middle}{post}").lstrip("/")
        return join(old), join(new)
    if " => " in path:
        old, new = path.split(" => ", 1)
        return old, new
    return path, path


def git_log(repo, commit):
    cmd = ["git", "-c", "diff.renameLimit=0", "-C", str(repo), "log", commit, "--reverse", "--no-merges",
           "-M", "--numstat", "--format=@@%ae|%ct"]
    return subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", check=True).stdout


def history(repo, commit):
    """Stats per file path, as the path is at the snapshot."""
    stats = {}
    author = when = None
    for line in git_log(repo, commit).splitlines():
        if line.startswith("@@"):
            author, when = line[2:].rsplit("|", 1)
            author, when = author.lower(), int(when)
            continue
        if not line.strip():
            continue
        added, deleted, path = line.split("\t", 2)
        old, new = rename_paths(path)
        if not new.endswith(".java"):
            continue
        stat = stats.pop(old, None) if old != new else stats.get(new)
        if stat is None:
            stat = {"commits": 0, "churn": 0, "authors": set(), "first": when, "last": when}
        stat["commits"] += 1
        stat["churn"] += sum(int(n) for n in (added, deleted) if n != "-")  # "-" for binary files
        stat["authors"].add(author)
        stat["last"] = when
        stats[new] = stat
    return stats


def main():
    systems = load_systems()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or list(systems):
        repo, commit = REPOS / name, systems[name]["commit"]
        snapshot = int(subprocess.run(["git", "-C", str(repo), "show", "-s", "--format=%ct", commit],
                                      capture_output=True, text=True, check=True).stdout)
        stats = history(repo, commit)
        with open(GRAPH / name / "classes.csv", encoding="utf-8") as f:
            classes = list(csv.DictReader(f))
        missing = 0
        with open(OUTPUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fqn", "commits", "churn", "authors", "age_days", "days_since_last_change"])
            for c in classes:
                s = stats.get(c["path"])
                if s is None:
                    missing += 1
                    w.writerow([c["fqn"], 0, 0, 0, 0, 0])
                    continue
                w.writerow([c["fqn"], s["commits"], s["churn"], len(s["authors"]),
                            (snapshot - s["first"]) // 86400, (snapshot - s["last"]) // 86400])
        print(f"{name:22} classes={len(classes):5}  without history={missing}", flush=True)


if __name__ == "__main__":
    main()
