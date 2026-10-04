# Verification record

Final verification date: 2026-10-02. Rust 1.99.0, Linux x86_64.

Passed:
- cargo test --locked --lib --tests --examples: 32 tests
  - 15 guard tests, including 20,000 deterministic adversarial state transitions
  - 14 filter tests, including a 59-row hand-authored corpus and 5,000 seeded UTF-8 cases
  - 3 authoritative-ingress example tests
- cargo test --locked --doc (no doctests defined in crate source)
- cargo fmt -- --check
- cargo clippy --locked --all-targets -- -D warnings
- cargo run --locked --example server_gate
- Release microbenchmark executed, with raw CSV and environment record

Coverage: plain/obfuscated English and Thai; harmless English substring cases;
Thai span-local exceptions; fullwidth, combining marks, normalization expansion,
UTF-8 source span safety, family ZWJ emoji, repeat letters, bounded separator gaps,
config errors, overlapping candidates, all resource limit branches; guard refill,
duplicates, capacity, incremental expiry, backwards time, bounded history and
queue, per-user aggregate rate across channels; before-broadcast withholding and
bidi/invisible-only ingress rejection.

Fixture agreement is not real-world precision/recall. The seeded UTF-8 test is
deterministic pseudo-random testing, not coverage-guided fuzzing or formal proof.

Not run: Xexoria production integration, actual WebSocket/packet tests, browser
or Babylon UI tests, distributed/shard tests, sustained multi-user load, memory
profiler, sanitizer/Miri, cargo-audit, commercial dictionary review, or real user
corpus evaluation. No server or game deployment was performed.
