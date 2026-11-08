# First EPUB conversion verification

2026-11-08, branch `feat/convert-epub-to-tf`, local uncommitted work.

| Command | Result |
| --- | --- |
| `make doctor` | Required root tools available. |
| `make fmt` | Passed. |
| `make ci` | Passed after the converter Clippy fixes; Rust, Swift, agent checks, tests and builds. |
| `cargo build -p corpora-convert --bin corpora-epub-check` | Passed. |
| `uv run --group dev ruff check .` (package) | Passed. |
| `uv run --group dev ruff format --check .` (package) | Passed. |
| `uv run --group dev mypy src` (package) | Passed. |
| `uv run --group dev pytest -q` (package) | 15 passed, including actual Text-Fabric and Context-Fabric loads. |
| `uv build` (package) | Wheel and source distribution built. |
| `make -C packages/tei-to-tf check build` | 138 passed, 11 skipped; lint, type and build passed. |
| `git diff --check` | Passed. |

Static `tf_validate.py` on the generated 11-slot fixture returned 0 errors,
TF064 warning, TF065 info. Those findings are caused by intentional character
slots: slots 7 and 9 contain literal spaces, and `{text}` deliberately adds no
separator. Exact `T.text(document)` was checked against the independently
specified `Áβcafé & 東京` using both real loaders.

`doc_schema.py` followed by `tf_reconcile.py` reported RC001/RC002 against
that same fixture. Its EPUB reference extractor treats the adjacent inline
`Á<em>β</em>` as separate words (`Á β`), while the XHTML source has no space
and the converter correctly preserves `Áβ`. This reconciliation is unsuitable
as an acceptance oracle for adjacent inline characters; the independent
source-text assertion and loader round trips are the acceptance evidence.

No hosted service or remote acquisition was used. No commit or push was made.
