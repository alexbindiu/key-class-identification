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

from heuristics import CUTOFFS, METRICS, hits_in_top
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(FEATURES, encoding="utf-8") as f:
        systems = {}
        for row in csv.DictReader(f):
            systems.setdefault(row["project"], []).append(row)
    labelled = [p for p, rows in systems.items() if rows[0]["is_key_class"] != ""]

    data = {}
    for project in labelled:
        names, x = system_features(systems[project])
        data[project] = (x, np.array([int(r["is_key_class"]) for r in systems[project]]))
    print(f"{len(labelled)} systems, {len(names)} features")

    results, gain = [], dict.fromkeys(names, 0.0)
    for test in labelled:
        train = [p for p in labelled if p != test]
        model = XGBRanker()
        model.fit(np.vstack([data[p][0] for p in train]),
                  np.concatenate([data[p][1] for p in train]),
                  qid=np.concatenate([np.full(len(data[p][1]), i) for i, p in enumerate(train)]))
        for feature, value in model.get_booster().get_score(importance_type="total_gain").items():
            gain[names[int(feature[1:])]] += value / len(labelled)  # "f12" -> 12th feature

        x, y = data[test]
        scores = list(model.predict(x))
        labels = list(y)
        result = {"project": test, "model": "xgboost", "key_classes": sum(labels)}
        for k in CUTOFFS:
            hits = hits_in_top(scores, labels, k)
            result[f"recall_at_{k}"] = round(hits / sum(labels), 4)
            result[f"precision_at_{k}"] = round(hits / k, 4)
        results.append(result)
    mean = {m: round(sum(r[m] for r in results) / len(results), 4) for m in METRICS}
    results.append({"project": "mean", "model": "xgboost", "key_classes": "", **mean})

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

    total = sum(gain.values())
    print("\nmean importance (share of gain), top 10:")
    for name, value in sorted(gain.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {name:45} {value / total:.3f}")
    print(f"\n-> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
