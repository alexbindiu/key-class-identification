"""Maps the key class names from Sora & Chirila (2019) to classes in the code.
Inner classes are mapped to their outer class; names that can't be found are written as null.

Output: data/ground_truth/<system>.yaml
"""
import yaml

from sources import ROOT, classes, load_systems

INPUT = ROOT / "config" / "sora_key_classes.yaml"
OUTPUT = ROOT / "data" / "ground_truth"

# the log4j repo also has the old 1.2 API with the same class names (Logger, Appender...)
PAPER_SCOPE = {"log4j": "org.apache.logging.log4j"}
KIND_ORDER = {"interface": 0, "class": 1, "enum": 1, "annotation": 2}


def pick(candidates, info):
    """If a name matches several classes: shortest package, then interface, class, annotation."""
    return sorted(candidates, key=lambda f: (info[f]["package"].count("."),
                                             KIND_ORDER[info[f]["kind"]], f))[0]


def resolve(name, info):
    """Exact name, then ignoring case, then inner classes. Returns (fqn or None, note)."""
    simple = {f: f.rsplit(".", 1)[-1] for f in info}
    exact = [f for f, s in simple.items() if s == name]
    if exact:
        chosen = pick(exact, info)
        note = f"chosen from {len(exact)} candidates" if len(exact) > 1 else ""
        return chosen, note
    nocase = [f for f, s in simple.items() if s.lower() == name.lower()]
    if nocase:
        return pick(nocase, info), "case-insensitive match"
    parents = [f for f, i in info.items() if name in i["nested"]]
    if parents:
        chosen = pick(parents, info)
        return chosen, f"inner class of {simple[chosen]}"
    return None, "unresolved: not found in the code"


def write_yaml(system, rows):
    lines = [f"# Key classes of {system} (Sora & Chirila 2019, Table A.7), resolved by src/resolve_sora.py"]
    width = max(len(name) for name, _, _ in rows) + 1
    for name, fqn, note in rows:
        value = fqn if fqn else "null"
        comment = f"   # {note}" if note else ""
        lines.append(f"{name + ':':{width + 1}} {value}{comment}")
    (OUTPUT / f"{system}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    systems = load_systems()
    key_names = yaml.safe_load(INPUT.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for system, names in key_names.items():
        info = classes(system, systems[system])
        scope = PAPER_SCOPE.get(system)
        if scope:
            info = {f: i for f, i in info.items() if f.startswith(scope + ".")}
        rows = [(name, *resolve(name, info)) for name in names]
        write_yaml(system, rows)
        unresolved = sum(fqn is None for _, fqn, _ in rows)
        print(f"{system:10} classes={len(info):5}  key={len(rows):3}  unresolved={unresolved}")


if __name__ == "__main__":
    main()
