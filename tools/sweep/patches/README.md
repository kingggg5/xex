# Root-only tick-profile integration proposal

Nothing here is applied to `apps/server`. `tick_profile.rs` is compiled by this
crate's tests; the integrator owns server wiring and runtime validation.

Apply `tick-profile-hook.patch`, then connect `TickProfile` as follows:

1. Only when `AETHERFIELD_SWEEP_PROFILE=1`, construct one `TickProfile::new(channel)`
   for each of the 20 normal rooms **in the channel-creation loop**. Pass the
   same clone to its `RoomHandle` and `WorldServices`. Do not assign channel
   identities from world-thread start order. Towers need separate identities;
   do not aggregate 500 private instances into the channel's profile.
2. In `room.rs::world_loop`, use the existing `work_started`. Capture a commands
   span immediately before `world.advance()`, an advance span immediately after,
   and a publish/encode span through the existing `metrics.record_work` call.
   Record all three plus the total, excluding `interval.tick().await`. Convert
   Tokio's `work_started` with `.into_std()` for this module's `std::time::Instant`.
   Optional
   profiles must impose no sample allocations when disabled.
3. Add opt-in **loopback-only** `GET /__sweep/profile?channel=N`. Keep Origin
   validation, verify remote socket address is loopback, return `Cache-Control:
   no-store`, bound channel to 0..19 and the run token to 64 safe characters.
   No auth, session, simulation or admission changes belong to this patch.
4. Baseline: return `profile.window(None, "")`. Final request adds `after=<end_seq>`
   and `run_token=<label>`; return `window(Some(after), token)`. Return HTTP 409
   for a missing room, an invalid marker or an evicted window. Never silently
   substitute the latest N samples. Queue capacity is 4096 samples per room;
   intervals longer than about 204s require a larger reviewed cap or a shorter
   scenario. Mutex sampling overhead must be measured with the hook disabled/on.
5. Root verifies disabled endpoint, off/on overhead, bounds, CPU/wall units,
   exact-window loss rejection and 500 admitted bots. `cpu_ms` means elapsed
   owner work; it is not OS process CPU consumption. Profile scopes only the
   selected normal room; dungeon instance timing remains unverified.

The sweep's adapter validates schema, room and process-instance identity,
sequence coverage, finite ordered percentiles and run token before copying
profile data into ledger frame columns. RTT is never substituted for tick time.
