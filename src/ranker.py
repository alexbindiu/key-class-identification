"""E4: XGBoost ranker with leave-one-system-out. The model is trained on all systems but one and
tested on the one left out, for every system with ground truth. Default parameters, no tuning.

Features: all columns of the feature table except the identification columns and the label.
The declaration kind becomes four 0/1 columns (a plain class has all four 0). Counts, PageRank,
history, size, package depth and name length become percentiles inside their own system;
0/1 flags stay as they are.

Output: results/ranker.csv
"""
import csv
import sys

import numpy as np
from scipy.stats import rankdata
from xgboost import XGBRanker

from heuristics import METRICS, metrics
from sources import ROOT

FEATURES = ROOT / "data" / "features" / "raw_features.csv"
HEURISTICS = ROOT / "results" / "heuristics.csv"
OUTPUT = ROOT / "results" / "ranker.csv"
NOT_FEATURES = {"project", "file_name", "file_path", "package", "class_full_name",
                "declaration_kind", "is_key_class"}
KINDS = ["interface", "enum", "annotation", "record"]


def is_flag(column):
    return column == "is_abstract_class" or column.startswith("name_")


def system_features(rows):
    """Feature names and matrix of one system."""
    names, columns = [], []
    for kind in KINDS:
        names.append(f"declaration_is_{kind}")
        columns.append([float(r["declaration_kind"] == kind) for r in rows])
    for column in rows[0]:
        if column in NOT_FEATURES:
            continue
        values = np.array([float(r[column]) for r in rows])
        names.append(column)
        # percentile = rank / number of classes; tied classes share the average rank
        columns.append(values if is_flag(column) else rankdata(values) / len(values))
    return names, np.column_stack(columns)


def load():
    """Feature names, and {project: (features, labels)} for every system with ground truth."""
    with open(FEATURES, encoding="utf-8") as f:
        systems = {}
        for row in csv.DictReader(f):
            systems.setdefault(row["project"], []).append(row)
    data = {}
    for project, rows in systems.items():
        if rows[0]["is_key_class"] == "":
            continue
        names, x = system_features(rows)
        data[project] = (x, np.array([int(r["is_key_class"]) for r in rows]))
    return names, data


def leave_one_system_out(data, columns):
    """Trains on all systems but one and scores the one left out, for every system.
    columns: indices of the features to use.
    Returns the results per system and the mean gain of each used feature."""
    results, gain = [], np.zeros(len(columns))
    for test in data:
        train = [p for p in data if p != test]
        model = XGBRanker()
        model.fit(np.vstack([data[p][0][:, columns] for p in train]),
                  np.concatenate([data[p][1] for p in train]),
                  qid=np.concatenate([np.full(len(data[p][1]), i) for i, p in enumerate(train)]))
        for feature, value in model.get_booster().get_score(importance_type="total_gain").items():
            gain[int(feature[1:])] += value / len(data)  # "f12" -> 12th used column
        x, y = data[test]
        labels = list(y)
        results.append({"project": test, "key_classes": sum(labels),
                        **metrics(list(model.predict(x[:, columns])), labels)})
    return results, gain


def mean_row(results):
    return {"project": "mean", "key_classes": "",
            **{m: round(sum(r[m] for r in results) / len(results), 4) for m in METRICS}}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names, data = load()
    print(f"{len(data)} systems, {len(names)} features")
    results, gain = leave_one_system_out(data, list(range(len(names))))
    results = [{"model": "xgboost", **r} for r in results + [mean_row(results)]]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["project", "model", "key_classes"] + METRICS)
        w.writeheader()
        w.writerows(results)

    pagerank = {}
    if HEURISTICS.exists():
        with open(HEURISTICS, encoding="utf-8") as f:
            pagerank = {r["project"]: r for r in csv.DictReader(f) if r["heuristic"] == "pagerank"}
    print(f"\n{'project':22} {'XGBoost R@20 R@30 P@20 P@30':>28}   {'PageRank R@20 R@30 P@20 P@30':>29}")
    for r in results:
        line = f"{r['project']:22} {'':8}" + "".join(f" {r[m]:.2f}" for m in METRICS)
        if r["project"] in pagerank:
            line += f"   {'':9}" + "".join(f" {float(pagerank[r['project']][m]):.2f}" for m in METRICS)
        print(line)

    print("\nmean importance (share of gain), top 10:")
    for i in np.argsort(-gain)[:10]:
        print(f"  {names[i]:45} {gain[i] / gain.sum():.3f}")
    print(f"\n-> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
