# Annotation rules (new systems)

Read the developer document and list its key classes.

## A class is key if
The document names it and explains its role in the structure or main flow of the system.

Examples: "X is the main entry point", "Important classes: X, Y", "X manages the Y instances".

## A class is not key if
- it only appears in a code example;
- it is only mentioned in passing;
- the word is only an ordinary word, a product name or a heading;
- it is one item of a list of all the variants of something (e.g. every endpoint and its class);
- it belongs to the JDK or a third-party library, or it is a test class.

Packages and modules are not classes.

## Mapping names to classes
- Use the code at the system's snapshot commit, inside its `source` folders and outside `exclude`
  (`config/systems.yaml`).
- Inner class: map it to its top-level class, with `# inner class of X`.
- Same simple name several times: take the one the document refers to (link or path). If the document
  does not say: shortest package, then interface, then class/enum, then annotation, then by name.
- Key class that does not exist in the code: `Name: null   # unresolved: reason`.

## Format
One YAML file per system, one line per key class:

    Foo: com.example.core.Foo
    Inner: com.example.core.Outer   # inner class of Outer
    Bar: null   # unresolved: not in the code
