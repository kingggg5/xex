// Reproducible dependency-free microbenchmark. Measures this process, not MMO CCU.
use std::{
    hint::black_box,
    time::{Duration, Instant},
};
use xexoria_chat_filter::{
    guard::{ChatGuard, GuardConfig, SenderKey},
    Action, Boundary, Config, Filter, Language, Rule,
};

fn measure<F: FnMut(&str) -> usize>(name: &str, inputs: &[String], mut check: F) {
    const BATCHES: usize = 21;
    const PER_BATCH: usize = 1000;
    const LATENCY_SAMPLES: usize = 10_000;
    let mut checksum = 0;
    for i in 0..3000 {
        checksum ^= check(black_box(&inputs[i % inputs.len()]));
    }
    let mut batch_ns = Vec::new();
    for batch in 0..BATCHES {
        let start = Instant::now();
        for i in 0..PER_BATCH {
            checksum ^= check(black_box(&inputs[(batch * PER_BATCH + i) % inputs.len()]));
        }
        batch_ns.push(start.elapsed().as_nanos() as f64 / PER_BATCH as f64);
    }
    batch_ns.sort_by(f64::total_cmp);
    let mut latency = Vec::with_capacity(LATENCY_SAMPLES);
    for i in 0..LATENCY_SAMPLES {
        let start = Instant::now();
        checksum ^= check(black_box(&inputs[i % inputs.len()]));
        latency.push(start.elapsed().as_nanos());
    }
    latency.sort_unstable();
    let median = batch_ns[BATCHES / 2];
    let bytes = inputs.iter().map(String::len).sum::<usize>() as f64 / inputs.len() as f64;
    println!(
        "{name},{bytes:.1},{median:.1},{:.0},{:.1},{},{},{},{}",
        1e9 / median,
        bytes / median * 1e9 / 1_048_576.0,
        latency[LATENCY_SAMPLES / 2],
        latency[LATENCY_SAMPLES * 95 / 100],
        latency[LATENCY_SAMPLES * 99 / 100],
        black_box(checksum)
    );
}
fn main() {
    let start = Instant::now();
    for _ in 0..100 {
        black_box(Filter::seed().unwrap());
    }
    let build_us = start.elapsed().as_secs_f64() * 1e6 / 100.0;
    let filter = Filter::seed().unwrap();
    eprintln!("rules={} automata_bytes={} mean_compile_us={build_us:.1}; batches=21x1000 warmup=3000 latency_samples=10000", filter.rule_count(), filter.automaton_memory_bytes());
    println!("case,mean_input_bytes,median_batch_ns_per_message,messages_per_second,MiB_per_second,p50_ns,p95_ns,p99_ns,checksum");
    let corpus: Vec<String> = include_str!("../tests/data/corpus.tsv")
        .lines()
        .filter(|l| !l.starts_with('#') && !l.is_empty())
        .map(|l| l.split_once('\t').unwrap().1.to_owned())
        .collect();
    let cases = [
        (
            "clean_ascii",
            vec!["Looking for two healers for the castle raid, meet near the west gate!".into()],
        ),
        (
            "clean_thai",
            vec!["หาปาร์ตี้ตีบอสอีกสองคน เจอกันที่ประตูเมืองฝั่งตะวันตกครับ 🎮".into()],
        ),
        (
            "literal_hit",
            vec!["what the fuck, the boss reset again!".into()],
        ),
        (
            "obfuscation",
            vec!["he said f.u.c.k and sh1t in chat".into()],
        ),
        ("seeded_mixed", corpus),
        ("long_ascii_4096B", vec!["a".repeat(4096)]),
        ("long_thai_4095B", vec!["ก".repeat(1365)]),
        ("over_limit_4097B", vec!["a".repeat(4097)]),
    ];
    let dense = vec!["fuck ".repeat(800)];
    measure("dense_match_limit", &dense, |text| {
        let report = filter.inspect(text);
        black_box(report.findings().len() + report.verdict() as usize)
    });
    for count in [100, 1000] {
        let rules = (0..count)
            .map(|i| Rule {
                id: format!("synthetic_{i}"),
                language: Language::English,
                boundary: Boundary::Word,
                action: Action::Mask,
                term: format!("syntheticterm{i}"),
            })
            .collect();
        let started = Instant::now();
        let large = Filter::new(rules, vec![], Config::default()).unwrap();
        eprintln!(
            "synthetic_rules={count} automata_bytes={} compile_us={:.1}",
            large.automaton_memory_bytes(),
            started.elapsed().as_secs_f64() * 1e6
        );
        measure(&format!("synthetic_{count}_clean"), &cases[0].1, |text| {
            let report = large.inspect(text);
            black_box(report.findings().len() + report.verdict() as usize)
        });
    }
    for (name, inputs) in &cases {
        measure(name, inputs, |text| {
            let report = filter.inspect(text);
            black_box(report.findings().len() + report.verdict() as usize)
        });
    }
    let config = GuardConfig {
        repeat_window: Duration::ZERO,
        ..GuardConfig::default()
    };
    let mut guard = ChatGuard::new(config).unwrap();
    let mut tick = 0u64;
    measure("guard_only_existing_key", &cases[0].1, |text| {
        tick += 1;
        black_box(
            guard
                .check(SenderKey(42), 0, text, Duration::from_secs(tick))
                .is_ok() as usize,
        )
    });
}
