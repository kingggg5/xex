# Fuzz targets (V5-02 acceptance)

Targets: `hot_decode` (binary client-packet decoder) and `cold_validate`
(tagged-JSON cold validator). Both must never panic and stay bounded on any
input. Seeds live in `seeds/` (golden packets + golden cold JSON + edge
cases); copy them into the working corpus before a run.

## One-time setup (Windows)

- Nightly toolchain: `rustup toolchain install nightly --profile minimal`
- cargo-fuzz: `cargo install cargo-fuzz`
- ASan runtime (fuzz builds use AddressSanitizer by default): copy
  `clang_rt.asan_dynamic-x86_64.dll` from the Visual Studio MSVC tools
  (`VC\Tools\MSVC\<ver>\bin\Hostx64\x64`) next to the built target binary, or
  onto `PATH`. The LLVM.org release DLL is version-skewed and fails to load.

## Run (≥ 10 min each per plan §7/§15)

```powershell
$env:RUSTUP_TOOLCHAIN = "nightly"
Copy-Item fuzz/seeds/hot_decode/* fuzz/corpus/hot_decode/ -Force
Copy-Item fuzz/seeds/cold_validate/* fuzz/corpus/cold_validate/ -Force
cargo fuzz run hot_decode -- -max_total_time=660 -print_final_stats=1
cargo fuzz run cold_validate -- -max_total_time=660 -print_final_stats=1
```

A clean run ends with `Done N runs in 66X second(s)` and empty
`artifacts/<target>/`. Any artifact is a release-blocking bug: minimize,
file the input bytes in the evidence, and fix before any protocol change
ships.

Baseline (2026-09-24, nightly 1.100): hot 86,338,166 runs / 661 s clean;
cold 31,549,794 runs / 661 s clean. See `planning/evidence/v5-02-protocol.json`.
