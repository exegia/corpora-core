# corpora-source

This Rust crate reserves a place for future source connectors. It has **no
public connector methods or parameters yet**.

For source acquisition today, use the [TEI converter](../../packages/tei-to-tf/README.md):
it accepts local TEI plus specified public HTTPS, GitHub and Hugging Face
sources. The [EPUB converter](../../packages/epub-to-tf/README.md) accepts a
local EPUB file. The two READMEs list what each source path can and cannot do.

License: MIT OR Apache-2.0.
