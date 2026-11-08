//! JSON bridge for the reusable EPUB validator.

use std::{env, fs, process};

fn main() {
    let Some(path) = env::args_os().nth(1) else {
        eprintln!("usage: corpora-epub-check INPUT.epub");
        process::exit(2);
    };
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(error) => {
            eprintln!("cannot read EPUB: {error}");
            process::exit(2);
        }
    };
    let report = corpora_convert::epub::validate_epub(&bytes);
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
