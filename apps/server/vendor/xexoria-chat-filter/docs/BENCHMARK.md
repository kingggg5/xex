# Measured microbenchmark

Recorded 2026-10-02 05:41 UTC, Linux x86_64 cloud container, AMD EPYC 9V74 host-reported CPU.
Nine logical CPUs were exposed; benchmark code itself is single-threaded. Shared-host
scheduling/turbo/background activity were not controlled. Rust 1.99.0, LLVM 23.1.1.
Release profile uses thin LTO and one codegen unit. Cargo.lock pins dependencies.

**These are CPU measurements, not MMO CCU, transport throughput, production p99,
or a promised server capacity.** Input cases have different lengths/content;
do not infer relative algorithm speed from differently sized inputs.

## Method

Run: cargo bench --locked --bench throughput

For each case: 3,000 warm-up checks, then 21 batches of 1,000. Report the median
batch elapsed time per message. Separately measure 10,000 individual calls with
Instant for p50/p95/p99; those include timer overhead. black_box consumes results.
Filter construction is excluded from inspection timings. inspect includes
normalization, matching, boundaries, exceptions and report allocation, but not
mask rendering, network/auth, queueing, database, or the game loop.

The seed automata have 11 rules and report 46,600 bytes for their internal automaton
storage (not whole Filter/temporary-buffer/allocator RSS). Mean seed compilation
over 100 constructions was 89.6 microseconds.

Synthetic 100/1,000-rule dictionaries are deliberately simple generated strings:
compile times 227.7/1,766.6 microseconds and automaton-reported memory 35,592/42,824
bytes. Memory need not grow monotonically across different automaton layouts.
These synthetic clean scans demonstrate this fixture only, not arbitrary
production dictionary scaling.

| Case | Mean bytes | Median batch µs/message | Single-call p95 µs | Single-call p99 µs |
|---|---:|---:|---:|---:|
| dense_match_limit | 4000.0 | 61.209 | 100.081 | 143.186 |
| synthetic_100_clean | 69.0 | 2.073 | 2.214 | 2.273 |
| synthetic_1000_clean | 69.0 | 2.112 | 2.204 | 2.303 |
| clean_ascii | 69.0 | 2.187 | 2.234 | 2.394 |
| clean_thai | 174.0 | 6.756 | 6.770 | 9.594 |
| literal_hit | 36.0 | 1.402 | 1.442 | 1.462 |
| obfuscation | 32.0 | 1.219 | 1.242 | 1.272 |
| seeded_mixed | 24.0 | 1.220 | 2.935 | 3.656 |
| long_ascii_4096B | 4096.0 | 71.825 | 104.919 | 231.079 |
| long_thai_4095B | 4095.0 | 133.613 | 172.160 | 280.653 |
| over_limit_4097B | 4097.0 | 0.006 | 0.030 | 0.031 |
| guard_only_existing_key | 69.0 | 0.064 | 0.091 | 0.091 |

The over-limit case measures only an O(1) length rejection: its derived MiB/sec
in the raw CSV is not scanning throughput. The guard-only case has one existing
key, repeat detection disabled, and synthetic monotonic times advanced by one
second per call; it is not a real flood workload or a worst-case capacity test.

The mixed corpus is 59 hand-authored English/Thai/emoji messages with clean,
literal and obfuscated examples. The dense case reaches the finding cap and
returns incomplete Review. The 4KiB cases exercise default-length boundaries.

Raw data: [benchmark.csv](benchmark.csv). Environment: [benchmark-environment.txt](benchmark-environment.txt).
Rerun on the actual server with its allocator, deployed dictionary, thread/queue
model and representative authorized traffic. Profile before introducing
scratch-buffer reuse or a Thai segmenter. No comparative regex benchmark was
performed, and no speed superiority over another implementation is claimed.
