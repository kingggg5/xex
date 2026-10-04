# Aetherfield binary WebSocket protocol v3

Status: local loopback prototype. V3 replaces v2's client-selected numeric resume token with a server-issued, one-time join ticket. The HTTP session cookie and WebSocket Origin check are part of the connection contract; v2 packets are rejected.

## Envelope

Each WebSocket application message is exactly one envelope. Multi-byte values are little-endian; do not serialize Rust or JavaScript memory layouts. The fixed six-byte header is unchanged from v2:

| Offset | Width | Field | Rule |
|---:|---:|---|---|
| 0 | u16 | Magic `0xA731` | Wire bytes `31 A7` |
| 2 | u8 | Version | Must be `3` |
| 3 | u8 | Type | Unknown values are rejected |
| 4 | u16 | Payload length | Exact payload bytes after the header |

Client application packets are capped at 4 KiB. WebSocket frames/messages are capped at 16 KiB. No compression is negotiated. Reject short headers, oversized messages, wrong magic/version, length mismatches, trailing bytes, and unknown enums.

## Admission and message types

Before opening the WebSocket, the browser calls `POST /session` and `POST /session/ticket` through the same-origin Vite proxy. The server sets an HttpOnly, SameSite=Strict loopback session cookie. It returns a short-lived ticket in a no-store response; the ticket is sent in the first binary message and never placed in a URL or persistent browser storage. The WebSocket must carry the exact allowed Origin and the matching session cookie. A ticket is bound to that cookie, expires after 15 seconds, and can be consumed once.

| Type | Direction | Payload |
|---:|---|---|
| `0x01` | client → server: Join | `ticket:bytes[32]`. All-zero tickets are invalid. The server resolves the owning session; the client cannot choose a player ID. |
| `0x02` | client → server: Input | `epoch:u32`, `sequence:u32`, `x:i16`, `z:i16`. Epoch/sequence are nonzero; axes are `[-32767,32767]`, with `-32768` rejected. Total 12 bytes. |
| `0x03` | client → server: Action | `epoch:u32`, `sequence:u32`, `action:u8`. Attack `1`, Arc Slash `2`, dodge `3`. Total 9 bytes. |
| `0x81` | server → client: Welcome | `player_id:u32`, `epoch:u32`, `tick:u64`, `x:f32`, `z:f32`. Coordinates are finite and within world bounds. Total 24 bytes. No credential is returned. |
| `0x82` | server → client: Snapshot | `tick:u64`, player/monster/event counts, zero reserved byte, then the fixed-width records described in [v2's record table](binary-v2.md#message-types). Counts remain capped at 16/64/64. |
| `0x83` | server → client: Error | `code:u16`; same bounded error enum as v2. Invalid, expired, replayed or wrong-session tickets return generic `invalid_join`. |

Session IDs and join tickets are independent 256-bit OS-generated random values. The cookie is server-only to JavaScript; the ephemeral ticket stays in memory only until the Join frame is sent. A fresh ticket from the same cookie reconnects the same in-memory player during the 30-second world resume grace period and advances its epoch. One live WebSocket is allowed per session.

The loopback server accepts only Origin `http://127.0.0.1:5173`. Missing, `null`, alternate-host and foreign Origins are rejected before upgrade. Session creation and ticket issuance are rate-limited. Join must arrive within 5 seconds; established sockets close after 120 seconds without inbound activity, and each connection is capped at 60 inbound messages per second. These controls are local-prototype safeguards, not public Internet authentication or a production deployment contract.

## Record validation and golden bytes

V3 keeps the v2 fixed-width snapshot records and semantic checks: IDs are nonzero, HP does not exceed max HP, coordinates are finite and within bounds, boolean bytes are only `0` or `1`, monster/action IDs are known, and counts/reserved fields are valid. The shared [v3 golden corpus](golden-v3.json) includes a full player+monster+event snapshot with event ID `9007199254740993`; the JavaScript client preserves it as `bigint`.

Rust rejects every shorter prefix of each client golden packet; the TypeScript decoder rejects every shorter prefix of each server golden packet. Protocol and ticket errors never log the cookie or ticket. This covers local wire compatibility and admission invariants only; persistence, account identity, TLS, multi-host operation, load capacity and public deployment remain out of scope.
