//! Real Poppler and Tesseract integration against independently specified PDFs.

use std::path::PathBuf;

use corpora_pdf::{
    ElementKind, ExtractOptions, ExtractionMethod, MarkKind, PdfError, ScoreBasis, extract_pdf,
};

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
}

#[test]
fn text_layer_preserves_content_and_evidence() {
    let result = extract_pdf(fixture("semantic.pdf"), &ExtractOptions::default()).unwrap();
    assert_eq!(result.pages.len(), 1);
    let page = &result.pages[0];
    assert_eq!(page.method, ExtractionMethod::TextLayer);
    assert_eq!(page.language.as_deref(), Some("eng"));
    assert!(!page.language_reliable);
    assert_eq!(page.elements[0].text, "Sample Document");
    assert_eq!(page.elements[0].kind, ElementKind::H1);
    assert!(
        page.elements
            .iter()
            .any(|e| e.kind == ElementKind::ListItem && e.text == "1. First item")
    );
    assert!(
        page.elements
            .iter()
            .any(|e| e.kind == ElementKind::Reference && e.text == "[1] Example Source.")
    );
    assert!(
        page.elements
            .iter()
            .any(|e| e.kind == ElementKind::TableCell && e.text == "42")
    );
    let link = page
        .elements
        .iter()
        .flat_map(|e| &e.marks)
        .find(|m| m.kind == MarkKind::Link)
        .unwrap();
    assert_eq!(
        link.target.as_deref(),
        Some("https://example.org/reference")
    );
    let score = page.extraction_score.as_ref().unwrap();
    assert_eq!(score.basis, ScoreBasis::TextLayerOcrAgreement);
    assert!(score.value > 0.6, "score: {}", score.value);
    assert_eq!(result.source_sha256.len(), 64);
    let repeated = extract_pdf(fixture("semantic.pdf"), &ExtractOptions::default()).unwrap();
    assert_eq!(
        serde_json::to_vec(&result).unwrap(),
        serde_json::to_vec(&repeated).unwrap()
    );
}

#[test]
fn scanned_page_uses_ocr_and_scores_it() {
    let result = extract_pdf(fixture("scanned.pdf"), &ExtractOptions::default()).unwrap();
    let page = &result.pages[0];
    assert_eq!(page.method, ExtractionMethod::Ocr);
    let text = page
        .elements
        .iter()
        .map(|e| e.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    assert!(text.contains("Sample Document"), "{text}");
    assert!(text.contains("First item"), "{text}");
    assert!(
        page.elements
            .iter()
            .any(|e| e.kind == ElementKind::H1 && e.text == "Sample Document")
    );
    assert!(
        page.elements
            .iter()
            .any(|e| e.kind == ElementKind::Reference && e.text.contains("Example Source"))
    );
    assert_eq!(
        page.extraction_score.as_ref().unwrap().basis,
        ScoreBasis::OcrWordConfidence
    );
    assert!(page.extraction_score.as_ref().unwrap().value > 0.5);
    assert!(page.elements.iter().any(|e| e.kind == ElementKind::Image));
    assert!(
        !fixture("scanned-1_1.png").exists(),
        "Poppler must not write beside the source"
    );
}

#[test]
fn mixed_pages_keep_pdf_order_and_distinct_methods() {
    let result = extract_pdf(fixture("mixed.pdf"), &ExtractOptions::default()).unwrap();
    assert_eq!(result.pages.len(), 2);
    assert_eq!(result.pages[0].number, 1);
    assert_eq!(result.pages[0].method, ExtractionMethod::TextLayer);
    assert_eq!(result.pages[1].number, 2);
    assert_eq!(result.pages[1].method, ExtractionMethod::Ocr);
}

#[test]
fn visual_check_can_be_skipped_for_text_layer() {
    let options = ExtractOptions {
        verify_text_layer_with_ocr: false,
        ..ExtractOptions::default()
    };
    let result = extract_pdf(fixture("semantic.pdf"), &options).unwrap();
    assert_eq!(result.pages[0].method, ExtractionMethod::TextLayer);
    assert!(result.pages[0].extraction_score.is_none());
}

#[test]
fn input_limits_and_invalid_header_block_extraction() {
    let options = ExtractOptions {
        max_pages: 0,
        ..ExtractOptions::default()
    };
    assert!(matches!(
        extract_pdf(fixture("semantic.pdf"), &options),
        Err(PdfError::Limit(_))
    ));
    let options = ExtractOptions {
        max_pdf_bytes: 10,
        ..ExtractOptions::default()
    };
    assert!(matches!(
        extract_pdf(fixture("semantic.pdf"), &options),
        Err(PdfError::Limit(_))
    ));
    let dir = tempfile::tempdir().unwrap();
    let invalid = dir.path().join("invalid.pdf");
    std::fs::write(&invalid, "not a PDF").unwrap();
    assert!(matches!(
        extract_pdf(invalid, &ExtractOptions::default()),
        Err(PdfError::Unsupported(_))
    ));
}
