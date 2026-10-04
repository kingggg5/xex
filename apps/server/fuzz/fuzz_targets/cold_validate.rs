#![no_main]

use aetherfield_server::cold::validate_client_payload;
use libfuzzer_sys::fuzz_target;

// The cold JSON validator must never panic on any bytes, including invalid
// UTF-8 and pathological nesting (serde size/depth limits apply).
fuzz_target!(|data: &[u8]| {
    let _ = validate_client_payload(data);
});
