//! # corpora-convert
//!
//! Source-bound validation and reading projection for bounded local EPUB input.

// zip and the workspace's other dependencies resolve two transitive hash table versions.
#![expect(
    clippy::multiple_crate_versions,
    reason = "transitive zip dependency graph"
)]

pub mod epub;
