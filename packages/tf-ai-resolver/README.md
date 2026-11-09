# Text-Fabric AI selection resolver

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
