"""Helpers for finding the Java files and classes of a system.
Tests, examples and benchmarks are always skipped.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "systems.yaml"
REPOS = ROOT / "data" / "repos"

# always left out: tests, examples/samples, benchmarks
SKIP_DIR = re.compile(r"(^|/)(test|tests|testcases|it|testing|example|examples|sample|samples|"
                      r"benchmark|benchmarks|jmh)(/|$)", re.I)
SKIP_FILE = re.compile(r"(Test|Tests|IT)\.java$")
PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
TYPE_DECL = re.compile(r"(@interface|\bclass|\binterface|\benum)\s+(\w+)")


def load_systems():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _inside(path, folders):
    return any(f in (".", "") or path == f or path.startswith(f.rstrip("/") + "/") for f in folders)


def main_java_files(name, system):
    """Paths of the .java files we analyse, relative to the repo."""
    repo = REPOS / name
    files = []
    for p in repo.rglob("*.java"):
        rel = p.relative_to(repo).as_posix()
        if rel.startswith(".git/"):
            continue
        if not _inside(rel, system["source"]) or _inside(rel, system.get("exclude", [])):
            continue
        if SKIP_DIR.search(rel) or SKIP_FILE.search(rel):
            continue
        files.append(rel)
    return sorted(files)


def read_java(path):
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def classes(name, system):
    """Classes of a system, found with simple regexes. Enough for matching names."""
    prefix = system.get("package_prefix")
    result = {}
    for rel in main_java_files(name, system):
        text = COMMENTS.sub(" ", read_java(REPOS / name / rel))
        m = PACKAGE.search(text)
        package = m.group(1) if m else ""
        if prefix and not (package == prefix or package.startswith(prefix + ".")):
            continue
        top = Path(rel).stem
        kind, nested = "class", []
        for decl_kind, decl_name in TYPE_DECL.findall(text):
            if decl_name == top:
                kind = "annotation" if decl_kind == "@interface" else decl_kind
            elif decl_name not in nested:
                nested.append(decl_name)
        fqn = f"{package}.{top}" if package else top
        result[fqn] = {"kind": kind, "package": package, "nested": nested}
    return result
