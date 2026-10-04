# Aetherfield binary WebSocket protocol v2

Status: local prototype protocol; no public deployment or authentication claim. Version 1 JSON is intentionally not accepted after this migration. The browser and Rust server must use the same golden bytes in `golden-v2.json`.

## Envelope

Every WebSocket application message is exactly one envelope. All multi-byte fields use little-endian byte order; do not serialize Rust or TypeScript memory layouts. The fixed six-byte header is:

| Offset | Width | Field | Rule |
|---:|---:|---|---|
| 0 | u16 | Magic `0xA731` | Wire bytes `31 A7` |
| 2 | u8 | Version | Must be `2` |
| 3 | u8 | Type | Values below; unknown values are rejected |
| 4 | u16 | Payload length | Exact payload bytes after the header |

Reject messages shorter than six bytes, larger than the endpoint limit, with the wrong magic/version, a length mismatch, a forbidden trailing byte, or an unknown enum. Client application packets are capped at 4 KiB. WebSocket message and frame limits are 16 KiB; server encoders remain below the u16 payload limit. No compression is negotiated.

## Message types

| Type | Direction | Payload |
|---:|---|---|
| `0x01` | client → server: Join | `flags:u8`, `resume_token:u64`. Only flag bit 0 is allowed. Bit 0 clear requires token zero; bit 0 set requires a nonzero token. Total payload: 9 bytes. |
| `0x02` | client → server: Input | `epoch:u32`, `sequence:u32`, `x:i16`, `z:i16`. Epoch and sequence are nonzero. Axes are normalized quantized values `[-32767,32767]`; `-32768` is invalid. Decode each axis as `value / 32767.0`. Total payload: 12 bytes. |
| `0x03` | client → server: Action | `epoch:u32`, `sequence:u32`, `action:u8`. Action IDs: attack `1`, Arc Slash `2`, dodge `3`. Total payload: 9 bytes. |
| `0x81` | server → client: Welcome | `player_id:u32`, `epoch:u32`, `resume_token:u64`, `tick:u64`, `x:f32`, `z:f32`. Coordinates must be finite and inside the world bound. Total payload: 32 bytes. |
| `0x82` | server → client: Snapshot | `tick:u64`, `player_count:u8`, `monster_count:u8`, `event_count:u8`, `reserved:u8=0`, then fixed records below. Counts are capped at 16/64/64 and the declared packet length must equal the computed size. |
| `0x83` | server → client: Error | `code:u16`. IDs: protocol mismatch `1`, malformed packet `2`, room full `3`, session active `4`, session expired `5`, invalid join `6`. Total payload: 2 bytes. |

Snapshot records are fixed-width and contain no strings:

| Record | Fields, in order | Bytes |
|---|---|---:|
| Player | `id:u32, x:f32, z:f32, hp:u16, max_hp:u16, connected:u8` | 17 |
| Monster | `id:u32, kind:u8, x:f32, z:f32, hp:u16, max_hp:u16, active:u8` | 18 |
| Combat event | `id:u64, player_id:u32, monster_id:u32, action:u8, damage:u16, defeated:u8, world_x:f32, world_z:f32` | 28 |

Monster kind `1` is the original prototype's Meadow Slime; other kinds are rejected until added to both peers. Boolean bytes must be `0` or `1`; entity/event IDs must be nonzero; and `hp` must not exceed `max_hp`. All float values must be finite and inside the world bounds. Unsupported or malformed inbound messages close the local connection; a version error during Join returns the v2 Error envelope.

## Choice and limits

The traffic is a small, stable set of bounded messages with fixed records, so v2 uses an explicit fixed-layout codec instead of adding a schema compiler or a general-purpose serializer. This trades automatic evolution for a small runtime and direct bounds checks; the golden fixture is the compatibility gate. Additive changes require a new message type or protocol version. Do not reuse a field with different units or semantics.

### Short codec comparison

`tools/protocol-size-comparison.mjs` measures the current JSON v1 application payload and the actual fixed-v2 encoder, then computes a small Protocol Buffers wire-format candidate from an explicit proto3 field layout. The candidate is a byte-count prototype, not a generated-library benchmark: no Protobuf compiler/runtime was installed. The comparison uses the same sample input and one-player snapshot, and excludes WebSocket/TLS framing for all options.

| Sample | JSON v1 | Fixed v2 | Protobuf schema candidate |
|---|---:|---:|---:|
| Input: epoch 1, sequence 2, axes +1/-1 | 65 bytes | 18 bytes | 14 bytes |
| Snapshot: tick 42, one player, no mobs/events | 145 bytes | 35 bytes | 24 bytes |

The Protobuf candidate is smaller on these two examples and has a cleaner additive-field evolution story. Its wire tags and varints skip default values, and schema evolution requires keeping old field numbers stable and reserving deleted numbers. The candidate layout and compatibility notes follow the official [wire encoding guide](https://protobuf.dev/programming-guides/encoding) and [schema evolution guidance](https://protobuf.dev/getting-started/cpptutorial).

| Concern | Fixed v2 | Generated schema candidate |
|---|---|---|
| Malformed packets | Exact type lengths, record counts and trailing-byte rejection are hand-coded and covered by golden/negative tests. | A generated parser can enforce field wire types and skip unknown tags; message/depth limits and game-specific semantic checks are still required. |
| Evolution | Additive fields require an explicit v3 or a new message type. | Additive fields can use new tags; deleted tags must stay reserved and never be reused. |
| Rust/TypeScript setup | No added codec dependency or generator; two small explicit codecs and shared golden bytes. | Requires a `.proto`, Rust and TypeScript codegen/runtime, build integration, version pinning and generated-code review. This setup effort was not benchmarked in this spike. |
| Fit for this slice | Predictable bounded records for six local message kinds; already tested across both peers. | Revisit when optional fields, many content events, or independent external clients make version evolution more costly than the toolchain. |

The measured size samples favor the schema candidate, but this project currently values a dependency-free, explicit parser for its narrow local message set. This does not prove a CPU, bandwidth, or production-performance advantage. The decision should be revisited before P2 adds more message families or supports independently deployed clients.

The client sends intents only. It never sends a position, target authority, damage amount, item grant, currency change, or quest completion. The server resolves the actor from the connection and checks epoch, sequence, cooldown, range, and world state. Reconnect changes the epoch, which invalidates old commands.

`golden-v2.json` includes client and server packets, including a complete player+monster+event snapshot whose event ID is `2^53 + 1`. JavaScript keeps every wire `u64` as `bigint`; conversion to `number` would lose identity. Rust rejects every truncation of client golden packets, and the browser decoder rejects every truncation of server golden packets. Negative cases cover non-finite/out-of-bounds coordinates, invalid HP, counts, reserved fields, enums and booleans. The codec is one step in G0; it does not establish authentication, durable state, Internet hardening, or production readiness.
