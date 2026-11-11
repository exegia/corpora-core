//! JSON bridge for the reusable EPUB validator.

use std::{env, fs, process};

fn main() {
    let mut args = env::args_os().skip(1);
    let Some(path) = args.next() else {
        eprintln!("usage: corpora-epub-check INPUT.epub [--max-slots N]");
        process::exit(2);
    };
    let max_slots = match (args.next(), args.next(), args.next()) {
        (None, None, None) => corpora_convert::epub::DEFAULT_MAX_SLOTS,
        (Some(flag), Some(value), None) if flag == "--max-slots" => value
            .to_str()
            .and_then(|text| text.parse::<usize>().ok())
            .filter(|value| (1..=corpora_convert::epub::HARD_MAX_SLOTS).contains(value))
            .unwrap_or_else(|| {
                eprintln!(
                    "--max-slots must be between 1 and {}",
                    corpora_convert::epub::HARD_MAX_SLOTS
                );
                process::exit(2);
            }),
        _ => {
            eprintln!("usage: corpora-epub-check INPUT.epub [--max-slots N]");
            process::exit(2);
        }
    };
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(error) => {
            eprintln!("cannot read EPUB: {error}");
            process::exit(2);
        }
    };
    let report = corpora_convert::epub::validate_epub_with_slot_limit(&bytes, max_slots);
    match serde_json::to_string_pretty(&report) {
        Ok(json) => println!("{json}"),
        Err(error) => {
            eprintln!("cannot serialize report: {error}");
            process::exit(2);
        }
    }
    if !report.passed() {
        process::exit(1);
    }
}
