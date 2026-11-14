"""Offline tests for integration configuration and dependency failure behavior."""

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
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
            args = argparse.Namespace(
                mode="local", corpus=name, command=sys.executable, features="word lemma"
            )
            server = configure.configuration(args)["mcpServers"]["text-fabric-expert"]
            self.assertEqual(
                server["args"],
                ["--corpus", f"dataset={root.resolve()}", "--features", "word lemma"],
            )
            self.assertNotIn("shell", server)

    def test_invalid_corpus_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError, "otype.tf"):
                configure.configuration(argparse.Namespace(mode="local", corpus=name))

    def test_agora_root_checked_and_absolute(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = argparse.Namespace(
                mode="agora", plugin_root=name, command=sys.executable
            )
            with self.assertRaisesRegex(ValueError, "pyproject.toml"):
                configure.configuration(args)
            for filename in (
                "pyproject.toml",
                "uv.lock",
                "src/agora_context_fabric/server.py",
            ):
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
            with patch.object(
                configure, "configuration", return_value={"mcpServers": {}}
            ):
                self.assertEqual(
                    configure.main(
                        ["local", "--corpus", name, "--output", str(output)]
                    ),
                    2,
                )
            self.assertEqual(output.read_text(), "keep")

    def test_converter_inventory_missing_files_is_not_readiness(self):
        with tempfile.TemporaryDirectory(prefix="converter space ") as name:
            inventory = configure.local_converters(name)
            self.assertEqual(inventory["repo_root"], str(Path(name).resolve()))
            self.assertEqual(
                set(inventory["packages"]),
                {"tei-to-tf", "epub-to-tf", "pdf-to-tf", "tf-ai-resolver"},
            )
            for package in inventory["packages"].values():
                for item in package.values():
                    self.assertFalse(item["present"])
                    self.assertTrue(Path(item["path"]).is_absolute())
            for profiles in inventory["binaries"].values():
                for item in profiles.values():
                    self.assertFalse(item["present"])
                    self.assertFalse(item["executable"])
            self.assertFalse(inventory["quality_ai"]["compiled_bridge"]["present"])
            self.assertEqual(list(Path(name).iterdir()), [])

    def test_converter_inventory_reports_artifacts_without_running_them(self):
        with tempfile.TemporaryDirectory(prefix="converter space ") as name:
            root = Path(name)
            paths = (
                "packages/epub-to-tf/src/epub_to_tf/__init__.py",
                "packages/quality-ai/dist/bridge.js",
                "target/debug/corpora-epub-check",
            )
            for filename in paths:
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("not runnable: inventory must never execute this")
                path.chmod(0o600)
            binary = root / paths[-1]
            first = configure.local_converters(root)
            self.assertTrue(first["packages"]["epub-to-tf"]["entrypoint"]["present"])
            self.assertFalse(first["packages"]["epub-to-tf"]["manifest"]["present"])
            self.assertTrue(first["quality_ai"]["compiled_bridge"]["present"])
            self.assertFalse(
                first["binaries"]["corpora-epub-check"]["debug"]["executable"]
            )
            binary.chmod(0o700)
            second = configure.local_converters(root)
            self.assertTrue(
                second["binaries"]["corpora-epub-check"]["debug"]["executable"]
            )
            self.assertFalse(
                second["binaries"]["corpora-epub-check"]["release"]["present"]
            )
            self.assertEqual(
                binary.read_text(), "not runnable: inventory must never execute this"
            )

    def test_doctor_anchors_inventory_to_script_not_working_directory(self):
        with patch.object(configure.shutil, "which", return_value=None):
            result = configure.doctor()
        self.assertEqual(result["local_converters"]["repo_root"], str(ROOT.parents[1]))
        self.assertTrue(
            result["local_converters"]["packages"]["tei-to-tf"]["entrypoint"]["present"]
        )
        self.assertTrue(all(value is None for value in result["executables"].values()))
        self.assertIn("no install", result["note"])
        self.assertIn("freshness", result["local_converters"]["note"])
        json.dumps(result)

    def test_source_inventory_complete_and_pinned(self):
        sources = json.loads((ROOT / "knowledge/sources.json").read_text())["sources"]
        self.assertEqual(len(sources), 17)
        self.assertEqual(len({x["repository"] for x in sources}), 17)
        for source in sources:
            self.assertRegex(source["revision"], r"^[a-f0-9]{40}$")
            self.assertIn(source["revision"], source["url"])


if __name__ == "__main__":
    unittest.main()
