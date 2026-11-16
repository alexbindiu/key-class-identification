"""Builds the dependency graph of each system from its Java sources, using tree-sitter.
Every use of another class is counted by type (field, method call, ...), and the edge weight is
the sum of count x weight. One file is one class: inner classes belong to the file's class.

Output: data/graph/<system>/classes.csv and edges.csv
Usage: python src/dependencies.py [system ...]
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import tree_sitter_java
from tree_sitter import Language, Parser

from sources import REPOS, ROOT, load_systems, main_java_files

PARSER = Parser(Language(tree_sitter_java.language()))
OUTPUT = ROOT / "data" / "graph"
# weights from Sora (2015), section 2.2.1; member_access, cast and annotation aren't in the paper
WEIGHTS = {"inheritance": 4, "realization": 4, "field": 3, "parameter": 3, "return_type": 3,
           "method_call": 2, "instantiation": 2, "local_variable": 1, "member_access": 1,
           "cast": 1, "annotation": 1}
CATEGORIES = list(WEIGHTS)
TYPE_DECLS = {"class_declaration": "class", "interface_declaration": "interface",
              "enum_declaration": "enum", "annotation_type_declaration": "annotation",
              "record_declaration": "record"}
SCOPES = {"method_declaration", "constructor_declaration", "lambda_expression",
          "static_initializer", "compact_constructor_declaration"}


def text(node):
    return node.text.decode("utf-8", errors="replace")


def walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def qualified(node):
    """'Outer<T>.Inner' -> 'Outer.Inner'"""
    if node.type in ("identifier", "type_identifier"):
        return text(node)
    parts = [c for c in node.named_children if c.type not in ("annotation", "marker_annotation", "type_arguments")]
    if node.type == "generic_type":
        return qualified(parts[0])
    return ".".join(qualified(p) for p in parts)


def type_names(node):
    """'Map<K, a.B>' -> ['Map', 'K', 'a.B']"""
    if node is None:
        return []
    names, stack = [], [node]
    while stack:
        n = stack.pop()
        if n.type == "scoped_type_identifier":
            names.append(qualified(n))
            stack.extend(a for c in n.named_children if c.type == "generic_type"
                         for a in c.children if a.type == "type_arguments")
            stack.extend(c for c in n.children if c.type == "type_arguments")
        elif n.type == "type_identifier":
            names.append(text(n))
        else:
            stack.extend(n.children)
    return names


def base_type(node):
    """'List<B>' -> 'List'"""
    if node is None:
        return None
    if node.type == "generic_type":
        node = node.named_children[0]
    if node.type in ("type_identifier", "scoped_type_identifier"):
        return type_names(node)[0]
    return None


def declared_variables(scope):
    """Parameters and local variables of a method, with their types."""
    variables = {}
    for n in walk(scope):
        if n.type in ("formal_parameter", "spread_parameter", "catch_formal_parameter", "resource",
                      "local_variable_declaration", "enhanced_for_statement"):
            type_node = n.child_by_field_name("type")
            if n.type == "catch_formal_parameter":
                type_node = next((c for c in n.children if c.type == "catch_type"), None)
            for c in n.children:
                if c.type == "variable_declarator":
                    name = c.child_by_field_name("name")
                    if name is not None:
                        variables[text(name)] = type_node
            name = n.child_by_field_name("name")
            if name is not None and n.type != "local_variable_declaration":
                variables[text(name)] = type_node
    return variables


def parse_file(source, stem):
    """Reads one file: package, imports, its class, and every use of another class."""
    root = PARSER.parse(source).root_node
    package, imports, wildcards, tops, declared = "", [], [], [], set()
    uses = []
    fields = {}

    for n in walk(root):
        if n.type == "package_declaration":
            package = "".join(text(c) for c in n.named_children if c.type in ("scoped_identifier", "identifier"))

        elif n.type == "import_declaration":
            body = "".join(text(c) for c in n.children if c.type in ("scoped_identifier", "identifier", "asterisk", "."))
            (wildcards if body.endswith(".*") else imports).append(body.removesuffix(".*"))
        elif n.type in TYPE_DECLS:
            name = n.child_by_field_name("name")
            if name is None:
                continue
            declared.add(text(name))
            if n.parent is not None and n.parent.type == "program":
                modifiers = next((c for c in n.children if c.type == "modifiers"), None)
                abstract = modifiers is not None and "abstract" in text(modifiers).split()
                tops.append((text(name), TYPE_DECLS[n.type], abstract))
        elif n.type in ("field_declaration", "constant_declaration"):
            type_node = n.child_by_field_name("type")
            for c in n.children:
                if c.type == "variable_declarator" and c.child_by_field_name("name") is not None:
                    fields[text(c.child_by_field_name("name"))] = type_node
    scope_vars = {}

    def variable_type(identifier):
        """Type of a variable: looks in the method first, then in the fields."""
        scope = identifier.parent
        while scope is not None and scope.type not in SCOPES:
            scope = scope.parent
        while scope is not None:
            if scope.id not in scope_vars:
                scope_vars[scope.id] = declared_variables(scope)
            found = scope_vars[scope.id].get(text(identifier))
            if found is not None:
                return base_type(found)
            scope = scope.parent
            while scope is not None and scope.type not in SCOPES:
                scope = scope.parent
        found = fields.get(text(identifier))
        return base_type(found) if found is not None else None

    def receiver_class(obj):
        """In obj.method() or obj.field, which class is obj?"""
        if obj is None:
            return None
        if obj.type == "identifier":
            declared_type = variable_type(obj)
            if declared_type:
                return declared_type
            return text(obj) if text(obj)[:1].isupper() else None
        if obj.type == "field_access":  # this.b.m() -> type of field b
            inner = obj.child_by_field_name("object")
            name = obj.child_by_field_name("field")
            if inner is not None and inner.type == "this" and name is not None:
                found = fields.get(text(name))
                return base_type(found) if found is not None else None
            if inner is not None and inner.type in ("identifier", "field_access") and text(obj)[:1].islower():
                # a.b.C.m()
                return text(obj) if text(obj).split(".")[-1][:1].isupper() else None
        if obj.type == "scoped_identifier":
            return text(obj)
        return None

    def add(category, names):
        uses.extend((category, name) for name in names)

    for n in walk(root):
        kind = n.type
        if kind in ("class_declaration", "enum_declaration", "record_declaration"):
            superclass = n.child_by_field_name("superclass")
            add("inheritance", type_names(superclass))
            interfaces = n.child_by_field_name("interfaces")
            add("realization", type_names(interfaces))
        elif kind == "interface_declaration":
            extends = next((c for c in n.children if c.type == "extends_interfaces"), None)
            add("inheritance", type_names(extends))
        elif kind in ("field_declaration", "constant_declaration"):
            add("field", type_names(n.child_by_field_name("type")))
        elif kind in ("method_declaration", "constructor_declaration"):
            if kind == "method_declaration":
                add("return_type", type_names(n.child_by_field_name("type")))
            throws = next((c for c in n.children if c.type == "throws"), None)
            add("parameter", type_names(throws))
        elif kind in ("formal_parameter", "spread_parameter"):
            if n.parent is not None and n.parent.type == "formal_parameters":
                type_node = n.child_by_field_name("type") or next(  # spread_parameter has no "type" field
                    (c for c in n.named_children if c.type not in ("modifiers", "variable_declarator")), None)
                owner = n.parent.parent
                if owner is not None and owner.type in ("method_declaration", "constructor_declaration"):
                    add("parameter", type_names(type_node))
                else:  # typed lambda parameter
                    add("local_variable", type_names(type_node))
        elif kind == "catch_formal_parameter":
            add("parameter", type_names(next((c for c in n.children if c.type == "catch_type"), None)))
        elif kind in ("local_variable_declaration", "enhanced_for_statement", "resource"):
            add("local_variable", type_names(n.child_by_field_name("type")))
        elif kind == "object_creation_expression":
            add("instantiation", type_names(n.child_by_field_name("type")))
        elif kind == "cast_expression":
            add("cast", type_names(n.child_by_field_name("type")))
        elif kind == "instanceof_expression":
            add("cast", type_names(n.child_by_field_name("right")))
        elif kind == "class_literal":
            add("cast", type_names(n))
        elif kind in ("marker_annotation", "annotation"):
            name = n.child_by_field_name("name")
            if name is not None:
                add("annotation", [text(name)])
        elif kind == "method_invocation":
            owner = receiver_class(n.child_by_field_name("object"))
            if owner:
                add("method_call", [owner])
        elif kind == "method_reference":
            first = n.named_children[0] if n.named_children else None
            if first is not None:
                owner = receiver_class(first) if first.type == "identifier" else (type_names(first) or [None])[0]
                if owner:
                    add("method_call", [owner])
        elif kind == "field_access":
            if n.parent is not None and n.parent.type == "method_invocation" and \
                    n.parent.child_by_field_name("object") == n and text(n).split(".")[-1][:1].isupper():
                continue  # a.b.C.m(): already counted as a method call
            owner = receiver_class(n.child_by_field_name("object"))
            if owner:
                add("member_access", [owner])
    top = next((t for t in tops if t[0] == stem), tops[0] if tops else None)
    others = [t[0] for t in tops if t is not top]
    return package, imports, wildcards, top, others, declared, uses


def top_level_of(name, classes):
    """'a.b.Outer.Inner' -> 'a.b.Outer', if it's a class of the system."""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in classes:
            return classes[candidate]["fqn"]
    return None


def resolve(name, f, classes, by_package):
    """Which class of the system a name refers to (None for JDK and libraries)."""
    if "." in name:
        hit = top_level_of(name, classes)
        if hit:
            return hit
        name = name.split(".")[0]  # Outer.Inner without package
    if name in f["declared"]:
        return f["self"]
    for imp in f["imports"]:
        if imp.rsplit(".", 1)[-1] == name:
            return top_level_of(imp, classes)
    same = by_package.get(f["package"], {}).get(name)
    if same:
        return same
    for w in f["wildcards"]:
        hit = by_package.get(w, {}).get(name)
        if hit:
            return hit
        outer = top_level_of(w, classes)  # import a.b.Outer.*
        if outer and name in classes[outer]["declared"]:
            return outer
    return None


def extract(name, system):
    prefix = system.get("package_prefix")
    classes, files, duplicates = {}, {}, 0

    extra = {}  # other classes in the same file -> the file's class
    for rel in main_java_files(name, system):
        package, imports, wildcards, top, others, declared, uses = parse_file(
            (REPOS / name / rel).read_bytes(), Path(rel).stem)
        if top is None:  # package-info.java, module-info.java
            continue
        if prefix and not (package == prefix or package.startswith(prefix + ".")):
            continue
        fqn = f"{package}.{top[0]}" if package else top[0]
        if fqn in classes:
            duplicates += 1
            continue
        classes[fqn] = {"fqn": fqn, "kind": top[1], "is_abstract": top[2], "path": rel, "declared": declared}
        files[fqn] = {"self": fqn, "package": package, "imports": imports, "wildcards": wildcards,
                      "declared": declared, "uses": uses}
        for other in others:
            extra[f"{package}.{other}" if package else other] = classes[fqn]
    lookup = {**{k: v for k, v in extra.items() if k not in classes}, **classes}
    by_package = defaultdict(dict)
    for key, c in lookup.items():
        package, simple = key.rsplit(".", 1) if "." in key else ("", key)
        by_package[package][simple] = c["fqn"]
    counts = defaultdict(Counter)
    for src, f in files.items():
        for category, used in f["uses"]:
            dst = resolve(used, f, lookup, by_package)
            if dst and dst != src:
                counts[src, dst][category] += 1
    return classes, counts, duplicates


def main():
    systems = load_systems()
    for name in sys.argv[1:] or list(systems):
        classes, counts, duplicates = extract(name, systems[name])
        out = OUTPUT / name
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "classes.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fqn", "kind", "is_abstract", "path"])
            for fqn, c in sorted(classes.items()):
                w.writerow([fqn, c["kind"], int(c["is_abstract"]), c["path"]])
        with open(out / "edges.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["src", "dst", *CATEGORIES, "weight"])
            for (src, dst), c in sorted(counts.items()):
                weight = sum(c[k] * WEIGHTS[k] for k in CATEGORIES)
                w.writerow([src, dst, *(c[k] for k in CATEGORIES), weight])
        print(f"{name:22} classes={len(classes):5}  edges={len(counts):6}  duplicates={duplicates}", flush=True)


if __name__ == "__main__":
    main()
