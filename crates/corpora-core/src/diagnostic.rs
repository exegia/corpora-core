//! Shared, source-bound diagnostics. Core proposes edits; callers apply and revalidate them.

use crate::{Error, Result};
use sha2::{Digest, Sha256};
use std::ops::Range;

/// Position in the exact UTF-8 string supplied to a checker, before XML normalization.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct SourcePosition {
    /// Zero-based UTF-8 byte offset.
    pub byte: usize,
    /// Zero-based Unicode scalar offset (not UTF-16 or grapheme clusters).
    pub scalar: usize,
    /// One-based line; LF starts a new line, including in CRLF input.
    pub line: usize,
    /// One-based Unicode scalar column.
    pub column: usize,
}

/// Half-open range; equal endpoints locate an insertion or parser failure point.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct SourceRange {
    /// Inclusive start.
    pub start: SourcePosition,
    /// Exclusive end.
    pub end: SourcePosition,
}

impl SourceRange {
    /// Resolve byte boundaries against the supplied source without rounding invalid offsets.
    pub fn from_bytes(text: &str, range: Range<usize>) -> Result<Self> {
        if range.start > range.end
            || !text.is_char_boundary(range.start)
            || !text.is_char_boundary(range.end)
        {
            return Err(Error::conversion(
                "Diagnostic range is outside UTF-8 boundaries",
            ));
        }
        let position = |byte| {
            let prefix = &text[..byte];
            SourcePosition {
                byte,
                scalar: prefix.chars().count(),
                line: prefix.bytes().filter(|b| *b == b'\n').count() + 1,
                column: prefix.rsplit('\n').next().unwrap_or("").chars().count() + 1,
            }
        };
        Ok(Self {
            start: position(range.start),
            end: position(range.end),
        })
    }
}

/// Sparse source index: one checkpoint per 256 scalars, bounded work per lookup.
pub(crate) struct SourceMap<'a> {
    text: &'a str,
    checkpoints: Vec<SourcePosition>,
}

impl<'a> SourceMap<'a> {
    pub(crate) fn new(text: &'a str) -> Self {
        let mut checkpoints = vec![];
        let mut point = SourcePosition {
            byte: 0,
            scalar: 0,
            line: 1,
            column: 1,
        };
        for ch in text.chars() {
            if point.scalar.is_multiple_of(256) {
                checkpoints.push(point.clone());
            }
            Self::advance(&mut point, ch);
        }
        checkpoints.push(point);
        Self { text, checkpoints }
    }

    const fn advance(point: &mut SourcePosition, ch: char) {
        point.byte += ch.len_utf8();
        point.scalar += 1;
        if ch == '\n' {
            point.line += 1;
            point.column = 1;
        } else {
            point.column += 1;
        }
    }

    fn position(&self, byte: usize) -> SourcePosition {
        let index = self.checkpoints.partition_point(|point| point.byte <= byte) - 1;
        let mut point = self.checkpoints[index].clone();
        for ch in self.text[point.byte..byte].chars() {
            Self::advance(&mut point, ch);
        }
        point
    }

    pub(crate) fn range(&self, bytes: Range<usize>) -> Result<SourceRange> {
        if bytes.start > bytes.end
            || !self.text.is_char_boundary(bytes.start)
            || !self.text.is_char_boundary(bytes.end)
        {
            return Err(Error::conversion(
                "Diagnostic range is outside UTF-8 boundaries",
            ));
        }
        Ok(SourceRange {
            start: self.position(bytes.start),
            end: self.position(bytes.end),
        })
    }

    #[cfg(feature = "spellcheck")]
    pub(crate) fn scalar_range(&self, scalars: Range<usize>) -> Result<SourceRange> {
        let byte_at = |scalar| {
            let index = self
                .checkpoints
                .partition_point(|point| point.scalar <= scalar)
                .checked_sub(1)?;
            let point = &self.checkpoints[index];
            self.text[point.byte..]
                .char_indices()
                .map(|(byte, _)| byte)
                .chain(std::iter::once(self.text.len() - point.byte))
                .nth(scalar - point.scalar)
                .map(|byte| byte + point.byte)
        };
        match (byte_at(scalars.start), byte_at(scalars.end)) {
            (Some(start), Some(end)) => self.range(start..end),
            _ => Err(Error::conversion(
                "Diagnostic scalar range is outside the input",
            )),
        }
    }
}

/// Checker family; severity and uncertainty are independent of this category.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Serialize, serde::Deserialize),
    serde(rename_all = "snake_case")
)]
pub enum DiagnosticCategory {
    /// XML syntax or supported TEI structural boundaries.
    Structural,
    /// Spelling and typography.
    Spelling,
}

/// Policy impact, never a probability that the suggested correction is right.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Serialize, serde::Deserialize),
    serde(rename_all = "snake_case")
)]
pub enum Severity {
    /// Nonblocking finding.
    Warning,
    /// Blocking finding.
    Error,
}

/// Strength of the diagnosis, separate from confidence in a proposed edit.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Serialize, serde::Deserialize),
    serde(rename_all = "snake_case")
)]
pub enum Certainty {
    /// A parser or explicit policy established the problem.
    Certain,
    /// A heuristic or dictionary flagged a possible problem.
    Possible,
}

/// How a caller may use a suggestion. Every applied edit still requires revalidation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Serialize, serde::Deserialize),
    serde(rename_all = "snake_case")
)]
pub enum Applicability {
    /// A bounded lexical correction, eligible for an automated attempt under caller policy.
    Automatic,
    /// A candidate requiring contextual assessment before application.
    Review,
}

/// One proposed replacement against the report's exact source snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct TextEdit {
    /// Range in the unchanged input, never in a partially repaired string.
    pub range: SourceRange,
    /// Expected source text; callers must check this and the report's source hash.
    pub before: String,
    /// Proposed replacement; may be empty for deletion.
    pub after: String,
}

impl TextEdit {
    /// Check the snapshot, all coordinates, and expected original text before an edit.
    /// This does not apply the edit or establish that its proposed replacement is correct.
    pub fn matches_source(&self, report: &DiagnosticReport, text: &str) -> bool {
        let bytes = self.range.start.byte..self.range.end.byte;
        report.matches_source(text)
            && text.get(bytes.clone()) == Some(self.before.as_str())
            && SourceRange::from_bytes(text, bytes).is_ok_and(|range| range == self.range)
    }
}

/// A candidate fix or an explanation of the decision needed when no edit is defensible.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Suggestion {
    /// Why this action could resolve the finding.
    pub message: String,
    /// Eligibility, not proof that the complete document will pass validation.
    pub applicability: Applicability,
    /// Atomic edits in original-source coordinates; empty for guidance-only suggestions.
    pub edits: Vec<TextEdit>,
}

/// Shared diagnostic from a structural or spelling checker.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Diagnostic {
    /// Stable machine-readable code.
    pub code: String,
    /// Checker family.
    pub category: DiagnosticCategory,
    /// Policy severity, independent of certainty.
    pub severity: Severity,
    /// Whether this unresolved finding blocks the checked operation.
    pub blocking: bool,
    /// Optional checker-specific policy score; never a confidence percentage.
    pub score: Option<u8>,
    /// Whether the problem is established or only suspected.
    pub certainty: Certainty,
    /// Explanation and evidence for the diagnosis.
    pub message: String,
    /// Primary range first, followed by related ranges. Empty means location unavailable.
    pub locations: Vec<SourceRange>,
    /// Candidate fixes or actionable guidance; never an invented guaranteed correction.
    pub suggestions: Vec<Suggestion>,
}

/// Findings bound to one immutable input string (a full XML source or a text segment).
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct DiagnosticReport {
    /// Shared diagnostic schema version, currently 1.
    pub schema_version: u16,
    /// Caller-supplied document or segment identity.
    pub source_id: String,
    /// Lowercase SHA-256 of the exact UTF-8 input bytes, before normalization.
    pub source_sha256: String,
    /// Findings in deterministic source order when locations are available.
    pub diagnostics: Vec<Diagnostic>,
}

impl DiagnosticReport {
    /// Bind findings to an input. All locations and edits must refer to this exact string.
    pub fn new(source_id: impl Into<String>, text: &str, diagnostics: Vec<Diagnostic>) -> Self {
        Self {
            schema_version: 1,
            source_id: source_id.into(),
            source_sha256: format!("{:x}", Sha256::digest(text.as_bytes())),
            diagnostics,
        }
    }

    /// Whether the selected checks found no blocking diagnostics; not a universal validity claim.
    pub fn passed(&self) -> bool {
        self.diagnostics.iter().all(|d| !d.blocking)
    }

    /// Detect a stale or different source before interpreting ranges or attempting edits.
    pub fn matches_source(&self, text: &str) -> bool {
        self.source_sha256 == format!("{:x}", Sha256::digest(text.as_bytes()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn indexed_positions_agree_with_original_source_across_checkpoints() {
        for text in [String::new(), "😀e\u{301}\r\nline\n".repeat(100)] {
            let positions = SourceMap::new(&text);
            for (scalar, byte) in text
                .char_indices()
                .map(|(byte, _)| byte)
                .chain(std::iter::once(text.len()))
                .enumerate()
            {
                let expected = SourceRange::from_bytes(&text, byte..byte).unwrap();
                assert_eq!(positions.range(byte..byte).unwrap(), expected);
                #[cfg(feature = "spellcheck")]
                assert_eq!(positions.scalar_range(scalar..scalar).unwrap(), expected);
                #[cfg(not(feature = "spellcheck"))]
                let _ = scalar;
            }
            assert!(positions.range(text.len() + 1..text.len() + 1).is_err());
            #[cfg(feature = "spellcheck")]
            assert!(
                positions
                    .scalar_range(text.chars().count() + 1..text.chars().count() + 1)
                    .is_err()
            );
        }
    }
}
