# Verification receipt — 2026-11-06

| Check | Observed result |
| --- | --- |
| `make doctor`, `make setup` | Passed; existing environment retained; local hooks/skill links configured |
| `python3 -m unittest discover -s agent/text-fabric-expert/tests -v` | 6 passed |
| `make agents-check` | Passed, 14 skills |
| `make fmt` | Rust passed; Swift formatting skipped by existing runner |
| `make ci` | Passed: automation selftests, agent assets, Rust/Swift lint/tests/build |
| Existing validator `scripts/selftest.sh` | 17 passed; optional PDF test skipped, pdf-inspector absent |
| `uv run --python 3.13 --with cfabric-mcp==0.1.8 --with text-fabric==13.1.2 python agent/text-fabric-expert/tests/smoke_runtime.py` | Passed |
| `git diff --check` | Passed |

The live smoke test authors a synthetic 2-slot corpus through official TF save,
checks exact Unicode text, three-level sections and an integer-valued edge using
both loaders cold and warm, then starts the real MCP process over stdio, initializes
it, discovers 11 tools, calls list_corpora/describe_corpus/get_node_features and
checks retrieved text. All datasets/caches are temporary. Runtime versions:
Text-Fabric 13.1.2, Context-Fabric 0.5.8, cfabric-mcp 0.1.8. Dependencies were resolved
in uv's isolated cache, not installed globally or enabled in the user's host config.

Limits: synthetic acceptance is not arbitrary-dataset acceptance. No full PDF,
DOC/DOCX, EPUB, USX, TEI, SQL or XML conversion end-to-end suite was run. Agora and
MetaBook integrations were source-inspected, not launched. CFR was not tested.
The ten model-behavior evaluation cases are specifications, not completed runs.
The one-level section fixture exposed an upstream sectionFromNode IndexError;
see knowledge/workflows.md. No claim of universal format fidelity is made.
