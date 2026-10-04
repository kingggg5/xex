# Competitor teardown — Lumivara Online (read 2026-09-29)

Source: supplied teardown text describes a Thai browser MMO patch-notes page and claims 764 updates.
An exact source URL, captured entries and retention data were not supplied; those claims are unverified here.
Read the observations as product hypotheses and candidates for usability tests, not demonstrated retention effects.
Everything below is a mechanic or an interaction pattern written in our own words. No art, text, data, names or code
from that project enters this repository, and the ban on Ragnarok Online names, maps, art and client data in
[browser_ragnarok_babylon_rust_10k_plan_v5.md](browser_ragnarok_babylon_rust_10k_plan_v5.md) §3 covers their
RO-derived naming too.

## What their update stream actually shows

- They ship **small, legible changes constantly** and write every one in plain player language, in Thai, with the
  consequence stated ("what changes for you", "what stays the same"). The changelog itself is a retention feature.
- Roughly half of the recent entries are **quality-of-life and UI polish**, not content. Rarity borders in storage,
  unread counts on party and guild chat tabs, a settings toggle for screen shake, chat history surviving a refresh.
- A visible slice is **fixing damage caused by their own architecture**: server clock drift making cooldowns read
  ~2000 s, a congested channel mis-timing buffs and respawns, a warp that bounced the player back, chat history drawn
  twice on reconnect. We have the same class of bug open in [2026-09-25-deep-review.md](reviews/historical-visual-reviews.md#deep-review-20260925).
- Balance is communicated as **player-facing arithmetic**, not patch jargon: monster damage cut to about half above
  Lv.100, dodge as a formula with a stated cap, two-handed weapons doubling weapon stats.
- They treat **transparency as a feature**: a public page listing every vote and who cast it, published box odds, an
  hourly notice telling players exactly what a future reset keeps and what it wipes.

## Copy — ranked by value to us

| # | Pattern | Why it matters | Where it lands |
|---|---|---|---|
| 1 | **Per-job equipment sets** — gear stays parked on the job that wore it, switching jobs re-equips instantly, other jobs' items are visible but locked | Removes the worst friction in a multi-class MMO; it is why their "Preset 1·2·3" buttons could be deleted | M3.1 |
| 2 | **A written changelog per change, in player language** | Cheapest retention and trust tool that exists; also forces honest scope | Start now, M1.1 |
| 3 | **Chat that behaves like a messenger** — per-tab unread counts, whisper/party/guild/map tabs, history surviving refresh, stored per character | Social stickiness; ours has chat but no unread state or history | M2.5 |
| 4 | **Rarity borders everywhere** (bag, storage, trade, inspect) and one visual grammar shared by every item surface | Reading gear at a glance is most of an MMO's UI | M2.5 |
| 5 | **Item cards that state the result, not the rule** — "+7 → ATK +17 (already included)" | Removes the wiki tax; our refine and equip UI needs exactly this | M2.5 |
| 6 | **Guild window split: overview / members / benefits** with contribution columns and a level table | Guild retention comes from visible contribution | M3.5 |
| 7 | **Inspect another player** using the same layout as your own equipment screen | Aspiration drives progression; nearly free once the equip screen exists | M3.1 |
| 8 | **Boss per channel per map, fixed respawn window, random nest** | Predictable enough to plan, random enough to hunt | M3.2 |
| 9 | **Full keybind remapping + gamepad support** with a sane default pad layout | Candidate for input/accessibility work; estimate after keyboard, touch, focus-loss and controller tests are scoped | M2.5 |
| 10 | **Comfort settings** — screen-shake off, effect density, damage-number density | Accessibility and low-end performance in one switch | M1.5, M2.5 |
| 11 | **Guest play, then an explicit confirm before binding to a Google account**, showing the e-mail and the character | Their own bug report shows what happens without the confirm step; we ship accounts in Q4 | M4.1 |
| 12 | **Occlusion fade** — buildings, statues and trees go translucent when they hide the player | Directly relevant to a dense city on a small screen | M2.1 |
| 13 | **Monster life**: walk cycles matched to travel speed, wider idle wander, occasional emotes | Cheap perceived quality; our monsters are static by comparison | M3.2 |
| 14 | **NPC placement as a readability problem** — moving vendors into distinct plazas, click-from-distance auto-walk | Our city has the same job ahead of it | M2.1 |
| 15 | **A public wiki and monster book generated from live data** | Ours can generate from `content/build` for free | M3.6 |

## Copy with a decision first

- **Auto-battle / bot mode.** Their bot is a first-class system with its own patch notes (skill priority by cooldown,
  instant retarget, auto-unlock when returning to town). In this market it is close to mandatory, and it decides the
  shape of the whole game: combat must be worth watching, and the economy must survive unattended farming. Answer it
  as a design decision before Q3, not as a feature request during it. It contradicts nothing in our exclusions.
- **Voting on live decisions**, paid for with soft currency. Strong trust signal, and it needs moderation rules,
  a quorum, and a written promise about which decisions are ever put to a vote.
- **Dual currency (hard + soft) with a premium tier.** Our monetization is undecided (D-19). Their model is a cash
  shop plus premium days plus a Gold market — legal to imitate structurally, but it commits us to payments, tax,
  refunds and a support queue. Decide before building anything in Q4.

## Do not copy

- **Any asset, sprite, icon, map, UI art, string or database row** from that game, and no scraping of their pages.
  Mechanics are not protectable; their expression is.
- **Their RO-derived naming** (stat abbreviations, item and skill names, monster names, town names). We use our own.
- **Random boxes as a revenue line.** Their headline item is a 1-in-100,000 box drop. Our plan already bans gacha and
  paid random boxes; a drop-only box with published odds is the most we should consider, and only with the odds shown.
- **A server-wide wipe as a launch plan.** They are running a test server that will reset levels, items and guilds
  while carrying paid currency over. That is a promise we cannot keep cheaply and it caps early retention.
- **Their update cadence as a target.** Several updates a day is a two-person-plus operation with no art pipeline in
  the loop; matching it solo would stop the world build dead.
- **Their channel/instance model** (20 fixed channels with per-channel bosses and per-channel clocks) — it is the
  source of several of their own bugs, and our AOI work in M1.3 is the better answer to the same crowding problem.

## What this changes in our plan

Nothing in the quarter order changes. It sharpens three things:

1. **Q2's UI pass gets a concrete target**: item cards that state results, rarity grammar everywhere, messenger-grade
   chat, keybinds and gamepad, comfort toggles. That is the whole list above, and it is achievable in one pass.
2. **Per-job equipment sets become a Q3 requirement**, not a nice-to-have, and it should be designed before the second
   vocation exists rather than retrofitted.
3. **Two owner decisions move earlier**: auto-battle (design-defining) and monetization (D-19), both needed before Q3
   content starts, not at Q4.

The supplied observations suggest useful hypotheses around communication, chat and equipment clarity.
Our implementation prioritizes the authored 3D world, streaming/LOD and classic MMO progression.
Competitor speed, technical limitations and retention advantages need primary evidence before being treated as facts.
