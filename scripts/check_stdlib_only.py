#!/usr/bin/env python3
"""Fail if any script in this bundle imports something outside the standard library.

The bundle promises "Python 3.8+, standard library only". A reader with no
network cannot install a dependency, so a stray third-party import is not a
style question -- it is a bundle that does not run. This is the single
implementation of that promise: `.github/workflows/selfcheck.yml` runs it on
every supported interpreter and `scripts/selfcheck.py` runs it locally, so the
promise is enforced by the same code in both places instead of by two copies
that can drift.

    python3 scripts/check_stdlib_only.py

Exits non-zero and prints `file:line imports 'name'` for each violation.

Standard library only. Python 3.8+.
"""

import ast
import os
import sys
import sysconfig

HERE = os.path.dirname(os.path.abspath(__file__))


def top_level_names(directory):
    """Importable top-level names directly inside `directory`, without descending.

    Not descending is the whole point: `site-packages` lives inside the stdlib
    directory on several layouts, and walking into it would whitelist exactly
    the third-party packages this script exists to catch.
    """
    names = set()
    try:
        entries = os.listdir(directory)
    except OSError:
        return names
    for entry in entries:
        if entry.endswith(".py"):
            names.add(entry[:-3])
        elif entry.endswith((".so", ".pyd", ".dylib")):
            # math.cpython-39-darwin.so -> math
            names.add(entry.split(".", 1)[0])
        elif entry.isidentifier():
            names.add(entry)
    return names


def stdlib_names():
    """Every top-level module name the running interpreter ships itself.

    `sys.stdlib_module_names` only exists from 3.10, and this bundle supports
    3.8. Falling back to an empty set there would classify `import os` as a
    third-party dependency and fail every run on 3.8 and 3.9 -- a guard that is
    wrong on the oldest supported interpreter is worse than no guard.

    The directory enumeration is therefore always unioned in, not used only as a
    fallback, and it must cover `lib-dynload`: on a 3.9 framework build `math`,
    `hashlib` and `unicodedata` are extension modules under
    `<stdlib>/lib-dynload/`, not top-level entries, so enumerating only the
    stdlib directory still reported them as third-party. CI covers both paths --
    3.8/3.9 jobs exercise the enumeration, 3.10+ jobs exercise the attribute.
    """
    names = set(getattr(sys, "stdlib_module_names", None) or ())
    names.update(sys.builtin_module_names)
    names.add("__future__")
    paths = sysconfig.get_paths()
    directories = {paths.get("stdlib", ""), paths.get("platstdlib", ""),
                   os.path.dirname(os.__file__)}
    for directory in list(directories):
        if directory:
            directories.add(os.path.join(directory, "lib-dynload"))
    for directory in directories:
        if directory:
            names.update(top_level_names(directory))
    return {name for name in names if name.isidentifier()}


def local_module_names():
    """Sibling scripts, which are intra-bundle imports rather than dependencies."""
    try:
        entries = os.listdir(HERE)
    except OSError:
        return set()
    return {entry[:-3] for entry in entries if entry.endswith(".py")}


def scan(paths, allowed):
    """Return `file:line imports 'name'` for every root module outside `allowed`."""
    violations = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            # A file this interpreter cannot parse has no dependency list to
            # inspect, so the guard must say that rather than raise a traceback
            # that reads like a bug in the guard itself.
            violations.append("%s:%s cannot be parsed (%s)"
                              % (os.path.basename(path), exc.lineno, exc.msg))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # a relative import is intra-bundle by construction
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                if root and root not in allowed:
                    violations.append("%s:%d imports %r"
                                      % (os.path.basename(path), node.lineno, root))
    return violations


def main():
    # Including this file: a guard that skips itself is the "checks nothing and
    # reports green" failure this bundle keeps running into.
    paths = sorted(os.path.join(HERE, name) for name in os.listdir(HERE)
                   if name.endswith(".py"))
    allowed = stdlib_names() | local_module_names()
    violations = scan(paths, allowed)
    if violations:
        print("scripts import modules outside the standard library:")
        for item in violations:
            print("  " + item)
        return 1
    print("%d script(s) import nothing outside the standard library" % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
