# Aetherfield binary WebSocket protocol v5

Status: historical v5 wire, superseded by [v6](binary-v6.md). V5 extends the v4 message set with a
per-connection position anchor for the last applied movement input. This lets
the client replay newer inputs from the state at the acknowledged sequence,
even when the server repeats that input on later ticks. **v3 and v4 packets are
rejected**. The HTTP session cookie, one-use join tickets and the exact-Origin
check from [v3](binary-v3.md) are unchanged.

## Envelope

Each WebSocket application message is exactly one envelope. Multi-byte values
are little-endian. The fixed six-byte header is unchanged:

| Offset | Width | Field | Rule |
|---:|---:|---|---|
| 0 | u16 | Magic `0xA731` | Wire bytes `31 A7` |
| 2 | u8 | Version | Must be `5` |
| 3 | u8 | Type | Unknown values are rejected |
| 4 | u16 | Payload length | Exact payload bytes after the header |

Client application packets are capped at 4 KiB. WebSocket frames/messages are
capped at 16 KiB. No compression is negotiated. Reject short headers,
oversized messages, wrong magic/version, length mismatches, trailing bytes,
and unknown enums. The shared [v5 golden corpus](golden-v5.json) pins every
hot message and every canonical cold JSON string.

## Hot path (fixed binary)

Angles (`facing`, `aim`) are u16 circles: `0` is east (+x),
`quantized = round(angle mod 2π / 2π × 65535)`.

| Type | Direction | Payload | Bytes |
|---:|---|---|---:|
| `0x01` Join | C → S | `ticket[32]` (nonzero; bound to the cookie session) | 32 |
| `0x02` Input | C → S | `epoch u32 ≠ 0`, `seq u32 ≠ 0`, `move_x i16`, `move_z i16` (≠ `i16::MIN`), `facing u16` | 14 |
| `0x03` Action | C → S | `epoch u32 ≠ 0`, `seq u32 ≠ 0`, `ability u8` (1 attack, 2 arc slash, 3 dodge, 4 guard; 5 Splash Hop is server-only and rejected), `aim u16`, `target_id u32` (0 = none), `view_tick u32` | 19 |
| `0x04` Ping | C → S | `nonce u32`, `client_ms u32` | 8 |
| `0x81` Welcome | S → C | `player_id u32 ≠ 0`, `epoch u32 ≠ 0`, `tick u64`, `x f32`, `z f32` (finite, ±28 m), `zone_id u16`, `content_hash u64`, `tick_hz u8` | 35 |
| `0x82` Snapshot | S → C | 24-byte header: `tick u64`, `ack_seq u32`, `own_flags u8`, `ack_x f32`, `ack_z f32` (position immediately after ack_seq was applied), then `players u8`, `monsters u8`, `events u8`; then records | Variable, capped |
| `0x83` Error | S → C | `code u16` (1 protocol_mismatch … 6 invalid_join, as v3, plus 7 rate_limited: sustained per-type excess, sent before the close) | 2 |
| `0x84` ActionResult | S → C (owner only) | `seq u32 ≠ 0`, `result u8` (0 rejected, 1 accepted), `reason u8` (0 none, 1 cooldown, 2 out_of_range, 3 no_target, 4 dead, 5 busy, 6 not_allowed, 7 rate_limited), `cooldown_ms u16` | 8 |
| `0x85` Pong | S → C (owner only) | `nonce u32`, `client_ms u32` (echoes), `server_tick u64` | 16 |

Snapshot records:

| Record | Fields | Bytes |
|---|---|---:|
| Player | `id u32 ≠ 0`, `x f32`, `z f32`, `facing u16`, `hp u16 ≤ max_hp`, `max_hp u16`, `flags u8` (bit0 connected, bit1 down, bit2 dodging, bit3 guarding), `anim u8` | 20 |
| Monster | `id u32 ≠ 0`, `kind u8 ≠ 0` (1 = Puddlekin, from the content bundle), `x f32`, `z f32`, `facing u16`, `hp u16 ≤ max_hp`, `max_hp u16`, `flags u8` (bit0 active), `state u8` (0 idle, 1 approach, 2 windup, 3 active, 4 recovery, 5 stagger), `ability u8`, `state_ticks_left u16`, `target_x f32`, `target_z f32` | 32 |
| Event | `id u64 ≠ 0`, `source_kind u8` (0 player, 1 monster), `source_id u32 ≠ 0`, `target_kind u8` (0 monster, 1 player), `target_id u32 ≠ 0`, `ability u8` (1 attack, 2 arc slash, 3 dodge, 4 guard, 5 Splash Hop), `amount u16`, `flags u8` (bit0 defeated, bit1 blocked, bit2 perfect, bit3 dodged, bit4 heal), `x f32`, `z f32` | 30 |

Counts stay capped at 50 players / 64 monsters / 64 events. Coordinates are
finite and within the current zone (±28 m); the protocol hard maximum is
±4,096 m and bounds move into content data in V5-03.

## Cold path (tagged JSON)

| Direction | Envelope | Cap | Messages (`"t"` tag) |
|---|---|---:|---|
| C → S | `0x10` | 512 B | `interact{npc}`, `choose{npc, token, choice}`, `claim{quest, op_id}`, `use_item{item, op_id}`, `party_create{}`, `party_join{code}`, `party_leave{}`, `resync{}` |
| S → C | `0x90` | 4 KiB | `character_state`, `quest_state`, `dialogue`, `dialogue_closed`, `op_result`, `party_state`, `notice` (shapes in `cold.rs` / `cold_v4.gen.ts`) |

Rules: payload must be UTF-8 JSON object with a known string `"t"`;
unknown fields are denied. Content ids are `1–64` chars of `[A-Za-z0-9_]`;
party codes are exactly 6 `[A-Z0-9]`; `op_id` is UUID-shaped
(`8-4-4-4-12` hex). In v4 the server validates, rate-limits and counts cold
payloads; typed handlers land with their gameplay items (V5-06 onward).

## Rate budgets (per message type, 1 s windows)

Input ≤ 25/s, Action ≤ 10/s, cold ≤ 5/s, Ping ≤ 2/s. Sustained excess closes
the connection. The world thread additionally drains at most 4 inputs, 2
actions and 2 cold messages per connection per tick; excess is dropped and
counted.

## Compatibility and identity

- Welcome carries `zone_id`, `content_hash` and `tick_hz` from the content
  bundle: `content/source/` builds to `content/build/<hash>/bundle.json`
  (canonical JSON; FNV-1a-64 of the file bytes names the directory). The
  server verifies the hash at boot and refuses to start on mismatch; the
  client hashes the same bytes it fetched and reloads on mismatch. Any content
  edit changes the wire-visible hash, so the golden welcome is regenerated
  alongside (see the `dump_golden_hex` helper).
- Every value-changing cold request carries an `op_id` UUID; idempotency
  storage lands with durable handlers (V5-13).
- A P1 snapshot with 4 players, 8 monsters and 2 events is ~350 bytes; at
  20 Hz ≈ 57 kbit/s per client before framing, in line with v3's budget.
