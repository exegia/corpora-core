"""Offline tests for integration configuration and dependency failure behavior."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("configure", ROOT / "configure.py")
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)


class ConfigurationTests(unittest.TestCase):
    def test_local_spaces_are_single_argument(self):
        with tempfile.TemporaryDirectory(prefix="TF space ") as name:
            root = Path(name)
            for feature in ("otype", "oslots"):
                (root / f"{feature}.tf").touch()
            args = argparse.Namespace(mode="local", corpus=name, command=sys.executable,
                                      features="word lemma")
            server = configure.configuration(args)["mcpServers"]["text-fabric-expert"]
            self.assertEqual(server["args"], ["--corpus", f"dataset={root.resolve()}",
                                               "--features", "word lemma"])
            self.assertNotIn("shell", server)

    def test_invalid_corpus_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError, "otype.tf"):
                configure.configuration(argparse.Namespace(mode="local", corpus=name))

    def test_agora_root_checked_and_absolute(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = argparse.Namespace(mode="agora", plugin_root=name, command=sys.executable)
            with self.assertRaisesRegex(ValueError, "pyproject.toml"):
                configure.configuration(args)
            for filename in ("pyproject.toml", "uv.lock", "src/agora_context_fabric/server.py"):
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            server = configure.configuration(args)["mcpServers"]["text-fabric-expert"]
            self.assertEqual(server["cwd"], str(root.resolve()))
            self.assertEqual(server["args"][-1], str(root.resolve()))

    def test_missing_executable(self):
        with patch.object(configure.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "Executable not found"):
                configure.executable("cfabric-mcp")

    def test_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "config.json"
            output.write_text("keep")
            with patch.object(configure, "configuration", return_value={"mcpServers": {}}):
                self.assertEqual(configure.main(["local", "--corpus", name,
                                                 "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "keep")

    def test_source_inventory_complete_and_pinned(self):
        sources = json.loads((ROOT / "knowledge/sources.json").read_text())["sources"]
        self.assertEqual(len(sources), 17)
        self.assertEqual(len({x["repository"] for x in sources}), 17)
        for source in sources:
            self.assertRegex(source["revision"], r"^[a-f0-9]{40}$")
            self.assertIn(source["revision"], source["url"])


if __name__ == "__main__":
    unittest.main()
