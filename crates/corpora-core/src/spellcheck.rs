//! Matchum dictionary engine with location-aware diagnostic policy.

use crate::{
    Error, Result,
    diagnostic::{
        Applicability, Certainty, Diagnostic, DiagnosticCategory, DiagnosticReport, Severity,
        SourceMap, Suggestion, TextEdit,
    },
    language::{DICTIONARIES, LanguageDetection, detect_language},
};
use matchum_dict::{
    dictionary::Dictionary,
    loader::{DictFormat, load_dictionary_from_bytes},
    repmap::RepMap,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    cell::RefCell,
    collections::{BTreeSet, HashMap},
    path::Path,
};

/// Text provenance determines whether an unknown spelling can block conversion.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TextRole {
    /// Primary historical reading text.
    Corpus,
    /// Header or descriptive metadata.
    Metadata,
    /// Introductory material outside the primary body.
    Frontmatter,
    /// Annotation text excluded from the main reading.
    Footnote,
    /// Other supplementary prose.
    Additional,
    /// Heading/title spelling is flagged but never blocks.
    Heading,
}

/// A diagnostic range uses Unicode scalar offsets within its input segment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpellDiagnostic {
    /// Stable category: `unknown_word` or `suspicious_typography`.
    pub code: String,
    /// Original source spelling.
    pub text: String,
    /// Inclusive scalar start.
    pub start: usize,
    /// Exclusive scalar end.
    pub end: usize,
    /// Policy severity, not a statistical probability: 20 low, 60 medium, 90 high.
    pub score: u8,
    /// Whether this unresolved diagnostic blocks conversion.
    pub blocking: bool,
    /// Optional for low/medium; required before unresolved high issues can pass.
    pub review_optional: bool,
    /// Candidate corrections from the selected Matchum dictionary.
    pub suggestions: Vec<String>,
    /// Deterministic correction eligible for the repair pass (never corpus text).
    pub replacement: Option<String>,
    /// Human-readable reason for the policy decision.
    pub reason: String,
}

/// Language and spelling diagnostics for one text segment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpellReport {
    /// Detection or supplied language evidence.
    pub language: LanguageDetection,
    /// False if any diagnostic is blocking.
    pub passed: bool,
    /// All reported occurrences; duplicate words are not silently capped.
    pub diagnostics: Vec<SpellDiagnostic>,
}

#[derive(Deserialize)]
struct InstalledDictionary {
    file: String,
    sha256: String,
    #[serde(default)]
    case_sensitive: bool,
    #[serde(default)]
    rep_map: Vec<(String, String)>,
    #[serde(default)]
    ignore_forbidden_words: bool,
}

struct LoadedDictionary {
    words: Box<dyn Dictionary>,
    ignore_forbidden: bool,
}

/// Reusable engine. Dictionary artifacts are local, allowlisted and hash checked.
pub struct SpellEngine {
    dictionaries: HashMap<String, LoadedDictionary>,
    words: Regex,
    suspicious: Regex,
    suggestions: RefCell<HashMap<String, Vec<String>>>,
}

impl SpellEngine {
    /// Load the manifest created by `tools/install_dictionaries.py`.
    pub fn load(root: &Path) -> Result<Self> {
        Self::load_selected(root, &[])
    }

    /// Load only requested dictionaries, avoiding unrelated language models in memory.
    pub fn load_selected(root: &Path, selected: &[&str]) -> Result<Self> {
        let manifest: HashMap<String, InstalledDictionary> =
            serde_json::from_slice(&std::fs::read(root.join("installed.json"))?)
                .map_err(|e| Error::config(e.to_string()))?;
        let mut dictionaries = HashMap::new();
        let root = root.canonicalize()?;
        for (name, entry) in manifest {
            if !selected.is_empty() && !selected.contains(&name.as_str()) {
                continue;
            }
            if !DICTIONARIES.contains(&name.as_str()) {
                return Err(Error::config(format!(
                    "Dictionary outside allowlist: {name}"
                )));
            }
            let path = root.join(&entry.file).canonicalize()?;
            if !path.starts_with(&root) {
                return Err(Error::config("Dictionary path escapes root"));
            }
            let data = std::fs::read(&path)?;
            if format!("{:x}", Sha256::digest(&data)) != entry.sha256 {
                return Err(Error::config(format!("Dictionary hash mismatch: {name}")));
            }
            let format = if entry.file.ends_with(".trie.gz") {
                DictFormat::TrieV3Gz
            } else if Path::new(&entry.file)
                .extension()
                .is_some_and(|ext| ext.eq_ignore_ascii_case("trie"))
            {
                DictFormat::TrieV3
            } else if entry.file.ends_with(".txt.gz") {
                DictFormat::TxtGz
            } else if Path::new(&entry.file)
                .extension()
                .is_some_and(|ext| ext.eq_ignore_ascii_case("txt"))
            {
                DictFormat::Txt
            } else {
                return Err(Error::config("Unsupported dictionary format"));
            };
            let words: Box<dyn Dictionary> = if ["he", "it_IT", "la"].contains(&name.as_str()) {
                if entry.case_sensitive || !entry.rep_map.is_empty() {
                    return Err(Error::config(
                        "Unsupported compact dictionary configuration",
                    ));
                }
                Box::new(
                    crate::compact_trie::CompactTrie::load(
                        &data,
                        Path::new(&entry.file)
                            .extension()
                            .is_some_and(|ext| ext.eq_ignore_ascii_case("gz")),
                    )
                    .map_err(|e| Error::config(e.to_string()))?,
                )
            } else {
                let mut words = load_dictionary_from_bytes(&data, format)
                    .map_err(|e| Error::config(e.to_string()))?;
                words.set_case_sensitive(entry.case_sensitive);
                words.set_repmap(RepMap::new(entry.rep_map));
                Box::new(words)
            };
            dictionaries.insert(
                name,
                LoadedDictionary {
                    words,
                    ignore_forbidden: entry.ignore_forbidden_words,
                },
            );
        }
        for id in selected {
            if !dictionaries.contains_key(*id) {
                return Err(Error::config(format!("Dictionary not installed: {id}")));
            }
        }
        Self::from_dictionaries(dictionaries)
    }

    fn from_dictionaries(dictionaries: HashMap<String, LoadedDictionary>) -> Result<Self> {
        Ok(Self {
            dictionaries,
            suggestions: RefCell::new(HashMap::new()),
            words: Regex::new(r"[\p{L}\p{M}]+(?:['’\x{200c}][\p{L}\p{M}]+)*")
                .map_err(|e| Error::config(e.to_string()))?,
            suspicious: Regex::new(
                r"[!?;,]{2,}|\.{2,}|[\p{L}\p{M}]+[0-9@#$%_\x{200b}\x{feff}]+[\p{L}\p{M}]+",
            )
            .map_err(|e| Error::config(e.to_string()))?,
        })
    }

    fn lookup(
        &self,
        dictionary: &LoadedDictionary,
        id: &str,
        word: &str,
    ) -> matchum_dict::dictionary::FindResult {
        let mut found = dictionary.words.find(word);
        let letters: Vec<_> = word.chars().collect();
        let capitalized = letters.first().is_some_and(|c| c.is_uppercase())
            && (letters.iter().skip(1).all(|c| !c.is_uppercase())
                || letters.iter().all(|c| !c.is_lowercase()));
        if !found.found && !found.forbidden && capitalized {
            found = dictionary.words.find(&word.to_lowercase());
        }
        if !found.found && !found.forbidden {
            for supplement in ["en_shared", "public-licenses"] {
                if supplement == "en_shared" && !id.starts_with("en_") {
                    continue;
                }
                if let Some(extra) = self.dictionaries.get(supplement) {
                    let extra_found = extra.words.find(word);
                    if extra_found.found && !extra_found.forbidden {
                        found = extra_found;
                        break;
                    }
                }
            }
        }
        found
    }

    /// Check literal text. Source text cannot execute inline cspell directives.
    pub fn check(&self, text: &str, role: TextRole, hint: Option<&str>) -> Result<SpellReport> {
        let language = detect_language(text, hint)?;
        let id = language.dictionary.as_deref().ok_or_else(|| {
            Error::config("Language unresolved or unsupported; supply a supported locale")
        })?;
        let dictionary = self
            .dictionaries
            .get(id)
            .ok_or_else(|| Error::config(format!("Dictionary not installed: {id}")))?;
        let mut diagnostics = Vec::new();
        let mut cache = self.suggestions.borrow_mut();
        for token in self.words.find_iter(text) {
            let word = token.as_str();
            let found = self.lookup(dictionary, id, word);
            if found.found && !found.forbidden {
                continue;
            }
            // Matchum's ignoreForbiddenWords treats forbidden entries as unknown, never accepted.
            let forbidden = found.forbidden && !dictionary.ignore_forbidden;
            let correction = repeated_letter_fix(word, dictionary.words.as_ref());
            let repeated = correction.is_some()
                || word
                    .chars()
                    .collect::<Vec<_>>()
                    .windows(3)
                    .any(|w| w[0] == w[1] && w[1] == w[2]);
            let corpus = role == TextRole::Corpus;
            let score = if role == TextRole::Heading || word.starts_with(char::is_uppercase) {
                20
            } else if corpus {
                60
            } else {
                90
            };
            let suggestions = cache
                .entry(format!("{id}:{word}"))
                .or_insert_with(|| {
                    if word.chars().count() <= 128 {
                        dictionary.words.suggest(word, 5)
                    } else {
                        Vec::new()
                    }
                })
                .clone();
            let replacement = if score == 90 { correction } else { None };
            diagnostics.push(SpellDiagnostic {
                code: "unknown_word".into(),
                text: word.into(),
                start: text[..token.start()].chars().count(),
                end: text[..token.end()].chars().count(),
                score,
                blocking: score == 90,
                review_optional: score < 90,
                suggestions,
                replacement,
                reason: if score == 20 {
                    "Heading or capitalized spelling is flagged but ignored"
                } else if repeated || forbidden {
                    "Repeated letters suggest a typo"
                } else if corpus {
                    "Corpus spelling or typography needs an optional AI suggestion"
                } else {
                    "Unknown spelling outside primary corpus content"
                }
                .into(),
            });
        }
        for token in self.suspicious.find_iter(text) {
            // A three-dot ellipsis is valid typography, not a duplicate punctuation error.
            if token.as_str() == "..." {
                continue;
            }
            let corpus = role == TextRole::Corpus;
            let score =
                if role == TextRole::Heading || token.as_str().starts_with(char::is_uppercase) {
                    20
                } else if corpus {
                    60
                } else {
                    90
                };
            diagnostics.push(SpellDiagnostic {
                code: "suspicious_typography".into(),
                text: token.as_str().into(),
                start: text[..token.start()].chars().count(),
                end: text[..token.end()].chars().count(),
                score,
                blocking: score == 90,
                review_optional: score < 90,
                suggestions: vec![],
                replacement: None,
                reason: "Repeated punctuation or a non-letter embedded in a word needs review"
                    .into(),
            });
        }
        diagnostics.sort_by_key(|d| (d.start, d.end));
        Ok(SpellReport {
            language,
            passed: !diagnostics.iter().any(|d| d.blocking),
            diagnostics,
        })
    }

    /// Check one text segment using the shared source-bound diagnostic contract.
    ///
    /// Coordinates refer to this exact decoded segment, not to an enclosing XML file.
    /// Pass a segment-specific identity and retain its mapping to source XML at the API layer.
    /// The legacy [`Self::check`] report and JSON shape remain unchanged.
    pub fn check_diagnostics(
        &self,
        source_id: &str,
        text: &str,
        role: TextRole,
        hint: Option<&str>,
    ) -> Result<DiagnosticReport> {
        let report = self.check(text, role, hint)?;
        let positions = SourceMap::new(text);
        let diagnostics = report
            .diagnostics
            .into_iter()
            .map(|issue| {
                let range = positions.scalar_range(issue.start..issue.end)?;
                let mut candidates = issue.suggestions;
                if let Some(replacement) = &issue.replacement {
                    candidates.retain(|candidate| candidate != replacement);
                    candidates.insert(0, replacement.clone());
                }
                let suggestions = candidates
                    .into_iter()
                    .map(|after| Suggestion {
                        message:
                            "Dictionary candidate; apply only under caller policy and revalidate"
                                .into(),
                        applicability: if issue.replacement.as_ref() == Some(&after) {
                            Applicability::Automatic
                        } else {
                            Applicability::Review
                        },
                        edits: vec![TextEdit {
                            range: range.clone(),
                            before: issue.text.clone(),
                            after,
                        }],
                    })
                    .collect();
                Ok(Diagnostic {
                    code: issue.code,
                    category: DiagnosticCategory::Spelling,
                    severity: if issue.blocking {
                        Severity::Error
                    } else {
                        Severity::Warning
                    },
                    blocking: issue.blocking,
                    score: Some(issue.score),
                    certainty: Certainty::Possible,
                    message: issue.reason,
                    locations: vec![range],
                    suggestions,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        Ok(DiagnosticReport::new(source_id, text, diagnostics))
    }
}

fn repeated_letter_fix(word: &str, dictionary: &dyn Dictionary) -> Option<String> {
    // Only lowercase repeated-letter deletions that yield exactly one known spelling.
    if word.chars().count() > 128 || word.chars().any(char::is_uppercase) {
        return None;
    }
    let chars: Vec<_> = word.chars().collect();
    let mut candidates = BTreeSet::new();
    for index in 1..chars.len() {
        if chars[index] == chars[index - 1] {
            let candidate: String = chars
                .iter()
                .enumerate()
                .filter(|(i, _)| *i != index)
                .map(|(_, c)| *c)
                .collect();
            if dictionary.has(&candidate) && !dictionary.is_forbidden(&candidate) {
                candidates.insert(candidate);
            }
        }
    }
    if candidates.len() == 1 {
        candidates.pop_first()
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn engine() -> SpellEngine {
        let words = load_dictionary_from_bytes(b"hello\nworld\nletter\n", DictFormat::Txt).unwrap();
        SpellEngine::from_dictionaries(HashMap::from([(
            "en_US".into(),
            LoadedDictionary {
                words: Box::new(words),
                ignore_forbidden: false,
            },
        )]))
        .unwrap()
    }
    #[test]
    fn corpus_findings_are_nonblocking() {
        assert!(
            engine()
                .check("archaick", TextRole::Corpus, Some("en"))
                .unwrap()
                .passed
        );
        let report = engine()
            .check("helllo world!!", TextRole::Corpus, Some("en"))
            .unwrap();
        assert!(report.passed);
        assert!(
            report
                .diagnostics
                .iter()
                .all(|d| d.score == 60 && d.replacement.is_none())
        );
    }
    #[test]
    fn headings_and_capitals_are_yellow_and_zero_width_is_orange() {
        for (text, role) in [
            ("unknown", TextRole::Heading),
            ("Unknown UNKNOWN", TextRole::Metadata),
        ] {
            let report = engine().check(text, role, Some("en")).unwrap();
            assert!(report.passed);
            assert!(!report.diagnostics.is_empty());
            assert!(report.diagnostics.iter().all(|d| d.score == 20));
        }
        let report = engine()
            .check("hello\u{200b}world", TextRole::Corpus, Some("en"))
            .unwrap();
        assert!(report.passed);
        assert!(
            report
                .diagnostics
                .iter()
                .any(|d| d.code == "suspicious_typography" && d.score == 60)
        );
    }
    #[test]
    fn metadata_repairs_are_dictionary_verified() {
        let report = engine()
            .check("helllo", TextRole::Metadata, Some("en"))
            .unwrap();
        assert_eq!(report.diagnostics[0].replacement.as_deref(), Some("hello"));
        assert_eq!(report.diagnostics[0].score, 90);
    }
    #[test]
    fn literal_directives_cannot_suppress_validation() {
        assert!(
            !engine()
                .check("cspell:disable\nhelllo", TextRole::Metadata, Some("en"))
                .unwrap()
                .passed
        );
    }
    #[test]
    fn offsets_are_unicode_scalars() {
        let report = engine()
            .check("😀 helllo", TextRole::Metadata, Some("en"))
            .unwrap();
        assert_eq!(
            (report.diagnostics[0].start, report.diagnostics[0].end),
            (2, 8)
        );
    }

    #[test]
    fn shared_spelling_diagnostics_preserve_policy_and_bind_the_segment() {
        let text = "😀 helllo";
        let engine = engine();
        let report = engine
            .check_diagnostics("doc#segment", text, TextRole::Metadata, Some("en"))
            .unwrap();
        let issue = &report.diagnostics[0];
        let range = &issue.locations[0];
        assert_eq!(
            (range.start.byte, range.start.scalar, range.end.scalar),
            (5, 2, 8)
        );
        assert_eq!(issue.score, Some(90));
        assert!(!report.passed());
        let edit = &issue.suggestions[0].edits[0];
        assert_eq!(edit.after, "hello");
        assert!(edit.matches_source(&report, text));
        assert!(!edit.matches_source(&report, "😀 helllo!"));
        let corpus = engine
            .check_diagnostics("doc#body", text, TextRole::Corpus, Some("en"))
            .unwrap();
        assert!(
            corpus
                .diagnostics
                .iter()
                .flat_map(|d| &d.suggestions)
                .all(|s| s.applicability == Applicability::Review)
        );
        let legacy =
            serde_json::to_value(engine.check(text, TextRole::Metadata, Some("en")).unwrap())
                .unwrap();
        assert!(legacy.get("source_sha256").is_none());
        assert_eq!(legacy["diagnostics"][0]["start"], 2);
        let json = serde_json::to_string(&report).unwrap();
        let decoded: DiagnosticReport = serde_json::from_str(&json).unwrap();
        assert_eq!(report, decoded);
    }
}
