use super::native::LineStyle;
use super::semantics::label_document;
use super::*;

const WIDTH: f32 = 918.0;
const HEIGHT: f32 = 1188.0;

fn line(text: &str, x: f32, y: f32, width: f32, height: f32) -> Element {
    Element {
        kind: ElementKind::Paragraph,
        text: text.to_owned(),
        bounds: Rect {
            x,
            y,
            width,
            height,
        },
        marks: Vec::new(),
        section_path: Vec::new(),
        table_id: None,
        paragraph: None,
        extraction_score: None,
        words: Vec::new(),
    }
}

/// Body text at size 16 unless a line says otherwise.
fn body(text: &str, y: f32) -> (Element, LineStyle) {
    styled(line(text, 135.0, y, 600.0, 24.0), 16.0)
}

const fn styled(element: Element, size: f32) -> (Element, LineStyle) {
    (
        element,
        LineStyle {
            size,
            emphasized: false,
        },
    )
}

fn page(number: usize, lines: Vec<(Element, LineStyle)>) -> (Page, Vec<LineStyle>) {
    let (elements, styles) = lines.into_iter().unzip();
    let page = Page {
        number,
        width: WIDTH,
        height: HEIGHT,
        language: None,
        language_reliable: false,
        method: ExtractionMethod::TextLayer,
        elements,
        extraction_score: None,
    };
    (page, styles)
}

fn label(pages: Vec<(Page, Vec<LineStyle>)>) -> Vec<Page> {
    let (mut pages, mut styles): (Vec<Page>, Vec<Vec<LineStyle>>) = pages.into_iter().unzip();
    label_document(&mut pages, &mut styles);
    pages
}

fn kinds(page: &Page) -> Vec<(&str, ElementKind)> {
    page.elements
        .iter()
        .map(|e| (e.text.as_str(), e.kind))
        .collect()
}

#[test]
fn repeated_margin_lines_and_page_numbers_are_running_headers() {
    let pages = label(vec![
        page(
            3,
            vec![
                body("60 Triadic to Trinitarian", 54.0),
                body("Body text on the page.", 300.0),
            ],
        ),
        page(
            4,
            vec![
                body("Triadic to Trinitarian 61", 54.0),
                body("Other body text.", 300.0),
                body("62", 1120.0),
                body(". ", 1150.0),
            ],
        ),
    ]);
    assert_eq!(pages[0].elements[0].kind, ElementKind::RunningHeader);
    assert_eq!(pages[1].elements[0].kind, ElementKind::RunningHeader);
    assert_eq!(pages[1].elements[2].kind, ElementKind::RunningFooter);
    // Punctuation alone is not a page number.
    assert_eq!(pages[1].elements[3].kind, ElementKind::Paragraph);
    assert_eq!(pages[0].elements[1].kind, ElementKind::Paragraph);
}

#[test]
fn a_heading_repeated_at_the_top_of_pages_stays_a_heading() {
    let heading = || {
        let (mut element, style) = body("Sample Document", 44.0);
        element.kind = ElementKind::H1;
        (element, style)
    };
    let pages = label(vec![
        page(1, vec![heading(), body("Text.", 300.0)]),
        page(2, vec![heading(), body("Text.", 300.0)]),
    ]);
    assert!(pages.iter().all(|p| p.elements[0].kind == ElementKind::H1));
}

#[test]
fn lines_below_the_footnote_rule_are_footnotes_and_the_rule_is_dropped() {
    let pages = label(vec![page(
        5,
        vec![
            body("Body text that cites a note.1", 300.0),
            styled(line("   ", 135.0, 900.0, 221.0, 16.0), 16.0),
            styled(line("1 A footnote that", 135.0, 920.0, 600.0, 20.0), 13.0),
            styled(line("continues here.", 135.0, 941.0, 600.0, 20.0), 13.0),
        ],
    )]);
    assert_eq!(
        kinds(&pages[0]),
        [
            ("Body text that cites a note.1", ElementKind::Paragraph),
            ("1 A footnote that", ElementKind::Footnote),
            ("continues here.", ElementKind::Footnote),
        ]
    );
}

#[test]
fn small_numbered_lines_at_the_foot_are_footnotes_without_a_rule() {
    let pages = label(vec![page(
        5,
        vec![
            body("Body line one.", 300.0),
            body("Body line two.", 324.0),
            body("Body line three.", 348.0),
            styled(
                line("2 A note in small type.", 135.0, 1000.0, 600.0, 20.0),
                13.0,
            ),
        ],
    )]);
    assert_eq!(pages[0].elements[3].kind, ElementKind::Footnote);
    assert_eq!(pages[0].elements[2].kind, ElementKind::Paragraph);
}

#[test]
fn labelled_blocks_caps_headings_and_bibliography_span_pages() {
    let pages = label(vec![
        page(
            1,
            vec![
                body("Abstract", 200.0),
                body("This article argues a point.", 224.0),
                body("It has two lines.", 248.0),
                body("Body after a gap.", 400.0),
                styled(line("INTRODUCTION", 400.0, 500.0, 118.0, 24.0), 16.0),
                body("Body text.", 530.0),
                styled(line("BIBLIOGRAPHY", 400.0, 800.0, 118.0, 24.0), 16.0),
                body("Barth, Karl. Church Dogmatics.", 830.0),
            ],
        ),
        page(
            2,
            vec![body("Vanhoozer, Kevin J. Remythologizing Theology.", 100.0)],
        ),
    ]);
    let first: Vec<ElementKind> = pages[0].elements.iter().map(|e| e.kind).collect();
    assert_eq!(
        first,
        [
            ElementKind::H2,
            ElementKind::Abstract,
            ElementKind::Abstract,
            ElementKind::Paragraph,
            ElementKind::H2,
            ElementKind::Paragraph,
            ElementKind::H2,
            ElementKind::Reference,
        ]
    );
    assert_eq!(pages[1].elements[0].kind, ElementKind::Reference);
    assert_eq!(pages[0].elements[5].section_path, ["INTRODUCTION"]);
}

#[test]
fn cover_page_front_matter_needs_issue_details() {
    let large = |text: &str, y: f32| styled(line(text, 135.0, y, 600.0, 30.0), 24.0);
    let pages = label(vec![page(
        1,
        vec![
            large("Eleutheria", 148.0),
            body("Volume 1", 230.0),
            body("October 2010", 260.0),
            large("Triadic to Trinitarian", 348.0),
            body("Joshua C. Stone", 420.0),
            body("Liberty University, jstone@liberty.edu", 450.0),
            body("Recommended Citation", 600.0),
            body("Stone, Joshua C. (2010) \"Triadic to Trinitarian,\"", 624.0),
            body(
                "Follow this and additional works at: https://example.org",
                1047.0,
            ),
            body("https://example.org/vol1/iss1/6", 1064.0),
        ],
    )]);
    assert_eq!(
        pages[0].elements.iter().map(|e| e.kind).collect::<Vec<_>>(),
        [
            ElementKind::JournalTitle,
            ElementKind::PublicationMetadata,
            ElementKind::PublicationMetadata,
            ElementKind::Title,
            ElementKind::Author,
            ElementKind::Affiliation,
            ElementKind::H2,
            ElementKind::Citation,
            ElementKind::RunningFooter,
            ElementKind::RunningFooter,
        ]
    );

    // A plain first page with a large heading and a References section keeps its
    // heading: there is no issue information, abstract or citation label.
    let (mut plain, styles) = page(
        1,
        vec![
            large("Sample Document", 100.0),
            body("A paragraph.", 160.0),
            body("References", 220.0),
            body("[1] Example Source.", 250.0),
        ],
    );
    plain.elements[0].kind = ElementKind::H1;
    let pages = label(vec![(plain, styles)]);
    assert_eq!(pages[0].elements[0].kind, ElementKind::H1);
    assert_eq!(pages[0].elements[3].kind, ElementKind::Reference);
}

#[test]
fn paragraphs_are_numbered_by_first_line_indent_across_pages() {
    let indented = |text: &str, y: f32| styled(line(text, 162.0, y, 655.0, 24.0), 16.0);
    let pages = label(vec![
        page(
            1,
            vec![
                indented("First paragraph starts", 150.0),
                body("and continues here.", 172.0),
                indented("Second paragraph starts", 193.0),
                // Poppler emits this line after the one below it.
                body("and runs to the foot", 237.0),
                body("of the second paragraph", 215.0),
                body("of the page without ending", 258.0),
            ],
        ),
        page(
            2,
            vec![
                body("ends on the next page.", 107.0),
                body("Short.", 128.0),
                indented("Third paragraph.", 150.0),
            ],
        ),
    ]);
    let numbers = |page: &Page| {
        page.elements
            .iter()
            .map(|e| e.paragraph)
            .collect::<Vec<_>>()
    };
    assert_eq!(
        numbers(&pages[0]),
        [Some(1), Some(1), Some(2), Some(2), Some(2), Some(2)]
    );
    assert_eq!(numbers(&pages[1]), [Some(2), Some(2), Some(3)]);
    // The late line now sits in reading order.
    assert_eq!(
        pages[0].elements[3..5]
            .iter()
            .map(|e| e.text.as_str())
            .collect::<Vec<_>>(),
        ["of the second paragraph", "and runs to the foot"]
    );
}

#[test]
fn a_late_line_rejoins_its_paragraph_before_the_next_one() {
    let indented = |text: &str, y: f32| styled(line(text, 162.0, y, 655.0, 24.0), 16.0);
    let pages = label(vec![page(
        3,
        vec![
            indented("Paragraph five starts", 100.0),
            body("and goes on.", 122.0),
            indented("Paragraph six starts", 210.0),
            body("and ends.", 232.0),
            // Poppler emits the end of paragraph five last.
            body("Paragraph five ends", 144.0),
            body("here.", 166.0),
            styled(line("1 A note.", 135.0, 1000.0, 600.0, 20.0), 13.0),
        ],
    )]);
    let texts: Vec<&str> = pages[0].elements.iter().map(|e| e.text.as_str()).collect();
    assert_eq!(
        texts,
        [
            "Paragraph five starts",
            "and goes on.",
            "Paragraph five ends",
            "here.",
            "Paragraph six starts",
            "and ends.",
            "1 A note.",
        ]
    );
}

#[test]
fn a_short_last_line_or_a_heading_ends_the_paragraph_at_a_page_break() {
    let short = |text: &str, y: f32| styled(line(text, 135.0, y, 60.0, 24.0), 16.0);
    let pages = label(vec![
        page(
            1,
            vec![body("A full body line that", 150.0), short("ends.", 172.0)],
        ),
        page(2, vec![body("Not a continuation.", 107.0)]),
    ]);
    assert_eq!(pages[1].elements[0].paragraph, Some(2));

    let pages = label(vec![
        page(1, vec![body("A full body line that", 150.0)]),
        page(
            2,
            vec![
                styled(line("INTRODUCTION", 400.0, 60.0, 118.0, 24.0), 16.0),
                body("Body after the heading.", 107.0),
            ],
        ),
    ]);
    assert_eq!(pages[1].elements[1].paragraph, Some(2));
}

#[test]
fn pages_with_lines_in_pieces_keep_their_order() {
    // One printed line left in two pieces on one row, then a line above it emitted late.
    let pages = label(vec![page(
        1,
        vec![
            body("Second line", 122.0),
            styled(
                line("and its other piece.", 400.0, 122.0, 300.0, 24.0),
                16.0,
            ),
            body("First line", 100.0),
        ],
    )]);
    let texts: Vec<&str> = pages[0].elements.iter().map(|e| e.text.as_str()).collect();
    assert_eq!(texts, ["Second line", "and its other piece.", "First line"]);
}
