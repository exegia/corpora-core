//! Compile the generated Rust model and pin its JSON wire representation.

#[allow(clippy::pedantic, clippy::derive_partial_eq_without_eq, dead_code)]
#[path = "../../../generated/rust/document.rs"]
mod document;
#[allow(clippy::pedantic, clippy::derive_partial_eq_without_eq, dead_code)]
#[path = "../../../generated/rust/enums.rs"]
mod enums;

#[test]
fn generated_text_range_round_trips_as_an_object() {
    let range = document::TextRange { start: 1, end: 2 };
    let json = serde_json::to_string(&range).unwrap();
    assert_eq!(json, r#"{"start":1,"end":2}"#);
    assert_eq!(
        serde_json::from_str::<document::TextRange>(&json).unwrap(),
        range
    );
    assert_eq!(
        serde_json::from_str::<document::TextRange>(r#"{"start":1,"end":2,"ignored":"value"}"#)
            .unwrap(),
        range
    );
    assert!(serde_json::from_str::<document::TextRange>(r#"{"start":-1,"end":2}"#).is_err());
    assert!(
        serde_json::from_str::<document::TextRange>(r#"{"start":1,"end":4294967296}"#).is_err()
    );
}
