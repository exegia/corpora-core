//! Text-layer lines built from Poppler's `pdftohtml -xml` fragments.

use std::collections::HashMap;

use super::{Element, ElementKind, InlineMark, MarkKind, PdfError, Rect, attribute_f32};

/// Font evidence for one extracted line. The semantic pass uses it; it is not part
/// of the extraction output.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct LineStyle {
    /// The font size covering most of the line's visible characters (0 for images).
    pub size: f32,
    /// Most of the line is drawn twice at the same place, a common way to fake bold.
    pub emphasized: bool,
}

/// The fragments joined into one line so far: font size and visible characters per
/// fragment, and how many visible characters were drawn a second time.
struct Runs {
    sizes: Vec<(f32, usize)>,
    emphasized: usize,
}

impl Runs {
    fn new(size: f32, element: &Element) -> Self {
        Self {
            sizes: vec![(size, visible(&element.text))],
            emphasized: 0,
        }
    }

    fn style(&self) -> LineStyle {
        let total: usize = self.sizes.iter().map(|(_, count)| count).sum();
        LineStyle {
            size: dominant_size(&self.sizes),
            emphasized: total > 0 && self.emphasized * 2 >= total,
        }
    }
}

fn visible(text: &str) -> usize {
    text.chars().filter(|c| !c.is_whitespace()).count()
}

/// Poppler starts a new `<text>` fragment at every font change, so one printed line
/// can arrive in pieces: a small-caps heading alternates two sizes, and an italic
/// word splits a sentence. `next` continues `previous` when the two share most of
/// their height and the horizontal gap is no wider than a word space allows.
/// Table columns and page columns sit much further apart, so they stay separate.
fn continues_line(previous: &Rect, next: &Rect) -> bool {
    let line = previous.height.min(next.height).max(1.0);
    let overlap = (previous.y + previous.height).min(next.y + next.height) - previous.y.max(next.y);
    let gap = next.x - (previous.x + previous.width);
    overlap >= line * 0.5 && gap >= -line * 0.25 && gap <= line * 0.8
}

/// Join `fragment` to `line`, after it or (when `before`) in front of it: text (with a
/// space when a visible gap has none), marks, bounds and font runs.
fn join_fragment(
    line: &mut Element,
    runs: &mut Runs,
    fragment: Element,
    fragment_runs: Runs,
    before: bool,
) {
    let (left, right) = if before {
        (&fragment, &*line)
    } else {
        (&*line, &fragment)
    };
    let height = left.bounds.height.min(right.bounds.height).max(1.0);
    let gap = right.bounds.x - (left.bounds.x + left.bounds.width);
    let space = gap > height * 0.2
        && !left.text.ends_with(char::is_whitespace)
        && !right.text.starts_with(char::is_whitespace);
    let mut text = String::with_capacity(left.text.len() + right.text.len() + 1);
    text.push_str(&left.text);
    if space {
        text.push(' ');
    }
    text.push_str(&right.text);
    runs.sizes.extend(fragment_runs.sizes);
    runs.emphasized += fragment_runs.emphasized;
    line.text = text;
    let next = fragment;
    if before {
        let after = std::mem::replace(&mut line.marks, next.marks);
        line.marks.extend(after);
    } else {
        line.marks.extend(next.marks);
    }
    let right = (line.bounds.x + line.bounds.width).max(next.bounds.x + next.bounds.width);
    let bottom = (line.bounds.y + line.bounds.height).max(next.bounds.y + next.bounds.height);
    line.bounds.x = line.bounds.x.min(next.bounds.x);
    line.bounds.y = line.bounds.y.min(next.bounds.y);
    line.bounds.width = right - line.bounds.x;
    line.bounds.height = bottom - line.bounds.y;
}

/// Join the text element at `index` with every other text element on the same line,
/// repeating until the line stops growing. Poppler does not always emit a line's
/// fragments in order (a footnote number or a trailing space can come after the
/// next line), and a late fragment can bridge two pieces already on the page.
/// The joined line keeps the earlier reading position.
fn join_line(elements: &mut Vec<(Element, Runs)>, mut index: usize) {
    loop {
        let current = elements[index].0.bounds;
        let other = (0..elements.len()).rev().find(|&j| {
            let bounds = &elements[j].0.bounds;
            j != index
                && elements[j].0.kind != ElementKind::Image
                && (continues_line(bounds, &current) || continues_line(&current, bounds))
        });
        let Some(other) = other else { return };
        let (keep, gone) = if other < index {
            (other, index)
        } else {
            (index, other)
        };
        let (fragment, fragment_runs) = elements.remove(gone);
        let (line, runs) = &mut elements[keep];
        let before = !continues_line(&line.bounds, &fragment.bounds);
        join_fragment(line, runs, fragment, fragment_runs, before);
        index = keep;
    }
}

/// The element that already shows `fragment`: the same text, drawn again within two
/// layout units of where it was printed. PDFs do this to fake bold or as a shadow;
/// readers see the text once, so it is kept once.
fn overprinted(elements: &[(Element, Runs)], fragment: &Element) -> Option<usize> {
    let text = fragment.text.trim();
    if text.is_empty() {
        return None;
    }
    let b = &fragment.bounds;
    elements.iter().position(|(element, _)| {
        let r = &element.bounds;
        element.kind != ElementKind::Image
            && element.text.contains(text)
            && b.x >= r.x - 2.0
            && b.y >= r.y - 2.0
            && b.x + b.width <= r.x + r.width + 2.0
            && b.y + b.height <= r.y + r.height + 2.0
    })
}

/// The font size that covers the most visible characters of a joined line.
fn dominant_size(sizes: &[(f32, usize)]) -> f32 {
    let mut totals: Vec<(f32, usize)> = Vec::new();
    for &(size, count) in sizes {
        match totals.iter_mut().find(|(s, _)| (*s - size).abs() < 0.01) {
            Some((_, total)) => *total += count,
            None => totals.push((size, count)),
        }
    }
    totals
        .iter()
        .max_by_key(|(_, count)| *count)
        .map_or(0.0, |(size, _)| *size)
}

/// One Poppler `<text>` fragment as a paragraph element, with its font size.
fn text_fragment(
    node: roxmltree::Node<'_, '_>,
    font_sizes: &HashMap<&str, f32>,
) -> Result<(Element, f32), PdfError> {
    let text = node
        .descendants()
        .filter_map(|n| n.text().filter(|_| n.is_text()))
        .collect::<String>();
    let marks = node
        .descendants()
        .filter(roxmltree::Node::is_element)
        .filter_map(|n| {
            let kind = match n.tag_name().name() {
                "b" => MarkKind::Bold,
                "i" => MarkKind::Italic,
                "a" => MarkKind::Link,
                _ => return None,
            };
            let marked = n
                .descendants()
                .filter_map(|t| t.text().filter(|_| t.is_text()))
                .collect::<String>();
            Some(InlineMark {
                kind,
                text: marked,
                target: n.attribute("href").map(ToOwned::to_owned),
            })
        })
        .collect();
    let bounds = Rect {
        x: attribute_f32(node, "left")?,
        y: attribute_f32(node, "top")?,
        width: attribute_f32(node, "width")?,
        height: attribute_f32(node, "height")?,
    };
    let font_size = node
        .attribute("font")
        .and_then(|id| font_sizes.get(id))
        .copied()
        .unwrap_or(bounds.height);
    let fragment = Element {
        kind: ElementKind::Paragraph,
        text,
        bounds,
        marks,
        section_path: Vec::new(),
        table_id: None,
        paragraph: None,
        entry: None,
        extraction_score: None,
        words: Vec::new(),
    };
    Ok((fragment, font_size))
}

fn image(node: roxmltree::Node<'_, '_>) -> Result<Element, PdfError> {
    Ok(Element {
        kind: ElementKind::Image,
        text: String::new(),
        bounds: Rect {
            x: attribute_f32(node, "left")?,
            y: attribute_f32(node, "top")?,
            width: attribute_f32(node, "width")?,
            height: attribute_f32(node, "height")?,
        },
        marks: Vec::new(),
        section_path: Vec::new(),
        table_id: None,
        paragraph: None,
        entry: None,
        extraction_score: None,
        words: Vec::new(),
    })
}

/// A page's lines and images in source order, each with its font evidence.
/// Headings here use relative font size plus bold (a `<b>` mark or overprinted
/// text); the semantic pass adds the labels that need the whole document.
pub fn parse_elements(
    page: roxmltree::Node<'_, '_>,
    font_sizes: &HashMap<&str, f32>,
) -> Result<Vec<(Element, LineStyle)>, PdfError> {
    let mut elements: Vec<(Element, Runs)> = Vec::new();
    for node in page.children().filter(roxmltree::Node::is_element) {
        if node.has_tag_name("text") {
            let (fragment, font_size) = text_fragment(node, font_sizes)?;
            if let Some(index) = overprinted(&elements, &fragment) {
                elements[index].1.emphasized += visible(&fragment.text);
                continue;
            }
            let runs = Runs::new(font_size, &fragment);
            elements.push((fragment, runs));
            let last = elements.len() - 1;
            join_line(&mut elements, last);
        } else if node.has_tag_name("image") {
            elements.push((
                image(node)?,
                Runs {
                    sizes: vec![(0.0, 0)],
                    emphasized: 0,
                },
            ));
        }
    }
    let mut elements: Vec<(Element, LineStyle)> = elements
        .into_iter()
        .map(|(element, runs)| (element, runs.style()))
        .collect();
    let mut sizes: Vec<f32> = elements
        .iter()
        .filter(|(e, _)| !e.text.trim().is_empty())
        .map(|(_, style)| style.size)
        .collect();
    sizes.sort_by(f32::total_cmp);
    let body_size = sizes.get(sizes.len() / 2).copied().unwrap_or(1.0).max(1.0);
    for (element, style) in &mut elements {
        if element.text.trim().is_empty() {
            continue;
        }
        let ratio = style.size / body_size;
        let bold = style.emphasized || element.marks.iter().any(|m| m.kind == MarkKind::Bold);
        element.kind = if ratio >= 1.45 && bold {
            ElementKind::H1
        } else if ratio >= 1.28 && bold {
            ElementKind::H2
        } else if ratio >= 1.13 && bold {
            ElementKind::H3
        } else if ratio >= 1.08 && bold {
            ElementKind::H4
        } else {
            ElementKind::Paragraph
        };
    }
    Ok(elements)
}
