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
const HEADER_BAND: f32 = 0.10;
/// A line whose top is below this fraction of the page height is in the bottom band.
const FOOTER_BAND: f32 = 0.90;
/// At most this many leading pages can hold title-page front matter.
const MAX_FRONT_PAGES: usize = 2;

pub fn label_document(pages: &mut [Page], styles: &mut [Vec<LineStyle>]) {
    label_running_lines(pages, styles);
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
    number_entries(pages);
    for page in pages.iter() {
        debug_assert!(page.elements.iter().all(|e| {
            e.paragraph.is_some() == (e.kind == ElementKind::Paragraph)
                && e.entry.is_some() == (e.kind == ElementKind::Reference)
        }));
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

/// Median font size of the page's text lines.
fn body_size(page: &Page, styles: &[LineStyle]) -> f32 {
    median(
        page.elements
            .iter()
            .zip(styles)
            .filter(|(e, _)| is_text(e))
            .map(|(_, s)| s.size)
            .collect(),
    )
}

/// A text line that could be page furniture. A heading set larger than the body
/// text is a document title even when the same page layout repeats; a running head
/// that only looks like a heading (capitals, bold) is not larger than the body.
fn margin_candidate(element: &Element, style: Option<&LineStyle>, body: f32) -> bool {
    is_text(element)
        && (heading_level(element.kind) == 0 || style.is_some_and(|s| s.size <= body * 1.15))
}

/// Text that can be a page number: digits and no letters ("12", "- 12 -").
fn page_number_text(text: &str) -> bool {
    letters(text).is_empty() && text.chars().any(|c| c.is_ascii_digit())
}

/// Whether a line opens with a note number: "12 Ibid.", not "1982), 20.".
fn opens_with_number(text: &str) -> bool {
    text.trim_start()
        .split_once(char::is_whitespace)
        .is_some_and(|(number, rest)| {
            !number.is_empty()
                && number.chars().all(|c| c.is_ascii_digit())
                && !rest.trim().is_empty()
        })
}

/// Space between a line and the nearest text line above it that it overlaps
/// horizontally; a page number stands apart, a wrapped "243." does not.
fn space_above(page: &Page, index: usize) -> f32 {
    let b = &page.elements[index].bounds;
    page.elements
        .iter()
        .enumerate()
        .filter(|&(i, e)| {
            let a = &e.bounds;
            i != index
                && is_text(e)
                && a.y < b.y
                && (a.x + a.width).min(b.x + b.width) > a.x.max(b.x)
        })
        .map(|(_, e)| b.y - bottom(e))
        .reduce(f32::min)
        .unwrap_or(f32::INFINITY)
}

/// The page's footnote rule: a long run of blank (underlined) text in the lower
/// half of the page.
fn footnote_rule(page: &Page) -> Option<f32> {
    page.elements
        .iter()
        .filter(|e| {
            e.kind != ElementKind::Image
                && !is_text(e)
                && e.bounds.width >= page.width * 0.12
                && e.bounds.y >= page.height * 0.45
        })
        .map(|e| e.bounds.y)
        .reduce(f32::min)
}

/// Lines in the top or bottom margin band whose letters repeat in that band on
/// another page, or that hold a page number and no letters. A page number at the
/// foot stands clear of the text above it, so a wrapped footnote line ("243.") is
/// not one. Footnotes are never footers: a line that opens with a note number or
/// sits below the footnote rule keeps its place, even when it repeats ("Ibid.").
fn label_running_lines(pages: &mut [Page], styles: &[Vec<LineStyle>]) {
    let empty = Vec::new();
    let mut candidates: Vec<Vec<(usize, bool, String)>> = Vec::with_capacity(pages.len());
    let mut counts: HashMap<(bool, String), usize> = HashMap::new();
    for (number, page) in pages.iter().enumerate() {
        let styles = styles.get(number).unwrap_or(&empty);
        let body = body_size(page, styles);
        let rule = footnote_rule(page);
        let line = line_height(page);
        let mut found = Vec::new();
        for (index, element) in page.elements.iter().enumerate() {
            if !margin_candidate(element, styles.get(index), body) {
                continue;
            }
            // Below the footnote rule only a page number standing apart is furniture;
            // a wrapped note line such as "243." sits right under the line above.
            let standalone = page_number_text(&element.text) && space_above(page, index) > line;
            for top in [true, false] {
                let note = !top
                    && (opens_with_number(&element.text)
                        || (!standalone && rule.is_some_and(|y| element.bounds.y >= y - 1.0)));
                if band(page.height, element, top) && !note {
                    found.push((index, top, letters(&element.text)));
                }
            }
        }
        // Running lines are the page's outermost text: anything else between a
        // candidate and the page edge (a title above it, say) makes it body text.
        let outer = |&(index, top, _): &(usize, bool, String)| {
            let edge = &page.elements[index].bounds;
            page.elements.iter().enumerate().all(|(other, e)| {
                let beyond = if top {
                    bottom(e) <= edge.y
                } else {
                    e.bounds.y >= bottom(&page.elements[index])
                };
                !is_text(e) || !beyond || found.iter().any(|f| f.0 == other && f.1 == top)
            })
        };
        let found: Vec<(usize, bool, String)> =
            found.iter().filter(|f| outer(f)).cloned().collect();
        let seen: HashSet<(bool, String)> = found
            .iter()
            .map(|(_, top, signature)| (*top, signature.clone()))
            .collect();
        for key in seen {
            *counts.entry(key).or_default() += 1;
        }
        candidates.push(found);
    }
    for (page, found) in pages.iter_mut().zip(candidates) {
        let line = line_height(page);
        for (index, top, signature) in found {
            let element = &page.elements[index];
            let page_number =
                page_number_text(&element.text) && (top || space_above(page, index) > line);
            let repeated =
                !signature.is_empty() && counts.get(&(top, signature)).copied().unwrap_or(0) >= 2;
            if page_number || repeated {
                page.elements[index].kind = if top {
                    ElementKind::RunningHeader
                } else {
                    ElementKind::RunningFooter
                };
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
    let rule = footnote_rule(page);
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
    let body = body_size(page, styles);
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
    if opens_with_number(&opener.text) && opener.bounds.y >= page.height * 0.5 {
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

fn centred(element: &Element, page_width: f32) -> bool {
    let centre = element.bounds.x + element.bounds.width / 2.0;
    (centre - page_width / 2.0).abs() <= page_width * 0.06
        && element.bounds.width <= page_width * 0.85
}

/// A centred line in capitals (small caps included), such as "INTRODUCTION".
fn is_caps_heading(element: &Element, page_width: f32) -> bool {
    let text = element.text.trim();
    let letters = text.chars().filter(|c| c.is_alphabetic()).count();
    letters >= 3
        && !text.chars().any(char::is_lowercase)
        && text.split_whitespace().count() <= 14
        && !text.ends_with('.')
        && centred(element, page_width)
}

/// A centred section number on its own line: "2.", "II", "IV.".
fn is_section_number(element: &Element, page_width: f32) -> bool {
    let text = element.text.trim().trim_end_matches('.');
    let arabic = (1..=2).contains(&text.len()) && text.chars().all(|c| c.is_ascii_digit());
    let roman = (1..=6).contains(&text.len()) && text.chars().all(|c| "IVXLC".contains(c));
    (arabic || roman) && centred(element, page_width)
}

/// Whether the next line below `position` in `order` is body text in ordinary
/// case, close enough to be what a heading introduces. A title page's centred
/// capitals ("KEN TULLY", "FINAL PAPER", a date) are followed by more capitals or
/// by nothing, so they are not section headings.
fn followed_by_body(page: &Page, order: &[usize], position: usize, line: f32) -> bool {
    let here = &page.elements[order[position]];
    order[position + 1..]
        .iter()
        .map(|&i| &page.elements[i])
        .find(|e| !furniture(e.kind) && e.kind != ElementKind::Image)
        .is_some_and(|next| {
            matches!(
                next.kind,
                ElementKind::Paragraph
                    | ElementKind::ListItem
                    | ElementKind::Citation
                    | ElementKind::Reference
            ) && next.text.chars().any(char::is_lowercase)
                && next.bounds.y - bottom(here) <= line * 5.0
        })
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
/// next heading at its level or above, across pages ("Primary" and "Secondary"
/// sub-headings keep it going).
fn label_sections(pages: &mut [Page]) {
    // The level of the bibliography heading, while its entries run.
    let mut bibliography: Option<usize> = None;
    for page in pages.iter_mut() {
        let line = line_height(page);
        let width = page.width;
        let mut block: Option<(ElementKind, f32)> = None;
        let order = visual_order(page);
        for (position, &index) in order.iter().enumerate() {
            let introduces = followed_by_body(page, &order, position, line);
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
                bibliography =
                    (label == Label::Bibliography).then_some(heading_level(element.kind));
                block = match label {
                    Label::Block(kind) => Some((kind, bottom(element))),
                    Label::Bibliography => None,
                };
                continue;
            }
            let new_heading = introduces
                && (is_caps_heading(element, width) || is_section_number(element, width));
            if heading_level(element.kind) > 0 || new_heading {
                if heading_level(element.kind) == 0 {
                    element.kind = ElementKind::H2;
                }
                if bibliography.is_some_and(|level| heading_level(element.kind) <= level) {
                    bibliography = None;
                }
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
            if bibliography.is_some() {
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
    /// Each line's piece of its paragraph within one column: a paragraph that runs
    /// on into the next column has one piece per column, in reading order.
    piece: Vec<usize>,
    carried_in: Option<usize>,
    /// The page's last paragraph line, when its paragraph runs on past the page.
    open_end: Option<usize>,
}

/// Whether `b` sits below `a` in the same column.
fn stacked(a: &crate::Rect, b: &crate::Rect, line: f32) -> bool {
    let overlap = (a.x + a.width).min(b.x + b.width) - a.x.max(b.x);
    b.y > line.mul_add(0.3, a.y) && overlap >= a.width.min(b.width) * 0.5
}

/// The page's usual space between consecutive lines: the median gap from each
/// paragraph line to the nearest line below it, ignoring gaps over a line height.
/// Scanned pages wobble around it; a paragraph break leaves clearly more.
fn line_spacing(page: &Page, lines: &[usize], line: f32) -> f32 {
    let mut gaps: Vec<f32> = lines
        .iter()
        .filter_map(|&i| {
            let a = &page.elements[i].bounds;
            lines
                .iter()
                .filter(|&&j| j != i && stacked(a, &page.elements[j].bounds, line))
                .map(|&j| page.elements[j].bounds.y - (a.y + a.height))
                .reduce(f32::min)
        })
        .filter(|&gap| gap <= line)
        .collect();
    gaps.sort_by(f32::total_cmp);
    gaps.get(gaps.len() / 2).copied().unwrap_or(0.0)
}

/// The paragraph line directly above `below`: in the same column, with no more
/// space between them than `max_gap`. Poppler's element order is not always
/// reading order, so lines are linked by position.
fn line_above(
    page: &Page,
    lines: &[usize],
    below: usize,
    line: f32,
    max_gap: f32,
) -> Option<usize> {
    let b = &page.elements[below].bounds;
    lines
        .iter()
        .copied()
        .filter(|&i| {
            let a = &page.elements[i].bounds;
            i != below && stacked(a, b, line) && b.y - (a.y + a.height) <= max_gap
        })
        .max_by(|&i, &j| {
            page.elements[i]
                .bounds
                .y
                .total_cmp(&page.elements[j].bounds.y)
        })
}

/// A paragraph that fills the foot of one column continues at the top of the
/// next: the column's first line is flush, and the paragraph line extracted just
/// before it is a full-width last line, lower down, in a column to its left.
/// `above` holds each line's line above; `root` is rewritten in place.
fn join_columns(
    page: &Page,
    lines: &[usize],
    above: &[Option<usize>],
    root: &mut [usize],
    indent: f32,
    full: f32,
) {
    let x = |i: usize| page.elements[i].bounds.x;
    let below_of = |p: usize| (0..lines.len()).find(|&q| above[q] == Some(lines[p]));
    let mut alias: HashMap<usize, usize> = HashMap::new();
    for start in (1..lines.len()).filter(|&p| above[p].is_none()) {
        let previous = start - 1;
        let flush = below_of(start).is_none_or(|q| x(lines[start]) <= x(lines[q]) + indent);
        let between_furniture =
            (lines[previous] + 1..lines[start]).all(|i| furniture(page.elements[i].kind));
        let (a, b) = (
            &page.elements[lines[previous]].bounds,
            &page.elements[lines[start]].bounds,
        );
        if flush
            && between_furniture
            && below_of(previous).is_none()
            && a.y > b.y
            && a.x + a.width <= b.x + indent
            && a.width >= full
        {
            alias.insert(root[start], root[previous]);
        }
    }
    for value in root.iter_mut() {
        for _ in 0..alias.len() {
            match alias.get(value) {
                Some(&next) if next != *value => *value = next,
                _ => break,
            }
        }
    }
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
    // More than the usual line spacing plus a third of a line starts a paragraph.
    let max_gap = line_spacing(page, &lines, line)
        .mul_add(1.0, line * 0.35)
        .clamp(line * 0.5, line * 0.6);
    // A line continues the paragraph of the line above it unless it is indented
    // past that line (a first-line indent, or the start of a block quotation).
    let above: Vec<Option<usize>> = lines
        .iter()
        .map(|&i| line_above(page, &lines, i, line, max_gap))
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
    let widths: Vec<f32> = lines
        .iter()
        .map(|&i| page.elements[i].bounds.width)
        .collect();
    let full = median(widths) * 0.8;
    let piece = root.clone();
    join_columns(page, &lines, &above, &mut root, indent, full);
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
        piece,
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
    let piece_of: HashMap<usize, usize> = flow.lines.iter().copied().zip(flow.piece).collect();
    let mut members: HashMap<usize, Vec<usize>> = HashMap::new();
    for (position, &index) in flow.lines.iter().enumerate() {
        members.entry(flow.root[position]).or_default().push(index);
    }
    // Column by column, then top to bottom within a column.
    for lines in members.values_mut() {
        lines.sort_by(|&a, &b| {
            piece_of[&a].cmp(&piece_of[&b]).then(
                page.elements[a]
                    .bounds
                    .y
                    .total_cmp(&page.elements[b].bounds.y),
            )
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

/// Number bibliography entries through the document by hanging indent. A
/// `reference` line flush with the left edge of its column starts an entry; a line
/// indented past that edge continues the entry above it, also at the top of the
/// next page. An indent wider than a fifth of the column (a centred subheading such
/// as "Secondary") is not a hanging indent and stands alone. A bibliography set
/// without hanging indents gets one entry per line.
fn number_entries(pages: &mut [Page]) {
    let mut count = 0;
    for page in pages.iter_mut() {
        let lines: Vec<usize> = (0..page.elements.len())
            .filter(|&i| page.elements[i].kind == ElementKind::Reference)
            .collect();
        let line = median(
            lines
                .iter()
                .map(|&i| page.elements[i].bounds.height)
                .collect(),
        );
        let continues: Vec<bool> = lines
            .iter()
            .map(|&i| {
                let b = &page.elements[i].bounds;
                // The column: reference lines on this page that overlap this one.
                let column = lines.iter().map(|&j| &page.elements[j].bounds).filter(|a| {
                    (a.x + a.width).min(b.x + b.width) - a.x.max(b.x) >= a.width.min(b.width) * 0.5
                });
                let (left, right) = column.fold((b.x, b.x + b.width), |(l, r), a| {
                    (l.min(a.x), r.max(a.x + a.width))
                });
                let indent = b.x - left;
                indent > line * 0.75 && indent <= (right - left) * 0.2
            })
            .collect();
        for (position, &index) in lines.iter().enumerate() {
            if !continues[position] || count == 0 {
                count += 1;
            }
            page.elements[index].entry = Some(count);
        }
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
