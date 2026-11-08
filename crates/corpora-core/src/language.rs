//! Language evidence and selection from the explicitly supported cspell dictionaries.

use crate::{Error, Result};

/// Only these cspell dictionary directories can be loaded.
pub const DICTIONARIES: &[&str] = &[
    "grc_GR",
    "ca",
    "en_US",
    "en_GB",
    "en_CA",
    "en_shared",
    "fr_FR_90",
    "fr_FR",
    "de_DE",
    "el",
    "he",
    "it_IT",
    "la",
    "fa_IR",
    "public-licenses",
];

/// Detection evidence. Regional defaults are suggestions, not inferred provenance.
#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct LanguageDetection {
    /// BCP-47 language/locale, or `und` when insufficient evidence exists.
    pub locale: String,
    /// Whatlang confidence; absent for an explicit hint.
    pub confidence: Option<f64>,
    /// `hint`, `statistical`, or `undetermined`.
    pub method: String,
    /// Selected directory from [`DICTIONARIES`], if supported.
    pub dictionary: Option<String>,
    /// Other relevant dictionaries; never silently union different regional spellings.
    pub alternatives: Vec<String>,
    /// Whether regional/orthographic choice is a default rather than detected.
    pub locale_is_default: bool,
    /// Selection caveat, if any.
    pub note: Option<String>,
}

fn selection(locale: &str) -> Option<(&'static str, &'static str)> {
    match locale.to_lowercase().replace('_', "-").as_str() {
        "en" | "en-us" => Some(("en-US", "en_US")),
        "en-gb" => Some(("en-GB", "en_GB")),
        "en-ca" => Some(("en-CA", "en_CA")),
        "fr" | "fr-fr" => Some(("fr-FR", "fr_FR")),
        "fr-fr-1990" | "fr-fr-90" => Some(("fr-FR", "fr_FR_90")),
        "grc" | "grc-gr" => Some(("grc-GR", "grc_GR")),
        "ca" | "ca-es" => Some(("ca", "ca")),
        "de" | "de-de" => Some(("de-DE", "de_DE")),
        "el" | "el-gr" => Some(("el", "el")),
        "he" | "he-il" => Some(("he", "he")),
        "it" | "it-it" => Some(("it-IT", "it_IT")),
        "la" => Some(("la", "la")),
        "fa" | "fa-ir" => Some(("fa-IR", "fa_IR")),
        _ => None,
    }
}

/// Detect text language or honor a supplied document `xml:lang`/locale hint.
///
/// Unsupported languages never fall back to English. Ancient Greek requires a `grc`
/// hint: polytonic spelling alone cannot reliably distinguish it from modern Greek.
pub fn detect_language(text: &str, hint: Option<&str>) -> Result<LanguageDetection> {
    let mut result = LanguageDetection {
        locale: "und".into(),
        confidence: None,
        method: "undetermined".into(),
        dictionary: None,
        alternatives: Vec::new(),
        locale_is_default: false,
        note: None,
    };
    let candidate = if let Some(hint) = hint {
        result.method = "hint".into();
        hint.to_owned()
    } else {
        if text.chars().filter(|c| c.is_alphabetic()).count() < 20 {
            result.note = Some("Too little alphabetic text; supply a locale hint".into());
            return Ok(result);
        }
        let Some(info) = whatlang::detect(text) else {
            return Ok(result);
        };
        result.confidence = Some(info.confidence());
        if !info.is_reliable() {
            result.note = Some("Uncertain language; supply a locale hint".into());
            return Ok(result);
        }
        result.method = "statistical".into();
        match info.lang() {
            whatlang::Lang::Eng => "en",
            whatlang::Lang::Fra => "fr",
            whatlang::Lang::Deu => "de",
            whatlang::Lang::Ell => "el",
            whatlang::Lang::Heb => "he",
            whatlang::Lang::Ita => "it",
            whatlang::Lang::Lat => "la",
            whatlang::Lang::Cat => "ca",
            whatlang::Lang::Pes => "fa",
            other => other.code(),
        }
        .to_owned()
    };
    if let Some((locale, dictionary)) = selection(&candidate) {
        result.locale = locale.into();
        result.dictionary = Some(dictionary.into());
        result.locale_is_default = matches!(candidate.as_str(), "en" | "fr" | "de" | "it" | "fa");
        result.alternatives = match dictionary {
            "en_US" | "en_GB" | "en_CA" => vec!["en_US", "en_GB", "en_CA"],
            "fr_FR" | "fr_FR_90" => vec!["fr_FR", "fr_FR_90"],
            "el" | "grc_GR" => vec!["el", "grc_GR"],
            _ => vec![],
        }
        .into_iter()
        .filter(|s| *s != dictionary)
        .map(str::to_owned)
        .collect();
        if result.locale_is_default || dictionary == "el" {
            result.note = Some("Regional spelling and historical language require an explicit hint; suggested locale is a default".into());
        }
    } else if hint.is_some() {
        return Err(Error::config(format!(
            "Unsupported locale hint: {candidate}"
        )));
    } else {
        result.locale = candidate;
        result.note = Some("Detected language has no dictionary in the allowed catalog".into());
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hints_select_regional_and_historical_dictionaries() {
        for (hint, expected) in [
            ("en-CA", "en_CA"),
            ("grc", "grc_GR"),
            ("fr-FR-1990", "fr_FR_90"),
            ("la", "la"),
        ] {
            assert_eq!(
                detect_language("", Some(hint))
                    .unwrap()
                    .dictionary
                    .as_deref(),
                Some(expected)
            );
        }
    }
    #[test]
    fn short_input_does_not_invent_a_language() {
        assert_eq!(detect_language("123 hello", None).unwrap().locale, "und");
    }
    #[test]
    fn detects_french_prose() {
        let result = detect_language("La langue française est une langue très riche. Ce document contient plusieurs phrases écrites en français pour expliquer la littérature et son histoire.", None).unwrap();
        assert_eq!(result.dictionary.as_deref(), Some("fr_FR"));
    }
    #[test]
    fn unsupported_locale_does_not_use_english() {
        assert!(detect_language("", Some("ja")).is_err());
    }
}
