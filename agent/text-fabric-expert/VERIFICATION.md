# Verification receipts

## Implemented verification targets and lifecycle — 2026-11-12

Documentation now reflects the implemented Make targets and quality-ai lifecycle.
`make agents-test` is the official offline verification command. `make ci` includes
`agents-test` and `types-check`; regeneration remains the explicit `make types` step.
The type targets skip when the type-generator crate is absent, and `agents-test`
skips when the agent test bundle is absent. `npm install`/`npm ci` automatically
builds quality-ai via `prepare: npm run build` unless lifecycle scripts are disabled.

| Check                                        | Observed result                                                                             |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `PYTHONDONTWRITEBYTECODE=1 make agents-test` | 17 passed: 9 configuration/inventory and 8 deterministic knowledge/CLI/automation contracts |
| `make agents-check`                          | Passed, 15 skills                                                                           |
| `make types-check`                           | Passed; all 22 generated files are up to date                                               |
| Scoped `git diff --check`                    | Passed                                                                                      |

Writes for this follow-up stayed within `agent/text-fabric-expert/**`,
`.github/skills/text-fabric-expert/**` and the additionally authorized
`.github/skills/dev-cycle/SKILL.md`. Root docs, automation, packages, generated models
and `.agents` aliases were not edited. No commits or hosted transmissions.
Full `make ci`, package conversion/provider suites, type regeneration and model
acceptance were not run. The 17 behavioral cases remain not executed; offline test
passes are not live model acceptance.

## Initial conversion knowledge update — 2026-11-12

Writes were restricted to `agent/text-fabric-expert/**` and the canonical
`.github/skills/text-fabric-expert/**`. No root docs, automation, converter packages,
generated models or `.agents` aliases were edited for this update. No commits.

| Check                                                                                            | Observed result                                                                                   |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s agent/text-fabric-expert/tests -v` | 15 passed: 9 configuration/inventory and 6 deterministic knowledge/CLI contracts                  |
| `make agents-check`                                                                              | Passed, 15 skills                                                                                 |
| `python3 -B agent/text-fabric-expert/configure.py doctor`                                        | Passed; local converter sources/default artifacts inventoried; no tool execution or install       |
| Existing package venv Python `-B` CLI `--help`                                                   | TEI, EPUB, PDF and resolver help passed; resolver inspect/resolve/apply/serve help also inspected |
| `git diff --check -- agent/text-fabric-expert .github/skills/text-fabric-expert`                 | Passed                                                                                            |

Package READMEs, actual argparse definitions and Rust bridge usage were read before
commands were documented. Help used existing virtual environments with bytecode
writes disabled, not dependency installation or hosted calls. This update did not
run package conversion suites, regenerate shared types, run the runtime/MCP smoke
or execute a model acceptance evaluation. Those commands are documented, not claimed
passed. `make types` regenerates all shared models; `make types-check` verifies
them without modifying files. Both skip when the type-generator crate is absent.
No additional aggregate conversion target is assumed here.

The 17 behavioral cases remain not executed. Offline documentation/CLI contract
checks and fake-artifact inventory tests do not establish per-corpus fidelity,
artifact freshness, live loader/provider acceptance or model quality.

## Historical receipt — 2026-11-06

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
The then-ten model-behavior evaluation cases were specifications, not completed runs.
The one-level section fixture exposed an upstream sectionFromNode IndexError;
see knowledge/workflows.md. No claim of universal format fidelity is made.
