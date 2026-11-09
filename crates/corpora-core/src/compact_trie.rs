//! Bounded shared `TrieXv3` adapter implementing Matchum's public Dictionary trait.
// Parser adapted from matchum-dict 0.0.1 (MIT), commit d3a3a7cdbcef8f1b0bd2711d42c7d51b49a2ac15.
// Copyright (c) 2025 matchum contributors. See tools/MATCHUM-LICENSE.
// Unlike the upstream loader, retain shared trie nodes instead of enumerating 107M words.
use matchum_dict::{
    dictionary::{Dictionary, FindResult},
    loader::LoadError,
};
use std::{collections::HashMap, io::Read};
use unicode_normalization::UnicodeNormalization;

pub struct CompactTrie {
    nodes: Vec<TrieNode>,
    count: usize,
    alphabet: Vec<char>,
}

impl CompactTrie {
    pub fn load(data: &[u8], gzip: bool) -> Result<Self, LoadError> {
        let mut content = String::new();
        let reader: Box<dyn Read + '_> = if gzip {
            Box::new(flate2::read::GzDecoder::new(data))
        } else {
            Box::new(data)
        };
        reader
            .take(32 * 1024 * 1024 + 1)
            .read_to_string(&mut content)?;
        if content.len() > 32 * 1024 * 1024 {
            return Err(LoadError::Format("Trie exceeds byte budget".into()));
        }
        Self::parse(&content)
    }

    fn parse(content: &str) -> Result<Self, LoadError> {
        let lines: Vec<_> = content.lines().collect();
        let start = lines
            .iter()
            .position(|s| s.contains("__DATA__"))
            .ok_or_else(|| LoadError::Format("Missing __DATA__".into()))?;
        let radix = parse_header(&lines[..start])?;
        let mut builder = TrieBuilder::new();
        let mut state = ParseState::Main;
        for line in &lines[start + 1..] {
            for c in line.chars() {
                state = process_char(&mut builder, state, c, radix);
                if builder.invalid {
                    return Err(LoadError::Format("Invalid or over-budget trie".into()));
                }
            }
        }
        if !matches!(state, ParseState::Main | ParseState::Back) {
            return Err(LoadError::Format("Truncated trie escape/reference".into()));
        }
        if builder
            .nodes
            .iter()
            .any(|node| node.children.keys().any(|c| matches!(c, '+' | ':' | '=')))
        {
            return Err(LoadError::Format(
                "Unsupported compound/suggestion metadata in compact dictionary".into(),
            ));
        }
        let mut states = vec![0; builder.nodes.len()];
        let mut counts = vec![0; builder.nodes.len()];
        let count = count_paths(&builder.nodes, 0, &mut states, &mut counts, 0)?;
        let alphabet = builder
            .nodes
            .iter()
            .flat_map(|n| n.children.keys().copied())
            .filter(|c| c.is_alphabetic())
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .take(256)
            .collect();
        Ok(Self {
            nodes: builder.nodes,
            count,
            alphabet,
        })
    }

    fn contains(&self, word: &str) -> bool {
        let mut index = 0;
        for c in word.chars() {
            let Some(child) = self.nodes[index].children.get(&c) else {
                return false;
            };
            index = *child;
        }
        self.nodes[index].is_word
    }
}

fn count_paths(
    nodes: &[TrieNode],
    index: usize,
    states: &mut [u8],
    counts: &mut [usize],
    depth: usize,
) -> Result<usize, LoadError> {
    if states[index] == 2 {
        return Ok(counts[index]);
    }
    if states[index] == 1 || depth > 256 {
        return Err(LoadError::Format("Cyclic/deep trie".into()));
    }
    states[index] = 1;
    let mut count = usize::from(nodes[index].is_word);
    for child in nodes[index].children.values() {
        count = count.saturating_add(count_paths(nodes, *child, states, counts, depth + 1)?);
    }
    states[index] = 2;
    counts[index] = count;
    Ok(count)
}

impl Dictionary for CompactTrie {
    fn has(&self, word: &str) -> bool {
        let exact: String = word.nfc().collect();
        let normalized = exact.to_lowercase();
        self.contains(&exact)
            || self.contains(&normalized)
            || self.contains(&format!("~{normalized}"))
    }
    fn is_forbidden(&self, word: &str) -> bool {
        self.contains(&format!(
            "!{}",
            word.nfc().collect::<String>().to_lowercase()
        ))
    }

    fn find(&self, word: &str) -> FindResult {
        FindResult {
            found: self.has(word),
            forbidden: self.is_forbidden(word),
            no_suggest: false,
        }
    }
    fn len(&self) -> usize {
        self.count
    }
    fn suggest(&self, word: &str, limit: usize) -> Vec<String> {
        // Query-local single edits: bounded by word length × dictionary alphabet,
        // never by the number of expanded dictionary paths.
        let chars: Vec<_> = word.nfc().collect();
        if chars.len() > 64 || limit == 0 {
            return vec![];
        }
        let mut results = std::collections::BTreeSet::new();
        let mut add = |candidate: Vec<char>| {
            let value: String = candidate.into_iter().collect();
            if value != word && self.has(&value) && !self.is_forbidden(&value) {
                results.insert(value);
            }
        };
        for index in 0..=chars.len() {
            if index < chars.len() {
                let mut candidate = chars.clone();
                candidate.remove(index);
                add(candidate);
                if index + 1 < chars.len() {
                    let mut candidate = chars.clone();
                    candidate.swap(index, index + 1);
                    add(candidate);
                }
            }
            for &letter in &self.alphabet {
                let mut candidate = chars.clone();
                candidate.insert(index, letter);
                add(candidate);
                if index < chars.len() {
                    let mut candidate = chars.clone();
                    candidate[index] = letter;
                    add(candidate);
                }
            }
        }
        results.into_iter().take(limit).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn compressed_lookup_matches_upstream_without_expansion() {
        let text = "TrieXv3\nbase=10\n__DATA__\nשלום$4עולם$\n";
        let compressed = CompactTrie::parse(text).unwrap();
        let expanded = matchum_dict::loader::load_dictionary_from_bytes(
            text.as_bytes(),
            matchum_dict::loader::DictFormat::TrieV3,
        )
        .unwrap();
        for word in ["שלום", "עולם", "שלומ", "אחר"] {
            assert_eq!(compressed.has(word), expanded.has(word));
        }
        assert!(compressed.suggest("שלומ", 10).contains(&"שלום".into()));
    }
    #[test]
    fn bad_reference_is_an_error_not_a_panic() {
        assert!(CompactTrie::parse("TrieXv3\nbase=10\n__DATA__\na#999;").is_err());
    }

    #[test]
    fn shared_suffix_reference_matches_upstream() {
        let text = "TrieXv3\nbase=10\n__DATA__\ncat$3ba#2;<<\n";
        let trie = CompactTrie::parse(text).unwrap();
        assert!(trie.has("cat") && trie.has("bat"));
        assert_eq!(trie.len(), 2);
        assert!(!trie.has("ba"));
    }

    #[test]
    fn invalid_depth_and_truncated_escape_are_rejected() {
        for suffix in ["<", "a\\", "a#", "a#2;"] {
            assert!(CompactTrie::parse(&format!("TrieXv3\nbase=10\n__DATA__\n{suffix}")).is_err());
        }
    }

    #[test]
    fn nonstrict_lookup_keeps_accents_and_matches_upstream() {
        let text = "TrieXv3\nbase=10\n__DATA__\n~cafe$5\n";
        let compact = CompactTrie::parse(text).unwrap();
        let expanded = matchum_dict::loader::load_dictionary_from_bytes(
            text.as_bytes(),
            matchum_dict::loader::DictFormat::TrieV3,
        )
        .unwrap();
        for word in ["cafe", "Cafe", "café", "CAFE"] {
            assert_eq!(compact.has(word), expanded.has(word), "{word}");
        }
    }
}

/// A node in the trie being built during `TrieXv3` parsing.
#[derive(Clone, Default)]
struct TrieNode {
    children: HashMap<char, usize>,
    is_word: bool,
    locked: bool,
}

struct StackEntry {
    parent_idx: usize,
    child_char: char,
}

/// Builds a trie from `TrieXv3` format data, mirroring cspell's `TrieBlobBuilder`
/// cursor semantics.
struct TrieBuilder {
    invalid: bool,
    /// Unique trie nodes. `nodes[0]` = root, `nodes[1]` = shared EOW sentinel.
    nodes: Vec<TrieNode>,
    /// History of node pushes as tracked by cspell's `TrieNodeBuilder` cursor.
    /// Reference ids in `TrieXv3` point into this history, not into unique nodes.
    history: Vec<usize>,
    /// Stack tracking parent info at each character depth level.
    stack: Vec<StackEntry>,
    /// Current unique node index.
    curr: usize,
    /// Current character depth in the trie.
    depth: usize,
}

impl TrieBuilder {
    fn new() -> Self {
        let root = TrieNode::default();
        let eow = TrieNode {
            is_word: true,
            locked: true,
            ..Default::default()
        };

        Self {
            invalid: false,
            nodes: vec![root, eow],
            history: vec![0, 1],
            stack: vec![StackEntry {
                parent_idx: 0,
                child_char: '\0',
            }],
            curr: 0,
            depth: 0,
        }
    }

    fn insert_char(&mut self, c: char) {
        if self.invalid || self.nodes.len() > 2_000_000 || self.depth > 256 {
            self.invalid = true;
            return;
        }
        if self.nodes[self.curr].locked {
            let mut cloned = self.nodes[self.curr].clone();
            cloned.locked = false;
            let new_idx = self.nodes.len();
            self.nodes.push(cloned);

            let entry = &self.stack[self.depth];
            self.nodes[entry.parent_idx]
                .children
                .insert(entry.child_char, new_idx);
            self.history.push(new_idx);
            self.curr = new_idx;
        }

        let parent = self.curr;
        let child = if let Some(existing) = self.nodes[parent].children.get(&c).copied() {
            existing
        } else {
            let idx = self.nodes.len();
            self.nodes.push(TrieNode::default());
            self.nodes[parent].children.insert(c, idx);
            idx
        };
        self.history.push(child);

        self.depth += 1;
        if self.depth < self.stack.len() {
            self.stack[self.depth] = StackEntry {
                parent_idx: parent,
                child_char: c,
            };
        } else {
            self.stack.push(StackEntry {
                parent_idx: parent,
                child_char: c,
            });
        }
        self.curr = child;
    }

    fn mark_eow(&mut self) {
        if self.invalid || self.depth == 0 {
            self.invalid = true;
            return;
        }
        if self.curr == 1 {
            return;
        }

        if self.nodes[self.curr].children.is_empty() {
            let entry = &self.stack[self.depth];
            self.nodes[entry.parent_idx]
                .children
                .insert(entry.child_char, 1);
            if self.history.last().copied() == Some(self.curr) {
                self.history.pop();
            }
            self.curr = 1;
        } else {
            self.nodes[self.curr].is_word = true;
        }
    }

    fn reference(&mut self, ref_id: usize) {
        if self.invalid || self.depth == 0 || ref_id >= self.history.len() {
            self.invalid = true;
            return;
        }
        let referenced = self.history[ref_id];
        let entry = &self.stack[self.depth];
        self.curr = entry.parent_idx;
        self.nodes[self.curr]
            .children
            .insert(entry.child_char, referenced);
        self.history.pop();
    }

    fn back_step(&mut self, n: usize) {
        if n == 0 {
            return;
        }
        if self.invalid || n > self.depth {
            self.invalid = true;
            return;
        }
        self.depth -= n;
        self.curr = self.stack[self.depth + 1].parent_idx;
    }
}

enum ParseState {
    Main,
    Back,
    Reference(String),
    EscapeStart,
    EscapeWithBackslash,
}

fn parse_header(header_lines: &[&str]) -> Result<u32, LoadError> {
    let mut found_trie_v3 = false;
    let mut radix: Option<u32> = None;

    for line in header_lines {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("#!") {
            continue;
        }
        if trimmed == "TrieXv3" {
            found_trie_v3 = true;
            continue;
        }
        if let Some(base_str) = trimmed.strip_prefix("base=") {
            radix = Some(
                base_str
                    .parse()
                    .map_err(|_| LoadError::Format(format!("Invalid radix: {base_str}")))?,
            );
        }
    }

    if !found_trie_v3 {
        return Err(LoadError::Format("Missing TrieXv3 identifier".into()));
    }

    let radix = radix.ok_or_else(|| LoadError::Format("Missing base= in header".into()))?;
    if !(2..=36).contains(&radix) {
        return Err(LoadError::Format(format!("Radix out of range: {radix}")));
    }

    Ok(radix)
}

fn process_char(builder: &mut TrieBuilder, state: ParseState, c: char, radix: u32) -> ParseState {
    match state {
        ParseState::Main => parse_main(builder, c),
        ParseState::Back => parse_back(builder, c),
        ParseState::Reference(ref_str) => parse_reference(builder, c, ref_str, radix),
        ParseState::EscapeStart => parse_escape_start(builder, c),
        ParseState::EscapeWithBackslash => parse_escape_mapped(builder, c),
    }
}

fn parse_main(builder: &mut TrieBuilder, c: char) -> ParseState {
    match c {
        '$' => {
            builder.mark_eow();
            builder.back_step(1);
            ParseState::Back
        }
        '<' => {
            builder.back_step(1);
            ParseState::Back
        }
        '#' => ParseState::Reference(String::new()),
        '\\' => ParseState::EscapeStart,
        '\n' | '\r' => ParseState::Main,
        _ => {
            builder.insert_char(c);
            ParseState::Main
        }
    }
}

fn parse_back(builder: &mut TrieBuilder, c: char) -> ParseState {
    match c {
        '<' => {
            builder.back_step(1);
            ParseState::Back
        }
        '2'..='9' => {
            let n = (c as u32 - u32::from(b'0') - 1) as usize;
            builder.back_step(n);
            ParseState::Back
        }
        _ => parse_main(builder, c),
    }
}

fn parse_reference(
    builder: &mut TrieBuilder,
    c: char,
    mut ref_str: String,
    radix: u32,
) -> ParseState {
    if c == ';' {
        let Ok(r) = usize::from_str_radix(&ref_str, radix) else {
            builder.invalid = true;
            return ParseState::Main;
        };
        if r == usize::MAX {
            builder.invalid = true;
            return ParseState::Main;
        }
        builder.reference(r + 1);
        ParseState::Main
    } else {
        ref_str.push(c);
        ParseState::Reference(ref_str)
    }
}

fn parse_escape_start(builder: &mut TrieBuilder, c: char) -> ParseState {
    if c == '\\' {
        // Two backslashes: wait for the mapped character
        ParseState::EscapeWithBackslash
    } else {
        // \X where X != \ -> literal X
        builder.insert_char(c);
        ParseState::Main
    }
}

fn parse_escape_mapped(builder: &mut TrieBuilder, c: char) -> ParseState {
    let mapped = match c {
        'n' => '\n',
        'r' => '\r',
        '\\' => '\\',
        _ => c,
    };
    builder.insert_char(mapped);
    ParseState::Main
}
