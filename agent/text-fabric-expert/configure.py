"""Generate reviewable MCP configuration; never modify host configuration."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def directory(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError(f"Not a directory: {path}")
    return path


def executable(value):
    resolved = shutil.which(value)
    if resolved is None:
        raise ValueError(f"Executable not found: {value}")
    return str(Path(resolved).resolve())


def configuration(args):
    if args.mode == "agora":
        root = directory(args.plugin_root)
        for required in (
            "pyproject.toml",
            "uv.lock",
            "src/agora_context_fabric/server.py",
        ):
            if not (root / required).is_file():
                raise ValueError(f"Missing Agora plugin file: {root / required}")
        return {
            "mcpServers": {
                "text-fabric-expert": {
                    "command": executable(args.command or "uv"),
                    "cwd": str(root),
                    "args": [
                        "run",
                        "--locked",
                        "--project",
                        str(root),
                        "agora-context-fabric-mcp",
                        "--plugin-root",
                        str(root),
                    ],
                    "tool_timeout_sec": 5400,
                }
            }
        }
    root = directory(args.corpus)
    for required in ("otype.tf", "oslots.tf"):
        if not (root / required).is_file():
            raise ValueError(f"Missing TF source: {root / required}")
    argv = ["--corpus", f"dataset={root}"]
    if args.features:
        argv.extend(["--features", args.features])
    return {
        "mcpServers": {
            "text-fabric-expert": {
                "command": executable(args.command or "cfabric-mcp"),
                "args": argv,
            }
        }
    }


def local_converters(repo_root):
    """Inventory files only; do not import packages, execute tools or install data."""
    root = Path(repo_root).resolve()

    def artifact(relative, binary=False):
        path = root / relative
        result = {"path": str(path), "present": path.is_file()}
        if binary:
            result["executable"] = path.is_file() and os.access(path, os.X_OK)
        return result

    entries = {
        "tei-to-tf": "tei_to_tf/cli.py",
        "epub-to-tf": "epub_to_tf/__init__.py",
        "pdf-to-tf": "pdf_to_tf/cli.py",
        "tf-ai-resolver": "tf_ai_resolver/cli.py",
    }
    packages = {
        name: {
            "manifest": artifact(f"packages/{name}/pyproject.toml"),
            "lockfile": artifact(f"packages/{name}/uv.lock"),
            "entrypoint": artifact(f"packages/{name}/src/{entrypoint}"),
        }
        for name, entrypoint in entries.items()
    }
    return {
        "repo_root": str(root),
        "packages": packages,
        "binaries": {
            name: {
                profile: artifact(f"target/{profile}/{name}", binary=True)
                for profile in ("debug", "release")
            }
            for name in (
                "corpora-epub-check",
                "corpora-pdf-extract",
                "corpora-text-check",
            )
        },
        "quality_ai": {
            "manifest": artifact("packages/quality-ai/package.json"),
            "source": artifact("packages/quality-ai/bridge.ts"),
            "compiled_bridge": artifact("packages/quality-ai/dist/bridge.js"),
        },
        "note": "Default target/debug and target/release only; custom Cargo target paths, "
        "artifact freshness, dictionaries, OCR models and runtime acceptance are not checked.",
    }


def doctor():
    roots = []
    if os.environ.get("TF_VALIDATOR"):
        roots.append(Path(os.environ["TF_VALIDATOR"]).expanduser())
    roots.extend(
        Path.home() / p
        for p in (
            ".agents/skills/text-fabric-validator",
            ".codex/skills/text-fabric-validator",
        )
    )
    validator = next(
        (p.resolve() for p in roots if (p / "scripts/tf_validate.py").is_file()), None
    )
    return {
        "python": sys.version.split()[0],
        "executables": {
            name: shutil.which(name)
            for name in (
                "uv",
                "cfabric-mcp",
                "cargo",
                "node",
                "npm",
                "codex",
                "pdfinfo",
                "pdftotext",
                "pdftoppm",
                "tesseract",
            )
        },
        "validator": str(validator) if validator else None,
        "local_converters": local_converters(Path(__file__).resolve().parents[2]),
        "note": "Inventory only; no install, tool execution, hosted request, server "
        "connection or converter acceptance tested.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("doctor")
    agora = sub.add_parser(
        "agora", help="Generate config for an existing Agora plugin checkout"
    )
    agora.add_argument("--plugin-root", required=True)
    local = sub.add_parser(
        "local", help="Generate config for an installed cfabric-mcp executable"
    )
    local.add_argument("--corpus", required=True)
    local.add_argument("--features", default="")
    for command in (agora, local):
        command.add_argument(
            "--command", help="Explicit executable; defaults to PATH lookup"
        )
        command.add_argument(
            "--output", help="New config file; existing files are refused"
        )
    args = parser.parse_args(argv)
    try:
        result = doctor() if args.mode == "doctor" else configuration(args)
        payload = json.dumps(result, indent=2) + "\n"
        if getattr(args, "output", None):
            with Path(args.output).open("x", encoding="utf-8") as stream:
                stream.write(payload)
        else:
            print(payload, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
