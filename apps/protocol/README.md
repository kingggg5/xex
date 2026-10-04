# Local room protocol artifacts

- [Current binary WebSocket protocol v6](binary-v6.md) and [golden byte fixtures](golden-v6.json): hot binary path with room-clock cooldown deadlines, tagged-JSON cold operation deadlines, per-type rate budgets, and content identity. v6 rejects v2–v5 packets; TypeScript and Rust consume the shared corpus.
- [Archived protocol v5](binary-v5.md) and [golden corpus](golden-v5.json): retained for the movement acknowledgement anchor revision.
- [Archived protocol v4](binary-v4.md) and [golden corpus](golden-v4.json): retained to trace the V5-02 revision.
- [Historical binary protocol v3](binary-v3.md) and [v3 fixtures](golden-v3.json): retain the session/Origin slice evidence.
- [Historical binary protocol v2](binary-v2.md) and [v2 fixtures](golden-v2.json): retain the original local codec evidence.
- [Coordinate fixture v1](coordinate-fixture-v1.json): shared meter/axis and geometry source for Babylon bounds and Rust/client movement collision.

The WebSocket room binds to loopback and remains a local prototype. Version 6 rejects v2–v5 packets, malformed/oversized messages, missing/foreign Origins, and unauthenticated or replayed join tickets. The anonymous session cookie is volatile and not an account identity; durable state and public deployment remain future gates.
