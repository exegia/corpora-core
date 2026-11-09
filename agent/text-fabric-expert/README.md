# Text-Fabric expert agent

A source-grounded expert for an existing coding-agent host. Invoke
`$text-fabric-expert` in this repository, or load `SYSTEM.md` as the agent's system
instructions. The host supplies the language model and file/command tools.
This bundle does not implement a separate autonomous model runtime.

## Start

```sh
make agents-link
python3 agent/text-fabric-expert/configure.py doctor
```

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
provided separately; the doctor never silently installs them.

## Verification

```sh
python3 -m unittest discover -s agent/text-fabric-expert/tests -v
make agents-check
uv run --python 3.13 --with cfabric-mcp==0.1.8 --with text-fabric==13.1.2 python agent/text-fabric-expert/tests/smoke_runtime.py
make fmt
make ci
```

`evals/cases.json` contains behavioral acceptance cases. Run them in the intended
host with its configured tools; record model/version, date, tool versions, transcript,
case scores and failures using `evals/README.md`. No model eval pass is claimed by
unit tests. No universal PDF/DOC/USX converter or lossless export is claimed.
