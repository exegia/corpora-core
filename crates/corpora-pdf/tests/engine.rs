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
    let title = page
        .elements
        .iter()
        .find(|e| e.text == "Sample Document")
        .unwrap();
    assert_eq!(
        title
            .words
            .iter()
            .map(|word| word.text.as_str())
            .collect::<Vec<_>>(),
        ["Sample", "Document"]
    );
    assert!(
        title
            .words
            .iter()
            .all(|word| word.bounds.width > 0.0 && word.bounds.height > 0.0)
    );
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

fn isolated_english_models() -> tempfile::TempDir {
    let output = std::process::Command::new("tesseract")
        .arg("--list-langs")
        .output()
        .unwrap();
    assert!(output.status.success());
    let listing = String::from_utf8(output.stdout).unwrap();
    let installed = PathBuf::from(listing.lines().next().unwrap().split('"').nth(1).unwrap());
    let dir = tempfile::tempdir().unwrap();
    std::fs::copy(
        installed.join("eng.traineddata"),
        dir.path().join("eng.traineddata"),
    )
    .unwrap();
    dir
}

#[test]
fn explicit_model_directory_works_without_tsv_config_files() {
    let dir = isolated_english_models();
    let options = ExtractOptions {
        tessdata_dir: Some(dir.path().to_owned()),
        ..ExtractOptions::default()
    };
    let result = extract_pdf(fixture("scanned.pdf"), &options).unwrap();
    assert_eq!(result.pages[0].method, ExtractionMethod::Ocr);
    assert!(
        result.pages[0]
            .elements
            .iter()
            .any(|e| e.text == "Sample Document")
    );
}

#[test]
fn missing_companion_language_cannot_silently_fall_back_to_english() {
    let dir = isolated_english_models();
    let mut options = ExtractOptions {
        ocr_languages: "eng+heb".to_owned(),
        tessdata_dir: Some(dir.path().to_owned()),
        ..ExtractOptions::default()
    };
    let error = extract_pdf(fixture("scanned.pdf"), &options).unwrap_err();
    assert!(error.to_string().contains("\"heb\" is not installed"));
    let native = extract_pdf(fixture("semantic.pdf"), &options).unwrap();
    assert!(native.pages[0].extraction_score.is_none());
    assert!(
        native
            .findings
            .iter()
            .any(|finding| finding.code == "visual_check_unavailable")
    );
    options.verify_text_layer_with_ocr = false;
    let native = extract_pdf(fixture("semantic.pdf"), &options).unwrap();
    assert!(native.findings.is_empty());
}

#[test]
fn corrupt_companion_model_cannot_silently_fall_back_to_english() {
    let dir = isolated_english_models();
    std::fs::write(dir.path().join("heb.traineddata"), b"invalid model").unwrap();
    let options = ExtractOptions {
        ocr_languages: "eng+heb".to_owned(),
        tessdata_dir: Some(dir.path().to_owned()),
        ..ExtractOptions::default()
    };
    let error = extract_pdf(fixture("scanned.pdf"), &options).unwrap_err();
    assert!(
        error.to_string().contains("Failed loading language"),
        "{error}"
    );
}
