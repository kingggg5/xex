//! Content bundle builder (V5-03).
//!
//! Validates `content/source/` and writes the canonical bundle to
//! `content/build/<hash>/bundle.json`, plus a copy for the web client at
//! `apps/client/public/content/bundle.json`.
//!
//! Run: `cargo run --manifest-path apps/server/Cargo.toml --bin build_content`

use aetherfield_server::content;
use std::path::PathBuf;

fn candidate_source_dirs() -> Vec<PathBuf> {
    [
        "content/source",
        "../content/source",
        "../../content/source",
    ]
    .iter()
    .map(PathBuf::from)
    .collect()
}

fn candidate_roots() -> Vec<PathBuf> {
    ["content", "../content", "../../content"]
        .iter()
        .map(PathBuf::from)
        .collect()
}

fn candidate_client_dirs() -> Vec<PathBuf> {
    [
        "apps/client/public/content",
        "../client/public/content",
        "../../client/public/content",
    ]
    .iter()
    .map(PathBuf::from)
    .collect()
}

fn main() {
    let source = candidate_source_dirs()
        .into_iter()
        .find(|dir| dir.is_dir())
        .expect("content/source not found: run from the repo root or apps/server");
    let content = content::load_source_dir(&source).expect("content source validates");
    let hash_hex = content.hash_hex();

    let root = candidate_roots()
        .into_iter()
        .find(|dir| dir.is_dir())
        .expect("content/ not found");
    // Rebuild deterministically: wipe previous builds so exactly one remains.
    let build = root.join("build");
    if build.is_dir() {
        std::fs::remove_dir_all(&build).expect("clear stale content builds");
    }
    let out_dir = build.join(&hash_hex);
    std::fs::create_dir_all(&out_dir).expect("create content build dir");
    std::fs::write(out_dir.join("bundle.json"), &content.bundle_json).expect("write bundle");
    println!(
        "content bundle {hash_hex} ({} bytes)",
        content.bundle_json.len()
    );

    if let Some(public) = candidate_client_dirs()
        .into_iter()
        .find(|dir| dir.parent().is_some_and(|parent| parent.is_dir()) || dir.is_dir())
    {
        std::fs::create_dir_all(&public).expect("create client content dir");
        std::fs::write(public.join("bundle.json"), &content.bundle_json)
            .expect("copy bundle for client");
        println!("client copy at {}", public.join("bundle.json").display());
    }
}
