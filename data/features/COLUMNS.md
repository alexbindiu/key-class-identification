# Columns of `raw_features.csv`

One row per class, for all 16 systems. All values are raw (not normalised).
"Class" always means a whole `.java` file: inner classes and other classes declared in the same file
are counted as part of it.

## Identification

| Column | Meaning |
|---|---|
| `project` | Name of the system, as in `config/systems.yaml` (e.g. `ant`). |
| `file_name` | Name of the Java file (e.g. `Task.java`). |
| `file_path` | Path of the file inside the repository (e.g. `src/main/org/apache/tools/ant/Task.java`). |
| `package` | Java package of the class (e.g. `org.apache.tools.ant`). |
| `class_full_name` | Package + class name (e.g. `org.apache.tools.ant.Task`). |

## Declaration

| Column | Meaning |
|---|---|
| `declaration_kind` | `class`, `interface`, `enum`, `annotation` or `record`. |
| `is_abstract_class` | 1 if the class is declared `abstract`, else 0 (interfaces are 0). |

## Dependencies by type

Dependency types, as in Șora (2015), plus `annotation`:

| Type | Class A depends on class B when... |
|---|---|
| `inheritance` | A extends B |
| `realization` | A implements B |
| `field` | A has a field of type B |
| `parameter` | a method of A has a parameter of type B, throws B or catches B |
| `return_type` | a method of A returns B |
| `method_call` | A calls a method of B (also `B::method`) |
| `instantiation` | A creates an object of B (`new B(...)`) |
| `local_variable` | A declares a local variable of type B |
| `member_access` | A reads or writes a field of B |
| `cast` | A casts to B, checks `instanceof B` or uses `B.class` |
| `annotation` | A uses the annotation `@B` |

Types inside generics count in the same type (a field `List<B>` is a field of type B).
Only classes of the same system are counted; JDK and library classes are ignored.

For each of the 11 types above there are two columns (22 in total):

| Column | Meaning |
|---|---|
| `classes_using_it_via_<type>` | Number of **distinct** classes that depend on this class through that type. Example: `classes_using_it_via_inheritance` = number of classes that extend it. |
| `classes_it_uses_via_<type>` | Number of **distinct** classes this class depends on through that type. |

## Dependencies in total

| Column | Meaning |
|---|---|
| `classes_using_it_total` | Number of distinct classes that depend on this class, through any type. |
| `classes_it_uses_total` | Number of distinct classes this class depends on, through any type. |
| `incoming_dependency_weight` | Sum of the weights of all dependencies towards this class. |
| `outgoing_dependency_weight` | Sum of the weights of all dependencies of this class towards others. |

Weight of a dependency from A to B = sum over types of (number of occurrences × weight of the type).
Every occurrence counts (two fields of type B count twice). Weights, from Șora (2015), section 2.2.1:
inheritance 4, realization 4, field 3, parameter 3, return type 3, method call 2, instantiation 2,
local variable 1. Not in the paper, chosen by us: member access 1, cast 1, annotation 1.

## PageRank

PageRank on the dependency graph. "Back-recommendations" (Șora 2015): besides the edge A → B, the graph
also has an edge B → A with half the weight (F = 1/2), so a class that uses many important classes also
gets some importance. The damping factor d is the probability of following an edge; with probability
1 − d the walk jumps to a random class.

| Column | Meaning |
|---|---|
| `pagerank_backrec_weighted_damping_085` | PageRank with back-recommendations (F = 1/2), edges weighted by dependency type, d = 0.85. Sums to 1 over the classes of a system. |

## Git history

Only commits up to the chosen commit of the system (`config/systems.yaml`). Renamed or moved files
keep their history from before the rename. Merge commits are not counted.

| Column | Meaning |
|---|---|
| `commit_count` | Number of commits that changed the file. |
| `churn_lines` | Total lines added + lines deleted in the file, over all those commits. |
| `author_count` | Number of distinct authors (by email) who changed the file. |
| `age_days` | Days from the first commit of the file to the chosen commit. |
| `days_since_last_change` | Days from the last change of the file to the chosen commit. |

## Size

| Column | Meaning |
|---|---|
| `lines_of_code` | Lines with code in the file: blank lines and comments are not counted. |
| `hotspot` | `commit_count × lines_of_code`. |

## Class name

| Column | Meaning |
|---|---|
| `name_contains_manager` | 1 if the class name contains `Manager`. |
| `name_contains_factory` | 1 if the class name contains `Factory`. |
| `name_ends_with_util` | 1 if the class name ends with `Util`, `Utils`, `Helper` or `Constants`. |
| `name_ends_with_exception` | 1 if the class name ends with `Exception` or `Error`. |
| `name_ends_with_impl` | 1 if the class name ends with `Impl`. |
| `name_starts_with_abstract_or_base` | 1 if the class name starts with `Abstract` or `Base` followed by a capital letter. |
| `package_depth` | Number of package levels below the system's root package (the part all its packages share). Example for Tomcat (root `org.apache.catalina`): `org.apache.catalina` → 0, `org.apache.catalina.core` → 1. For Ant the root is `org.apache.tools`, because it also has `org.apache.tools.zip`, `bzip2`, `tar` and `mail`. |
| `words_in_class_name` | Number of words in the class name, split by capital letters (`RuntimeConfigurable` → 2, `XMLParser` → 2). |

## Label

| Column | Meaning |
|---|---|
| `is_key_class` | 1 if the class is a key class in `data/ground_truth/<project>.yaml`, else 0. Empty for the 9 new systems until their ground truth is written. |
