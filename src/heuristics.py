"""E1 and E3: ranks the classes of each system by one heuristic at a time and counts how many key
classes are in the top 20 and top 30.

E1: PageRank (back-recommendations, weighted, d = 0.85), fan-in (distinct classes that use the class)
and hotspot (commits x lines of code).
E3: combined score = mean of the percentiles of PageRank and hotspot inside the system.
Added after the first E3 results: Reciprocal Rank Fusion of PageRank and hotspot,
1 / (60 + position) summed over the two rankings (k = 60 from Cormack et al., 2009; not tuned).
Systems without ground truth yet are skipped.

Output: results/heuristics.csv
"""
import csv
import sys

from scipy.stats import rankdata

from sources import ROOT

FEATURES = ROOT / "data" / "features" / "raw_features.csv"
OUTPUT = ROOT / "results" / "heuristics.csv"
CUTOFFS = (20, 30)
COLUMNS = {
    "pagerank": "pagerank_backrec_weighted_damping_085",
    "fan_in": "classes_using_it_total",
    "hotspot": "hotspot",
}
HEURISTICS = list(COLUMNS) + ["combined", "combined_rrf"]
METRICS = [f"{m}_at_{k}" for m in ("recall", "precision") for k in CUTOFFS]
RRF_K = 60


def heuristic_scores(rows):
    scores = {name: [float(r[column]) for r in rows] for name, column in COLUMNS.items()}
    # percentile = rank / number of classes (tied classes share the average rank);
    # the mean of two percentiles is (rank1 + rank2) / (2 x number of classes)
    ranks = rankdata(scores["pagerank"]) + rankdata(scores["hotspot"])
    scores["combined"] = list(ranks / (2 * len(rows)))
    # position 1 = highest score; tied classes share the average position
    positions = [len(rows) + 1 - rankdata(scores[name]) for name in ("pagerank", "hotspot")]
    scores["combined_rrf"] = list(sum(1 / (RRF_K + p) for p in positions))
    return scores


def hits_in_top(scores, labels, k):
    """Number of key classes in the top k.
    Classes tied with the one at position k are in random order, so the free places left
    are shared among them: the result is the expected number of hits."""
    if k >= len(scores):
        return sum(labels)
    threshold = sorted(scores, reverse=True)[k - 1]
    above = [label for s, label in zip(scores, labels) if s > threshold]
    tied = [label for s, label in zip(scores, labels) if s == threshold]
    return sum(above) + (k - len(above)) * sum(tied) / len(tied)


def evaluate(rows):
    labels = [int(r["is_key_class"]) for r in rows]
    results = []
    for name, scores in heuristic_scores(rows).items():
        result = {"heuristic": name, "key_classes": sum(labels)}
        for k in CUTOFFS:
            hits = hits_in_top(scores, labels, k)
            result[f"recall_at_{k}"] = round(hits / sum(labels), 4)
            result[f"precision_at_{k}"] = round(hits / k, 4)
        results.append(result)
    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(FEATURES, encoding="utf-8") as f:
        systems = {}
        for row in csv.DictReader(f):
            systems.setdefault(row["project"], []).append(row)

    results = []
    for project, rows in systems.items():
        if rows[0]["is_key_class"] == "":
            print(f"{project:22} skipped: no ground truth yet")
            continue
        results += [{"project": project, **r} for r in evaluate(rows)]

    evaluated = sorted({r["project"] for r in results}, key=list(systems).index)
    for name in HEURISTICS:
        own = [r for r in results if r["heuristic"] == name]
        mean = {m: round(sum(r[m] for r in own) / len(own), 4) for m in METRICS}
        results.append({"project": "mean", "heuristic": name, "key_classes": "", **mean})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["project", "heuristic", "key_classes"] + METRICS)
        w.writeheader()
        w.writerows(results)

    print(f"\n{'project':22} {'heuristic':12}  R@20  R@30  P@20  P@30")
    for r in results:
        print(f"{r['project']:22} {r['heuristic']:12}" + "".join(f"  {r[m]:.2f}" for m in METRICS))
    print(f"\n{len(evaluated)} systems -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
