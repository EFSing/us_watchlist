import ast
import subprocess
import unittest
from graphlib import TopologicalSorter
from importlib.util import resolve_name
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "us_watchlist"
SOURCE = ROOT / "src" / PACKAGE
LEAF_LAYERS = {"universe", "market_data", "strategies", "research", "tracking", "reporting"}
LAYERS = {
    "domain": set(),
    **{layer: {"domain"} for layer in LEAF_LAYERS | {"integrations"}},
    "app": LEAF_LAYERS | {"domain", "integrations"},
}
PURE_IMPORTS = {
    "__future__", "abc", "collections", "dataclasses", "datetime", "decimal",
    "enum", "functools", "hashlib", "html", "itertools", "math", "operator",
    "re", "statistics", "typing",
}
INDIRECT_CALLS = {"__import__", "compile", "eval", "exec"}
PATH_IO = {"open", "read_bytes", "read_text", "write_bytes", "write_text", "mkdir", "unlink"}


def imports_in(tree, module, is_package):
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (item.name for item in node.names)
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            for item in node.names:
                if item.name == "*":
                    raise AssertionError(f"{module}: use explicit imports")
                yield f"{base}.{item.name}"


class ArchitectureTests(unittest.TestCase):
    def test_layer_imports_are_directional_acyclic_and_pure(self):
        modules = {}
        for path in SOURCE.rglob("*.py"):
            parts = path.relative_to(SOURCE).with_suffix("").parts
            is_package = parts[-1] == "__init__"
            name = ".".join((PACKAGE, *(parts[:-1] if is_package else parts)))
            modules[name] = (path, is_package)

        graph = TopologicalSorter()
        for name, (path, is_package) in modules.items():
            graph.add(name)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            parts = name.split(".")
            if len(parts) > 1:
                self.assertIn(parts[1], LAYERS, name)
            if is_package:
                self.assertLessEqual(len(tree.body), 1, f"{name}: package markers are docstring-only")
                if tree.body:
                    self.assertIsNotNone(ast.get_docstring(tree), name)
                continue
            self.assertGreaterEqual(len(parts), 3, f"{name}: use a layer directory")
            layer = parts[1]
            pure = layer in LEAF_LAYERS or layer == "domain"
            allowed_external = PURE_IMPORTS | {"argparse", "pathlib"} if layer == "app" else PURE_IMPORTS
            for target in imports_in(tree, name, is_package):
                root, _, remainder = target.partition(".")
                self.assertNotIn(root, {"importlib", "builtins"}, f"{name} -> {target}")
                if root != PACKAGE:
                    if layer != "integrations":
                        self.assertIn(root, allowed_external, f"{name} -> {target}")
                    continue
                target_layer = remainder.split(".")[0]
                self.assertIn(target_layer, LAYERS[layer] | {layer}, f"{name} -> {target}")
                parts = target.split(".")
                for index in range(2, len(parts) + 1):
                    dependency = ".".join(parts[:index])
                    if dependency in modules and not name.startswith(f"{dependency}."):
                        graph.add(name, dependency)
            forbidden_calls = INDIRECT_CALLS | ({"open", "print", "input"} if pure else set())
            if layer == "app":
                forbidden_calls = forbidden_calls | {"open", "input"}
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    self.assertNotIn(node.id, forbidden_calls, name)
                if layer == "app" and isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, PATH_IO, f"{name}: use an integration for I/O")
        tuple(graph.static_order())

    def test_runtime_and_secrets_are_ignored_and_untracked(self):
        git = ["git", "-C", str(ROOT)]
        tracked_ignored = subprocess.check_output(
            [*git, "ls-files", "-z", "--cached", "--ignored", "--exclude-standard"]
        )
        self.assertEqual(tracked_ignored, b"")
        tracked_files = subprocess.check_output([*git, "ls-files", "-z"]).split(b"\x00")
        runtime_dirs = {"data", "runtime", "artifacts", "logs", "cache", "outputs", "research_data"}
        for tracked in filter(None, tracked_files):
            path = PurePosixPath(tracked.decode())
            self.assertNotIn(path.parts[0].lower(), runtime_dirs, str(path))
            self.assertNotIn(path.suffix.lower(), {".sqlite", ".sqlite3", ".parquet", ".html"}, str(path))
        candidates = b".runtime/artifacts/smoke/example.html\x00.venv/python\x00.env.local\x00"
        ignored = subprocess.check_output(
            [*git, "check-ignore", "--no-index", "--stdin", "-z"], input=candidates
        )
        self.assertEqual(ignored, candidates)
