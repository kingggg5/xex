use xexoria_chat_filter::{
    Action, Boundary, Config, Evidence, Exception, Filter, Language, Limit, Rule, Verdict,
};

const INVISIBLES: [char; 6] = [
    '\u{00ad}', '\u{200b}', '\u{200c}', '\u{200d}', '\u{2060}', '\u{feff}',
];

fn rule(id: &str, term: &str) -> Rule {
    Rule {
        id: id.into(),
        language: Language::English,
        boundary: Boundary::Word,
        action: Action::Mask,
        term: term.into(),
    }
}

#[test]
fn seeded_corpus() {
    let filter = Filter::seed().unwrap();
    let mut rows = 0;
    for line in include_str!("data/corpus.tsv")
        .lines()
        .filter(|l| !l.starts_with('#') && !l.is_empty())
    {
        let (expected, text) = line.split_once('\t').unwrap();
        let expected = match expected {
            "allow" => Verdict::Allow,
            "mask" => Verdict::Mask,
            "review" => Verdict::Review,
            _ => panic!("bad fixture"),
        };
        let report = filter.inspect(text);
        assert_eq!(
            report.verdict(),
            expected,
            "{text:?}: {:?}",
            report.findings()
        );
        assert!(report.complete(), "fixture exhausted budget: {text:?}");
        rows += 1;
    }
    assert!(rows >= 50);
}
#[test]
fn original_utf8_mask_and_emoji_preserved() {
    let filter = Filter::seed().unwrap();
    let text = "ไทย 👩‍👩‍👧‍👦 ＦＵＣＫ! ไทย";
    let report = filter.inspect(text);
    assert_eq!(report.verdict(), Verdict::Mask);
    assert_eq!(report.masked(), "ไทย 👩‍👩‍👧‍👦 ****! ไทย");
    assert_eq!(&text[report.findings()[0].span.clone()], "ＦＵＣＫ");
}
#[test]
fn combining_marks_are_whole_grapheme_spans() {
    let filter = Filter::seed().unwrap();
    for text in ["fu\u{301}ck", "f\u{301}uck", "fuck\u{301}", "f\u{0338}uck"] {
        let report = filter.inspect(text);
        assert_eq!(report.verdict(), Verdict::Review, "{text:?}");
        assert_eq!(report.findings()[0].evidence, Evidence::Heuristic);
        assert_eq!(report.redacted(), "****");
        assert_eq!(report.masked(), text);
        assert_eq!(report.findings()[0].span, 0..text.len());
    }
}
#[test]
fn dictionary_and_input_share_normalization() {
    let filter = Filter::new(vec![rule("accent", "café")], vec![], Config::default()).unwrap();
    let report = filter.inspect("cafe\u{301}");
    assert_eq!(report.verdict(), Verdict::Mask);
    assert_eq!(report.masked(), "****");
}
#[test]
fn partial_compatibility_expansion_is_not_a_whole_match() {
    let filter = Filter::new(vec![rule("part", "f")], vec![], Config::default()).unwrap();
    assert_eq!(filter.inspect("ﬃ").verdict(), Verdict::Allow);
    let filter = Filter::new(vec![rule("all", "ffi")], vec![], Config::default()).unwrap();
    let report = filter.inspect("ﬃ");
    assert_eq!(report.verdict(), Verdict::Mask);
    assert_eq!(report.masked(), "*");
}
#[test]
fn allowlist_is_span_local() {
    let filter = Filter::seed().unwrap();
    for (text, expected) in [
        ("เหี้ยมแต่เหี้ย", "เหี้ย"),
        ("แม่งานแม่ง", "แม่ง"),
        ("เหี้ยม fuck", "fuck"),
    ] {
        let r = filter.inspect(text);
        assert_eq!(r.findings().len(), 1, "{text:?}: {:?}", r.findings());
        assert_eq!(&text[r.findings()[0].span.clone()], expected);
    }
}
#[test]
fn overlapping_short_rejection_does_not_hide_long_match() {
    let filter = Filter::new(
        vec![rule("short", "fuck"), rule("long", "fucking")],
        vec![],
        Config::default(),
    )
    .unwrap();
    let r = filter.inspect("fucking");
    assert_eq!(r.verdict(), Verdict::Mask);
    assert_eq!(r.findings()[0].rule_id, "long");
}
#[test]
fn whitespace_joining_is_bounded_and_never_crosses_newline() {
    let filter = Filter::seed().unwrap();
    assert_eq!(filter.inspect("f u c k").verdict(), Verdict::Review);
    for text in ["f     uck", "fu\nck", "fu\tck", "f---uck"] {
        assert_eq!(filter.inspect(text).verdict(), Verdict::Allow, "{text:?}");
    }
}
#[test]
fn adjacent_invisibles_cannot_hide_seeded_english_words() {
    let filter = Filter::seed().unwrap();
    for invisible in INVISIBLES {
        for term in ["fuck", "fucking", "shit", "bullshit", "asshole", "bitch"] {
            for text in [
                format!("{invisible}{term}"),
                format!("{term}{invisible}"),
                format!("{invisible}{term}{invisible}"),
            ] {
                let report = filter.inspect(&text);
                assert!(
                    matches!(report.verdict(), Verdict::Mask | Verdict::Review),
                    "{text:?}: {:?}",
                    report.findings()
                );
                assert!(report.complete(), "{text:?}");
            }
        }
    }
}
#[test]
fn internal_invisibles_remain_review_only() {
    let filter = Filter::seed().unwrap();
    for invisible in INVISIBLES {
        let text = format!("f{invisible}uck");
        let report = filter.inspect(&text);
        assert_eq!(report.verdict(), Verdict::Review, "{text:?}");
        assert!(report.complete());
        assert_eq!(report.findings().len(), 1);
        assert_eq!(report.findings()[0].evidence, Evidence::Heuristic);
        assert_eq!(report.masked(), text);
    }
}
#[test]
fn invisible_boundaries_preserve_longer_words() {
    let filter = Filter::seed().unwrap();
    for invisible in INVISIBLES {
        for text in [
            format!("safe{invisible}fuck"),
            format!("fuck{invisible}tail"),
            format!("safe{invisible}fuck{invisible}tail"),
            format!("ไทย{invisible}fuck{invisible}ไทย"),
        ] {
            assert_eq!(filter.inspect(&text).verdict(), Verdict::Allow, "{text:?}");
        }
    }
}
#[test]
fn invisible_boundary_fix_preserves_thai_exceptions_and_emoji() {
    let filter = Filter::seed().unwrap();
    for invisible in INVISIBLES {
        let safe = format!("{invisible}เหี้ยม แม่งาน 👩‍👩‍👧‍👦 🎮{invisible}");
        assert_eq!(filter.inspect(&safe).verdict(), Verdict::Allow, "{safe:?}");
        let text = format!("👩‍👩‍👧‍👦 {invisible}fuck 🎮");
        let report = filter.inspect(&text);
        assert_eq!(report.verdict(), Verdict::Mask, "{text:?}");
        assert_eq!(report.masked(), format!("👩‍👩‍👧‍👦 {invisible}**** 🎮"));
    }
}
#[test]
fn configure_strict_only_or_individual_transform() {
    let mut config = Config::default();
    config.obfuscation.enabled = false;
    let filter = Filter::from_tsv(include_str!("../policy.tsv"), "", config).unwrap();
    assert_eq!(filter.inspect("f.u.c.k").verdict(), Verdict::Allow);
    assert_eq!(filter.inspect("FUCK").verdict(), Verdict::Mask);
    let mut config = Config::default();
    config.obfuscation.ascii_leet = false;
    let filter = Filter::from_tsv(include_str!("../policy.tsv"), "", config).unwrap();
    assert_eq!(filter.inspect("sh1t").verdict(), Verdict::Allow);
}
#[test]
fn limits_never_silently_allow() {
    let filter = Filter::seed().unwrap();
    let long = "a".repeat(4097);
    let r = filter.inspect(&long);
    assert_eq!(r.verdict(), Verdict::Reject);
    assert_eq!(r.limit(), Some(Limit::InputBytes));
    let zalgo = format!("f{}uck", "\u{0301}".repeat(65));
    assert_eq!(filter.inspect(&zalgo).limit(), Some(Limit::GraphemeScalars));
    assert_eq!(filter.inspect(&zalgo).verdict(), Verdict::Review);
    let config = Config {
        max_candidates: 1,
        ..Config::default()
    };
    let filter = Filter::new(vec![rule("term", "fuck")], vec![], config).unwrap();
    let r = filter.inspect("fuck fuck");
    assert_eq!(r.verdict(), Verdict::Review);
    assert_eq!(r.limit(), Some(Limit::Candidates));
    let config = Config {
        max_findings: 1,
        ..Config::default()
    };
    let filter = Filter::new(vec![rule("term", "fuck")], vec![], config).unwrap();
    assert_eq!(filter.inspect("fuck fuck").limit(), Some(Limit::Findings));
    let config = Config {
        max_normalized_bytes: 16,
        ..Config::default()
    };
    let filter = Filter::new(vec![rule("term", "fuck")], vec![], config).unwrap();
    assert_eq!(filter.inspect("ﷺﷺﷺ").limit(), Some(Limit::NormalizedBytes));
}
#[test]
fn invalid_policy_and_config_fail_at_startup() {
    for input in [
        "x\ten\tword\tmask",
        "x\tzz\tword\tmask\tx",
        "x\ten\tword\tban\tx",
        "x\ten\tword\tmask\t",
    ] {
        assert!(Filter::from_tsv(input, "", Config::default()).is_err());
    }
    assert!(Filter::new(
        vec![rule("id", "fuck"), rule("id", "shit")],
        vec![],
        Config::default()
    )
    .is_err());
    assert!(Filter::new(
        vec![rule("id", "fuck")],
        vec![Exception {
            rule_id: "missing".into(),
            phrase: "x".into()
        }],
        Config::default()
    )
    .is_err());
    assert!(Filter::new(
        vec![rule("id", "fuck")],
        vec![],
        Config {
            max_candidates: 0,
            ..Config::default()
        }
    )
    .is_err());
}
#[test]
fn thai_is_review_even_when_policy_requests_mask() {
    let mut r = rule("thai", "เหี้ย");
    r.language = Language::Thai;
    r.boundary = Boundary::Substring;
    let filter = Filter::new(vec![r], vec![], Config::default()).unwrap();
    assert_eq!(filter.inspect("เหี้ย").verdict(), Verdict::Review);
}
#[test]
fn transformed_dictionary_is_consistent_without_message_changes() {
    let filter = Filter::seed().unwrap();
    for text in ["ashole", "ashole "] {
        assert_eq!(filter.inspect(text).verdict(), Verdict::Review);
    }
}
#[test]
fn randomized_utf8_never_panics_and_spans_are_valid() {
    let filter = Filter::seed().unwrap();
    let alphabet = [
        'a', 'f', 'u', 'c', 'k', ' ', 'เ', 'ห', 'ี', '้', 'ย', '\u{0301}', '\u{200d}', '🎮', '\n',
        'ﬃ', 'Ａ', '$',
    ];
    let mut state = 0x5eed_u64;
    for _ in 0..5000 {
        let mut text = String::new();
        for _ in 0..(state as usize % 96) {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            text.push(alphabet[(state >> 32) as usize % alphabet.len()]);
        }
        state = state.wrapping_add(1);
        let report = filter.inspect(&text);
        for f in report.findings() {
            assert!(text.get(f.span.clone()).is_some());
            assert!(f.span.start < f.span.end);
        }
        let _ = report.masked();
        let _ = report.redacted();
    }
}
