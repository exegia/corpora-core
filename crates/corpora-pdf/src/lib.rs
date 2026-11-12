//! Local PDF text, layout, and OCR extraction.
//!
//! The engine invokes Poppler (`pdfinfo`, `pdftohtml`, `pdftoppm`) and
//! Tesseract. It does not download models or expose an API server. The
//! `corpora-pdf-extract` binary prints one extraction as JSON for consumers
//! such as `packages/pdf-to-tf`. Semantic labels and scores are evidence-backed
//! estimates, not a claim of ground-truth transcription accuracy.

// whatlang and the JSON bridge's serde_json resolve two transitive hash table versions.
#![expect(
    clippy::multiple_crate_versions,
    reason = "transitive whatlang and serde_json dependency graph"
)]

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

mod native;
pub mod review;
mod semantics;

/// Limits and installed OCR language data used by [`extract_pdf`].
#[derive(Clone, Debug)]
pub struct ExtractOptions {
    /// Maximum PDF bytes accepted before invoking external tools.
    pub max_pdf_bytes: u64,
    /// Maximum number of pages accepted.
    pub max_pages: usize,
    /// Maximum number of extracted elements accepted on one page.
    pub max_elements_per_page: usize,
    /// Longest rendered page edge in pixels for OCR.
    pub ocr_max_edge_px: u32,
    /// Tesseract language code or installed language combination, e.g. `eng+fra`.
    pub ocr_languages: String,
    /// Explicit directory of installed `.traineddata` files. When absent,
    /// Tesseract uses its normal environment/default lookup.
    pub tessdata_dir: Option<PathBuf>,
    /// Run visual OCR even when a PDF text layer exists to estimate agreement.
    pub verify_text_layer_with_ocr: bool,
}

impl Default for ExtractOptions {
    fn default() -> Self {
        Self {
            max_pdf_bytes: 100 * 1024 * 1024,
            max_pages: 200,
            max_elements_per_page: 20_000,
            ocr_max_edge_px: 2_400,
            ocr_languages: "eng".to_owned(),
            tessdata_dir: None,
            verify_text_layer_with_ocr: true,
        }
    }
}

/// A source PDF and its extracted pages.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PdfExtraction {
    /// Canonical local path used for extraction.
    pub source_path: PathBuf,
    /// SHA-256 of the original PDF bytes.
    pub source_sha256: String,
    /// Source PDF page count.
    pub pages: Vec<Page>,
    /// Nonfatal extraction and interpretation findings.
    pub findings: Vec<Finding>,
    /// Location-linked script risks; absent in older serialized extractions.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub script_review: Vec<review::ScriptReview>,
}

/// One PDF page in source order.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Page {
    /// One-based page number.
    pub number: usize,
    /// Page width in Poppler's XML layout units (108 DPI).
    pub width: f32,
    /// Page height in Poppler's XML layout units (108 DPI).
    pub height: f32,
    /// Language inferred from extracted text, when enough evidence exists.
    pub language: Option<String>,
    /// Whether language detection had enough evidence to be considered reliable.
    pub language_reliable: bool,
    /// Text-layer extraction or image OCR.
    pub method: ExtractionMethod,
    /// Layout and semantic elements in reading order.
    pub elements: Vec<Element>,
    /// A visual evidence estimate for this page.
    pub extraction_score: Option<ExtractionScore>,
}

/// Which source yielded the exported page text.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExtractionMethod {
    /// PDF text objects interpreted by Poppler.
    TextLayer,
    /// Tesseract text from a rendered page image.
    Ocr,
    /// No text was obtained.
    None,
}

/// Page-local rectangle in Poppler's 108-DPI layout coordinates.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Rect {
    /// Left position.
    pub x: f32,
    /// Top position.
    pub y: f32,
    /// Width.
    pub width: f32,
    /// Height.
    pub height: f32,
}

/// Extracted content or an inferred semantic structure.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Element {
    /// Semantic or visual classification.
    pub kind: ElementKind,
    /// Visible text, when available.
    pub text: String,
    /// Position in the source page; OCR coordinates are scaled to layout units.
    pub bounds: Rect,
    /// Inline formatting and link evidence.
    pub marks: Vec<InlineMark>,
    /// Current heading ancestry for this element.
    pub section_path: Vec<String>,
    /// Shared row-group identifier for cells inferred to be in one table.
    pub table_id: Option<usize>,
    /// One-based number of the visual paragraph a `paragraph` line belongs to,
    /// counted through the document. Lines of one paragraph share it, including a
    /// paragraph that continues on the next page. `None` for other labels; older
    /// serialized results may omit this field.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paragraph: Option<usize>,
    /// Element-specific visual estimate when one is available.
    pub extraction_score: Option<ExtractionScore>,
    /// OCR words in recognition order, retaining individual geometry and confidence.
    /// Empty for text-layer elements; older serialized results may omit this field.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub words: Vec<Word>,
}

/// One OCR word and its source-page evidence. Text is never reversed or corrected.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Word {
    /// Text emitted by the OCR engine, including Unicode combining marks.
    pub text: String,
    /// Page-local rectangle in the same units as the enclosing element.
    pub bounds: Rect,
    /// OCR word confidence from zero to one, not measured transcription accuracy.
    pub confidence: f32,
}

/// Semantic labels. Heuristic labels are never presented as source PDF tags.
/// New labels may be added, so match with a wildcard arm.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[non_exhaustive]
pub enum ElementKind {
    /// First-level heading candidate.
    H1,
    /// Second-level heading candidate.
    H2,
    /// Third-level heading candidate.
    H3,
    /// Fourth-level heading candidate.
    H4,
    /// Paragraph or unclassified text.
    Paragraph,
    /// List item candidate.
    ListItem,
    /// Citation marker or citation text candidate.
    Citation,
    /// Bibliographic reference candidate.
    Reference,
    /// Cell in a layout-detected table.
    TableCell,
    /// Embedded image whose semantics are unknown.
    Image,
    /// Possible graph based on image placement and nearby caption.
    GraphCandidate,
    /// Footnote line: below the page's footnote rule, or under a "cover page
    /// footnote" label.
    Footnote,
    /// Repeated text (or a page number) in the top margin band.
    RunningHeader,
    /// Repeated text (or a page number) in the bottom margin band, or a block set
    /// apart at the foot of the page.
    RunningFooter,
    /// Document title on a front-matter page.
    Title,
    /// Author line under the title on a front-matter page.
    Author,
    /// Institution or contact line under the author.
    Affiliation,
    /// Journal or series title above the issue details on a front-matter page.
    JournalTitle,
    /// Volume, issue, article number or date on a front-matter page.
    PublicationMetadata,
    /// Line under an "Abstract" label.
    Abstract,
    /// Line under a "Keywords" label.
    Keywords,
}

/// A source-observed inline mark.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InlineMark {
    /// Bold, italic, or link.
    pub kind: MarkKind,
    /// Marked visible text.
    pub text: String,
    /// Destination for links; absent for emphasis.
    pub target: Option<String>,
}

/// Inline formatting type.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MarkKind {
    /// Bold text.
    Bold,
    /// Italic text.
    Italic,
    /// PDF link annotation.
    Link,
}

/// A score supported by visual OCR evidence, from zero to one.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExtractionScore {
    /// Estimate between 0 and 1, not ground-truth accuracy.
    pub value: f32,
    /// Evidence used to compute the estimate.
    pub basis: ScoreBasis,
}

/// Meaning of a score.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreBasis {
    /// Mean Tesseract word confidence on a rendered page.
    OcrWordConfidence,
    /// Token overlap between the PDF text layer and rendered-page OCR.
    TextLayerOcrAgreement,
}

/// A limitation or problem at an actionable PDF page.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Finding {
    /// One-based page, if the finding concerns a page.
    pub page: Option<usize>,
    /// Stable machine-readable code.
    pub code: String,
    /// Plain-language detail.
    pub message: String,
}

/// Extraction failure that prevents a trustworthy result.
#[derive(Debug, Error)]
pub enum PdfError {
    /// Input or temporary file I/O failed.
    #[error("PDF I/O error: {0}")]
    Io(#[from] std::io::Error),
    /// PDF size or page limit was exceeded.
    #[error("PDF input exceeds configured limit: {0}")]
    Limit(String),
    /// PDF is encrypted or has no parseable pages.
    #[error("unsupported PDF: {0}")]
    Unsupported(String),
    /// Required local program was absent or failed.
    #[error("{program} failed: {detail}")]
    Tool {
        /// Program name.
        program: &'static str,
        /// Error detail.
        detail: String,
    },
    /// Generated layout XML could not be read.
    #[error("Poppler layout XML is invalid: {0}")]
    Layout(String),
}

/// Extract a bounded local PDF using Poppler and Tesseract.
///
/// A missing Tesseract installation is fatal for image-only pages. On pages
/// with a text layer, failed optional visual verification becomes a finding.
#[allow(clippy::too_many_lines)] // Keep one page pipeline while findings share mutable state.
pub fn extract_pdf(
    path: impl AsRef<Path>,
    options: &ExtractOptions,
) -> Result<PdfExtraction, PdfError> {
    if !(256..=8_192).contains(&options.ocr_max_edge_px) {
        return Err(PdfError::Limit(
            "ocr_max_edge_px must be between 256 and 8192".to_owned(),
        ));
    }
    let path = fs::canonicalize(path)?;
    let input_len = fs::metadata(&path)?.len();
    if input_len > options.max_pdf_bytes {
        return Err(PdfError::Limit(format!(
            "{input_len} bytes (max {})",
            options.max_pdf_bytes
        )));
    }
    let bytes = fs::read(&path)?;
    if bytes.len() as u64 > options.max_pdf_bytes {
        return Err(PdfError::Limit(format!(
            "{} bytes (max {})",
            bytes.len(),
            options.max_pdf_bytes
        )));
    }
    if !bytes.starts_with(b"%PDF-") {
        return Err(PdfError::Unsupported("file has no PDF header".to_owned()));
    }
    let hash = format!("{:x}", Sha256::digest(&bytes));
    let info = run("pdfinfo", &[path.as_os_str()])?;
    let info = String::from_utf8_lossy(&info);
    if info
        .lines()
        .any(|line| line.starts_with("Encrypted:") && !line.contains("no"))
    {
        return Err(PdfError::Unsupported(
            "encrypted PDFs require an unlocked copy".to_owned(),
        ));
    }
    let count = info
        .lines()
        .find_map(|line| {
            line.strip_prefix("Pages:")
                .and_then(|n| n.trim().parse::<usize>().ok())
        })
        .ok_or_else(|| PdfError::Unsupported("pdfinfo did not report a page count".to_owned()))?;
    if count == 0 || count > options.max_pages {
        return Err(PdfError::Limit(format!(
            "{count} pages (max {})",
            options.max_pages
        )));
    }

    let scratch = tempfile::tempdir()?;
    // Poppler writes extracted image files beside its input even with -stdout.
    // Work from a private copy so extraction never mutates the source folder.
    let working_pdf = scratch.path().join("source.pdf");
    fs::copy(&path, &working_pdf)?;
    let xml = run_in(
        "pdftohtml",
        &[
            "-xml".as_ref(),
            "-hidden".as_ref(),
            "-stdout".as_ref(),
            working_pdf.as_os_str(),
        ],
        scratch.path(),
    )?;
    let xml = String::from_utf8(xml).map_err(|e| PdfError::Layout(e.to_string()))?;
    let xml = xml
        .lines()
        .filter(|line| !line.trim_start().starts_with("<!DOCTYPE"))
        .collect::<Vec<_>>()
        .join("\n");
    let doc = roxmltree::Document::parse(&xml).map_err(|e| PdfError::Layout(e.to_string()))?;
    let xml_pages: Vec<_> = doc
        .descendants()
        .filter(|node| node.has_tag_name("page"))
        .collect();
    if xml_pages.len() != count {
        return Err(PdfError::Layout(format!(
            "pdfinfo reported {count} pages, layout returned {}",
            xml_pages.len()
        )));
    }

    let mut findings = Vec::new();
    let mut pages = Vec::with_capacity(count);
    let mut layouts = Vec::with_capacity(count);
    for (index, page_node) in xml_pages.into_iter().enumerate() {
        let number = index + 1;
        let width = attribute_f32(page_node, "width")?;
        let height = attribute_f32(page_node, "height")?;
        let font_sizes: HashMap<&str, f32> = doc
            .descendants()
            .filter(|n| n.has_tag_name("fontspec"))
            .filter_map(|n| Some((n.attribute("id")?, n.attribute("size")?.parse().ok()?)))
            .collect();
        let (mut elements, mut line_styles): (Vec<Element>, Vec<native::LineStyle>) =
            native::parse_elements(page_node, &font_sizes)?
                .into_iter()
                .unzip();
        if elements.len() > options.max_elements_per_page {
            return Err(PdfError::Limit(format!(
                "page {number} has {} elements (max {})",
                elements.len(),
                options.max_elements_per_page
            )));
        }
        classify(&mut elements, true);
        let has_text = elements.iter().any(|e| !e.text.trim().is_empty());
        let ocr = if !has_text || options.verify_text_layer_with_ocr {
            match ocr_page(&path, number, width, height, options, scratch.path()) {
                Ok(value) => Some(value),
                Err(error) if has_text => {
                    findings.push(Finding {
                        page: Some(number),
                        code: "visual_check_unavailable".to_owned(),
                        message: error.to_string(),
                    });
                    None
                }
                Err(error) => return Err(error),
            }
        } else {
            None
        };
        let (method, score) = if has_text {
            let score = ocr.as_ref().and_then(|words| agreement(&elements, words));
            if let Some(ref value) = score {
                for element in &mut elements {
                    element.extraction_score =
                        element_agreement(element, ocr.as_deref().unwrap_or_default());
                }
                if value.value < 0.6 {
                    findings.push(Finding {
                        page: Some(number),
                        code: "low_visual_agreement".to_owned(),
                        message: format!(
                            "text layer and page-image OCR agree at {:.0}% token overlap",
                            value.value * 100.0
                        ),
                    });
                }
            }
            (ExtractionMethod::TextLayer, score)
        } else if let Some(words) = ocr {
            let mut text_elements = ocr_elements(&words);
            if elements.len() + text_elements.len() > options.max_elements_per_page {
                return Err(PdfError::Limit(format!(
                    "page {number} has too many OCR elements (max {})",
                    options.max_elements_per_page
                )));
            }
            if text_elements.is_empty() {
                findings.push(Finding {
                    page: Some(number),
                    code: "no_text_found".to_owned(),
                    message: "neither the text layer nor OCR yielded text".to_owned(),
                });
                (ExtractionMethod::None, None)
            } else {
                // TSV block/paragraph/line order carries Tesseract's column layout.
                // A global y/x sort interleaves columns and invalidates section paths.
                classify(&mut text_elements, false);
                line_styles.extend(text_elements.iter().map(|e| native::LineStyle {
                    size: e.bounds.height,
                    emphasized: false,
                }));
                elements.extend(text_elements);
                let score = mean_ocr_confidence(&words);
                if let Some(ref value) = score {
                    if value.value < 0.6 {
                        findings.push(Finding {
                            page: Some(number),
                            code: "low_ocr_confidence".to_owned(),
                            message: format!(
                                "OCR mean word confidence is {:.0}%",
                                value.value * 100.0
                            ),
                        });
                    }
                }
                (ExtractionMethod::Ocr, score)
            }
        } else {
            (ExtractionMethod::None, None)
        };
        let text = elements
            .iter()
            .map(|e| e.text.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        let detection = whatlang::detect(&text);
        let language = detection.as_ref().map(|info| info.lang().code().to_owned());
        let language_reliable = detection.as_ref().is_some_and(whatlang::Info::is_reliable);
        if elements
            .iter()
            .any(|e| matches!(e.kind, ElementKind::Image | ElementKind::GraphCandidate))
        {
            findings.push(Finding {
                page: Some(number),
                code: "visual_semantics_unverified".to_owned(),
                message: "image or possible graph content needs human review".to_owned(),
            });
        }
        layouts.push(line_styles);
        pages.push(Page {
            number,
            width,
            height,
            language,
            language_reliable,
            method,
            elements,
            extraction_score: score,
        });
    }
    semantics::label_document(&mut pages, &mut layouts);
    let script_review = review::assess(&hash, &pages);
    Ok(PdfExtraction {
        source_path: path,
        source_sha256: hash,
        pages,
        findings,
        script_review,
    })
}

fn run(program: &'static str, args: &[&std::ffi::OsStr]) -> Result<Vec<u8>, PdfError> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|e| PdfError::Tool {
            program,
            detail: e.to_string(),
        })?;
    if !output.status.success() {
        return Err(PdfError::Tool {
            program,
            detail: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        });
    }
    Ok(output.stdout)
}

fn run_in(
    program: &'static str,
    args: &[&std::ffi::OsStr],
    dir: &Path,
) -> Result<Vec<u8>, PdfError> {
    let output = Command::new(program)
        .args(args)
        .current_dir(dir)
        .output()
        .map_err(|e| PdfError::Tool {
            program,
            detail: e.to_string(),
        })?;
    if !output.status.success() {
        return Err(PdfError::Tool {
            program,
            detail: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        });
    }
    Ok(output.stdout)
}

fn attribute_f32(node: roxmltree::Node<'_, '_>, name: &str) -> Result<f32, PdfError> {
    node.attribute(name)
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| PdfError::Layout(format!("missing or invalid {name} attribute")))
}

fn classify(elements: &mut [Element], infer_native_tables: bool) {
    let mut headings: Vec<String> = Vec::new();
    let mut reference_section = false;
    let mut rows: Vec<(f32, Vec<usize>)> = Vec::new();
    for (index, element) in elements.iter().enumerate() {
        // Whitespace-only fragments (indents, trailing spaces) are never table cells.
        if !element.text.trim().is_empty() {
            if let Some((_, row)) = rows
                .iter_mut()
                .find(|(y, _)| (*y - element.bounds.y).abs() < 1.0)
            {
                row.push(index);
            } else {
                rows.push((element.bounds.y, vec![index]));
            }
        }
    }
    let table_ids = if infer_native_tables {
        table_groups(&mut rows, elements)
    } else {
        // OCR cells already require repeated, aligned gaps within a block.
        // Aligned prose lines from separate columns are not a table.
        elements
            .iter()
            .enumerate()
            .filter_map(|(index, element)| element.table_id.map(|id| (index, id)))
            .collect()
    };
    let captions: Vec<(String, f32)> = elements
        .iter()
        .filter(|e| !e.text.is_empty())
        .map(|e| (e.text.to_lowercase(), e.bounds.y))
        .collect();
    for (index, element) in elements.iter_mut().enumerate() {
        let trimmed = element.text.trim();
        let heading_level = match element.kind {
            ElementKind::H1 => 1,
            ElementKind::H2 => 2,
            ElementKind::H3 => 3,
            ElementKind::H4 => 4,
            _ => 0,
        };
        if heading_level > 0 {
            headings.truncate(heading_level - 1);
            headings.push(trimmed.to_owned());
            reference_section = trimmed.eq_ignore_ascii_case("references")
                || trimmed.eq_ignore_ascii_case("bibliography");
        } else if element.kind == ElementKind::Image
            && captions.iter().any(|(text, y)| {
                (text.starts_with("figure ")
                    || text.starts_with("fig. ")
                    || text.starts_with("graph ")
                    || text.starts_with("chart "))
                    && (*y - element.bounds.y - element.bounds.height).abs() < 60.0
            })
        {
            element.kind = ElementKind::GraphCandidate;
        } else if let Some(table_id) = table_ids.get(&index) {
            element.kind = ElementKind::TableCell;
            element.table_id = Some(*table_id);
        } else if is_list_item(trimmed) {
            element.kind = ElementKind::ListItem;
        } else if reference_section && trimmed.starts_with('[') {
            element.kind = ElementKind::Reference;
        } else if has_numeric_citation(trimmed) {
            element.kind = ElementKind::Citation;
        }
        element.section_path.clone_from(&headings);
    }
}

fn table_groups(rows: &mut [(f32, Vec<usize>)], elements: &[Element]) -> HashMap<usize, usize> {
    rows.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut ids = HashMap::new();
    let mut group: Vec<&(f32, Vec<usize>)> = Vec::new();
    let mut next_id = 1;
    let flush = |group: &mut Vec<&(f32, Vec<usize>)>,
                 ids: &mut HashMap<usize, usize>,
                 next_id: &mut usize| {
        if group.len() >= 2 {
            for (_, row) in group.iter() {
                for index in row {
                    ids.insert(*index, *next_id);
                }
            }
            *next_id += 1;
        }
        group.clear();
    };
    // As on OCR pages: a table row has at least one short cell, and consecutive rows
    // have the same number of cells starting at the same places. Two prose columns
    // that happen to share baselines have neither.
    let short_cell = |row: &[usize]| {
        row.iter().any(|&i| {
            let bounds = &elements[i].bounds;
            bounds.width <= bounds.height.max(1.0) * 4.0
        })
    };
    let lefts = |row: &[usize]| {
        let mut lefts: Vec<f32> = row.iter().map(|&i| elements[i].bounds.x).collect();
        lefts.sort_by(f32::total_cmp);
        lefts
    };
    let aligned = |a: &[usize], b: &[usize], height: f32| {
        a.len() == b.len()
            && lefts(a)
                .iter()
                .zip(lefts(b))
                .all(|(x, y)| (x - y).abs() <= height * 1.5)
    };
    for row in rows
        .iter()
        .filter(|(_, cells)| cells.len() >= 2 && short_cell(cells))
    {
        if let Some(previous) = group.last() {
            let height = elements[previous.1[0]].bounds.height.max(1.0);
            if row.0 - previous.0 > height * 2.5 || !aligned(&previous.1, &row.1, height) {
                flush(&mut group, &mut ids, &mut next_id);
            }
        }
        group.push(row);
    }
    flush(&mut group, &mut ids, &mut next_id);
    ids
}

fn is_list_item(text: &str) -> bool {
    let text = text.trim_start();
    if text.starts_with("• ") || text.starts_with("- ") {
        return true;
    }
    // A numbered marker is followed by a space and more text: "1. First", not a
    // DOI such as "10.70623/NAJW4433." or a lone continued page number "243.".
    let digits = text.bytes().take_while(u8::is_ascii_digit).count();
    digits > 0
        && digits < 4
        && matches!(text.as_bytes().get(digits), Some(b'.' | b')'))
        && text[digits + 1..].starts_with(char::is_whitespace)
        && !text[digits + 1..].trim().is_empty()
}

/// A bracketed numeric citation such as `[1]`, `[2, 5]` or `[3-7]`. Brackets that
/// hold words (an editorial `[it]`) are not citations.
fn has_numeric_citation(text: &str) -> bool {
    text.split('[').skip(1).any(|rest| {
        rest.split_once(']').is_some_and(|(inside, _)| {
            inside.chars().any(|c| c.is_ascii_digit())
                && inside
                    .chars()
                    .all(|c| c.is_ascii_digit() || matches!(c, ',' | '-' | '–' | ' '))
        })
    })
}

#[derive(Clone, Debug)]
struct OcrWord {
    text: String,
    confidence: f32,
    left: f32,
    top: f32,
    width: f32,
    height: f32,
    line: (i32, i32, i32),
}

#[allow(clippy::cast_precision_loss)] // Pixel scaling is inherently approximate.
fn ocr_page(
    path: &Path,
    number: usize,
    width: f32,
    height: f32,
    options: &ExtractOptions,
    dir: &Path,
) -> Result<Vec<OcrWord>, PdfError> {
    validate_ocr_languages(options)?;
    let prefix = dir.join(format!("page-{number}"));
    let number_arg = number.to_string();
    let edge_arg = options.ocr_max_edge_px.to_string();
    run(
        "pdftoppm",
        &[
            "-f".as_ref(),
            number_arg.as_ref(),
            "-l".as_ref(),
            number_arg.as_ref(),
            "-singlefile".as_ref(),
            "-scale-to".as_ref(),
            edge_arg.as_ref(),
            "-png".as_ref(),
            path.as_os_str(),
            prefix.as_os_str(),
        ],
    )?;
    let image = prefix.with_extension("png");
    let mut args = vec![
        image.as_os_str(),
        "stdout".as_ref(),
        "-l".as_ref(),
        options.ocr_languages.as_ref(),
        "-c".as_ref(),
        "tessedit_create_tsv=1".as_ref(),
    ];
    if let Some(dir) = &options.tessdata_dir {
        args.extend(["--tessdata-dir".as_ref(), dir.as_os_str()]);
    }
    let output = Command::new("tesseract")
        .args(args)
        .output()
        .map_err(|error| PdfError::Tool {
            program: "tesseract",
            detail: error.to_string(),
        })?;
    let detail = String::from_utf8_lossy(&output.stderr);
    // Tesseract can exit successfully after failing one model in eng+heb.
    // A listed but corrupt model must not silently degrade to another language.
    if !output.status.success()
        || detail.contains("Failed loading language")
        || detail.contains("Error opening data file")
    {
        return Err(PdfError::Tool {
            program: "tesseract",
            detail: detail.trim().to_owned(),
        });
    }
    let tsv = String::from_utf8_lossy(&output.stdout);
    if !tsv.starts_with("level\tpage_num\t") {
        return Err(PdfError::Tool {
            program: "tesseract",
            detail: "OCR returned no TSV header".to_owned(),
        });
    }
    let scale = (options.ocr_max_edge_px as f32 / width.max(height)).max(0.01);
    let mut words = Vec::new();
    for row in tsv.lines().skip(1) {
        let columns: Vec<&str> = row.splitn(12, '\t').collect();
        if columns.len() != 12 || columns[0] != "5" || columns[11].trim().is_empty() {
            continue;
        }
        let parse = |n: usize| columns[n].parse::<f32>().ok();
        let (Some(left), Some(top), Some(w), Some(h), Some(conf)) =
            (parse(6), parse(7), parse(8), parse(9), parse(10))
        else {
            continue;
        };
        if conf < 0.0 {
            continue;
        }
        let line = (
            columns[2].parse().unwrap_or(0),
            columns[3].parse().unwrap_or(0),
            columns[4].parse().unwrap_or(0),
        );
        words.push(OcrWord {
            text: columns[11].to_owned(),
            confidence: conf / 100.0,
            left: left / scale,
            top: top / scale,
            width: w / scale,
            height: h / scale,
            line,
        });
    }
    Ok(words)
}

fn validate_ocr_languages(options: &ExtractOptions) -> Result<(), PdfError> {
    let mut args = vec!["--list-langs".as_ref()];
    if let Some(dir) = &options.tessdata_dir {
        if !dir.is_dir() {
            return Err(PdfError::Tool {
                program: "tesseract",
                detail: format!("model directory does not exist: {}", dir.display()),
            });
        }
        args.extend(["--tessdata-dir".as_ref(), dir.as_os_str()]);
    }
    let listing = run("tesseract", &args)?;
    let listing = String::from_utf8_lossy(&listing);
    for language in options.ocr_languages.split('+') {
        if language.is_empty() || !listing.lines().skip(1).any(|line| line.trim() == language) {
            return Err(PdfError::Tool {
                program: "tesseract",
                detail: format!(
                    "requested OCR language {language:?} is not installed; requested {}",
                    options.ocr_languages
                ),
            });
        }
    }
    Ok(())
}

fn ocr_elements(words: &[OcrWord]) -> Vec<Element> {
    let mut rows: BTreeMap<(i32, i32, i32), Vec<&OcrWord>> = BTreeMap::new();
    for word in words {
        rows.entry(word.line).or_default().push(word);
    }
    let rows: Vec<_> = rows.into_values().collect();
    let candidates: Vec<_> = rows.iter().map(|row| split_cells(row)).collect();
    let mut elements = Vec::new();
    let mut table_id = 0;
    let mut previous_is_table = false;
    for (index, row) in rows.iter().enumerate() {
        let matches_previous =
            index > 0 && aligned_cells(&candidates[index - 1], &candidates[index]);
        let matches_next =
            index + 1 < rows.len() && aligned_cells(&candidates[index], &candidates[index + 1]);
        let is_table = matches_previous || matches_next;
        if is_table {
            if !previous_is_table || !matches_previous {
                table_id += 1;
            }
            for cell in &candidates[index] {
                let mut element = ocr_element(cell);
                element.kind = ElementKind::TableCell;
                element.table_id = Some(table_id);
                elements.push(element);
            }
        } else {
            elements.push(ocr_element(row));
        }
        previous_is_table = is_table;
    }
    let mut heights: Vec<f32> = elements.iter().map(|e| e.bounds.height).collect();
    heights.sort_by(f32::total_cmp);
    let body_height = heights
        .get(heights.len() / 2)
        .copied()
        .unwrap_or(1.0)
        .max(1.0);
    for element in &mut elements {
        if element.table_id.is_some() {
            continue;
        }
        let short = element.text.split_whitespace().count() <= 8;
        let ratio = element.bounds.height / body_height;
        element.kind = if element.text.eq_ignore_ascii_case("references")
            || element.text.eq_ignore_ascii_case("bibliography")
        {
            ElementKind::H2
        } else if short && ratio >= 1.45 {
            ElementKind::H1
        } else if short && ratio >= 1.25 {
            ElementKind::H2
        } else if short && ratio >= 1.15 {
            ElementKind::H3
        } else {
            ElementKind::Paragraph
        };
    }
    elements
}

fn row_height(row: &[&OcrWord]) -> f32 {
    let mut heights: Vec<_> = row.iter().map(|word| word.height).collect();
    heights.sort_by(f32::total_cmp);
    heights
        .get(heights.len() / 2)
        .copied()
        .unwrap_or(1.0)
        .max(1.0)
}

fn split_cells<'a>(row: &[&'a OcrWord]) -> Vec<Vec<&'a OcrWord>> {
    let threshold = row_height(row) * 1.5;
    let mut cells = Vec::new();
    let mut cell = Vec::new();
    let mut previous: Option<&OcrWord> = None;
    for &word in row {
        if let Some(prev) = previous {
            // Handle either spatial direction without changing recognition order.
            let gap = (word.left - prev.left - prev.width).max(prev.left - word.left - word.width);
            if gap > threshold {
                cells.push(std::mem::take(&mut cell));
            }
        }
        cell.push(word);
        previous = Some(word);
    }
    if !cell.is_empty() {
        cells.push(cell);
    }
    cells
}

fn aligned_cells(first: &[Vec<&OcrWord>], second: &[Vec<&OcrWord>]) -> bool {
    if first.len() < 2 || first.len() != second.len() {
        return false;
    }
    // Hanging-indent lists also have repeated wide gaps and a short first cell.
    // Keep their marker attached so semantic classification can recognize it.
    let list_lead = |cells: &[Vec<&OcrWord>]| {
        let lead = cells[0][0].text.as_str();
        let digits = lead.bytes().take_while(u8::is_ascii_digit).count();
        let numbered = (1..4).contains(&digits) && matches!(&lead[digits..], "." | ")");
        numbered || is_list_item(lead) || matches!(lead, "•" | "-" | "–")
    };
    if list_lead(first) || list_lead(second) {
        return false;
    }
    let a = first[0][0];
    let b = second[0][0];
    let height = row_height(&first.iter().flatten().copied().collect::<Vec<_>>());
    if a.line.0 != b.line.0 || (a.top - b.top).abs() > height * 3.0 {
        return false;
    }
    // A short cell plus repeated alignment is evidence for a table, unlike two
    // long, justified prose columns. Complex/wrapped cells remain unsupported.
    let short_cell = |cells: &[Vec<&OcrWord>]| {
        cells.iter().any(|cell| {
            let left = cell.iter().map(|w| w.left).fold(f32::INFINITY, f32::min);
            let right = cell.iter().map(|w| w.left + w.width).fold(0.0, f32::max);
            right - left <= height * 4.0
        })
    };
    short_cell(first)
        && short_cell(second)
        && first.iter().zip(second).all(|(left, right)| {
            left.len() <= 8
                && right.len() <= 8
                && (left.iter().map(|w| w.left).fold(f32::INFINITY, f32::min)
                    - right.iter().map(|w| w.left).fold(f32::INFINITY, f32::min))
                .abs()
                    <= height * 1.5
        })
}

#[allow(clippy::cast_precision_loss)] // Confidence is an approximate mean.
fn ocr_element(row: &[&OcrWord]) -> Element {
    let x = row.iter().map(|w| w.left).fold(f32::INFINITY, f32::min);
    let y = row.iter().map(|w| w.top).fold(f32::INFINITY, f32::min);
    let right = row.iter().map(|w| w.left + w.width).fold(0.0, f32::max);
    let bottom = row.iter().map(|w| w.top + w.height).fold(0.0, f32::max);
    let score = row.iter().map(|w| w.confidence).sum::<f32>() / row.len() as f32;
    Element {
        kind: ElementKind::Paragraph,
        text: row
            .iter()
            .map(|w| w.text.as_str())
            .collect::<Vec<_>>()
            .join(" "),
        bounds: Rect {
            x,
            y,
            width: right - x,
            height: bottom - y,
        },
        marks: Vec::new(),
        section_path: Vec::new(),
        table_id: None,
        paragraph: None,
        extraction_score: Some(ExtractionScore {
            value: score,
            basis: ScoreBasis::OcrWordConfidence,
        }),
        words: row
            .iter()
            .map(|word| Word {
                text: word.text.clone(),
                bounds: Rect {
                    x: word.left,
                    y: word.top,
                    width: word.width,
                    height: word.height,
                },
                confidence: word.confidence,
            })
            .collect(),
    }
}

#[cfg(test)]
mod native_layout_tests;
#[cfg(test)]
mod ocr_layout_tests;
#[cfg(test)]
mod semantics_tests;

#[allow(clippy::cast_precision_loss)] // Confidence is an approximate mean.
fn mean_ocr_confidence(words: &[OcrWord]) -> Option<ExtractionScore> {
    (!words.is_empty()).then(|| ExtractionScore {
        value: words.iter().map(|w| w.confidence).sum::<f32>() / words.len() as f32,
        basis: ScoreBasis::OcrWordConfidence,
    })
}

fn tokens(text: &str) -> Vec<String> {
    text.split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty())
        .map(str::to_lowercase)
        .collect()
}

#[allow(clippy::cast_precision_loss)] // Token overlap is an approximate score.
fn overlap(reference: &[String], observed: &[String]) -> Option<f32> {
    if reference.is_empty() || observed.is_empty() {
        return None;
    }
    let mut counts = HashMap::<&str, usize>::new();
    for word in observed {
        *counts.entry(word).or_default() += 1;
    }
    let matched = reference
        .iter()
        .filter(|word| {
            let count = counts.entry(word).or_default();
            if *count == 0 {
                false
            } else {
                *count -= 1;
                true
            }
        })
        .count();
    Some(matched as f32 / reference.len() as f32)
}

fn agreement(elements: &[Element], words: &[OcrWord]) -> Option<ExtractionScore> {
    let text = elements
        .iter()
        .map(|e| e.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    let observed = words
        .iter()
        .map(|w| w.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    overlap(&tokens(&text), &tokens(&observed)).map(|value| ExtractionScore {
        value,
        basis: ScoreBasis::TextLayerOcrAgreement,
    })
}

fn element_agreement(element: &Element, words: &[OcrWord]) -> Option<ExtractionScore> {
    let observed = words
        .iter()
        .filter(|w| {
            w.left >= element.bounds.x - 5.0
                && w.left <= element.bounds.x + element.bounds.width + 5.0
                && w.top >= element.bounds.y - 5.0
                && w.top <= element.bounds.y + element.bounds.height + 5.0
        })
        .map(|w| w.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    overlap(&tokens(&element.text), &tokens(&observed)).map(|value| ExtractionScore {
        value,
        basis: ScoreBasis::TextLayerOcrAgreement,
    })
}
