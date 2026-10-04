# Xexoria integration — 2026-10-02

This is the working copy of the user-supplied `Xexoria_Chat_Filter_Rust_v0.1.zip`, archive SHA256 `da7ec355f7667cd11f7c370c0bfa56a6c847eb010bcb41f3d168e13734c88fb8`. Original bytes and checksums remain in the immutable source mirror under `Downloads/Xexoria-Game/agent-output/20261002-chat-filter/source/chat_filter/`; the original ZIP is untouched. `SHA256SUMS.txt` describes that original package, not the patched working copy. Working-source/host hashes and checks are in `admission.json`.

## What is integrated

- One compiled filter in the process-shared `SocialHub`, with bounded global/per-channel guards. Normal room chat, cross-instance group chat and Megaphone pass the authoritative gate before publication. Matching occurs outside social/quota locks; no filesystem, provider API or database lookup occurs per message.
- Production joins bind the full server-resolved principal to both social presence and its epoch-checked room connection before accepting Cold frames. The connection keeps it until queued dispatch finishes, even when social presence is removed, preserving limits across room/session changes and teardown. Standalone authenticated `RoomHandle` users without social presence retain a session-key quota. Guards are process-local, not distributed.
- Literal English matches can be masked. Thai/heuristic/incomplete-work Review and Reject are withheld with Thai/English feedback; no review queue or automatic ban/punishment is added. Exact-repeat protection records attempts admitted by its guard, including later policy holds, so repeat notices do not assert that the earlier message was published.
- The policy remains the supplied11 illustrative terms and2 literal exceptions. No complete profanity coverage or accuracy guarantee is claimed. Existing512-byte cold packets,160-scalar room/group text and110-scalar Megaphone checks remain; pre-existing sanitisation/truncation is separate from grapheme-safe masking.
- Host filter caps:512input bytes/2048normalised bytes/256candidates/32findings/64scalars per grapheme. Whole-user bucket6burst/2per second,1024keys; channel bucket3072keys,5second exact-repeat window,16fingerprints/key,60second idle TTL,8prune inspections/check. Rejections never refund attempts. Capacity/poison failure withholds.

## Local patches and evidence

The working boundary helper ignores adjacent configured invisible units before testing the nearest meaningful word neighbours. It closes the leading-U+200B bypass while preserving longer-word boundaries, original grapheme spans, Thai exceptions and emoji joiners. Regression tests cover all six invisibles around every seeded English term plus internal obfuscation and harmless neighbours. Manifest dependencies are pinned to the supplied versions: aho-corasick1.1.5,unicode-normalization0.1.25,unicode-segmentation1.13.3; the host Cargo.lock records actual resolution.

Windows/Rust1.96 verification: package36tests pass; host208library +7binary tests pass/7database-dependent tests ignored;9actual room/group/Megaphone publication/identity/backpressure tests pass, including presence-removal and stale-epoch binding regressions; host `cargo check --locked --all-targets` passes. Client302tests and TypeScript/Svelte checks pass. No upstream benchmark was rerun and no crowded-room/10k throughput qualification is claimed. Logs/receipts are in `Downloads/Xexoria-Game/agent-output/20261002-chat-filter/`.

Keep the MIT LICENSE and dependency notices. Do not log the upstream `Report` Debug representation: it includes original chat text; the host logs neither reports nor raw rejected text. No live server process was restarted, no existing player session reset and no public deployment performed. Restart/rebuild the desired local server/client to activate the updated source.

---

## Original standalone package README

The following original notes describe the supplied standalone package and its earlier Linux benchmark; the integration note above defines current host status.

# Xexoria chat filter + ingress guard (Rust)

Standalone server-side starter package for a Babylon.js/Rust MMO. No game repository was modified. Start with [QUICKSTART_TH.md](QUICKSTART_TH.md); measured performance is in [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Included

- Compile-once Aho–Corasick matching with bounded literal and heuristic lanes
- English whole-word rules; conservative Thai candidates and span-local exceptions
- Original UTF-8 byte spans and whole-original-grapheme masking
- Typed Allow / Mask / Review / Reject, plus explicit incomplete-work limits
- Per-account/channel token buckets, bounded exact-repeat history, TTL cleanup
- Runnable authoritative-server gate, configurable TSV policy, tests and benchmark

**11 illustrative seed terms, not a complete production profanity dictionary.** Review language/community policy before rollout. No external API, AI inference, database lookup, or network request occurs per message.

## Run

Verified with Rust 1.99.0 on Linux x86_64; other toolchains/platforms were not tested. Initial Cargo dependency download is required.

~~~sh
cargo test --locked --lib --tests --examples
cargo fmt -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo run --locked --example server_gate
cargo bench --locked --bench throughput
~~~

MIT license; dependency versions/checksums are in Cargo.lock and licenses in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

~~~rust
use xexoria_chat_filter::{Filter, Verdict};
let filter = Filter::seed()?; // once at startup; share Arc<Filter>
let report = filter.inspect("FUCK!");
match report.verdict() {
    Verdict::Allow => { /* publish original AFTER all ingress checks */ }
    Verdict::Mask => { let output = report.masked(); /* publish output */ }
    Verdict::Review => { /* WITHHOLD: bounded review queue or neutral rejection */ }
    Verdict::Reject => { /* reject oversized input */ }
}
~~~

Use examples/server_gate.rs for the full ingress sequence.

## Thai and uncertain findings

**Every Thai match is Review**, even if a custom Thai rule requests mask. Thai has no general whitespace word boundary. Words may describe animals, familiar speech, quotations, or occur inside harmless words. The seed omits several especially ambiguous short words. Exceptions for เหี้ยม and แม่งาน suppress only contained occurrences, never the entire message.

**Review means do not broadcast the original.** If no moderation queue exists, return a neutral response such as “ข้อความนี้ยังส่งไม่ได้ กรุณาปรับข้อความแล้วลองอีกครั้ง”. The example does this. Any future review queue needs bounded depth, short retention, access control, and fail-closed overflow.

Mask is a policy choice for literal English matches, not an inference about intent. No automatic ban, timeout, punishment score, or account action is implemented.

## Dictionary configuration

Load once at startup or authorized configuration reload:

~~~rust
let filter = xexoria_chat_filter::Filter::from_tsv(
    &std::fs::read_to_string("policy.tsv")?,
    &std::fs::read_to_string("exceptions.tsv")?,
    xexoria_chat_filter::Config::default(),
)?;
~~~

policy.tsv has five TAB-separated columns: id / en|th / word|substring / mask|review / literal term.
exceptions.tsv has two: rule_id / containing literal phrase.
Blank and # comment lines are ignored. IDs are unique ASCII identifiers; terms are literal, not regex.

Changes are validated before replacing the live filter. Build a new Arc and swap through your configuration mechanism; keep the old filter on errors. Never compile/read dictionaries per message. Keep versioned regression examples for false-positive fixes. Dictionary/configuration input is trusted server data, never client-supplied. Typed Rule and Exception construction is also supported.

## Normalization and source spans

1. Reject oversized bytes before filter allocation.
2. Segment the original into extended graphemes. Apply NFKC and Unicode lowercase to each; every emitted scalar retains that entire original grapheme's byte range. ASCII has a direct lowercase path.
3. Search using overlapping Standard Aho–Corasick matches. Check boundaries after candidate discovery so rejected short overlaps cannot hide longer valid terms.
4. Optionally scan a lossy heuristic lane; these findings always require Review.
5. Mask merged original ranges using one star per original grapheme. Untouched bytes, emoji and Thai marks are preserved.

This is **per-grapheme NFKC + lowercase**, not global NFKC_Casefold, full Unicode case folding, or a UTS #39 confusable skeleton. Compatibility expansions cannot be partially matched as whole source graphemes.

Spans are **Rust UTF-8 byte offsets**, not JavaScript UTF-16 indices. Use the server's masked string; do not feed byte offsets to JS slice().

English word boundaries reject adjacent Unicode alphanumeric characters, combining marks, underscore, or known invisibles. Thus ไทยfuckไทย is intentionally not an English whole-word hit. This is not a full UAX #29 word segmenter.

### Configurable heuristic lane

Config::obfuscation can enable/disable:
- Invisibles: U+00AD, U+200B/C/D, U+2060, U+FEFF
- ASCII leet: 0→o, 1→i, 3→e, 4/@→a, 5/$→s, 7→t
- Latin diacritics decomposable to an ASCII letter plus marks; Thai marks stay intact
- Repeated ASCII letters, collapsed in both dictionary and input
- Joining space, dot, hyphen, underscore, asterisk; never newline/tab/arbitrary symbols
- max_gap: default two skipped normalized units, including collapsed internal gaps

Rewrites can join innocent words or miss new spellings. For example ashole requires review because the dictionary's repeated ss also collapses. Disable the lane for exact-only behavior. No general Cyrillic/Greek homoglyph mapping, phonetic Thai matching, semantic toxicity, or full default-ignorable handling is claimed.

## Bounded work and memory

| Filter limit | Default | Allowed |
|---|---:|---:|
| Input bytes | 4,096 | 1..65,536 |
| Normalized bytes per lane | 16,384 | 1..262,144 |
| Scalars per original grapheme | 64 | 1..256 |
| Candidates including exceptions/both lanes | 512 | 1..8,192 |
| Accepted findings | 64 | 1..1,024 |
| Joined gap | 2 | 0..8 |

Dictionary: 1..2,048 rules, ≤2,048 exceptions, ≤128 bytes/term, ≤128KiB total term bytes, ≤256KiB per TSV input.

Oversize returns Reject + InputBytes. Normalization/candidate/finding exhaustion returns **incomplete Review with a typed Limit**, never clean Allow. Findings may be partial: masked() is insufficient to publish an incomplete report. Always use the verdict.

No unsafe code in this crate; dependencies make their own choices. Hot-path buffers allocate, with bounded sizes. This is not allocation-free. Matching is linear in text plus candidates; normalization, bounded exception checks/deduplication, and sorting add work. Larger configuration caps increase worst-case cost. Bound upstream work queues too.

## Authoritative ingress and deployment

The runnable example:
1. Gets account ID from a trusted authenticated session and checks server-owned channel permissions
2. Assumes transport frame size is capped before decoding/allocation
3. Applies a whole-account guard with constant channel, then a per-channel guard
4. Charges attempts before matching; duplicate/profanity holds do not refund tokens
5. Rejects controls, bidi overrides/isolates and common invisible-only content while preserving family ZWJ emoji
6. Publishes only Allow or Mask output; Review/limits stay withheld

Render chat as plain text, e.g. DOM textContent or Babylon text controls, never unescaped HTML. Client previews do not replace server validation.

Guard defaults: burst 6, refill 2/sec, 4KiB payload, 16,384 account/channel entries, idle TTL 60s, repeat window 5s, 16 hashes/entry, 8 cleanup probes/check. The example uses slower world/trade buckets too.

State stores **keyed hashes, never raw messages**. Duplicates are byte-exact; hash collisions are unlikely but possible. Case/Unicode/whitespace variants may evade duplicate detection but consume rate tokens. A guard-accepted message later held by the filter remains in repeat history. No live entry is evicted merely to grant fresh tokens. Capacity/history exhaustion is explicit backpressure.

Oversize is rejected O(1) without token charge, so edge frame/connection flood protection is still necessary. This is process-local, not a distributed quota. Keep guards alive across reconnects, key by account not socket, and route accounts consistently to their state owner or use a shared authoritative limiter. Multiple connections/servers must not each provide a new full burst. Use a monotonic server Instant, never client time. New-account bots need separate defenses.

No raw chat logging is enabled. Prefer aggregate verdict/rule/limit/latency counters. Any added review text needs access control, explicit retention and deletion policy. Don't log credentials or chat payloads by default.

## Verification and limits

See [docs/VERIFICATION.md](docs/VERIFICATION.md). Fixture agreement is regression coverage, **not real-world accuracy**. The single-process CPU benchmark is **not MMO CCU, multiplayer load, networking latency or production p99**.

Not included: actual transport/auth, distributed state, persistent review UI, automatic dictionary updates, account sanctions, client npm package, game-repository integration or deployment. No guarantee every offensive word/evasion is caught. Start with privacy-safe authorized examples and shadow metrics, review misses/false positives, then staged policies.

## Primary research (checked 2026-10-02)

- [Aho–Corasick](https://docs.rs/aho-corasick/latest/aho_corasick/) and [Standard semantics](https://docs.rs/aho-corasick/latest/aho_corasick/enum.MatchKind.html): compiled matching and overlapping candidates
- [UAX #15 normalization](https://www.unicode.org/reports/tr15/): representation/length changes and compatibility-folding tradeoffs
- [UAX #29 segmentation](https://www.unicode.org/reports/tr29/): default boundaries need tailoring for Thai
- [unicode-normalization API](https://docs.rs/unicode-normalization/latest/unicode_normalization/) and [grapheme API](https://docs.rs/unicode-segmentation/latest/unicode_segmentation/trait.UnicodeSegmentation.html): implementation building blocks
- [UTS #39 security](https://www.unicode.org/reports/tr39/): spoofing is broader than a substitution list
- [OWASP WebSocket guidance](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): auth, message size limits, rate limits, and safe logging
- Future option: [ICU4X WordSegmenter](https://docs.rs/icu_segmenter/latest/icu_segmenter/struct.WordSegmenter.html), not included/benchmarked here; segmentation still cannot determine intent

The design choices and seed policy are engineering judgments, not endorsements by these sources.
