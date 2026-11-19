"""E5: the XGBoost ranker of E4, trained with one feature group at a time, with all of them, and with
all of them but one ("without_<group>": what that group adds on top of the others).

Groups:
- structure: dependencies per type, totals, dependency weights, PageRank
- history: Git history and lines of code (hotspot uses both)
- names: name flags, package depth, words in the class name
- declaration: abstract, interface, enum, annotation, record

Output: results/feature_groups.csv (one group, all groups)
        results/feature_groups_without_one.csv (all groups but one)
"""
import csv
import sys

from heuristics import METRICS
from ranker import leave_one_system_out, load, mean_row
from sources import ROOT

OUTPUT = ROOT / "results" / "feature_groups.csv"
OUTPUT_WITHOUT_ONE = ROOT / "results" / "feature_groups_without_one.csv"
GROUPS = ["structure", "history", "names", "declaration"]
HISTORY = {"commit_count", "churn_lines", "author_count", "age_days", "days_since_last_change",
           "lines_of_code", "hotspot"}


def group_of(feature):
    if feature.startswith(("classes_", "pagerank_")) or feature.endswith("_dependency_weight"):
        return "structure"
    if feature in HISTORY:
        return "history"
    if feature.startswith("name_") or feature in ("package_depth", "words_in_class_name"):
        return "names"
    if feature == "is_abstract_class" or feature.startswith("declaration_is_"):
        return "declaration"
    raise ValueError(f"feature without a group: {feature}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names, data = load()
    groups = {g: [i for i, n in enumerate(names) if group_of(n) == g] for g in GROUPS}
    groups["all"] = list(range(len(names)))
    for g in GROUPS:
        groups[f"without_{g}"] = [i for i in groups["all"] if i not in groups[g]]
    print(f"{len(data)} systems; features per group: "
          + ", ".join(f"{g} {len(c)}" for g, c in groups.items()))

    results = []
    for group, columns in groups.items():
        own, _ = leave_one_system_out(data, columns)
        results += [{"group": group, **r} for r in own + [mean_row(own)]]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for path, without_one in ((OUTPUT, False), (OUTPUT_WITHOUT_ONE, True)):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["group", "project", "key_classes"] + METRICS)
            w.writeheader()
            w.writerows(r for r in results if r["group"].startswith("without_") == without_one)

    print(f"\n{'mean over systems':22}  R@20  R@30  P@20  P@30")
    for r in results:
        if r["project"] == "mean":
            print(f"{r['group']:22}" + "".join(f"  {r[m]:.2f}" for m in METRICS))

    for metric in ("recall_at_20", "recall_at_30"):
        print(f"\n{metric + ' per system':22}" + "".join(f"{g.replace('without_', '-'):>13}" for g in groups))
        for project in list(data) + ["mean"]:
            print(f"{project:22}" + "".join(
                f"{next(r for r in results if r['group'] == g and r['project'] == project)[metric]:13.2f}"
                for g in groups))
    print(f"\n-> {OUTPUT.relative_to(ROOT)}, {OUTPUT_WITHOUT_ONE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
