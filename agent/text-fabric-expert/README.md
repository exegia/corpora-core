# Text-Fabric expert agent

A Text-Fabric (TF) corpus is text plus labels and links. This bundle gives a
coding agent instructions for reading that graph carefully. It is a guide for
an agent host, not a separate converter or a model that runs by itself.

A source-grounded expert for an existing coding-agent host. Invoke
`$text-fabric-expert` in this repository, or load `SYSTEM.md` as the agent's system
instructions. The host supplies the language model and file/command tools.
This bundle does not implement a separate autonomous model runtime.

## Start

```sh
python3 agent/text-fabric-expert/configure.py doctor
```

Use the canonical skill directly; creating host skill aliases is optional setup,
not a prerequisite for conversion or validation.

The canonical skill is `.github/skills/text-fabric-expert/SKILL.md`. The prompt
routes operations to existing tools and records unsupported conversion boundaries.
`knowledge/sources.json` pins all 17 requested repositories; `sources.md` explains
what to reuse, what is corpus-specific and what licensing prevents copying.

## MCP and plugin integration

Prefer the [Agora Context-Fabric plugin](https://github.com/alexsosn/Agora/tree/7f6bddf7810852b3039d1d7aa8fceeb5fde52e37/plugins/context-fabric).
It composes the official CF tools with corpus discovery, local-source snapshots,
revision selection, ordered feature modules and bounded cold compilation.
Use a reviewed checkout with its lockfile; do not assume current source features
exist in a published plugin release. Generate host configuration from its actual root:

```sh
python3 agent/text-fabric-expert/configure.py agora \
  --plugin-root /absolute/path/to/Agora/plugins/context-fabric \
  --output /new/path/agora-mcp.json
```

Alternatively, for an installed official `cfabric-mcp` and a known corpus:

```sh
python3 agent/text-fabric-expert/configure.py local \
  --corpus /absolute/path/to/tf \
  --command /absolute/path/to/venv/bin/cfabric-mcp \
  --features 'text lemma' --output /new/path/local-mcp.json
```

Choose features from the actual corpus; omit --features to use upstream defaults.
The official MCP snapshot requires Python 3.13+. The config generator itself uses
stdlib Python 3.9+. Generated JSON uses the common mcpServers shape; adapt it to
hosts using TOML or another configuration format. No host settings are changed.

| Command or parameter | Purpose |
| --- | --- |
| `configure.py doctor` | Check which local tools and paths are available. |
| `configure.py agora --plugin-root DIR --output NEW_FILE` | Generate configuration for a reviewed Agora plugin checkout. |
| `configure.py local --corpus TF_DIR --command MCP_EXECUTABLE --output NEW_FILE` | Generate configuration for an installed `cfabric-mcp` and one corpus. |
| `--features 'name name'` | In local mode, load only the named TF features; omit for upstream defaults. |

The commands produce configuration JSON; add it to your chosen host yourself.
The [TF AI resolver](../../packages/tf-ai-resolver/README.md) is the working
API for asking this expert about a selected TF text span and reviewing its
proposal.

Enable one selected integration, enumerate its tools and smoke-test `list_corpora`
and `describe_corpus`. Loading can create caches: use a disposable source copy when
read-only originals matter. Restrict host filesystem access to source/output roots.
Disable `search_csv` unless the host can enforce new output paths: upstream uses
unrestricted overwrite. Prompt instructions are not an OS sandbox. Agora cache
prune/remove and MetaBook upload tools are mutations, not research defaults.

Optional integrations: MetaBook's existing FastMCP `analyze_document` for structural
cross-checks; ontoTF for ontology correspondences; GitHub connector for pinned
source/documentation lookup. These are referenced integrations, not bundled servers
or automatically installed plugins. Do not send private documents remotely by default.

## Validation tools

The existing local text-fabric-validator skill is reused by reference because its
redistribution license is unspecified. Set TF_VALIDATOR to its directory and follow
`knowledge/workflows.md`. Its Python scripts cover static validation, document schema
extraction, reconciliation and optional PDF QC. Missing tools must be installed or
provided separately; the doctor never silently installs them. It inventories
converter entrypoints, package manifests/locks, default debug/release Rust binaries,
compiled quality-ai bridge and relevant executables. File existence is not freshness,
a connected integration, installed OCR/dictionary data or conversion acceptance.
Custom Cargo target paths are not inferred.

## Local converters and reviewed corrections

Read [knowledge/local-conversion.md](knowledge/local-conversion.md) for exact
root-relative build/test commands, package working directories and bounded routes:

- `packages/tei-to-tf`: explicit editorial policies, source retention and exact
  character-slot fidelity; unsupported TEI constructs fail closed.
- `packages/epub-to-tf`: implemented Rust `corpora-epub-check` validation followed
  by TF export; spine, notes, links/assets and source/display projections survive.
- `packages/pdf-to-tf`: implemented `corpora-pdf-extract`, strict score > 0.95,
  then TEI/TF with every line/word/page verified against extraction. The score is
  not measured transcription accuracy; rendered-page review remains necessary.
- `packages/quality-ai`: optional Node 22+ TypeScript bridge, compiled to
  `dist/bridge.js`; `npm install`/`npm ci` builds it automatically via
  `prepare: npm run build` unless lifecycle scripts are disabled. Bounded proposals
  receive local exact-span revalidation.
- `packages/tf-ai-resolver`: pinned selection → proposal → exact reviewed apply
  to `resolved_reading` in a new bundle, never a silent rewrite of source slots.

Read each actual package README and CLI help before execution. Preserve independent
static, real TF/CF loader and source-fidelity receipts. Word-slot reconciliation is
not a character-slot oracle. Do not invent universal Markdown/USX/DOC/XML adapters.
No hosted transmissions without explicit authorization, including selections sent
by a local resolver UI. Explain data/provider/cost bounds; credentials are not consent.

Shared model work starts in `crates/corpora-core/schema`, followed by `make types`
and `make types-check` for all Rust, TypeScript, Swift and SQL outputs. Generation
is explicit; the check rejects stale, missing or extra generated files without
modifying them. Both targets skip when the type-generator crate is absent.
Never edit generated files or substitute one-language checks. `make ci` includes
`types-check` and `agents-test`.

## Verification

```sh
make agents-test
make agents-check
uv run --python 3.13 --with cfabric-mcp==0.1.8 --with text-fabric==13.1.2 python agent/text-fabric-expert/tests/smoke_runtime.py
```

`make agents-test` is the official offline verification command: configuration/
inventory behavior and deterministic knowledge/skill/CLI drift contracts. It runs
the unittest suite when `agent/text-fabric-expert/tests` exists and otherwise skips.
It does not run converters, loaders or models.
`make agents-check` validates canonical agent assets; the explicit smoke command
above is a separate live local runtime/MCP check and can resolve dependencies.
Package conversion/build checks are listed in `knowledge/local-conversion.md`;
run them when validating those implementations, not as proof of model behavior.

`evals/cases.json` contains behavioral acceptance cases. Run them in the intended
host with its configured tools; record model/version, date, tool versions, transcript,
case scores and failures using `evals/README.md`. No model eval pass is claimed by
unit tests. No universal PDF/DOC/USX converter or lossless export is claimed.
