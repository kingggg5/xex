//! A small, bounded, server-side English/Thai chat policy filter.
//!
//! Compile once with [`Filter::seed`], share it across server workers, and inspect
//! only after authentication and rate checks. [`Verdict::Review`] is a hold, not
//! permission to broadcast. No finding should automatically ban a player.
#![forbid(unsafe_code)]

pub mod guard;
mod normalize;

use aho_corasick::{AhoCorasick, MatchKind};
use normalize::{normalize, relax, Normalized};
use std::{collections::HashSet, fmt, ops::Range};
use unicode_normalization::char::is_combining_mark;
use unicode_segmentation::UnicodeSegmentation;

/// A server policy recommendation, never a player punishment.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Verdict {
    Allow,
    Mask,
    Review,
    Reject,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Action {
    Mask,
    Review,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Language {
    English,
    Thai,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Boundary {
    Word,
    Substring,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Evidence {
    NormalizedLiteral,
    Heuristic,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Limit {
    InputBytes,
    NormalizedBytes,
    GraphemeScalars,
    Candidates,
    Findings,
}

/// All optional lossy rewrites produce review-only findings.
#[derive(Clone, Debug)]
pub struct Obfuscation {
    pub enabled: bool,
    pub remove_invisibles: bool,
    pub ascii_leet: bool,
    pub latin_diacritics: bool,
    pub ascii_repeats: bool,
    /// Join spaces/dot/dash/underscore/star. Never newlines or arbitrary symbols.
    pub ascii_separators: bool,
    /// Maximum skipped normalized characters between adjacent retained units.
    pub max_gap: usize,
}
impl Default for Obfuscation {
    fn default() -> Self {
        Self {
            enabled: true,
            remove_invisibles: true,
            ascii_leet: true,
            latin_diacritics: true,
            ascii_repeats: true,
            ascii_separators: true,
            max_gap: 2,
        }
    }
}
#[derive(Clone, Debug)]
pub struct Config {
    pub max_input_bytes: usize,
    pub max_normalized_bytes: usize,
    pub max_grapheme_scalars: usize,
    pub max_candidates: usize,
    pub max_findings: usize,
    pub obfuscation: Obfuscation,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            max_input_bytes: 4096,
            max_normalized_bytes: 16384,
            max_grapheme_scalars: 64,
            max_candidates: 512,
            max_findings: 64,
            obfuscation: Obfuscation::default(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct Rule {
    pub id: String,
    pub language: Language,
    pub boundary: Boundary,
    pub action: Action,
    pub term: String,
}
#[derive(Clone, Debug)]
pub struct Exception {
    pub rule_id: String,
    pub phrase: String,
}
#[derive(Debug)]
pub struct BuildError(pub String);
impl fmt::Display for BuildError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for BuildError {}

#[derive(Clone, Debug)]
pub struct Finding {
    pub rule_id: String,
    /// Original UTF-8 byte range, expanded to whole original grapheme clusters.
    pub span: Range<usize>,
    pub action: Action,
    pub evidence: Evidence,
}
/// Borrows the exact inspected input; this prevents masking a different string.
#[derive(Debug)]
pub struct Report<'a> {
    original: &'a str,
    verdict: Verdict,
    findings: Vec<Finding>,
    limit: Option<Limit>,
}
impl Report<'_> {
    pub fn verdict(&self) -> Verdict {
        self.verdict
    }
    pub fn findings(&self) -> &[Finding] {
        &self.findings
    }
    pub fn limit(&self) -> Option<Limit> {
        self.limit
    }
    pub fn complete(&self) -> bool {
        self.limit.is_none()
    }
    /// Mask only high-confidence mask-policy findings. A Review still stays held.
    pub fn masked(&self) -> String {
        self.mask_impl(false)
    }
    /// Explicit moderator preview: redact even uncertain findings. Not a verdict.
    pub fn redacted(&self) -> String {
        self.mask_impl(true)
    }
    fn mask_impl(&self, include_review: bool) -> String {
        let mut spans: Vec<_> = self
            .findings
            .iter()
            .filter(|f| include_review || f.action == Action::Mask)
            .map(|f| f.span.clone())
            .collect();
        spans.sort_by_key(|r| (r.start, r.end));
        let mut merged: Vec<Range<usize>> = Vec::new();
        for span in spans {
            if let Some(last) = merged.last_mut() {
                if span.start <= last.end {
                    last.end = last.end.max(span.end);
                    continue;
                }
            }
            merged.push(span);
        }
        let mut result = String::with_capacity(self.original.len());
        let mut pos = 0;
        for span in merged {
            result.push_str(&self.original[pos..span.start]);
            for _ in self.original[span.clone()].graphemes(true) {
                result.push('*');
            }
            pos = span.end;
        }
        result.push_str(&self.original[pos..]);
        result
    }
}

/// Immutable compiled automata. Construction belongs at startup/reload, not per message.
pub struct Filter {
    config: Config,
    rules: Vec<Rule>,
    strict: AhoCorasick,
    loose: AhoCorasick,
    exceptions: Option<AhoCorasick>,
    exception_rules: Vec<usize>,
}
impl Filter {
    pub fn seed() -> Result<Self, BuildError> {
        Self::from_tsv(
            include_str!("../policy.tsv"),
            include_str!("../exceptions.tsv"),
            Config::default(),
        )
    }
    pub fn from_tsv(policy: &str, exceptions: &str, config: Config) -> Result<Self, BuildError> {
        if policy.len() > 262_144 || exceptions.len() > 262_144 {
            return Err(BuildError("dictionary text exceeds 256KiB".into()));
        }
        let mut rules = Vec::new();
        for (line, cols) in rows(policy) {
            if cols.len() != 5 {
                return Err(BuildError(format!(
                    "policy line {line}: expected five tab-separated columns"
                )));
            }
            let language = match cols[1] {
                "en" => Language::English,
                "th" => Language::Thai,
                _ => {
                    return Err(BuildError(format!(
                        "policy line {line}: language must be en or th"
                    )))
                }
            };
            let boundary = match cols[2] {
                "word" => Boundary::Word,
                "substring" => Boundary::Substring,
                _ => {
                    return Err(BuildError(format!(
                        "policy line {line}: boundary must be word or substring"
                    )))
                }
            };
            let action = match cols[3] {
                "mask" => Action::Mask,
                "review" => Action::Review,
                _ => {
                    return Err(BuildError(format!(
                        "policy line {line}: action must be mask or review"
                    )))
                }
            };
            rules.push(Rule {
                id: cols[0].into(),
                language,
                boundary,
                action,
                term: cols[4].into(),
            });
        }
        let mut allow = Vec::new();
        for (line, cols) in rows(exceptions) {
            if cols.len() != 2 {
                return Err(BuildError(format!(
                    "exception line {line}: expected two columns"
                )));
            }
            allow.push(Exception {
                rule_id: cols[0].into(),
                phrase: cols[1].into(),
            });
        }
        Self::new(rules, allow, config)
    }
    pub fn new(
        rules: Vec<Rule>,
        exceptions: Vec<Exception>,
        config: Config,
    ) -> Result<Self, BuildError> {
        validate_config(&config)?;
        if rules.is_empty() || rules.len() > 2048 || exceptions.len() > 2048 {
            return Err(BuildError(
                "need 1..=2048 rules and at most 2048 exceptions".into(),
            ));
        }
        let mut ids = HashSet::new();
        let mut strict_patterns = Vec::new();
        let mut loose_patterns = Vec::new();
        let mut total = 0usize;
        for rule in &rules {
            if rule.id.is_empty()
                || rule.id.len() > 64
                || !rule
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_')
                || !ids.insert(&rule.id)
            {
                return Err(BuildError(
                    "rule IDs must be unique ASCII identifiers of 1..=64 bytes".into(),
                ));
            }
            validate_term(&rule.term)?;
            total += rule.term.len();
            let base = normalize(&rule.term, &config)
                .map_err(|_| BuildError("term exceeds normalization limits".into()))?;
            let relaxed = relax(&base, &config.obfuscation, config.max_normalized_bytes)
                .map_err(|_| BuildError("term exceeds relaxed normalization limits".into()))?;
            if base.text.is_empty() || relaxed.text.is_empty() {
                return Err(BuildError("term normalizes to empty".into()));
            }
            strict_patterns.push(base.text);
            loose_patterns.push(relaxed.text);
        }
        let mut exception_patterns = Vec::new();
        let mut exception_rules = Vec::new();
        for exception in exceptions {
            validate_term(&exception.phrase)?;
            total += exception.phrase.len();
            let rule_index = rules
                .iter()
                .position(|r| r.id == exception.rule_id)
                .ok_or_else(|| {
                    BuildError(format!("unknown exception rule {}", exception.rule_id))
                })?;
            let normalized = normalize(&exception.phrase, &config)
                .map_err(|_| BuildError("exception exceeds normalization limits".into()))?;
            if !normalized.text.contains(&strict_patterns[rule_index]) {
                return Err(BuildError(
                    "exception must contain its rule term after normalization".into(),
                ));
            }
            exception_patterns.push(normalized.text);
            exception_rules.push(rule_index);
        }
        if total > 131_072 {
            return Err(BuildError("total term bytes exceed 128KiB".into()));
        }
        let build = |patterns: &[String]| {
            AhoCorasick::builder()
                .match_kind(MatchKind::Standard)
                .build(patterns)
                .map_err(|e| BuildError(e.to_string()))
        };
        let exception_ac = if exception_patterns.is_empty() {
            None
        } else {
            Some(build(&exception_patterns)?)
        };
        Ok(Self {
            config,
            rules,
            strict: build(&strict_patterns)?,
            loose: build(&loose_patterns)?,
            exceptions: exception_ac,
            exception_rules,
        })
    }
    pub fn rule_count(&self) -> usize {
        self.rules.len()
    }
    pub fn config(&self) -> &Config {
        &self.config
    }
    pub fn automaton_memory_bytes(&self) -> usize {
        self.strict.memory_usage()
            + self.loose.memory_usage()
            + self
                .exceptions
                .as_ref()
                .map_or(0, AhoCorasick::memory_usage)
    }
    pub fn inspect<'a>(&self, text: &'a str) -> Report<'a> {
        let mut report = Report {
            original: text,
            verdict: Verdict::Allow,
            findings: Vec::new(),
            limit: None,
        };
        if text.len() > self.config.max_input_bytes {
            report.verdict = Verdict::Reject;
            report.limit = Some(Limit::InputBytes);
            return report;
        }
        let base = match normalize(text, &self.config) {
            Ok(n) => n,
            Err(limit) => {
                report.limit = Some(limit);
                report.verdict = Verdict::Review;
                return report;
            }
        };
        let mut budget = self.config.max_candidates;
        let mut exceptions = Vec::new();
        if let Some(ac) = &self.exceptions {
            for found in ac.find_overlapping_iter(&base.text) {
                if budget == 0 {
                    return limited(report, Limit::Candidates);
                }
                budget -= 1;
                let (first, last) = base.unit_bounds(found.start(), found.end());
                exceptions.push((
                    self.exception_rules[found.pattern().as_usize()],
                    base.units[first].start..base.units[last].end,
                ));
            }
        }
        if let Err(limit) = self.scan(&base, &base, false, &exceptions, &mut budget, &mut report) {
            return limited(report, limit);
        }
        if self.config.obfuscation.enabled {
            let relaxed = match relax(
                &base,
                &self.config.obfuscation,
                self.config.max_normalized_bytes,
            ) {
                Ok(n) => n,
                Err(limit) => return limited(report, limit),
            };
            // Dictionary rewrites can differ even when the message itself is unchanged.
            if !relaxed.text.is_empty() {
                if let Err(limit) =
                    self.scan(&relaxed, &base, true, &exceptions, &mut budget, &mut report)
                {
                    return limited(report, limit);
                }
            }
        }
        report.findings.sort_by(|a, b| {
            (a.span.start, a.span.end, &a.rule_id).cmp(&(b.span.start, b.span.end, &b.rule_id))
        });
        report.verdict = if report.findings.iter().any(|f| f.action == Action::Review) {
            Verdict::Review
        } else if report.findings.is_empty() {
            Verdict::Allow
        } else {
            Verdict::Mask
        };
        report
    }
    fn scan(
        &self,
        lane: &Normalized,
        base: &Normalized,
        heuristic: bool,
        exceptions: &[(usize, Range<usize>)],
        budget: &mut usize,
        report: &mut Report<'_>,
    ) -> Result<(), Limit> {
        let ac = if heuristic { &self.loose } else { &self.strict };
        for found in ac.find_overlapping_iter(&lane.text) {
            if *budget == 0 {
                return Err(Limit::Candidates);
            }
            *budget -= 1;
            let index = found.pattern().as_usize();
            let rule = &self.rules[index];
            let (first, last) = lane.unit_bounds(found.start(), found.end());
            let start = lane.units[first].base_start;
            let end = lane.units[last].base_end;
            // Do not match half of a compatibility expansion or grapheme.
            if start > 0 && base.units[start - 1].start == base.units[start].start {
                continue;
            }
            if end < base.units.len() && base.units[end - 1].end == base.units[end].end {
                continue;
            }
            if rule.boundary == Boundary::Word && !word_boundary(base, start, end) {
                continue;
            }
            if heuristic
                && (lane.units[first..=last]
                    .iter()
                    .any(|u| u.max_gap > self.config.obfuscation.max_gap)
                    || lane.units[first..=last].windows(2).any(|pair| {
                        pair[1].base_start.saturating_sub(pair[0].base_end)
                            > self.config.obfuscation.max_gap
                    }))
            {
                continue;
            }
            let span = lane.units[first].start..lane.units[last].end;
            if exceptions
                .iter()
                .any(|(r, allow)| *r == index && allow.start <= span.start && allow.end >= span.end)
            {
                continue;
            }
            if report
                .findings
                .iter()
                .any(|f| f.rule_id == rule.id && f.span == span)
            {
                continue;
            }
            if report.findings.len() >= self.config.max_findings {
                return Err(Limit::Findings);
            }
            // Thai substring matches cannot establish word meaning without segmentation/context.
            let action = if heuristic || rule.language == Language::Thai {
                Action::Review
            } else {
                rule.action
            };
            report.findings.push(Finding {
                rule_id: rule.id.clone(),
                span,
                action,
                evidence: if heuristic {
                    Evidence::Heuristic
                } else {
                    Evidence::NormalizedLiteral
                },
            });
        }
        Ok(())
    }
}
fn limited(mut report: Report<'_>, limit: Limit) -> Report<'_> {
    report.limit = Some(limit);
    report.verdict = Verdict::Review;
    report
}
fn word_boundary(n: &Normalized, start: usize, end: usize) -> bool {
    // Ignore only the same invisibles the relaxed lane can remove. Inspect the
    // nearest meaningful neighbours so invisibles cannot hide a whole word or
    // turn a substring of a longer word into an independent word.
    let mut before = start;
    while before > 0 && normalize::invisible(n.units[before - 1].ch) {
        before -= 1;
    }
    let mut after = end;
    while after < n.units.len() && normalize::invisible(n.units[after].ch) {
        after += 1;
    }
    (before == 0 || !word_char(n.units[before - 1].ch))
        && (after == n.units.len() || !word_char(n.units[after].ch))
}
fn word_char(c: char) -> bool {
    c.is_alphanumeric() || is_combining_mark(c) || c == '_' || normalize::invisible(c)
}
fn validate_term(term: &str) -> Result<(), BuildError> {
    if term.is_empty() || term.len() > 128 || term.chars().any(char::is_control) {
        return Err(BuildError(
            "terms must be 1..=128 bytes without controls".into(),
        ));
    }
    Ok(())
}
fn validate_config(c: &Config) -> Result<(), BuildError> {
    if !(1..=65_536).contains(&c.max_input_bytes)
        || !(1..=262_144).contains(&c.max_normalized_bytes)
        || !(1..=256).contains(&c.max_grapheme_scalars)
        || !(1..=8192).contains(&c.max_candidates)
        || !(1..=1024).contains(&c.max_findings)
        || c.obfuscation.max_gap > 8
    {
        return Err(BuildError(
            "invalid resource bounds (see Config documentation/README)".into(),
        ));
    }
    Ok(())
}
fn rows(input: &str) -> impl Iterator<Item = (usize, Vec<&str>)> {
    input.lines().enumerate().filter_map(|(i, line)| {
        let line = line.trim_end_matches('\r');
        if line.trim().is_empty() || line.starts_with('#') {
            None
        } else {
            Some((i + 1, line.split('\t').collect()))
        }
    })
}
