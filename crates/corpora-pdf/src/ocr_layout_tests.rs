use super::*;

fn word(text: &str, left: f32, top: f32, line: (i32, i32, i32)) -> OcrWord {
    OcrWord {
        text: text.to_owned(),
        confidence: 0.9,
        left,
        top,
        width: 10.0,
        height: 10.0,
        line,
    }
}

#[test]
fn aligned_table_cells_keep_each_word_once_with_its_geometry() {
    let mut words = Vec::new();
    for (line, top) in [(1, 10.0), (2, 25.0), (3, 40.0)] {
        words.extend([
            word("same", 0.0, top, (1, 1, line)),
            word("same", 50.0, top + 1.0, (1, 1, line)),
            word("two", 100.0, top, (1, 1, line)),
            word("words", 113.0, top, (1, 1, line)),
        ]);
    }
    let mut elements = ocr_elements(&words);
    classify(&mut elements, false);
    assert_eq!(elements.len(), 9);
    assert!(
        elements
            .iter()
            .all(|e| e.kind == ElementKind::TableCell && e.table_id == Some(1))
    );
    assert_eq!(elements[2].text, "two words");
    assert_eq!(elements[2].bounds.width, 23.0);
    let actual: Vec<_> = elements
        .iter()
        .flat_map(|e| &e.words)
        .map(|w| w.text.as_str())
        .collect();
    let expected: Vec<_> = words.iter().map(|w| w.text.as_str()).collect();
    assert_eq!(actual, expected);
    assert_eq!(elements[2].words[1].bounds.x, 113.0);
}

#[test]
fn isolated_justification_gap_does_not_split_a_sentence() {
    let words = [
        word("A", 0.0, 10.0, (1, 1, 1)),
        word("sentence", 45.0, 10.0, (1, 1, 1)),
        word("next", 10.0, 25.0, (1, 1, 2)),
        word("line", 23.0, 25.0, (1, 1, 2)),
    ];
    let elements = ocr_elements(&words);
    assert_eq!(elements[0].text, "A sentence");
    assert_eq!(elements.len(), 2);
    assert!(elements.iter().all(|e| e.table_id.is_none()));
}

#[test]
fn aligned_prose_columns_keep_block_order_without_table_labels() {
    let words = [
        word("left-top", 0.0, 10.0, (1, 1, 1)),
        word("left-bottom", 0.0, 30.0, (1, 1, 2)),
        word("right-top", 100.0, 10.0, (2, 1, 1)),
        word("right-bottom", 100.0, 30.0, (2, 1, 2)),
    ];
    let mut elements = ocr_elements(&words);
    classify(&mut elements, false);
    assert_eq!(
        elements.iter().map(|e| e.text.as_str()).collect::<Vec<_>>(),
        ["left-top", "left-bottom", "right-top", "right-bottom"]
    );
    assert!(
        elements
            .iter()
            .all(|e| e.kind == ElementKind::Paragraph && e.table_id.is_none())
    );
}

#[test]
fn long_parallel_prose_fragments_are_not_a_table() {
    let mut words = Vec::new();
    for (line, y) in [(1, 10.0), (2, 30.0)] {
        for x in [0.0, 13.0, 26.0, 39.0, 100.0, 113.0, 126.0, 139.0] {
            words.push(word("text", x, y, (1, 1, line)));
        }
    }
    let elements = ocr_elements(&words);
    assert_eq!(elements.len(), 2);
    assert!(elements.iter().all(|e| e.table_id.is_none()));
}

#[test]
fn spanning_heading_and_footer_follow_block_order_with_section_ancestry() {
    let mut heading = word("Title", 0.0, 0.0, (1, 1, 1));
    heading.height = 18.0;
    heading.width = 200.0;
    let words = [
        heading,
        word("left", 0.0, 40.0, (2, 1, 1)),
        word("right", 100.0, 30.0, (3, 1, 1)),
        word("footer", 0.0, 100.0, (4, 1, 1)),
    ];
    let mut elements = ocr_elements(&words);
    classify(&mut elements, false);
    assert_eq!(elements[0].kind, ElementKind::H1);
    assert_eq!(
        elements.iter().map(|e| e.text.as_str()).collect::<Vec<_>>(),
        ["Title", "left", "right", "footer"]
    );
    assert!(elements.iter().all(|e| e.section_path == ["Title"]));
}

#[test]
fn rtl_words_and_combining_marks_retain_recognition_order() {
    let words = [
        word("לֹא", 30.0, 10.0, (1, 1, 1)),
        word("לָא", 16.0, 10.0, (1, 1, 1)),
        word("no", 100.0, 10.0, (1, 1, 1)),
        word("לֹא", 30.0, 30.0, (1, 1, 2)),
        word("לָא", 16.0, 30.0, (1, 1, 2)),
        word("no", 100.0, 30.0, (1, 1, 2)),
    ];
    let elements = ocr_elements(&words);
    assert_eq!(elements.len(), 4);
    assert_eq!(elements[0].text, "לֹא לָא");
    assert_eq!(elements[0].words[0].text, "לֹא");
    assert_eq!(elements[0].words[1].bounds.x, 16.0);
}

#[test]
fn older_serialized_elements_without_words_still_load() {
    let element = ocr_element(&[&word("old", 0.0, 0.0, (1, 1, 1))]);
    let mut value = serde_json::to_value(element).unwrap();
    value.as_object_mut().unwrap().remove("words");
    let decoded: Element = serde_json::from_value(value).unwrap();
    assert!(decoded.words.is_empty());
    assert_eq!(decoded.text, "old");
}

#[test]
fn hanging_indent_lists_are_not_split_into_table_cells() {
    for markers in [["1.", "2."], ["•", "•"], ["-", "-"]] {
        let words = [
            word(markers[0], 0.0, 10.0, (1, 1, 1)),
            word("First", 50.0, 10.0, (1, 1, 1)),
            word("item", 63.0, 10.0, (1, 1, 1)),
            word(markers[1], 0.0, 30.0, (1, 1, 2)),
            word("Second", 50.0, 30.0, (1, 1, 2)),
            word("item", 63.0, 30.0, (1, 1, 2)),
        ];
        let mut elements = ocr_elements(&words);
        classify(&mut elements, false);
        assert_eq!(elements.len(), 2);
        assert!(
            elements
                .iter()
                .all(|e| e.kind == ElementKind::ListItem && e.table_id.is_none())
        );
        assert_eq!(elements[0].words.len(), 3);
    }
}
