# `xexoria.dungeon/1` (D0 proposal)

This is a normative authoring schema, not an installed validator or a live content
registration. Every field below is required; reject unknown fields when D1 adds
the validator. The accompanying temple is a placeholder on an 8 m grid. Its
manifest, enemy, puzzle, reward and localisation references are deliberately
unresolved; do not admit it to the built bundle until Claude replaces and validates
them. No content manifest or protocol hash is changed by D0.

## Types and limits

`id`/local refs: 1–64 ASCII letters, digits or underscores. `name_key`: 1–128
characters, localisation key. `content_version`: immutable 1–128 character
version token; change it whenever package, collision, spawn or encounters change.
Paths are relative to the content delivery root, at most 256 characters; reject
absolute paths, URL schemes, `..`, backslashes and query strings. All numbers are
finite; counts and bytes are safe nonnegative integers. Distances are metres.
Coordinates are `[x,y,z]`, Y up, in the project's runtime coordinates (no Blender
axis conversion at runtime). Facing is radians, the wire angle convention `atan2(dx, dz)`: 0 faces +Z, π/2 faces +X
(client `lastFacing = atan2(move.x, move.z)`, server `monster.facing = dx.atan2(dz)`;
corrected by Claude review 2026-10-01). Normalise to `[0,2π)` at admission; existing
NPC content still stores some negative angles such as −1.5708. Outdoor and dungeon coordinates are
different spaces. Position/bounds must remain within ±4096 m and match the
authoritative zone's admitted bounds, traversal and collision version.

| Required field | Shape / validation |
|---|---|
| `schema` | Exactly `"xexoria.dungeon/1"` |
| `id` | Stable dungeon content ID |
| `name_key` | Localisation key; admission requires Thai and English entries |
| `overworld_entrance` | `{zone_ref, position, radius, facing}`; radius >0 and ≤32 m; validate actual player range on the server |
| `package` | `{manifest_path, critical_bytes_budget}`; positive budget ≤12,582,912 bytes (12 MiB initial authoring target) |
| `spawn` | `{room_id, position, facing}`; inside referenced room, collision-clear and navigation-reachable with character clearance |
| `return_portal` | `{room_id, position, radius, facing, availability, destination}`; `availability:"always"`; destination `{zone_ref,position,facing}` is an authoritative safe outdoor egress |
| `rooms` | 1–32 `{id,bounds,encounter_refs}`; bounds `{min:[x,y,z],max:[x,y,z]}`, min < max on every axis; ≤16 encounter refs per room |
| `encounters` | 1–64 `{id,room_id,kind,content_ref,spawn_positions}`; kind `combat`, `puzzle` or `boss`; 0–16 positions inside room bounds |
| `boss` | `{id,encounter_ref,content_ref}`; reference an encounter with kind `boss`; entity/tuning refs agree |
| `rewards` | `{authority,trigger_encounter_ref,table_ref,dedupe_scope}`; authority `server`; trigger is the boss encounter; scope exactly `instance_encounter_character` |
| `content_version` | Immutable package/gameplay identity, not a mutable display name |

IDs in each array must be unique. Encounter/room references must resolve locally;
each encounter belongs to exactly one room, and that room lists it exactly once.
Spawn/portal room refs must resolve. Validate geometry, collision, terrain height,
navigation and package hashes against the same content version at admission.
The manifest lists critical dependencies, their exact transfer sizes and hashes,
and traversal identity; enforce the total bytes budget before loading. The 5–12
MiB target is compressed transfer size, not decoded/GPU memory.

## Placeholder and reward semantics

The temple uses 8 m grid positions and room bounds, including height 0 and ceilings
at 8 m. These values establish no walkability evidence. The two combat rooms,
pressure-plate gate and guardian encounter are references to future server-authored
content, not working puzzle or combat rules. The return portal stays available
independently of boss progress; the adapter must also provide a reconnect egress.
Party size, difficulty, keys, lockouts, exact drops and payout amounts are owner
choices and intentionally absent.

Rewards use a durable server ledger keyed by `(instance_id, encounter_id,
character_id)`; the transfer ID is not a loot entitlement. Encounter victory,
reward inventory/wallet mutation and ledger insert are one authoritative durable
transaction. Duplicate claims and reconnects replay the original award. D0 writes
no ledger and grants no reward.
