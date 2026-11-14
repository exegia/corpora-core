"""Offline documentation/CLI contracts, not converter or model acceptance tests."""

import ast
import json
import re
import shlex
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1]
REPO = AGENT.parents[1]
GUIDE = AGENT / "knowledge/local-conversion.md"
ROUTES = {
    "tei-to-tf": "tei_to_tf/cli.py",
    "epub-to-tf": "epub_to_tf/__init__.py",
    "pdf-to-tf": "pdf_to_tf/cli.py",
    "tf-ai-resolver": "tf_ai_resolver/cli.py",
}


def argument_names(path):
    """Read argparse declarations without importing converters or their dependencies."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        argument.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }


class ConversionKnowledgeTests(unittest.TestCase):
    def test_documented_routes_match_real_entrypoints_and_options(self):
        guide = GUIDE.read_text(encoding="utf-8")
        seen = set()
        for line in guide.splitlines():
            if not line.startswith("uv run "):
                continue
            words = shlex.split(line)
            if "--project" not in words:
                continue
            index = words.index("--project")
            project, command = words[index + 1 : index + 3]
            name = Path(project).name
            if name not in ROUTES or command != name:
                continue
            with self.subTest(command=line):
                package = REPO / project
                manifest = (package / "pyproject.toml").read_text(encoding="utf-8")
                self.assertRegex(manifest, rf'(?m)^{re.escape(name)}\s*=\s*"')
                entrypoint = package / "src" / ROUTES[name]
                self.assertTrue(entrypoint.is_file())
                allowed = argument_names(entrypoint) | {"--help"}
                flags = {word for word in words[index + 3 :] if word.startswith("--")}
                self.assertFalse(
                    flags - allowed, f"Unknown CLI flags: {flags - allowed}"
                )
                seen.add(name)
        self.assertEqual(seen, set(ROUTES))

    def test_build_and_test_commands_have_real_local_targets(self):
        guide = GUIDE.read_text(encoding="utf-8")
        for name in ("tei-to-tf", "pdf-to-tf"):
            with self.subTest(package=name):
                self.assertIn(f"make -C packages/{name} check build", guide)
                makefile = (REPO / "packages" / name / "Makefile").read_text()
                self.assertRegex(makefile, r"(?m)^check:")
                self.assertRegex(makefile, r"(?m)^build:")
                self.assertIn("uv run --locked pytest -q", makefile)
        for crate, binary in (
            ("corpora-convert", "corpora-epub-check"),
            ("corpora-pdf", "corpora-pdf-extract"),
        ):
            with self.subTest(crate=crate):
                self.assertIn(f"cargo build -p {crate} --bin {binary}", guide)
                manifest = (REPO / "crates" / crate / "Cargo.toml").read_text()
                self.assertIn(f'name = "{binary}"', manifest)
        self.assertIn("cargo test --locked -p corpora-convert", guide)
        self.assertIn("pytest -q packages/epub-to-tf/tests", guide)
        self.assertTrue((REPO / "packages/epub-to-tf/tests").is_dir())
        for name in ("epub-to-tf", "tf-ai-resolver"):
            self.assertIn(f"from `packages/{name}`", guide)
        for command in (
            "ruff check .",
            "ruff format --check .",
            "mypy src",
            "pytest -q",
        ):
            self.assertIn(f"uv run --locked --group dev {command}", guide)

    def test_quality_bridge_is_compiled_and_package_scripts_exist(self):
        guide = GUIDE.read_text(encoding="utf-8")
        manifest = json.loads((REPO / "packages/quality-ai/package.json").read_text())
        self.assertIn("npm ci --prefix packages/quality-ai", guide)
        for script in ("check", "build", "test"):
            self.assertIn(script, manifest["scripts"])
            self.assertIn(
                f"npm run {script} --prefix packages/quality-ai"
                if script != "test"
                else "npm test --prefix packages/quality-ai",
                guide,
            )
        self.assertIn("tsc", manifest["scripts"]["build"])
        self.assertIn("dist/bridge.test.js", manifest["scripts"]["test"])
        self.assertTrue((REPO / "packages/quality-ai/bridge.ts").is_file())
        self.assertEqual(manifest["scripts"]["prepare"], "npm run build")
        self.assertIn("`npm install` and `npm ci` automatically compile", guide)
        self.assertIn("prepare: npm run build", guide)
        self.assertIn("unless lifecycle scripts are disabled", guide)
        self.assertIn("--ai-bridge packages/quality-ai/dist/bridge.js", guide)
        tei = argument_names(REPO / "packages/tei-to-tf/src/tei_to_tf/cli.py")
        self.assertTrue(
            {
                "--ai-bridge",
                "--ai-model",
                "--ai-max-requests",
                "--repair-cycles",
                "--quality-engine",
                "--dictionaries",
            }
            <= tei
        )
        self.assertNotIn("--ai-bridge packages/quality-ai/bridge.mjs", guide)
        self.assertNotIn("--ai-bridge packages/quality-ai/bridge.ts", guide)

    def test_skill_prompt_and_workflows_route_to_local_knowledge(self):
        paths = [
            REPO / ".github/skills/text-fabric-expert/SKILL.md",
            AGENT / "SYSTEM.md",
            AGENT / "knowledge/workflows.md",
        ]
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("local-conversion.md", text)
                self.assertRegex(
                    text.lower(), r"(?:explicit.{0,10}authoriz|authoriz.{0,30}explicit)"
                )
                self.assertNotIn("conversion crates are placeholders", text)
        for path in paths[:2]:
            text = path.read_text(encoding="utf-8")
            for contract in (
                "crates/corpora-core/schema",
                "make types",
                "make types-check",
                "Rust, TypeScript, Swift and SQL",
                "resolved_reading",
                "packages/quality-ai/dist/bridge.js",
                "character slots",
            ):
                self.assertIn(contract, text)

    def test_safety_and_fidelity_contracts_are_explicit(self):
        guide = GUIDE.read_text(encoding="utf-8")
        for contract in (
            "score > 0.95",
            "equality fails",
            "not transcription accuracy",
            "cold-load",
            "Context-Fabric",
            "Source fidelity",
            "word-slot",
            "not a character-slot oracle",
            "TF064/TF065",
            "text-source-full",
            "standOff",
            "--repair",
            "repair ledger",
            "non-linear",
            "No hosted transmissions without authorization",
            "not consent",
            "AI_GATEWAY_API_KEY",
            "request cap is not a dollar",
            "Node 22+",
            "expected_replacement",
            "F.resolved_reading.v(node)",
            "no_change",
            "T.text(node)",
            "half-open Unicode scalar offsets",
            "127.0.0.1",
            "make types\nmake types-check",
            "all Rust, TypeScript, Swift and SQL",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, guide)
        self.assertTrue((REPO / "crates/corpora-core/schema/model.json").is_file())
        self.assertTrue((REPO / "crates/corpora-core/schema/domains").is_dir())
        # Do not advertise an aggregate conversion target that does not exist.
        self.assertNotIn("make conversion-check", guide)

    def test_make_verification_targets_and_dev_cycle_match_implementation(self):
        makefile = (REPO / "makefile").read_text(encoding="utf-8")
        dev_cycle = (REPO / ".github/skills/dev-cycle/SKILL.md").read_text()
        prerequisites = re.search(r"(?m)^ci:\s*(.*?)\s*##", makefile).group(1).split()
        documented = re.search(r"`make ci` = ([^.]+)\.", dev_cycle).group(1)
        self.assertEqual(documented.split(" + "), prerequisites)
        self.assertIn("agents-test", prerequisites)
        self.assertIn("types-check", prerequisites)
        self.assertNotIn("types", prerequisites)
        for target in ("types", "types-check", "agents-test"):
            with self.subTest(target=target):
                body = re.search(rf"(?m)^{target}:.*\n((?:\t.*\n)+)", makefile).group(1)
                self.assertIn("else echo", body)
                self.assertIn(f"make {target}", dev_cycle)
                if target == "agents-test":
                    self.assertIn("[ -d agent/text-fabric-expert/tests ]", body)
                    self.assertIn(
                        "python3 -m unittest discover -s agent/text-fabric-expert/tests -v",
                        body,
                    )
                else:
                    self.assertIn("[ -f crates/corpora-typegen/Cargo.toml ]", body)
                    self.assertIn("cargo run --locked -p corpora-typegen", body)
                    self.assertEqual("-- --check" in body, target == "types-check")
        self.assertIn("crates/corpora-typegen/Cargo.toml", dev_cycle)
        self.assertIn("agent/text-fabric-expert/tests", dev_cycle)
        self.assertIn("stack-dispatched tasks", dev_cycle)
        self.assertIn("skip when", dev_cycle)
        self.assertIn("without modifying them", dev_cycle)

    def test_official_agent_verification_command_is_documented(self):
        for path in (
            GUIDE,
            AGENT / "README.md",
            AGENT / "evals/README.md",
            REPO / ".github/skills/text-fabric-expert/SKILL.md",
        ):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("make agents-test", text)
                self.assertIn("skip", text)
                self.assertNotIn("python3 -m unittest discover", text)

    def test_eval_cases_cover_routes_without_claiming_model_acceptance(self):
        cases = json.loads((AGENT / "evals/cases.json").read_text())
        identifiers = [case["id"] for case in cases]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        expected = {
            "pdf-qc": "packages/pdf-to-tf",
            "local-tei-policy": "packages/tei-to-tf",
            "local-epub-route": "corpora-epub-check",
            "character-slot-validation": "character-slot oracle",
            "compiled-quality-bridge": "packages/quality-ai/dist/bridge.js",
            "resolver-reviewed-reading": "resolved_reading",
            "shared-schema-generation": "make types-check",
            "hosted-consent": "explicit authorization",
        }
        by_id = {case["id"]: case for case in cases}
        for identifier, criterion in expected.items():
            with self.subTest(case=identifier):
                self.assertIn(identifier, by_id)
                self.assertIn(criterion, " ".join(by_id[identifier]["required"]))
        for case in cases:
            self.assertTrue(case["prompt"].strip())
            for key in ("required", "forbidden"):
                self.assertTrue(case[key])
                self.assertTrue(
                    all(isinstance(item, str) and item.strip() for item in case[key])
                )
        acceptance = (AGENT / "evals/README.md").read_text()
        self.assertIn("not executed", acceptance)
        self.assertIn("not a behavioral run", acceptance)
        self.assertNotIn("10/10", acceptance)


if __name__ == "__main__":
    unittest.main()
