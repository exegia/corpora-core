# Text-Fabric AI selection resolver

Point to a small piece of TF text, ask for a change, and review the answer.
The resolver treats the selection like a bookmark pinned to one exact version
of the corpus. It writes a **new** TF bundle with the proposal; applying a
reviewed proposal writes another new bundle. The source words stay intact.

This package runs the repository's Text-Fabric expert on one pinned selection and
exports an audited TF overlay. It also serves the EPUB semantic QA page with a
local selection and review UI.

## Selection and result

`inspect_selection(tf_dir, node, start, end, text_feature)` returns a JSON-ready
`Selection`. Offsets are zero-based, half-open Unicode scalar offsets in
`T.text(node)`; the expected text and SHA-256 source revision pin the request.
The revision includes every `.tf` file and exported asset, excluding loader
caches. The selected span is limited to 4,096 characters. A request targets one
TF node and names the text feature and optional TF text format explicitly.

`resolve(tf_dir, output, selection, mode, prompt, expert)` accepts `fix`,
`suggest`, or `custom`. The prompt is limited to 2,000 characters. The expert
receives the selected text, node type, and at most 500 characters of context on
each side. Its structured result is validated locally. The resolver copies the
source graph to `output/tf`, adds `ai_resolutions.tf` to the selected node, and
writes `output/resolution.json` with the candidate text and review status. Every
result has status `proposed`. The original corpus reading, node IDs, and slot
edges remain intact. The host does not silently apply AI wording to source
slots. `apply_resolution(proposal_dir, output, resolution_id,
expected_replacement)` requires an exact reviewed candidate and writes a new
bundle with status `applied` and a `resolved_reading` node feature. Read that
corrected string with `F.resolved_reading.v(node)`; `T.text(node)` remains the
source-faithful reading. Multiple non-overlapping applied replacements compose
against their original Unicode offsets.

The output is loaded again with both Text-Fabric and Context-Fabric before it is
published. The output directory must be new and outside the source. Loader
caches stay out of `output/tf`.

## Python API

```python
from pathlib import Path
from tf_ai_resolver import CodexExpert, inspect_selection, resolve, apply_resolution

tf_dir = Path("output/book/tf")
selection = inspect_selection(tf_dir, node=123, start=5, end=10, text_feature="text")
expert = CodexExpert(Path("agent/text-fabric-expert/SYSTEM.md"))
proposal = resolve(
    tf_dir,
    Path("output/proposal"),
    selection,
    mode="fix",
    prompt="Correct this spelling.",
    expert=expert,
)
print(proposal["resolution"])  # review action, replacement, and reason
```

Use node/offset values obtained from the **actual loaded TF text**; `123` and
`5..10` above are example values. Inspect the proposal's reason and replacement
before calling `apply_resolution`. If its `action` is `replace` and you approve
the exact `replacement`, apply it with:

```python
resolution = proposal["resolution"]
reviewed = apply_resolution(
    Path("output/proposal"),
    Path("output/applied"),
    resolution["id"],
    resolution["replacement"],
)
```

A selection has `node`, `start`, `end`,
`expected_text`, `revision`, `text_feature`, and optional `text_format`.

| Call | Parameters | Purpose |
| --- | --- | --- |
| `inspect_selection` | `tf_dir`, positive node, Unicode scalar `start`/`end`, `text_feature`, optional `text_format` | Capture exact text and source revision for one node. |
| `CodexExpert` | Expert instruction path; optional `command="codex"`, `model=None` | Configure the local Codex expert invocation. |
| `resolve` | `tf_dir`, new `output`, `Selection`, `mode`, `prompt`, `expert` | Validate a `fix`, `suggest`, or `custom` request and write a proposal bundle. |
| `apply_resolution` | `proposal_dir`, new `output`, `resolution_id`, `expected_replacement` | Apply one approved exact candidate to `resolved_reading`. |

All paths are `Path` objects. Invalid/stale selections and unsafe destinations
raise `ResolveError`. Selection length is at most 4,096 Unicode scalars; prompt
length is 1–2,000 characters. `resolve` and `apply_resolution` return report
dictionaries. The model can suggest text, but the host checks the proposal and
owns all TF writes.

## CLI

From this directory:

```sh
uv sync --group dev
uv run tf-ai-resolver inspect /path/to/tf 123 5 10 --text-feature text > selection.json
```

Create `request.json` containing the selection object from that command:

```json
{
  "selection": {"node": 123, "start": 5, "end": 10, "expected_text": "word", "revision": "SOURCE_SHA256", "text_feature": "text", "text_format": null},
  "mode": "fix",
  "prompt": "Correct the selected spelling."
}
```

Then run:

```sh
uv run tf-ai-resolver resolve /path/to/tf request.json /path/to/new-output
uv run tf-ai-resolver apply /path/to/new-output RESOLUTION_ID REPLACEMENT /path/to/applied-output
```

To use the browser UI, first generate the QA site from an EPUB bundle, then
start the loopback service from the repository root:

```sh
uv run --project packages/epub-to-tf python packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE
uv run --project packages/tf-ai-resolver tf-ai-resolver serve BUNDLE/tf SITE RESOLUTIONS --port 8772
```

Open `http://127.0.0.1:8772/`, select text inside one semantic TF document or
note, choose `fix`, `suggest`, or `custom`, and run the expert. Review its
candidate and reason before selecting **Apply candidate to derived reading**.
The service binds only to `127.0.0.1`, checks same-origin JSON requests, and
accepts application only for proposals issued in that server session. Each
proposal and application gets a new output directory under `RESOLUTIONS`.

For a custom local UI, the loopback service is
`tf_ai_resolver.server.create_server(site, tf_dir, output_root, expert, port=0)`.
It serves the generated QA site and exposes three same-origin JSON requests:

| Route | JSON body | JSON result |
| --- | --- | --- |
| `POST /api/inspect` | `node`, `start`, `end`, `expected_text` | Pinned `selection`. |
| `POST /api/resolve` | `selection`, `mode`, `prompt` | `output`, session `proposal_id`, `report`. |
| `POST /api/apply` | `proposal_id`, `resolution_id`, `expected_replacement` | `output`, `report`. |

Requests need `Content-Type: application/json`, `X-TF-Resolver: 1`, and the
matching local `Origin`/`Host`; bodies are capped at 16 KiB. The built-in
browser sends these fields. A `proposal_id` works only in the server session
that issued it, and a proposal can be applied once.

The default expert instructions are
[`agent/text-fabric-expert/SYSTEM.md`](../../agent/text-fabric-expert/SYSTEM.md)
in this repository. Installed users can pass `--expert-instructions PATH`.
`CodexExpert` invokes the locally configured Codex CLI in a read-only,
ephemeral workspace with a strict JSON response schema. Selected text and its
small context are sent to the configured model provider. The model cannot edit
the source TF through this API; the host writes the checked overlay.
The selected corpus text is treated as untrusted data.

## Current boundary

This API handles text proposals on one node and applies reviewed replacements
to a derived node feature. It does not rewrite source slots, change graph
structure, or resolve asset edits. Requests needing those changes should
receive `no_change` with a reason. A corrected semantic HTML rendering of the
derived feature is not yet provided; the QA iframe continues showing the
source-faithful reading. Each new request must be pinned against the exact
source bundle; after an overlay is added, inspect again before making another
request.

## Checks

```sh
uv run --group dev ruff format --check .
uv run --group dev ruff check .
uv run --group dev mypy src
uv run --group dev pytest -q
uv build
```
