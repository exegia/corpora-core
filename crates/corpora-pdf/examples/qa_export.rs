//! Test-only JSON bridge for the static PDF review site.

use std::env;

use corpora_pdf::{ExtractOptions, extract_pdf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let path = args.next().ok_or("usage: qa_export PDF [OCR_LANGUAGES]")?;
    let mut options = ExtractOptions::default();
    if let Some(languages) = args.next() {
        options.ocr_languages = languages;
    }
    let result = extract_pdf(path, &options)?;
    serde_json::to_writer_pretty(std::io::stdout(), &result)?;
    Ok(())
}
