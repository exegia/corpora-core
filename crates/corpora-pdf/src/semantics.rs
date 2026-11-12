//! Document-level semantic labels: page furniture (running headers and footers),
//! footnotes, front matter, labelled sections and caps headings.
//!
//! These rules need more than one line at a time: a running header is text that
//! repeats across pages, a footnote is anything below the page's footnote rule, and
//! an abstract is the block under an "Abstract" label. They run once every page is
//! extracted. Like every label, they are layout heuristics, not source PDF tags.

use std::collections::{HashMap, HashSet};

use crate::native::LineStyle;
use crate::{Element, ElementKind, MarkKind, Page};

/// A line whose bottom is above this fraction of the page height is in the top band.
const HEADER_BAND: f32 = 0.085;
/// A line whose top is below this fraction of the page height is in the bottom band.
const FOOTER_BAND: f32 = 0.93;
/// At most this many leading pages can hold title-page front matter.
const MAX_FRONT_PAGES: usize = 2;

pub fn label_document(pages: &mut [Page], styles: &mut [Vec<LineStyle>]) {
    label_running_lines(pages);
    for page in pages.iter_mut() {
        label_detached_footer(page);
    }
    for (page, styles) in pages.iter_mut().zip(styles.iter()) {
        label_footnotes(page, styles);
    }
    let front = pages
        .iter()
        .take(MAX_FRONT_PAGES)
        .take_while(|page| {
            !page
                .elements
                .iter()
                .any(|e| e.kind == ElementKind::RunningHeader)
        })
        .count();
    for (page, styles) in pages.iter_mut().zip(styles.iter()).take(front) {
        label_front_matter(page, styles);
    }
    label_sections(pages);
    for (page, styles) in pages.iter_mut().zip(styles.iter_mut()) {
        drop_blank_lines(page, styles);
        order_paragraph_lines(page, styles);
        assign_section_paths(&mut page.elements);
    }
    number_paragraphs(pages);
    for page in pages.iter() {
        debug_assert!(
            page.elements
                .iter()
                .all(|e| { e.paragraph.is_some() == (e.kind == ElementKind::Paragraph) })
        );
    }
}

fn is_text(element: &Element) -> bool {
    !element.text.trim().is_empty()
}

fn bottom(element: &Element) -> f32 {
    element.bounds.y + element.bounds.height
}

/// Lowercase letters only: the same running header on every page, whatever its
/// page number or punctuation.
fn letters(text: &str) -> String {
    text.chars()
        .filter(|c| c.is_alphabetic())
        .flat_map(char::to_lowercase)
        .collect()
}

fn median(mut values: Vec<f32>) -> f32 {
    values.sort_by(f32::total_cmp);
    values
        .get(values.len() / 2)
        .copied()
        .unwrap_or(1.0)
        .max(1.0)
}

/// Median text-line height on the page, the unit for vertical gaps.
fn line_height(page: &Page) -> f32 {
    median(
        page.elements
            .iter()
            .filter(|e| is_text(e))
            .map(|e| e.bounds.height)
            .collect(),
    )
}

/// Indices of the page's text lines in visual order, top to bottom then left to right.
fn visual_order(page: &Page) -> Vec<usize> {
    let mut order: Vec<usize> = (0..page.elements.len())
        .filter(|&i| is_text(&page.elements[i]))
        .collect();
    order.sort_by(|&a, &b| {
        let (a, b) = (&page.elements[a].bounds, &page.elements[b].bounds);
        a.y.total_cmp(&b.y).then(a.x.total_cmp(&b.x))
    });
    order
}

fn band(page_height: f32, element: &Element, top: bool) -> bool {
    if top {
        bottom(element) <= page_height * HEADER_BAND
    } else {
        element.bounds.y >= page_height * FOOTER_BAND
    }
}

/// A text line that could be page furniture. A line already set as a heading (large
/// and bold) is a document title even when the same page layout repeats.
fn margin_candidate(element: &Element) -> bool {
    is_text(element) && heading_level(element.kind) == 0
}

/// Lines in the top or bottom margin band whose letters repeat on another page, or
/// that hold a page number and no letters.
fn label_running_lines(pages: &mut [Page]) {
    let mut counts: HashMap<(bool, String), usize> = HashMap::new();
    for page in pages.iter() {
        let mut seen = HashSet::new();
        for element in page.elements.iter().filter(|e| margin_candidate(e)) {
            for top in [true, false] {
                if band(page.height, element, top) {
                    seen.insert((top, letters(&element.text)));
                }
            }
        }
        for key in seen {
            *counts.entry(key).or_default() += 1;
        }
    }
    for page in pages.iter_mut() {
        let height = page.height;
        for element in page.elements.iter_mut().filter(|e| margin_candidate(e)) {
            for top in [true, false] {
                if !band(height, element, top) {
                    continue;
                }
                let signature = letters(&element.text);
                let page_number =
                    signature.is_empty() && element.text.chars().any(|c| c.is_ascii_digit());
                if page_number || counts.get(&(top, signature)).copied().unwrap_or(0) >= 2 {
                    element.kind = if top {
                        ElementKind::RunningHeader
                    } else {
                        ElementKind::RunningFooter
                    };
                }
            }
        }
    }
}

/// A source notice at the foot of the page: a block set apart from everything
/// above by more than five line heights that holds a link, such as a repository
/// notice on a cover page. A publisher imprint at the foot of a title page has no
/// link and stays body text.
fn label_detached_footer(page: &mut Page) {
    let line = line_height(page);
    let order: Vec<usize> = visual_order(page)
        .into_iter()
        .filter(|&i| !matches!(page.elements[i].kind, ElementKind::RunningHeader))
        .collect();
    let Some(&last) = order.last() else { return };
    let mut start = order.len() - 1;
    let mut top = page.elements[last].bounds.y;
    while start > 0 {
        let above = &page.elements[order[start - 1]];
        if top - bottom(above) > line * 1.5 {
            break;
        }
        start -= 1;
        top = top.min(above.bounds.y);
    }
    if start == 0 || top < page.height * 0.85 {
        return;
    }
    let gap = top - bottom(&page.elements[order[start - 1]]);
    let linked = order[start..].iter().any(|&i| {
        let element = &page.elements[i];
        element.marks.iter().any(|m| m.kind == MarkKind::Link)
            || ["http://", "https://", "www.", "doi.org/"]
                .iter()
                .any(|prefix| element.text.contains(prefix))
    });
    if linked && gap > line * 5.0 {
        for &index in &order[start..] {
            page.elements[index].kind = ElementKind::RunningFooter;
        }
    }
}

/// Footnotes sit below the footnote rule: a long run of blank (underlined) text in
/// the lower half of the page. Without a rule, a run of smaller lines at the foot of
/// the page that starts with a note number is taken instead.
fn label_footnotes(page: &mut Page, styles: &[LineStyle]) {
    let rule = page
        .elements
        .iter()
        .filter(|e| {
            e.kind != ElementKind::Image
                && !is_text(e)
                && e.bounds.width >= page.width * 0.12
                && e.bounds.y >= page.height * 0.45
        })
        .map(|e| e.bounds.y)
        .reduce(f32::min);
    let free = |e: &Element| {
        is_text(e)
            && !matches!(
                e.kind,
                ElementKind::RunningHeader | ElementKind::RunningFooter
            )
    };
    if let Some(rule) = rule {
        for element in &mut page.elements {
            if free(element) && element.bounds.y >= rule - 1.0 {
                element.kind = ElementKind::Footnote;
            }
        }
        return;
    }
    let body = median(
        page.elements
            .iter()
            .zip(styles)
            .filter(|(e, _)| is_text(e))
            .map(|(_, s)| s.size)
            .collect(),
    );
    let line = line_height(page);
    let order: Vec<usize> = visual_order(page)
        .into_iter()
        .filter(|&i| free(&page.elements[i]))
        .collect();
    let mut start = order.len();
    while start > 0 {
        let index = order[start - 1];
        let small = styles
            .get(index)
            .is_some_and(|s| s.size > 0.0 && s.size <= body * 0.88);
        let close = start == order.len()
            || page.elements[order[start]].bounds.y - bottom(&page.elements[index]) <= line * 1.5;
        if !small || !close {
            break;
        }
        start -= 1;
    }
    // The run must start with a note number and lie in the lower half of the page.
    let Some(&first) = order.get(start) else {
        return;
    };
    let opener = &page.elements[first];
    let numbered = opener
        .text
        .trim_start()
        .split_once(char::is_whitespace)
        .is_some_and(|(number, _)| {
            !number.is_empty() && number.chars().all(|c| c.is_ascii_digit())
        });
    if numbered && opener.bounds.y >= page.height * 0.5 {
        for &index in &order[start..] {
            page.elements[index].kind = ElementKind::Footnote;
        }
    }
}

/// The label a short line names, with the kind its following block takes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Label {
    Block(ElementKind),
    Bibliography,
}

fn section_label(text: &str) -> Option<Label> {
    if text.split_whitespace().count() > 4 {
        return None;
    }
    match letters(text).as_str() {
        "abstract" | "summary" => Some(Label::Block(ElementKind::Abstract)),
        "keywords" | "keyword" => Some(Label::Block(ElementKind::Keywords)),
        "recommendedcitation" | "citeas" | "howtocite" | "citation" => {
            Some(Label::Block(ElementKind::Citation))
        }
        "coverpagefootnote" => Some(Label::Block(ElementKind::Footnote)),
        "bibliography"
        | "references"
        | "workscited"
        | "selectbibliography"
        | "selectedbibliography" => Some(Label::Bibliography),
        _ => None,
    }
}

/// A centred line in capitals (small caps included), such as "INTRODUCTION".
fn is_caps_heading(element: &Element, page_width: f32) -> bool {
    let text = element.text.trim();
    let letters = text.chars().filter(|c| c.is_alphabetic()).count();
    let centre = element.bounds.x + element.bounds.width / 2.0;
    letters >= 3
        && !text.chars().any(char::is_lowercase)
        && text.split_whitespace().count() <= 14
        && !text.ends_with('.')
        && (centre - page_width / 2.0).abs() <= page_width * 0.06
        && element.bounds.width <= page_width * 0.85
}

const fn heading_level(kind: ElementKind) -> usize {
    match kind {
        ElementKind::H1 => 1,
        ElementKind::H2 => 2,
        ElementKind::H3 => 3,
        ElementKind::H4 => 4,
        _ => 0,
    }
}

/// Section labels and caps headings, then the blocks they introduce: lines under
/// "Abstract", "Keywords", "Recommended Citation" or "Cover Page Footnote" until a
/// gap of more than 1.5 line heights, and every line of a bibliography until the
/// next heading, across pages.
fn label_sections(pages: &mut [Page]) {
    let mut bibliography = false;
    for page in pages.iter_mut() {
        let line = line_height(page);
        let width = page.width;
        let mut block: Option<(ElementKind, f32)> = None;
        for index in visual_order(page) {
            let element = &mut page.elements[index];
            if !matches!(
                element.kind,
                ElementKind::Paragraph
                    | ElementKind::ListItem
                    | ElementKind::Citation
                    | ElementKind::Reference
                    | ElementKind::H1
                    | ElementKind::H2
                    | ElementKind::H3
                    | ElementKind::H4
            ) {
                continue;
            }
            if let Some(label) = section_label(&element.text) {
                if heading_level(element.kind) == 0 {
                    element.kind = ElementKind::H2;
                }
                bibliography = label == Label::Bibliography;
                block = match label {
                    Label::Block(kind) => Some((kind, bottom(element))),
                    Label::Bibliography => None,
                };
                continue;
            }
            if heading_level(element.kind) > 0 || is_caps_heading(element, width) {
                if heading_level(element.kind) == 0 {
                    element.kind = ElementKind::H2;
                }
                bibliography = false;
                block = None;
                continue;
            }
            if let Some((kind, last)) = block {
                if element.bounds.y - last <= line * 1.5 {
                    element.kind = kind;
                    block = Some((kind, bottom(element)));
                    continue;
                }
                block = None;
            }
            if bibliography {
                element.kind = ElementKind::Reference;
            }
        }
    }
}

fn is_publication_metadata(text: &str) -> bool {
    const MONTHS: [&str; 16] = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "spring",
        "summer",
        "fall",
        "winter",
    ];
    let lower = text.trim().to_lowercase();
    let mut words = lower.split_whitespace();
    let first = words.next().unwrap_or_default();
    let numbered = ["volume", "vol.", "issue", "no.", "number", "article", "pp."].contains(&first)
        && lower.chars().any(|c| c.is_ascii_digit());
    let dated = MONTHS.contains(&first)
        && words
            .next()
            .is_some_and(|year| year.len() == 4 && year.chars().all(|c| c.is_ascii_digit()))
        && words.next().is_none();
    numbered || dated
}

fn is_author_line(text: &str) -> bool {
    let words: Vec<&str> = text.split_whitespace().collect();
    (2..=8).contains(&words.len())
        && !text
            .chars()
            .any(|c| c.is_ascii_digit() || c == '@' || c == ':')
        && section_label(text).is_none()
        && words.iter().all(|w| {
            w.chars().next().is_some_and(char::is_uppercase)
                || matches!(*w, "and" | "&" | "de" | "van" | "von" | "der" | "la")
        })
}

fn is_affiliation_line(text: &str) -> bool {
    let lower = text.to_lowercase();
    lower.contains('@')
        || [
            "university",
            "college",
            "seminary",
            "institute",
            "school",
            "department",
            "faculty",
            "academy",
        ]
        .iter()
        .any(|word| lower.contains(word))
}

/// Title-page front matter, only on leading pages that show front-matter evidence
/// (issue details, or an abstract, keywords or citation label). Large lines above the issue
/// details are the journal title, large lines below them the document title; the
/// name line after the title is the author, followed by affiliation lines.
fn label_front_matter(page: &mut Page, styles: &[LineStyle]) {
    let order: Vec<usize> = visual_order(page)
        .into_iter()
        .filter(|&i| {
            matches!(
                page.elements[i].kind,
                ElementKind::Paragraph
                    | ElementKind::ListItem
                    | ElementKind::H1
                    | ElementKind::H2
                    | ElementKind::H3
                    | ElementKind::H4
            )
        })
        .collect();
    let evidence = order.iter().any(|&i| {
        let text = &page.elements[i].text;
        is_publication_metadata(text) || matches!(section_label(text), Some(Label::Block(_)))
    });
    if !evidence {
        return;
    }
    let body = median(
        order
            .iter()
            .filter_map(|&i| styles.get(i))
            .map(|s| s.size)
            .collect(),
    );
    let first_metadata = order
        .iter()
        .filter(|&&i| is_publication_metadata(&page.elements[i].text))
        .map(|&i| page.elements[i].bounds.y)
        .reduce(f32::min);
    let label_top = order
        .iter()
        .filter(|&&i| section_label(&page.elements[i].text).is_some())
        .map(|&i| page.elements[i].bounds.y)
        .reduce(f32::min)
        .unwrap_or(f32::INFINITY);
    let mut after_title = false;
    let mut author_seen = false;
    for &index in &order {
        let large = styles.get(index).is_some_and(|s| s.size >= body * 1.2);
        let element = &mut page.elements[index];
        if element.bounds.y >= label_top {
            break;
        }
        if large {
            let above_metadata = first_metadata.is_some_and(|y| element.bounds.y < y);
            element.kind = if above_metadata {
                ElementKind::JournalTitle
            } else {
                after_title = true;
                ElementKind::Title
            };
            continue;
        }
        if is_publication_metadata(&element.text)
            && first_metadata.is_some_and(|y| element.bounds.y <= page.height.mul_add(0.1, y))
        {
            element.kind = ElementKind::PublicationMetadata;
            continue;
        }
        if after_title && !author_seen && is_author_line(&element.text) {
            element.kind = ElementKind::Author;
            author_seen = true;
            continue;
        }
        if author_seen && is_affiliation_line(&element.text) {
            element.kind = ElementKind::Affiliation;
            continue;
        }
        if after_title {
            // Only the lines directly under the title are author and affiliation.
            after_title = author_seen && is_affiliation_line(&element.text);
        }
    }
}

/// Blank lines (indents, spacing, the footnote rule) carry no text: drop them now
/// that the footnote rule has been used.
fn drop_blank_lines(page: &mut Page, styles: &mut Vec<LineStyle>) {
    let keep: Vec<bool> = page
        .elements
        .iter()
        .map(|e| {
            e.kind == ElementKind::Image || e.kind == ElementKind::GraphCandidate || is_text(e)
        })
        .collect();
    let mut flags = keep.iter();
    page.elements.retain(|_| *flags.next().unwrap_or(&true));
    let mut flags = keep.iter();
    styles.retain(|_| *flags.next().unwrap_or(&true));
}

/// Heading ancestry, page by page, after headings have been relabelled. A heading
/// closes every open heading at its level or deeper, so two `h2` headings with no
/// `h1` above them are siblings.
fn assign_section_paths(elements: &mut [Element]) {
    let mut open: Vec<(usize, String)> = Vec::new();
    for element in elements {
        let level = heading_level(element.kind);
        if level > 0 {
            while open.last().is_some_and(|(depth, _)| *depth >= level) {
                open.pop();
            }
            open.push((level, element.text.trim().to_owned()));
        }
        element.section_path = open.iter().map(|(_, text)| text.clone()).collect();
    }
}

/// A line of body text that continues into the next line of the same paragraph.
const fn flows(kind: ElementKind) -> bool {
    matches!(kind, ElementKind::Paragraph)
}

/// Lines that the body text runs around without ending a paragraph.
const fn furniture(kind: ElementKind) -> bool {
    matches!(
        kind,
        ElementKind::RunningHeader | ElementKind::RunningFooter | ElementKind::Footnote
    )
}

/// One page's paragraph lines: for each line, the line right above it in the same
/// paragraph, if any, and whether it may continue a paragraph from the previous
/// page (its first line, not indented) or leaves one open for the next page.
struct Flow {
    lines: Vec<usize>,
    root: Vec<usize>,
    carried_in: Option<usize>,
    /// The page's last paragraph line, when its paragraph runs on past the page.
    open_end: Option<usize>,
}

/// The paragraph line directly above `below`: overlapping it horizontally, with no
/// more than half a line of space between them. Poppler's element order is not
/// always reading order, so lines are linked by position.
fn line_above(page: &Page, lines: &[usize], below: usize, line: f32) -> Option<usize> {
    let b = &page.elements[below].bounds;
    lines
        .iter()
        .copied()
        .filter(|&i| {
            let a = &page.elements[i].bounds;
            let overlap = (a.x + a.width).min(b.x + b.width) - a.x.max(b.x);
            let gap = b.y - (a.y + a.height);
            i != below
                && b.y > line.mul_add(0.3, a.y)
                && gap <= line * 0.5
                && overlap >= a.width.min(b.width) * 0.5
        })
        .max_by(|&i, &j| {
            page.elements[i]
                .bounds
                .y
                .total_cmp(&page.elements[j].bounds.y)
        })
}

fn page_flow(page: &Page) -> Flow {
    let lines: Vec<usize> = (0..page.elements.len())
        .filter(|&i| flows(page.elements[i].kind))
        .collect();
    let line = median(
        lines
            .iter()
            .map(|&i| page.elements[i].bounds.height)
            .collect(),
    );
    let indent = line * 0.75;
    let x = |i: usize| page.elements[i].bounds.x;
    // A line continues the paragraph of the line above it unless it is indented
    // past that line (a first-line indent, or the start of a block quotation).
    let above: Vec<Option<usize>> = lines
        .iter()
        .map(|&i| line_above(page, &lines, i, line))
        .collect();
    let continues =
        |position: usize| above[position].filter(|&a| x(lines[position]) <= x(a) + indent);
    let mut root: Vec<usize> = lines.clone();
    // Lines are linked top to bottom, so resolve roots in vertical order.
    let mut order: Vec<usize> = (0..lines.len()).collect();
    order.sort_by(|&a, &b| {
        page.elements[lines[a]]
            .bounds
            .y
            .total_cmp(&page.elements[lines[b]].bounds.y)
    });
    for &position in &order {
        if let Some(a) = continues(position) {
            let a_position = lines.iter().position(|&l| l == a).unwrap_or(position);
            root[position] = root[a_position];
        }
    }
    // Anything else in the body (a heading, a list, an image) between the page top
    // and a line, or below the last line, ends the paragraph at the page break.
    let interrupts = |range: std::ops::Range<f32>| {
        page.elements
            .iter()
            .any(|e| !flows(e.kind) && !furniture(e.kind) && range.contains(&e.bounds.y))
    };
    let starts: Vec<usize> = (0..lines.len()).filter(|&p| above[p].is_none()).collect();
    let first = starts.iter().copied().min_by(|&a, &b| {
        page.elements[lines[a]]
            .bounds
            .y
            .total_cmp(&page.elements[lines[b]].bounds.y)
    });
    let carried_in = first.filter(|&p| {
        let next = (0..lines.len()).find(|&q| above[q] == Some(lines[p]));
        let flush = next.is_none_or(|q| x(lines[p]) <= x(lines[q]) + indent);
        flush && !interrupts(0.0..page.elements[lines[p]].bounds.y)
    });
    let widths: Vec<f32> = lines
        .iter()
        .map(|&i| page.elements[i].bounds.width)
        .collect();
    let full = median(widths) * 0.8;
    let last = lines.iter().copied().max_by(|&a, &b| {
        page.elements[a]
            .bounds
            .y
            .total_cmp(&page.elements[b].bounds.y)
    });
    // A short last line ends its paragraph on this page.
    let open_end = last.filter(|&i| {
        let element = &page.elements[i];
        element.bounds.width >= full
            && !interrupts(line.mul_add(0.3, element.bounds.y)..f32::INFINITY)
    });
    Flow {
        lines,
        root,
        carried_in,
        open_end,
    }
}

/// Whether two paragraph lines sit side by side on one row: page columns, or one
/// printed line that Poppler left in pieces (some fonts misreport glyph widths).
fn shares_rows(page: &Page, lines: &[usize]) -> bool {
    lines.iter().enumerate().any(|(n, &i)| {
        let a = &page.elements[i].bounds;
        lines[n + 1..].iter().any(|&j| {
            let b = &page.elements[j].bounds;
            let overlap = (a.y + a.height).min(b.y + b.height) - a.y.max(b.y);
            overlap >= a.height.min(b.height) * 0.5
        })
    })
}

/// Put each paragraph's lines together, top to bottom, where its first line was
/// extracted. Poppler can emit a later line of a paragraph after the next
/// paragraph's lines; other elements keep their order. Pages where paragraph lines
/// share a row keep Poppler's order: there, one element is not one printed line.
fn order_paragraph_lines(page: &mut Page, styles: &mut Vec<LineStyle>) {
    let flow = page_flow(page);
    if shares_rows(page, &flow.lines) {
        return;
    }
    let mut members: HashMap<usize, Vec<usize>> = HashMap::new();
    for (position, &index) in flow.lines.iter().enumerate() {
        members.entry(flow.root[position]).or_default().push(index);
    }
    for lines in members.values_mut() {
        lines.sort_by(|&a, &b| {
            page.elements[a]
                .bounds
                .y
                .total_cmp(&page.elements[b].bounds.y)
        });
    }
    let root_of: HashMap<usize, usize> = flow
        .lines
        .iter()
        .zip(&flow.root)
        .map(|(&index, &root)| (index, root))
        .collect();
    let mut order = Vec::with_capacity(page.elements.len());
    for index in 0..page.elements.len() {
        match root_of.get(&index) {
            // The paragraph's first extracted line brings all of its lines.
            Some(root) => order.extend(members.remove(root).unwrap_or_default()),
            None => order.push(index),
        }
    }
    if order.iter().copied().eq(0..page.elements.len()) {
        return;
    }
    let mut elements: Vec<Option<Element>> = page.elements.drain(..).map(Some).collect();
    page.elements = order.iter().filter_map(|&i| elements[i].take()).collect();
    if styles.len() == elements.len() {
        let old = std::mem::take(styles);
        *styles = order.iter().map(|&i| old[i]).collect();
    }
}

/// Number visual paragraphs through the document. Every `paragraph` line gets the
/// number of its paragraph; a paragraph whose last line fills the page's last
/// body line and resumes, unindented, at the top of the next page keeps its number.
fn number_paragraphs(pages: &mut [Page]) {
    let mut count = 0;
    let mut open: Option<usize> = None;
    for page in pages.iter_mut() {
        let flow = page_flow(page);
        let mut numbers: HashMap<usize, usize> = HashMap::new();
        if let (Some(number), Some(position)) = (open, flow.carried_in) {
            numbers.insert(flow.root[position], number);
        }
        // Number paragraphs in the order their first line was extracted.
        let mut roots: Vec<usize> = flow.root.clone();
        roots.sort_unstable();
        roots.dedup();
        for root in roots {
            numbers.entry(root).or_insert_with(|| {
                count += 1;
                count
            });
        }
        for (position, &index) in flow.lines.iter().enumerate() {
            page.elements[index].paragraph = numbers.get(&flow.root[position]).copied();
        }
        open = flow
            .open_end
            .and_then(|index| page.elements[index].paragraph);
    }
}
