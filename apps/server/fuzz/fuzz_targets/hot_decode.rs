#![no_main]

use aetherfield_server::wire::decode_client_packet;
use libfuzzer_sys::fuzz_target;

// The hot binary decoder must never panic and must stay bounded on any
// input: every path returns a bounded DecodeError.
fuzz_target!(|data: &[u8]| {
    let _ = decode_client_packet(data);
});
