//! Conservative script risks, never inferred corrections or automatic vocalization.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use unicode_normalization::{UnicodeNormalization, char::is_combining_mark};

use crate::{Page, Rect};

/// A revision-pinned source region that needs visual review.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ScriptReview {
    /// Stable identity including source, location, script, and literal text revision.
    pub region_id: String,
    /// SHA-256 of the original PDF.
    pub source_sha256: String,
    /// One-based physical page number.
    pub page: usize,
    /// Zero-based element index in extraction order.
    pub element_index: usize,
    /// Zero-based OCR word index, or absent for an enclosing text element.
    pub word_index: Option<usize>,
    /// Enclosing word/element rectangle; not estimated character geometry.
    pub bounds: Rect,
    /// Coordinate system of bounds.
    pub coordinate_space: String,
    /// Half-open Unicode scalar range within `raw_text` (not UTF-8 bytes).
    pub scalar_range: [usize; 2],
    /// Script name; Hebrew does not distinguish Hebrew from Aramaic language.
    pub script: String,
    /// Literal unmodified engine text for this anchor.
    pub raw_text: String,
    /// SHA-256 of `raw_text` UTF-8 bytes for later optimistic revision checks.
    pub text_sha256: String,
    /// Combining marks observed after canonical decomposition, in source order.
    pub observed_marks: Vec<String>,
    /// Unknown until source evidence confirms missing marks; always null here.
    pub missing_marks: Option<Vec<String>>,
    /// Machine-readable risk code, not a confirmed transcription error.
    pub code: String,
    /// Consumer-facing explanation including source location.
    pub message: String,
    /// Review is required before accepting a source-faithful transcription.
    pub status: String,
}

const fn script(c: char) -> Option<&'static str> {
    match c as u32 {
        0x0590..=0x05ff | 0xfb1d..=0xfb4f => Some("hebrew"),
        0x0370..=0x03ff | 0x1f00..=0x1fff => Some("greek"),
        0x0600..=0x06ff | 0x0750..=0x077f | 0x08a0..=0x08ff | 0xfb50..=0xfdff | 0xfe70..=0xfeff => {
            Some("arabic")
        }
        0x0700..=0x074f | 0x0860..=0x086f => Some("syriac"),
        0x10380..=0x1039f => Some("ugaritic"),
        0x10900..=0x1091f => Some("phoenician"),
        0x12000..=0x1254f => Some("cuneiform"),
        0x0041..=0x005a | 0x0061..=0x007a | 0x00c0..=0x024f | 0x1e00..=0x1eff => Some("latin"),
        _ => None,
    }
}

/// Detect visible script runs only. Entirely lost scripts require caller-supplied
/// image-region hints; plain unpointed Hebrew is a review risk, not an error.
pub fn assess(source_sha256: &str, pages: &[Page]) -> Vec<ScriptReview> {
    let mut findings = Vec::new();
    for page in pages {
        for (element_index, element) in page.elements.iter().enumerate() {
            if element.words.is_empty() {
                findings.extend(assess_text(
                    source_sha256,
                    page.number,
                    element_index,
                    None,
                    element.bounds,
                    &element.text,
                ));
            } else {
                for (word_index, word) in element.words.iter().enumerate() {
                    findings.extend(assess_text(
                        source_sha256,
                        page.number,
                        element_index,
                        Some(word_index),
                        word.bounds,
                        &word.text,
                    ));
                }
            }
        }
    }
    findings
}

fn assess_text(
    source: &str,
    page: usize,
    element: usize,
    word: Option<usize>,
    bounds: Rect,
    text: &str,
) -> Vec<ScriptReview> {
    let chars: Vec<char> = text.chars().collect();
    let mut result = Vec::new();
    let mut start = 0;
    while start < chars.len() {
        let Some(name) = script(chars[start]) else {
            start += 1;
            continue;
        };
        let mut end = start + 1;
        while end < chars.len()
            && (script(chars[end]) == Some(name) || is_combining_mark(chars[end]))
        {
            end += 1;
        }
        let run: String = chars[start..end].iter().collect();
        let observed_marks: Vec<String> = run
            .nfd()
            .filter(|c| is_combining_mark(*c))
            .map(|c| format!("U+{:04X}", c as u32))
            .collect();
        if name != "latin" || !observed_marks.is_empty() {
            let text_sha256 = format!("{:x}", Sha256::digest(text.as_bytes()));
            let identity = format!(
                "{source}:{page}:{element}:{word:?}:{start}:{end}:{name}:{text_sha256}:{}:{}:{}:{}",
                bounds.x, bounds.y, bounds.width, bounds.height
            );
            let unsupported = matches!(name, "ugaritic" | "phoenician" | "cuneiform");
            result.push(ScriptReview {
                region_id: format!("{:x}", Sha256::digest(identity.as_bytes())),
                source_sha256: source.to_owned(), page, element_index: element,
                word_index: word, bounds, coordinate_space: "poppler_108_dpi_top_left".into(),
                scalar_range: [start, end], script: name.into(), raw_text: text.into(),
                text_sha256, observed_marks, missing_marks: None,
                code: if unsupported { "script_model_unverified" } else { "script_marks_review" }.into(),
                message: format!("Page {page}, element {element}, word {word:?}, scalar range {start}..{end}: {name} requires image review. {} Exact missing marks are unknown; unmarked text may be intentional.",
                    if unsupported { "No specialist model is validated for this script." }
                    else { "OCR can omit or move pointing and accents." }),
                status: "review_required".into(),
            });
        }
        start = end;
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    const BOX: Rect = Rect {
        x: 1.0,
        y: 2.0,
        width: 3.0,
        height: 4.0,
    };
    fn check(text: &str) -> Vec<ScriptReview> {
        assess_text("source", 2, 3, Some(0), BOX, text)
    }
    #[test]
    fn anchors_are_scalar_based_stable_and_revision_sensitive() {
        let findings = check("😀 לֹא ἄ");
        assert_eq!(findings.len(), 2);
        assert_eq!(findings[0].scalar_range, [2, 5]);
        assert_eq!(findings[0].observed_marks, ["U+05B9"]);
        assert_eq!(findings[0].region_id, check("😀 לֹא ἄ")[0].region_id);
        assert_ne!(findings[0].region_id, check("😀 לָא ἄ")[0].region_id);
        assert!(findings.iter().all(|f| f.missing_marks.is_none()));
    }
    #[test]
    fn unpointed_is_not_a_missing_mark_claim() {
        let finding = &check("לא")[0];
        assert_eq!(finding.observed_marks, [] as [String; 0]);
        assert!(finding.missing_marks.is_none());
        assert!(finding.message.contains("may be intentional"));
        assert!(check("English words").is_empty());
        assert_eq!(check("ā")[0].observed_marks, ["U+0304"]);
        assert_eq!(check("𐎀")[0].code, "script_model_unverified");
    }
    #[test]
    fn canonical_equivalents_keep_original_ranges() {
        assert_eq!(
            check("ἄ")[0].observed_marks,
            check("α\u{313}\u{301}")[0].observed_marks
        );
        assert_eq!(check("ἄ")[0].scalar_range, [0, 1]);
        assert_eq!(check("α\u{313}\u{301}")[0].scalar_range, [0, 3]);
    }
    #[test]
    fn real_word_geometry_is_preferred_over_element_geometry() {
        let page: Page = serde_json::from_value(serde_json::json!({
            "number": 1, "width": 100.0, "height": 200.0,
            "language": null, "language_reliable": false, "method": "ocr",
            "extraction_score": null, "elements": [{
                "kind": "paragraph", "text": "לֹא", "bounds": BOX,
                "marks": [], "section_path": [], "table_id": null,
                "extraction_score": null, "words": [{
                    "text": "לֹא", "confidence": 0.99,
                    "bounds": {"x": 10.0, "y": 20.0, "width": 5.0, "height": 6.0}
                }]
            }]
        }))
        .unwrap();
        let findings = assess("source", &[page]);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].word_index, Some(0));
        assert!((findings[0].bounds.x - 10.0).abs() < f32::EPSILON);
        assert_eq!(findings[0].raw_text, "לֹא");
    }

    #[test]
    fn legacy_extraction_deserializes() {
        let extraction: crate::PdfExtraction = serde_json::from_str(
            r#"{"source_path":"test.pdf","source_sha256":"sha","pages":[],"findings":[]}"#,
        )
        .unwrap();
        assert!(extraction.script_review.is_empty());
    }
}
