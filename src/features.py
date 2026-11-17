"""Builds the raw feature table: one row per class, for all systems.
It joins the graph, the Git history, the lines of code and the ground truth.
The columns are explained in data/features/COLUMNS.md.

Output: data/features/raw_features.csv
"""
import csv
import re

import networkx as nx
import yaml

from dependencies import CATEGORIES
from sources import ROOT, load_systems

DATA = ROOT / "data"
OUTPUT = DATA / "features" / "raw_features.csv"
BACK = 0.5  # weight of a back-recommendation, relative to the forward edge (Sora 2015)
DAMPING = 0.85

NAME_FLAGS = {
    "name_contains_manager": r"Manager",
    "name_contains_factory": r"Factory",
    "name_ends_with_util": r"(?:Util|Utils|Helper|Constants)$",
    "name_ends_with_exception": r"(?:Exception|Error)$",
    "name_ends_with_impl": r"Impl$",
    "name_starts_with_abstract_or_base": r"^(?:Abstract|Base)[A-Z]",
}
COLUMNS = (
    ["project", "file_name", "file_path", "package", "class_full_name",
     "declaration_kind", "is_abstract_class"]
    + [f"classes_using_it_via_{c}" for c in CATEGORIES]
    + [f"classes_it_uses_via_{c}" for c in CATEGORIES]
    + ["classes_using_it_total", "classes_it_uses_total",
       "incoming_dependency_weight", "outgoing_dependency_weight"]
    + ["pagerank_backrec_weighted_damping_085"]
    + ["commit_count", "churn_lines", "author_count", "age_days", "days_since_last_change",
       "lines_of_code", "hotspot"]
    + list(NAME_FLAGS) + ["package_depth", "words_in_class_name"]
    + ["is_key_class"]
)


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pagerank(classes, edges):
    """PageRank with back-recommendations, on the weighted graph."""
    graph = nx.DiGraph()
    graph.add_nodes_from(classes)
    for e in edges:
        weight = float(e["weight"])
        for a, b, w in ((e["src"], e["dst"], weight), (e["dst"], e["src"], weight * BACK)):
            graph.add_edge(a, b, weight=graph.get_edge_data(a, b, {}).get("weight", 0) + w)
    return nx.pagerank(graph, alpha=DAMPING, weight="weight", max_iter=1000)


def root_package_depth(packages):
    """Number of package levels all packages of a system share."""
    parts = [p.split(".") for p in packages if p]
    depth = 0
    for level in zip(*parts):
        if len(set(level)) != 1:
            break
        depth += 1
    return depth


def words(name):
    return len(re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", name))


def key_classes(project):
    path = DATA / "ground_truth" / f"{project}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {v for v in data.values() if v}


def system_rows(project):
    classes = read_csv(DATA / "graph" / project / "classes.csv")
    edges = read_csv(DATA / "graph" / project / "edges.csv")
    history = {r["fqn"]: r for r in read_csv(DATA / "history" / f"{project}.csv")}
    size = {r["fqn"]: int(r["loc"]) for r in read_csv(DATA / "size" / f"{project}.csv")}
    names = [c["fqn"] for c in classes]

    using = {c: {k: set() for k in CATEGORIES} for c in names}  # classes that use c, per type
    uses = {c: {k: set() for k in CATEGORIES} for c in names}   # classes c uses, per type
    weight_in = dict.fromkeys(names, 0)
    weight_out = dict.fromkeys(names, 0)
    for e in edges:
        for k in CATEGORIES:
            if int(e[k]):
                using[e["dst"]][k].add(e["src"])
                uses[e["src"]][k].add(e["dst"])
        weight_in[e["dst"]] += int(e["weight"])
        weight_out[e["src"]] += int(e["weight"])

    rank = pagerank(names, edges)

    packages = [c["fqn"].rsplit(".", 1)[0] if "." in c["fqn"] else "" for c in classes]
    root_depth = root_package_depth(packages)
    keys = key_classes(project)

    rows = []
    for c, package in zip(classes, packages):
        fqn = c["fqn"]
        simple = fqn.rsplit(".", 1)[-1]
        h = history[fqn]
        row = {
            "project": project,
            "file_name": c["path"].rsplit("/", 1)[-1],
            "file_path": c["path"],
            "package": package,
            "class_full_name": fqn,
            "declaration_kind": c["kind"],
            "is_abstract_class": c["is_abstract"],
        }
        for k in CATEGORIES:
            row[f"classes_using_it_via_{k}"] = len(using[fqn][k])
            row[f"classes_it_uses_via_{k}"] = len(uses[fqn][k])
        row["classes_using_it_total"] = len(set().union(*using[fqn].values()))
        row["classes_it_uses_total"] = len(set().union(*uses[fqn].values()))
        row["incoming_dependency_weight"] = weight_in[fqn]
        row["outgoing_dependency_weight"] = weight_out[fqn]
        row["pagerank_backrec_weighted_damping_085"] = rank[fqn]
        row["commit_count"] = int(h["commits"])
        row["churn_lines"] = int(h["churn"])
        row["author_count"] = int(h["authors"])
        row["age_days"] = int(h["age_days"])
        row["days_since_last_change"] = int(h["days_since_last_change"])
        row["lines_of_code"] = size[fqn]
        row["hotspot"] = row["commit_count"] * row["lines_of_code"]
        for col, pattern in NAME_FLAGS.items():
            row[col] = int(bool(re.search(pattern, simple)))
        row["package_depth"] = (package.count(".") + 1 if package else 0) - root_depth
        row["words_in_class_name"] = words(simple)
        row["is_key_class"] = "" if keys is None else int(fqn in keys)
        rows.append(row)
    missing = set() if keys is None else keys - set(names)
    return rows, keys, missing


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for project in load_systems():
        rows, keys, missing = system_rows(project)
        all_rows.extend(rows)
        labels = "no ground truth yet" if keys is None else f"key classes={sum(r['is_key_class'] for r in rows)}"
        note = f"  MISSING: {sorted(missing)}" if missing else ""
        print(f"{project:22} classes={len(rows):5}  {labels}{note}", flush=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(all_rows)
    print(f"{len(all_rows)} rows, {len(COLUMNS)} columns -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
