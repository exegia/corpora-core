//! JSON-lines bridge for callers outside Rust; one response per request.
use corpora_core::{
    language::detect_language,
    spellcheck::{SpellEngine, TextRole},
};
use serde::Deserialize;
use std::{
    io::{self, BufRead},
    path::PathBuf,
};

#[derive(Deserialize)]
struct Request {
    text: String,
    locale: Option<String>,
    role: Option<TextRole>,
    #[serde(default)]
    detect_only: bool,
    #[serde(default)]
    supplements: Vec<String>,
}

fn main() {
    let root = std::env::args_os().nth(1).map(PathBuf::from);
    let mut engines = std::collections::HashMap::new();
    for line in io::stdin().lock().lines() {
        let result = (|| -> Result<serde_json::Value, Box<dyn std::error::Error>> {
            let request: Request = serde_json::from_str(&line?)?;
            Ok(
                if let Some(root) = root.as_ref().filter(|_| !request.detect_only) {
                    let detection = detect_language(&request.text, request.locale.as_deref())?;
                    let id = detection
                        .dictionary
                        .ok_or("Language unresolved or unsupported")?;
                    if request
                        .supplements
                        .iter()
                        .any(|s| !["en_shared", "public-licenses"].contains(&s.as_str()))
                    {
                        return Err("Only en_shared and public-licenses are supplements".into());
                    }
                    let mut selected = vec![id.as_str()];
                    selected.extend(request.supplements.iter().map(String::as_str));
                    selected.sort_unstable();
                    selected.dedup();
                    let key = selected.join("+");
                    if !engines.contains_key(&key) {
                        engines.insert(key.clone(), SpellEngine::load_selected(root, &selected)?);
                    }
                    let engine = &engines[&key];
                    serde_json::to_value(engine.check(
                        &request.text,
                        request.role.unwrap_or(TextRole::Corpus),
                        request.locale.as_deref(),
                    )?)?
                } else {
                    serde_json::to_value(detect_language(
                        &request.text,
                        request.locale.as_deref(),
                    )?)?
                },
            )
        })();
        println!(
            "{}",
            result.unwrap_or_else(|e| serde_json::json!({"error":e.to_string()}))
        );
    }
}
