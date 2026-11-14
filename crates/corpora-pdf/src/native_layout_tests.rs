use super::*;

/// Parse a Poppler `pdftohtml -xml` page and classify it as a native page.
fn native(page_xml: &str) -> Vec<Element> {
    let xml = format!(
        r#"<pdf2xml><page number="1" top="0" left="0" height="1188" width="918">
<fontspec id="0" size="16" family="Body"/>
<fontspec id="1" size="12" family="Body"/>
<fontspec id="2" size="16" family="Body"/>
{page_xml}
</page></pdf2xml>"#
    );
    let document = roxmltree::Document::parse(&xml).expect("test XML parses");
    let page = document
        .descendants()
        .find(|n| n.has_tag_name("page"))
        .expect("page node");
    let font_sizes: HashMap<&str, f32> = page
        .children()
        .filter(|n| n.has_tag_name("fontspec"))
        .filter_map(|n| Some((n.attribute("id")?, n.attribute("size")?.parse().ok()?)))
        .collect();
    let mut elements: Vec<Element> = crate::native::parse_elements(page, &font_sizes)
        .expect("page parses")
        .into_iter()
        .map(|(element, _)| element)
        .collect();
    classify(&mut elements, true);
    elements
}

#[test]
fn small_caps_heading_is_one_line_and_not_a_table() {
    // Capitals at 16pt (top 561), the rest at 12pt (top 565), as Poppler emits them.
    let elements = native(
        r#"<text top="561" left="168" width="13" height="24" font="0">A</text>
<text top="565" left="181" width="108" height="19" font="1">UTHORITY OF </text>
<text top="561" left="289" width="15" height="24" font="0">H</text>
<text top="565" left="304" width="35" height="19" font="1">OLY </text>
<text top="561" left="339" width="11" height="24" font="0">S</text>
<text top="565" left="350" width="114" height="19" font="1">CRIPTURES</text>
<text top="561" left="464" width="5" height="24" font="0"> </text>"#,
    );
    assert_eq!(elements.len(), 1);
    assert_eq!(elements[0].text, "AUTHORITY OF HOLY SCRIPTURES ");
    assert_eq!(elements[0].kind, ElementKind::Paragraph);
    assert_eq!(elements[0].table_id, None);
    let b = &elements[0].bounds;
    assert_eq!((b.x, b.y, b.width, b.height), (168.0, 561.0, 301.0, 24.0));
}

#[test]
fn italic_runs_rejoin_their_sentence_lines() {
    let elements = native(
        r#"<text top="100" left="108" width="200" height="24" font="0">Vanhoozer’s book </text>
<text top="100" left="308" width="120" height="24" font="2"><i>Is There a</i></text>
<text top="100" left="434" width="200" height="24" font="0">Meaning in This Text? argues</text>
<text top="122" left="108" width="300" height="24" font="0">that the reader’s task is </text>
<text top="122" left="408" width="80" height="24" font="2"><i>covenantal</i></text>
<text top="122" left="488" width="40" height="24" font="0">.</text>"#,
    );
    let texts: Vec<&str> = elements.iter().map(|e| e.text.as_str()).collect();
    assert_eq!(
        texts,
        [
            "Vanhoozer’s book Is There a Meaning in This Text? argues",
            "that the reader’s task is covenantal.",
        ]
    );
    assert!(elements.iter().all(|e| e.kind != ElementKind::TableCell));
    assert_eq!(elements[0].marks.len(), 1);
    assert_eq!(elements[0].marks[0].kind, MarkKind::Italic);
    assert_eq!(elements[0].marks[0].text, "Is There a");
}

#[test]
fn widely_spaced_columns_still_form_a_table() {
    let elements = native(
        r#"<text top="350" left="108" width="49" height="17" font="1"><b>Name</b></text>
<text top="350" left="390" width="48" height="17" font="1"><b>Value</b></text>
<text top="377" left="108" width="46" height="17" font="1">Alpha</text>
<text top="377" left="390" width="20" height="17" font="1">42</text>"#,
    );
    assert_eq!(elements.len(), 4);
    assert!(
        elements
            .iter()
            .all(|e| e.kind == ElementKind::TableCell && e.table_id == Some(1))
    );
}

#[test]
fn page_columns_on_the_same_baseline_stay_separate() {
    // A gutter of 36 units is wider than any word space at this line height.
    let elements = native(
        r#"<text top="200" left="108" width="380" height="24" font="0">end of a left-column line</text>
<text top="200" left="524" width="380" height="24" font="0">start of a right-column line</text>"#,
    );
    assert_eq!(elements.len(), 2);
}

#[test]
fn a_visible_gap_without_a_space_gains_one() {
    let elements = native(
        r#"<text top="100" left="108" width="60" height="24" font="0">speech</text>
<text top="100" left="176" width="40" height="24" font="2"><i>act</i></text>"#,
    );
    assert_eq!(elements.len(), 1);
    assert_eq!(elements[0].text, "speech act");
}

#[test]
fn overprinted_text_is_kept_once() {
    let elements = native(
        r#"<text top="127" left="108" width="300" height="23" font="0">Triadic to Trinitarian</text>
<text top="127" left="108" width="300" height="23" font="0">Triadic to Trinitarian</text>
<text top="151" left="108" width="65" height="23" font="0">Theory </text>
<text top="151" left="108" width="65" height="23" font="0">Theory </text>"#,
    );
    let texts: Vec<&str> = elements.iter().map(|e| e.text.as_str()).collect();
    assert_eq!(texts, ["Triadic to Trinitarian", "Theory "]);
    assert!(elements.iter().all(|e| e.kind != ElementKind::TableCell));
}

#[test]
fn out_of_order_fragments_and_indents_are_not_a_table() {
    // Poppler emits a line's trailing space after the next line, and an indent as a
    // lone space followed by a gap.
    let elements = native(
        r#"<text top="431" left="108" width="77" height="24" font="0">authors.</text>
<text top="453" left="108" width="5" height="24" font="0"> </text>
<text top="453" left="162" width="650" height="24" font="0">A representative example</text>
<text top="431" left="185" width="5" height="24" font="0"> </text>
<text top="475" left="108" width="300" height="24" font="0">that the Scriptures are the Word</text>
<text top="475" left="430" width="12" height="16" font="1">5</text>
<text top="475" left="408" width="22" height="24" font="0"> of</text>"#,
    );
    assert!(elements.iter().all(|e| e.kind != ElementKind::TableCell));
    let texts: Vec<&str> = elements.iter().map(|e| e.text.as_str()).collect();
    assert_eq!(
        texts,
        [
            "authors. ",
            " ",
            "A representative example",
            "that the Scriptures are the Word of5",
        ]
    );
}

#[test]
fn two_prose_columns_on_shared_baselines_are_not_a_table() {
    let elements = native(
        r#"<text top="186" left="84" width="489" height="14" font="1">ment prophet and is able to perceive the true intent of their writings</text>
<text top="186" left="714" width="488" height="14" font="1">Justin was acquainted with Judaism. Not only is he familiar with</text>
<text top="203" left="83" width="229" height="13" font="1">means of charismatic illumination.</text>
<text top="203" left="714" width="488" height="14" font="1">the text of the Old Testament, he also knows the exegesis of it</text>"#,
    );
    assert_eq!(elements.len(), 4);
    assert!(elements.iter().all(|e| e.kind != ElementKind::TableCell));
}
