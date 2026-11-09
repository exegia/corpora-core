# corpora-fabric

This Rust crate reserves a place for a future Text-Fabric builder. It has **no
public builder methods or parameters yet**. Adding it as a dependency will not
convert a document.

To make a TF bundle today, use the [TEI converter](../../packages/tei-to-tf/README.md)
or [EPUB converter](../../packages/epub-to-tf/README.md). Both describe their
commands, policies and output files. To load TF, use the real Text-Fabric or
Context-Fabric runtime described there.

License: MIT OR Apache-2.0.
