"""Lines of code of every class: lines with code, without blank lines and comments.
The whole file is counted, inner classes included.

Output: data/size/<system>.csv
Usage: python src/size.py [system ...]
"""
import csv
import re
import sys

from dependencies import PARSER, walk
from sources import REPOS, ROOT, load_systems

GRAPH = ROOT / "data" / "graph"
OUTPUT = ROOT / "data" / "size"


def lines_of_code(source):
    code = bytearray(source)
    for node in walk(PARSER.parse(source).root_node):
        if node.type in ("line_comment", "block_comment"):
            # blank out the comment but keep its line breaks
            code[node.start_byte:node.end_byte] = re.sub(rb"[^\n]", b" ", source[node.start_byte:node.end_byte])
    return sum(1 for line in code.splitlines() if line.strip())


def main():
    systems = load_systems()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or list(systems):
        with open(GRAPH / name / "classes.csv", encoding="utf-8") as f:
            classes = list(csv.DictReader(f))
        with open(OUTPUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fqn", "loc"])
            total = 0
            for c in classes:
                loc = lines_of_code((REPOS / name / c["path"]).read_bytes())
                total += loc
                w.writerow([c["fqn"], loc])
        print(f"{name:22} classes={len(classes):5}  total loc={total:7}", flush=True)


if __name__ == "__main__":
    main()
