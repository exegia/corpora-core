//! JSON bridge: extract one local PDF and print the full `PdfExtraction`.
//!
//! Exit 0 on success, 2 on invalid arguments or an extraction error.

use std::{env, path::PathBuf, process};

use corpora_pdf::{ExtractOptions, extract_pdf};

const USAGE: &str = "usage: corpora-pdf-extract INPUT.pdf [--languages LANGS] \
[--tessdata DIR] [--max-pages N] [--no-visual-check]";

fn fail(message: &str) -> ! {
    eprintln!("{message}");
    process::exit(2);
}

fn main() {
    let mut args = env::args_os().skip(1);
    let Some(path) = args.next() else { fail(USAGE) };
    let mut options = ExtractOptions::default();
    while let Some(flag) = args.next() {
        let mut value = || {
            args.next()
                .and_then(|v| v.into_string().ok())
                .unwrap_or_else(|| fail(USAGE))
        };
        match flag.to_str() {
            Some("--languages") => options.ocr_languages = value(),
            Some("--tessdata") => options.tessdata_dir = Some(PathBuf::from(value())),
            Some("--max-pages") => {
                options.max_pages = value()
                    .parse()
                    .ok()
                    .filter(|n| *n > 0)
                    .unwrap_or_else(|| fail("--max-pages must be a positive integer"));
            }
            Some("--no-visual-check") => options.verify_text_layer_with_ocr = false,
            _ => fail(USAGE),
        }
    }
    match extract_pdf(&path, &options) {
        Ok(result) => match serde_json::to_string(&result) {
            Ok(json) => println!("{json}"),
            Err(error) => fail(&format!("cannot serialize extraction: {error}")),
        },
        Err(error) => fail(&format!("{error}")),
    }
}
