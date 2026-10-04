use crate::{Config, Limit, Obfuscation};
use unicode_normalization::{char::is_combining_mark, UnicodeNormalization};
use unicode_segmentation::UnicodeSegmentation;

#[derive(Clone, Debug)]
pub(crate) struct Unit {
    pub ch: char,
    pub start: usize,
    pub end: usize,
    pub base_start: usize,
    pub base_end: usize,
    pub max_gap: usize,
}
pub(crate) struct Normalized {
    pub text: String,
    pub units: Vec<Unit>,
    byte_to_unit: Vec<usize>,
}
impl Normalized {
    fn new() -> Self {
        Self {
            text: String::new(),
            units: Vec::new(),
            byte_to_unit: Vec::new(),
        }
    }
    fn push(&mut self, unit: Unit, cap: usize) -> Result<(), Limit> {
        if self.text.len() + unit.ch.len_utf8() > cap {
            return Err(Limit::NormalizedBytes);
        }
        self.byte_to_unit
            .extend(std::iter::repeat_n(self.units.len(), unit.ch.len_utf8()));
        self.text.push(unit.ch);
        self.units.push(unit);
        Ok(())
    }
    pub fn unit_bounds(&self, start: usize, end: usize) -> (usize, usize) {
        (self.byte_to_unit[start], self.byte_to_unit[end - 1])
    }
}
/// Deliberately per original extended grapheme, not an NFKC_Casefold API.
pub(crate) fn normalize(text: &str, config: &Config) -> Result<Normalized, Limit> {
    let mut result = Normalized::new();
    if text.is_ascii() {
        for (offset, b) in text.bytes().enumerate() {
            result.push(
                Unit {
                    ch: b.to_ascii_lowercase() as char,
                    start: offset,
                    end: offset + 1,
                    base_start: offset,
                    base_end: offset + 1,
                    max_gap: 0,
                },
                config.max_normalized_bytes,
            )?;
        }
        return Ok(result);
    }
    for (offset, grapheme) in text.grapheme_indices(true) {
        if grapheme
            .chars()
            .take(config.max_grapheme_scalars + 1)
            .count()
            > config.max_grapheme_scalars
        {
            return Err(Limit::GraphemeScalars);
        }
        for c in grapheme.nfkc().flat_map(char::to_lowercase) {
            let index = result.units.len();
            result.push(
                Unit {
                    ch: c,
                    start: offset,
                    end: offset + grapheme.len(),
                    base_start: index,
                    base_end: index + 1,
                    max_gap: 0,
                },
                config.max_normalized_bytes,
            )?;
        }
    }
    Ok(result)
}
pub(crate) fn invisible(c: char) -> bool {
    matches!(
        c,
        '\u{00ad}' | '\u{200b}' | '\u{200c}' | '\u{200d}' | '\u{2060}' | '\u{feff}'
    )
}
fn separator(c: char) -> bool {
    matches!(c, ' ' | '.' | '-' | '_' | '*')
}
fn leet(c: char) -> char {
    match c {
        '0' => 'o',
        '1' => 'i',
        '3' => 'e',
        '4' | '@' => 'a',
        '5' | '$' => 's',
        '7' => 't',
        _ => c,
    }
}

pub(crate) fn relax(
    base: &Normalized,
    options: &Obfuscation,
    cap: usize,
) -> Result<Normalized, Limit> {
    let mut retained: Vec<Unit> = Vec::with_capacity(base.units.len());
    for original in &base.units {
        let mut unit = original.clone();
        if options.remove_invisibles && invisible(unit.ch) {
            // Preserve the skipped byte range in a preceding unit, including at EOF.
            if let Some(previous) = retained.last_mut() {
                previous.end = previous.end.max(unit.end);
                previous.base_end = unit.base_end;
                previous.max_gap += 1;
            }
            continue;
        }
        if options.ascii_separators && separator(unit.ch) {
            continue;
        }
        if options.ascii_leet {
            unit.ch = leet(unit.ch);
        }
        if options.latin_diacritics && !unit.ch.is_ascii() {
            let mut decomposed = std::iter::once(unit.ch).nfkd();
            let first = decomposed.next().expect("normalization preserves a scalar");
            if first.is_ascii_alphabetic() && decomposed.all(is_combining_mark) {
                unit.ch = first;
            } else if is_combining_mark(unit.ch)
                && retained
                    .last()
                    .is_some_and(|p| p.ch.is_ascii_alphabetic() && p.end == unit.end)
            {
                // This mark belongs to the same original Latin grapheme.
                let previous = retained.last_mut().expect("checked above");
                previous.base_end = unit.base_end;
                continue;
            }
        }
        if options.ascii_repeats && unit.ch.is_ascii_alphabetic() {
            if let Some(previous) = retained.last_mut() {
                if previous.ch == unit.ch {
                    previous.max_gap = previous
                        .max_gap
                        .max(unit.base_start.saturating_sub(previous.base_end));
                    previous.end = unit.end;
                    previous.base_end = unit.base_end;
                    continue;
                }
            }
        }
        retained.push(unit);
    }
    let mut result = Normalized::new();
    for unit in retained {
        result.push(unit, cap)?;
    }
    Ok(result)
}
