mod community_runtime;
mod mage_runtime;
mod durable_guard;
#[cfg(test)]
mod mage_tests;
#[cfg(test)]
mod go_server_tests;
static STORE_OWNERS:std::sync::atomic::AtomicU64=std::sync::atomic::AtomicU64::new(1);
use crate::character::{CharacterRecord, SharedCharacterStore};
use crate::cold::{
    BagEntry, BoxOpenRequest, CharacterStateMsg, CosmeticsEquipRequest, OpResultMsg, QuestStateMsg,
    StoreBuyRequest, UseItemRequest,
};
use crate::content::Content;
use crate::content::{ExpTrack, VocationStats};
use crate::coordinate_fixture::{
    CoordinateFixture, StaticCollider, capsule_position_is_clear, move_capsule,
};
use crate::grounded_city::{GroundedCity, Position};
use crate::storage::{Checkpoint, JoinCharacter, LedgerEntry, StorageEvent, StorageHandle};
use serde::Deserialize;
use std::{
    collections::{BTreeMap, BTreeSet, HashMap, VecDeque},
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::sync::mpsc;

pub const MAX_PLAYERS: usize = 500;
pub const MAX_MONSTERS: usize = 64;
/// Global half-second event pool; wire/AOI still caps each viewer at 64.
pub const MAX_RECENT_EVENTS: usize = 8192;
pub const RESUME_GRACE: Duration = Duration::from_secs(30);
/// Power-buff kinds (v6 batch): attack multiplier, move-speed multiplier.
pub const BUFF_ATK: u8 = 0;
pub const BUFF_SPEED: u8 = 1;
/// Snapshot pet-record cap (v6 pet batch); one follower per player at most.
pub const MAX_PETS: usize = 500;
/// Tower instances keep their compact arena boundary when the field expands.
const TOWER_WORLD_HALF_EXTENT: f32 = 28.0;
const FIXED_DT: f32 = 0.05;
/// Inputs queued per player; the world applies exactly one per tick.
const MAX_QUEUED_INPUTS: usize = 3;
/// Ticks a missing input is repeated before the player stops.
const MAX_INPUT_REPEAT: u8 = 5;
const SPAWN_SLOTS_PER_ROW: usize = 4;
const SPAWN_ORIGIN_Z: f32 = -3.0;
const SPAWN_SPACING_X: f32 = 2.0;
const SPAWN_SPACING_Z: f32 = 1.5;
const P1_QUEST_ID: &str = "three_windmarks";
const P1_QUEST_OBJECTIVES: &[&str] =
    &["windmark", "windmark_1", "windmark_2", "windmark_3", "hunt"];
/// Ticks (~2 s at 20 Hz) between a full tower clear and the next floor spawn.
const TOWER_ADVANCE_TICKS: u64 = 40;
/// Tower monsters spawn on a ring of this radius around the arena center.
const TOWER_ARENA_RADIUS: f32 = 8.0;
/// Ticks (2s) between bounded retries of a durable save that failed while the
/// database was unreachable (plan §12.4: "retries are bounded").
const DURABLE_RETRY_TICKS: u64 = 40;
/// The entitlement cycle for P1 quest claims (once per character).
const P1_ENTITLEMENT_CYCLE: &str = "p1";
/// Ground drops live for 60 s (1200 ticks) before despawning.
const DROP_TTL_TICKS: u64 = 1200;
/// Per-world drop cap; the oldest drop despawns when exceeded.
const MAX_DROPS: usize = 32;
/// Pickup reach in meters (walk-over range).
const DROP_PICKUP_RANGE: f32 = 2.0;

/// Tower instance lifecycle: fighting a floor, the cleared-floor grace, then
/// complete (top floor cleared; the instance is torn down by the watcher).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TowerPhase {
    Fighting,
    Cleared,
    Complete,
}

/// Per-instance tower state. The instance is bound to one session, holds the
/// current floor, and reports floor milestones (used to persist best_floor).
#[derive(Debug)]
struct TowerRuntime {
    session: [u8; 32],
    floor: u16,
    phase: TowerPhase,
    /// Tick at which a cleared floor advances to the next one.
    advance_at_tick: u64,
    /// Set when the instance must be torn down: the tower is complete or the
    /// bound session abandoned it. Consumed once by `take_tower_completed`.
    done: bool,
    done_taken: bool,
    table: crate::content::TowerTable,
    enemy: crate::content::EnemyTuning,
}

#[derive(Debug, Clone)]
struct CombatTuning {
    attack_range: f32,
    attack_damage: u16,
    attack_cooldown: Duration,
    arc_range: f32,
    arc_damage: u16,
    arc_cooldown: Duration,
    dodge_cooldown: Duration,
    dodge_cooldown_ticks: u64,
    dodge_duration_steps: u32,
    dodge_mult: f32,
    guard_cooldown: Duration,
    guard_cooldown_ticks: u64,
    guard_max_hold_ticks: u64,
    guard_perfect_ticks: u64,
    guard_reduction_pct: u8,
}

#[derive(Debug, Deserialize)]
struct RouteBundle {
    npcs: BTreeMap<String, RouteNpc>,
    quests: BTreeMap<String, RouteQuest>,
    zones: Vec<RouteZone>,
    /// Authored economy table (D-14); absent until the content pipeline ships
    /// it. Captured raw and parsed leniently by [`Economy::from_bundle`] so a
    /// schema drift degrades to defaults instead of failing the load.
    #[serde(default)]
    economy: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize, Clone)]
struct RouteNpc {
    zone: u16,
    x: f32,
    z: f32,
    radius: f32,
    dialogue: String,
}

#[derive(Debug, Deserialize, Clone)]
struct RouteQuest {
    giver: String,
    objectives: Vec<RouteObjective>,
    reward_exp: u32,
    reward_items: Vec<RouteReward>,
}

#[derive(Debug, Deserialize, Clone)]
struct RouteObjective {
    id: String,
    kind: String,
    #[serde(default)]
    target: Option<String>,
    count: u32,
    #[serde(default)]
    distinct: bool,
}

#[derive(Debug, Deserialize, Clone)]
struct RouteReward {
    def: String,
    count: u8,
}

// ---------------------------------------------------------------------------
// Session economy (D-14). In-memory only: everything resets on restart until
// V5-13 makes the economy durable.
//
// The authored table ships as `content/source/economy.json` and reaches the
// world through the canonical bundle's `economy` object (`Content.economy`
// exposes the same table typed). The reader below is deliberately lenient —
// every field is read independently from the raw JSON and anything missing or
// malformed falls back to its default, so the session economy still works if
// the table drifts. Authored shape (unknown keys are ignored):
//
// "economy": {
//   "starting": { "gold": 250, "coin": 10 },
//   "kill_gold": 5, "quest_claim_gold": 100, "duplicate_cosmetic_coin": 25,
//   "skins": { "skin_crimson": { "tunic": "#a83a4e" }, ... },
//   "pets":  { "pet_sprout": { "tint": "#8fd06a" }, ... },
//   "store": [ { "item": "trail_potion", "currency": "gold", "price": 25 },
//              { "item": "meadow_box", "currency": "gold", "price": 60 },
//              { "cosmetic": "skin_crimson", "currency": "gold", "price": 120 } ],
//   "boxes": { "meadow_box": { "table": [
//              { "weight": 30, "gold": 15 },
//              { "weight": 15, "item": "dew_bead", "min": 1, "max": 3 },
//              { "weight": 10, "cosmetic": "skin_rose" },
//              { "weight": 10, "coin": 20 } ] } }
// }
// ---------------------------------------------------------------------------

const DEFAULT_START_GOLD: u32 = 250;
const DEFAULT_START_COIN: u32 = 10;
const DEFAULT_KILL_GOLD: u32 = 5;
const DEFAULT_QUEST_CLAIM_GOLD: u32 = 100;
const DEFAULT_DUPLICATE_COSMETIC_COIN: u32 = 25;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Currency {
    Gold,
    Coin,
}

impl Currency {
    fn parse(value: Option<&str>) -> Currency {
        match value {
            Some("coin") => Currency::Coin,
            _ => Currency::Gold,
        }
    }

    fn grant_key(self) -> &'static str {
        match self {
            Currency::Gold => "gold",
            Currency::Coin => "coin",
        }
    }
}

#[derive(Debug, Clone)]
struct StoreEntry {
    /// Bag item, cosmetic or box def id (matched exactly as authored).
    id: String,
    /// True when the entry sells a cosmetic (`cosmetic` key in the table);
    /// the purchase lands in owned_cosmetics instead of the bag.
    cosmetic: bool,
    currency: Currency,
    price: u32,
    count: u8,
}

/// One outcome of a box's weighted table (D-14). Exactly one branch is set.
#[derive(Debug, Clone, PartialEq, Eq)]
enum RollOutcome {
    Gold(u32),
    Coin(u32),
    /// A bag item grant; the stack count is drawn uniformly from
    /// `[min, max]` (authored tables use min == max for fixed stacks).
    Item {
        id: String,
        min: u8,
        max: u8,
    },
    Cosmetic(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BoxRoll {
    weight: u32,
    outcome: RollOutcome,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BoxDef {
    id: String,
    /// Purchase price/currency live on the store entry that lists the box;
    /// opening an owned box is free.
    rolls: Vec<BoxRoll>,
}

/// Resolved session economy defaults plus whatever the bundle supplied.
#[derive(Debug, Clone)]
struct Economy {
    start_gold: u32,
    start_coin: u32,
    kill_gold: u32,
    quest_claim_gold: u32,
    duplicate_cosmetic_coin: u32,
    cosmetics: Vec<String>,
    store: Vec<StoreEntry>,
    boxes: Vec<BoxDef>,
}

impl Default for Economy {
    fn default() -> Self {
        Self {
            start_gold: DEFAULT_START_GOLD,
            start_coin: DEFAULT_START_COIN,
            kill_gold: DEFAULT_KILL_GOLD,
            quest_claim_gold: DEFAULT_QUEST_CLAIM_GOLD,
            duplicate_cosmetic_coin: DEFAULT_DUPLICATE_COSMETIC_COIN,
            cosmetics: Vec::new(),
            store: Vec::new(),
            boxes: Vec::new(),
        }
    }
}

impl Economy {
    /// Read the economy table defensively out of the canonical bundle value.
    fn from_bundle(value: Option<&serde_json::Value>) -> Self {
        let Some(fields) = value.and_then(serde_json::Value::as_object) else {
            return Self::default();
        };
        let u32_field = |key: &str| {
            fields
                .get(key)
                .and_then(serde_json::Value::as_u64)
                .and_then(|number| u32::try_from(number).ok())
        };
        // Wallet seeds: nested `starting` object first, flat keys as fallback.
        let starting = fields
            .get("starting")
            .and_then(serde_json::Value::as_object);
        let starting_u32 = |key: &str| {
            starting
                .and_then(|start| start.get(key))
                .and_then(serde_json::Value::as_u64)
                .and_then(|number| u32::try_from(number).ok())
        };
        // Cosmetic ids: the keys of the `skins`/`pets` tables, plus an
        // optional flat `cosmetics` array for tolerance.
        let mut cosmetics = fields
            .get("cosmetics")
            .and_then(serde_json::Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(serde_json::Value::as_str)
                    .map(str::to_string)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        for table in ["skins", "pets"] {
            if let Some(definitions) = fields.get(table).and_then(serde_json::Value::as_object) {
                cosmetics.extend(definitions.keys().cloned());
            }
        }
        let store = fields
            .get("store")
            .and_then(serde_json::Value::as_array)
            .map(|items| items.iter().filter_map(parse_store_entry).collect())
            .unwrap_or_default();
        // Boxes: an object keyed by box id, or an array of entries carrying
        // their own `id`.
        let boxes = match fields.get("boxes") {
            Some(serde_json::Value::Object(map)) => map
                .iter()
                .filter_map(|(id, definition)| parse_box_def(Some(id), definition))
                .collect(),
            Some(serde_json::Value::Array(items)) => items
                .iter()
                .filter_map(|definition| parse_box_def(None, definition))
                .collect(),
            _ => Vec::new(),
        };
        Self {
            start_gold: starting_u32("gold")
                .or(u32_field("start_gold"))
                .unwrap_or(DEFAULT_START_GOLD),
            start_coin: starting_u32("coin")
                .or(u32_field("start_coin"))
                .unwrap_or(DEFAULT_START_COIN),
            kill_gold: u32_field("kill_gold").unwrap_or(DEFAULT_KILL_GOLD),
            quest_claim_gold: u32_field("quest_claim_gold").unwrap_or(DEFAULT_QUEST_CLAIM_GOLD),
            duplicate_cosmetic_coin: u32_field("duplicate_cosmetic_coin")
                .unwrap_or(DEFAULT_DUPLICATE_COSMETIC_COIN),
            cosmetics,
            store,
            boxes,
        }
    }

    fn is_cosmetic(&self, id: &str) -> bool {
        self.cosmetics.iter().any(|cosmetic| cosmetic == id)
    }

    fn store_entry(&self, id: &str) -> Option<&StoreEntry> {
        self.store.iter().find(|entry| entry.id == id)
    }

    fn box_def(&self, id: &str) -> Option<&BoxDef> {
        self.boxes.iter().find(|def| def.id == id)
    }
}

fn parse_store_entry(value: &serde_json::Value) -> Option<StoreEntry> {
    let fields = value.as_object()?;
    // The authored table marks cosmetic sales with the `cosmetic` key; items
    // and boxes use `item` (an `id` alias is tolerated).
    let item = fields.get("item").and_then(serde_json::Value::as_str);
    let cosmetic = fields.get("cosmetic").and_then(serde_json::Value::as_str);
    let id = item
        .or(cosmetic)
        .or_else(|| fields.get("id").and_then(serde_json::Value::as_str))?;
    Some(StoreEntry {
        id: id.to_string(),
        cosmetic: item.is_none() && cosmetic.is_some(),
        currency: Currency::parse(fields.get("currency").and_then(serde_json::Value::as_str)),
        price: u32_at(fields, "price")?,
        count: u8_at(fields, "count").unwrap_or(1).max(1),
    })
}

fn parse_box_def(id: Option<&str>, value: &serde_json::Value) -> Option<BoxDef> {
    let fields = value.as_object()?;
    let id = id
        .map(str::to_string)
        .or_else(|| {
            fields
                .get("id")
                .and_then(serde_json::Value::as_str)
                .map(str::to_string)
        })
        .or_else(|| {
            fields
                .get("item")
                .and_then(serde_json::Value::as_str)
                .map(str::to_string)
        })?;
    Some(BoxDef {
        id,
        rolls: fields
            .get("table")
            .or_else(|| fields.get("rolls"))
            .and_then(serde_json::Value::as_array)
            .map(|items| items.iter().filter_map(parse_box_roll).collect())
            .unwrap_or_default(),
    })
}

fn parse_box_roll(value: &serde_json::Value) -> Option<BoxRoll> {
    let fields = value.as_object()?;
    // Outcome precedence when several keys are present: gold, coin, cosmetic,
    // then a bag item. Item stacks use `min`/`max` (or a fixed `count`).
    let outcome = if let Some(gold) = u32_at(fields, "gold") {
        RollOutcome::Gold(gold)
    } else if let Some(coin) = u32_at(fields, "coin") {
        RollOutcome::Coin(coin)
    } else if let Some(cosmetic) = fields.get("cosmetic").and_then(serde_json::Value::as_str) {
        RollOutcome::Cosmetic(cosmetic.to_string())
    } else if let Some(item) = fields
        .get("item")
        .or_else(|| fields.get("id"))
        .and_then(serde_json::Value::as_str)
    {
        let min = u8_at(fields, "min")
            .or_else(|| u8_at(fields, "count"))
            .unwrap_or(1)
            .max(1);
        let max = u8_at(fields, "max")
            .or_else(|| u8_at(fields, "count"))
            .unwrap_or(min)
            .max(min);
        RollOutcome::Item {
            id: item.to_string(),
            min,
            max,
        }
    } else {
        return None;
    };
    Some(BoxRoll {
        weight: u32_at(fields, "weight").unwrap_or(1),
        outcome,
    })
}

fn u32_at(fields: &serde_json::Map<String, serde_json::Value>, key: &str) -> Option<u32> {
    fields
        .get(key)
        .and_then(serde_json::Value::as_u64)
        .and_then(|number| u32::try_from(number).ok())
}

fn u8_at(fields: &serde_json::Map<String, serde_json::Value>, key: &str) -> Option<u8> {
    fields
        .get(key)
        .and_then(serde_json::Value::as_u64)
        .and_then(|number| u8::try_from(number).ok())
}

#[derive(Debug, Deserialize)]
struct RouteZone {
    id: u16,
    pois: BTreeMap<String, RoutePoint>,
}

#[derive(Debug, Deserialize, Clone, Copy)]
struct RoutePoint {
    x: f32,
    z: f32,
}

#[derive(Debug)]
struct DialogueSession {
    npc: String,
    token: String,
    expires_at: Instant,
}

#[derive(Debug, Clone)]
struct WindmarkChannel {
    marker: String,
    position: RoutePoint,
    start_x: f32,
    start_z: f32,
    ticks_left: u8,
}

#[derive(Debug)]
struct Party {
    leader: u32,
    members: BTreeSet<u32>,
    code: String,
    code_expires_at: Instant,
    revision: u32,
}

fn spawn_position(slot: usize) -> (f32, f32) {
    let lane = (slot % SPAWN_SLOTS_PER_ROW) as f32 - 1.5;
    let row = (slot / SPAWN_SLOTS_PER_ROW) as f32;
    (
        lane * SPAWN_SPACING_X,
        SPAWN_ORIGIN_Z - row * SPAWN_SPACING_Z,
    )
}

fn op_result(
    op_id: &str,
    status: &str,
    reason: &str,
    grants: Vec<crate::cold::GrantEntry>,
) -> OpResultMsg {
    OpResultMsg {
        t: "op_result".to_string(),
        op_id: op_id.to_string(),
        status: status.to_string(),
        reason: reason.to_string(),
        ends_at_ms: 0,
        grants,
    }
}

fn refresh_quest_state(player: &mut Player, targets: &BTreeMap<String, u32>) -> bool {
    if player.quest_state != "active"
        || !targets
            .iter()
            .all(|(id, target)| player.quest_objectives.get(id).copied().unwrap_or(0) >= *target)
    {
        return false;
    }
    player.quest_state = "ready_to_claim".to_string();
    true
}

/// Bag slot cap, single-sourced for the quest-claim and economy paths.
const BAG_CAPACITY: usize = 12;

/// The existing full-bag rule (quest-claim path): a grant only needs a new
/// slot when its def is not already stacked in the bag.
fn bag_has_room(bag: &BTreeMap<String, u8>, defs: &[&str]) -> bool {
    let new_slots = defs.iter().filter(|def| !bag.contains_key(**def)).count();
    bag.len() + new_slots <= BAG_CAPACITY
}

/// Shared op-id replay semantics for the economy ops: the same op_id with the
/// same request key replays the cached result; the same op_id with a
/// different key is a conflict.
fn replay_cached_op(
    cache: &VecDeque<(String, String, OpResultMsg)>,
    op_id: &str,
    key: &str,
) -> Option<OpResultMsg> {
    cache
        .iter()
        .find(|(cached_id, _, _)| cached_id == op_id)
        .map(|(_, cached_key, result)| {
            if cached_key == key {
                result.clone()
            } else {
                op_result(op_id, "rejected", "op_id_conflict", Vec::new())
            }
        })
}

fn remember_op(
    cache: &mut VecDeque<(String, String, OpResultMsg)>,
    op_id: String,
    key: String,
    result: &OpResultMsg,
) {
    cache.push_back((op_id, key, result.clone()));
    while cache.len() > 64 {
        cache.pop_front();
    }
}

/// V5-13: submit one cold op for durable recording. Called from the handlers
/// while `player` is mutably borrowed from `self.players` — hence a free
/// function over disjoint field borrows (players vs storage/zone_key/hash).
#[allow(clippy::too_many_arguments)]
fn submit_commit_op(
    storage: &StorageHandle,
    events: &mpsc::UnboundedSender<StorageEvent>,
    player: &Player,
    principal: crate::storage::PrincipalId,
    zone_key: &str,
    content_revision: u64,
    op_kind: &str,
    op_id: &str,
    request_key: &str,
    result: &OpResultMsg,
    entitlement: Option<(String, String)>,
    extra_ledger: Vec<LedgerEntry>,
) {
    let record = character_record_of(player);
    let checkpoint = Checkpoint {
        zone: zone_key.to_string(),
        x: player.x,
        z: player.z,
        hp: i32::from(player.hp),
    };
    // Grants carry item movements; wallet currencies are excluded and the
    // explicit extras carry consumed boxes/potions and claim EXP.
    let mut ledger: Vec<LedgerEntry> = result
        .grants
        .iter()
        .filter(|grant| {
            grant.def != Currency::Gold.grant_key() && grant.def != Currency::Coin.grant_key()
        })
        .map(|grant| LedgerEntry::Item {
            item: grant.def.clone(),
            delta: i64::from(grant.count),
        })
        .collect();
    ledger.extend(extra_ledger);
    storage.commit_op(
        principal,
        player.session_id,
        op_kind.to_string(),
        op_id.to_string(),
        request_key.to_string(),
        result.clone(),
        entitlement,
        ledger,
        record,
        Some(player.owner_epoch),
        Some(checkpoint),
        format!("{content_revision:016x}"),
        events,
    );
}

fn wallet_balance(player: &Player, currency: Currency) -> u32 {
    match currency {
        Currency::Gold => player.gold,
        Currency::Coin => player.coin,
    }
}

fn wallet_add(player: &mut Player, currency: Currency, amount: u32) {
    match currency {
        Currency::Gold => player.gold = player.gold.saturating_add(amount),
        Currency::Coin => player.coin = player.coin.saturating_add(amount),
    }
}

/// Spend from the wallet; callers check the balance first.
fn wallet_spend(player: &mut Player, currency: Currency, amount: u32) {
    match currency {
        Currency::Gold => player.gold = player.gold.saturating_sub(amount),
        Currency::Coin => player.coin = player.coin.saturating_sub(amount),
    }
}

/// Consume one stack entry of `id` from the bag (zero-count entries stay in
/// the map, mirroring the existing potion-use behavior).
fn consume_bag_item(player: &mut Player, id: &str) {
    if let Some(count) = player.bag.get_mut(id) {
        *count = count.saturating_sub(1);
    }
}

fn bump_state_revision(player: &mut Player) {
    player.inventory_valid=crate::inventory_instances::reconcile(&player.inventory_namespace,&mut player.inventory_schema,&mut player.item_instances,&player.bag,&player.equipment,&player.equipment_refine,&player.gear_slots).is_ok();
    player.state_revision = player.state_revision.wrapping_add(1).max(1);
}

/// Preflight the whole grant before changing stacks or creating per-piece IDs.
fn can_grant_items(player:&Player,items:&BTreeMap<String,u32>)->bool {
    player.inventory_valid && bag_has_room(&player.bag,&items.keys().map(String::as_str).collect::<Vec<_>>())
        && items.iter().all(|(id,n)|u32::from(player.bag.get(id).copied().unwrap_or(0)).checked_add(*n).is_some_and(|v|v<=99))
        && player.item_instances.len()+items.iter().filter(|(id,_)|player.gear_slots.contains_key(*id)).map(|(_,n)|*n as usize).sum::<usize>()<=crate::inventory_instances::MAX_INSTANCES
}

fn killer_id_session_of(players: &HashMap<u32, Player>, player_id: u32) -> [u8; 32] {
    players
        .get(&player_id)
        .map(|player| player.session_id)
        .unwrap_or([0; 32])
}

/// Snapshot the cross-instance slice of a player for the shared store.
/// Transient fields (position, hp, epoch, queues) are deliberately excluded.
/// `friends` is not carried: it is owned by the HTTP/social layer, and
/// `CharacterStore::save` preserves the stored list on publish.
/// E07 golden formulas (pinned by `e07_golden_formulas_hold`):
#[derive(Debug, Clone, Copy, Default)]
pub struct AllocatedStats {
    pub str_: u16,
    pub agi: u16,
    pub vit: u16,
    pub int_: u16,
    pub dex: u16,
    pub luk: u16,
}

/// STR/VIT grow +1 per `stat_growth_levels` base levels over the vocation
/// base + player allocated stats; ATK = base_attack + STR*2 + DEX/5 + LUK/5 + weapon_atk + weapon_refine_atk + (job_level - 1);
/// MAXHP = vocation_hp + VIT*10 + armor_hp + armor_refine_hp; DEF = armor_def + VIT/2 + armor_refine_def;
/// MAXSP = 30 + INT*5 + levels*2.
fn compute_derived(
    vocation: &VocationStats,
    vocation_hp: u16,
    base_level: u32,
    job_level: u32,
    equipment: &BTreeMap<String, String>,
    equipment_refine: &BTreeMap<String, u8>,
    items: &BTreeMap<String, crate::content::ItemTuning>,
    base_attack: u16,
    allocated: AllocatedStats,
) -> (u16, u16, u16, u16) {
    let growth = u32::from(vocation.stat_growth_levels).max(1);
    let levels = base_level.saturating_sub(1);
    let str_ = u32::from(vocation.stats.str_) + levels / growth + u32::from(allocated.str_);
    let vit = u32::from(vocation.stats.vit) + levels / growth + u32::from(allocated.vit);
    let mut weapon_atk = 0_u16;
    let mut armor_def = 0_u16;
    let mut armor_hp = 0_u16;
    for slot in ["weapon", "armor"] {
        if let Some(item) = equipment.get(slot)
            && let Some(tuning) = items.get(item)
        {
            weapon_atk = weapon_atk.saturating_add(tuning.atk);
            armor_def = armor_def.saturating_add(tuning.def);
            armor_hp = armor_hp.saturating_add(tuning.hp);
        }
    }
    let weapon_refine = equipment_refine.get("weapon").copied().unwrap_or(0);
    let weapon_refine_atk = u16::from(weapon_refine).saturating_mul(5);
    let armor_refine = equipment_refine.get("armor").copied().unwrap_or(0);
    let armor_refine_def = u16::from(armor_refine).saturating_mul(2);
    let armor_refine_hp = u16::from(armor_refine).saturating_mul(25);

    let stat_atk = (str_ * 2)
        .saturating_add(u32::from(allocated.dex) / 5)
        .saturating_add(u32::from(allocated.luk) / 5);
    let atk = base_attack
        .saturating_add(stat_atk.min(u16::MAX as u32) as u16)
        .saturating_add(weapon_atk)
        .saturating_add(weapon_refine_atk)
        .saturating_add(u16::try_from(job_level.saturating_sub(1)).unwrap_or(u16::MAX));
    let max_hp = u32::from(vocation_hp)
        .saturating_add(vit * 10)
        .saturating_add(u32::from(armor_hp))
        .saturating_add(u32::from(armor_refine_hp))
        .min(u16::MAX as u32) as u16;
    let def = armor_def
        .saturating_add((vit / 2).min(u16::MAX as u32) as u16)
        .saturating_add(armor_refine_def);
    let max_sp = 30_u32
        .saturating_add(u32::from(allocated.int_).saturating_mul(5))
        .saturating_add(levels.saturating_mul(2))
        .min(u16::MAX as u32) as u16;
    (atk, def, max_hp, max_sp)
}

/// Recompute one player's derived stats in place after a level/equip change.
fn recompute_player_stats(
    player: &mut Player,
    vocation: &VocationStats,
    vocation_hp: u16,
    items: &BTreeMap<String, crate::content::ItemTuning>,
    base_attack: u16,
) {
    let (atk, def, max_hp, max_sp) = compute_derived(
        vocation,
        vocation_hp,
        player.level,
        player.job_level,
        &player.equipment,
        &player.equipment_refine,
        items,
        base_attack,
        AllocatedStats {
            str_: player.allocated_str,
            agi: player.allocated_agi,
            vit: player.allocated_vit,
            int_: player.allocated_int,
            dex: player.allocated_dex,
            luk: player.allocated_luk,
        },
    );
    player.atk = atk;
    player.def = def;
    let old_max = player.max_hp;
    player.max_hp = max_hp;
    if max_hp > old_max {
        player.hp = player.hp.saturating_add(max_hp - old_max).min(max_hp);
    } else {
        player.hp = player.hp.min(max_hp);
    }
    let old_max_sp = player.max_sp;
    player.max_sp = max_sp;
    if old_max_sp == 0 {
        player.sp = max_sp;
    } else if max_sp > old_max_sp {
        player.sp = player.sp.saturating_add(max_sp - old_max_sp).min(max_sp);
    } else {
        player.sp = player.sp.min(max_sp);
    }
}

fn character_record_of(player: &Player) -> CharacterRecord {
    CharacterRecord {
        inventory_schema: player.inventory_schema,
        inventory_namespace: player.inventory_namespace.clone(),
        item_instances: player.item_instances.clone(),
        death_revision: player.death_revision,
        down: player.down,
        reward_receipts: player.reward_receipts.clone(),
        reward_mail: player.reward_mail.clone(),
        mvp_rune_pity: player.mvp_rune_pity,
        generation: 0,
        cache_owner:0,
        community: player.community.clone(),
        gold: player.gold,
        coin: player.coin,
        level: player.level,
        exp: player.exp,
        job_level: player.job_level,
        job_exp: player.job_exp,
        equipment: player.equipment.clone(),
        state_revision: player.state_revision,
        bag: player.bag.clone(),
        pouch: player.pouch.clone(),
        skin: player.skin.clone(),
        pet: player.pet.clone(),
        owned_cosmetics: player.owned_cosmetics.clone(),
        quest_revision: player.quest_revision,
        quest_id: player.quest_id.clone(),
        quest_state: player.quest_state.clone(),
        quest_objectives: player.quest_objectives.clone(),
        quest_step_ticks: player.quest_step_ticks.clone(),
        activated_windmarks: player.activated_windmarks.clone(),
        handle: player.handle.clone(),
        name: player.name.clone(),
        // Friends are the HTTP/social layer's field: the publish carries none
        // and `CharacterStore::save` preserves the stored list instead.
        friends: Vec::new(),
        item_operations: player.recent_item_operations.clone(),
        quest_operations: player.recent_quest_operations.clone(),
        store_operations: player.recent_store_operations.clone(),
        box_operations: player.recent_box_operations.clone(),
        equip_operations: player.recent_equip_operations.clone(),
        stat_points: player.stat_points,
        allocated_str: player.allocated_str,
        allocated_agi: player.allocated_agi,
        allocated_vit: player.allocated_vit,
        allocated_int: player.allocated_int,
        allocated_dex: player.allocated_dex,
        allocated_luk: player.allocated_luk,
        stat_operations: player.recent_stat_operations.clone(),
        equipment_refine: player.equipment_refine.clone(),
        refine_operations: player.recent_refine_operations.clone(),
    }
}

/// Adopt a shared record into a player: only the cross-instance fields move;
/// position, hp and connection state stay as the world holds them. `friends`
/// is skipped: worlds never read the contact list.
fn apply_character_record(player: &mut Player, record: &CharacterRecord) {
    let was_down=player.down;
    player.inventory_schema=record.inventory_schema;
    if !record.inventory_namespace.is_empty() {player.inventory_namespace=record.inventory_namespace.clone();}
    player.item_instances=record.item_instances.clone();
    player.death_revision = record.death_revision;
    player.down = record.down;
    if player.down { player.hp = 0; }
    else if was_down && player.hp==0 {player.hp=(player.max_hp/2).max(1);player.down_until_tick=0;}
    player.reward_receipts = record.reward_receipts.clone();
    player.reward_mail = record.reward_mail.clone();
    player.mvp_rune_pity = record.mvp_rune_pity;
    player.community = record.community.clone();
    player.community.ensure_season();
    player.gold = record.gold;
    player.coin = record.coin;
    player.level = record.level;
    player.exp = record.exp;
    player.job_level = record.job_level.max(1);
    player.job_exp = record.job_exp;
    player.equipment = record.equipment.clone();
    player.state_revision = record.state_revision.max(1);
    player.bag = record.bag.clone();
    player.pouch = record.pouch.clone();
    player.skin = record.skin.clone();
    player.pet = record.pet.clone();
    player.owned_cosmetics = record.owned_cosmetics.clone();
    player.quest_revision = record.quest_revision.max(1);
    player.quest_id = record.quest_id.clone();
    player.quest_state = record.quest_state.clone();
    player.quest_objectives = record.quest_objectives.clone();
    player.quest_step_ticks = record.quest_step_ticks.clone();
    player.activated_windmarks = record.activated_windmarks.clone();
    player.handle = record.handle.clone();
    player.name = record.name.clone();
    player.recent_item_operations = record.item_operations.clone();
    player.recent_quest_operations = record.quest_operations.clone();
    player.recent_store_operations = record.store_operations.clone();
    player.recent_box_operations = record.box_operations.clone();
    player.recent_equip_operations = record.equip_operations.clone();
    player.stat_points = record.stat_points;
    player.allocated_str = record.allocated_str;
    player.allocated_agi = record.allocated_agi;
    player.allocated_vit = record.allocated_vit;
    player.allocated_int = record.allocated_int;
    player.allocated_dex = record.allocated_dex;
    player.allocated_luk = record.allocated_luk;
    player.recent_stat_operations = record.stat_operations.clone();
    player.equipment_refine = record.equipment_refine.clone();
    player.recent_refine_operations = record.refine_operations.clone();
    player.inventory_valid=crate::inventory_instances::reconcile(&player.inventory_namespace,&mut player.inventory_schema,&mut player.item_instances,&player.bag,&player.equipment,&player.equipment_refine,&player.gear_slots).is_ok();
}

/// Integer weight walk over `rolls` for `value` reduced modulo the total
/// weight; no floating point anywhere in the box roll (D-14).
fn weighted_pick(rolls: &[BoxRoll], value: u64) -> Option<usize> {
    let total: u64 = rolls.iter().map(|roll| u64::from(roll.weight)).sum();
    if total == 0 {
        return None;
    }
    let mut point = value % total;
    for (index, roll) in rolls.iter().enumerate() {
        if point < u64::from(roll.weight) {
            return Some(index);
        }
        point -= u64::from(roll.weight);
    }
    None
}

/// Cryptographically random weighted pick: uniform u64 with rejection
/// sampling against the total weight, then the integer weight walk.
fn roll_weighted(rolls: &[BoxRoll]) -> Option<usize> {
    let total: u64 = rolls.iter().map(|roll| u64::from(roll.weight)).sum();
    if total == 0 {
        return None;
    }
    let limit = u64::MAX / total * total;
    loop {
        let mut bytes = [0_u8; 8];
        getrandom::fill(&mut bytes).ok()?;
        let value = u64::from_le_bytes(bytes);
        if value < limit {
            return weighted_pick(rolls, value);
        }
    }
}

/// Uniform integer draw in `[min, max]` (inclusive) from the crypto RNG;
/// integer-only, no floating point.
fn draw_u8_range(min: u8, max: u8) -> Option<u8> {
    if max <= min {
        return Some(min);
    }
    let span = u64::from(max) - u64::from(min) + 1;
    let limit = u64::MAX / span * span;
    loop {
        let mut bytes = [0_u8; 8];
        getrandom::fill(&mut bytes).ok()?;
        let value = u64::from_le_bytes(bytes);
        if value < limit {
            return Some(min + (value % span) as u8);
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActionKind {
    Attack,
    ArcSlash,
    Dodge,
    Guard,
    SplashHop,
}

pub mod monster_state {
    pub const IDLE: u8 = 0;
    pub const APPROACH: u8 = 1;
    pub const WINDUP: u8 = 2;
    pub const ACTIVE: u8 = 3;
    pub const RECOVERY: u8 = 4;
    pub const STAGGER: u8 = 5;
}

pub fn angle_diff(a: f32, b: f32) -> f32 {
    let diff = (a - b).rem_euclid(std::f32::consts::TAU);
    if diff > std::f32::consts::PI {
        std::f32::consts::TAU - diff
    } else {
        diff
    }
}

/// Why an action was rejected. Codes match `wire::reason`; variants activate
/// as their gameplay lands (Dead/Busy with V5-08 death/stagger, OutOfRange
/// with shape checks, RateLimited with per-ability budgets).
#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RejectReason {
    Cooldown,
    OutOfRange,
    NoTarget,
    Dead,
    Busy,
    NotAllowed,
    RateLimited,
}

impl RejectReason {
    pub fn code(self) -> u8 {
        match self {
            Self::Cooldown => crate::wire::reason::COOLDOWN,
            Self::OutOfRange => crate::wire::reason::OUT_OF_RANGE,
            Self::NoTarget => crate::wire::reason::NO_TARGET,
            Self::Dead => crate::wire::reason::DEAD,
            Self::Busy => crate::wire::reason::BUSY,
            Self::NotAllowed => crate::wire::reason::NOT_ALLOWED,
            Self::RateLimited => crate::wire::reason::RATE_LIMITED,
        }
    }
}

/// Map a validated cooldown duration onto the same room clock as snapshots.
fn cooldown_deadline(room_ms: u64, cooldown_ms: u16) -> u64 {
    if cooldown_ms == 0 {
        0
    } else {
        room_ms.saturating_add(u64::from(cooldown_ms))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ActionOutcome {
    pub accepted: bool,
    pub reason: u8,
    /// Absolute expiry in room-clock milliseconds (tick * 50); zero means none.
    pub ends_at_ms: u64,
}

impl ActionOutcome {
    pub fn accepted(ends_at_ms: u64) -> Self {
        Self {
            accepted: true,
            reason: crate::wire::reason::NONE,
            ends_at_ms,
        }
    }

    pub fn rejected(reason: RejectReason, ends_at_ms: u64) -> Self {
        Self {
            accepted: false,
            reason: reason.code(),
            ends_at_ms,
        }
    }
}

#[derive(Debug)]
pub struct Welcome {
    pub player_id: u32,
    pub epoch: u32,
    pub tick: u64,
    pub x: f32,
    pub z: f32,
    pub zone_id: u16,
    pub content_hash: u64,
    pub tick_hz: u8,
}

#[derive(Debug, Clone)]
pub struct PlayerSnapshot {
    pub id: u32,
    pub x: f32,
    pub z: f32,
    /// Authoritative height above ground (v6 jump batch); ground is 0.
    pub y: f32,
    pub facing: f32,
    pub hp: u16,
    pub max_hp: u16,
    pub connected: bool,
    pub down: bool,
    pub dodging: bool,
    pub guarding: bool,
    pub anim: u8,
}

#[derive(Debug, Clone)]
pub struct MonsterSnapshot {
    pub id: u32,
    /// Stable content kind (1 = Puddlekin). Display names live in the bundle;
    /// the wire never carries them (V5-03).
    pub kind: u8,
    pub x: f32,
    pub z: f32,
    pub facing: f32,
    pub hp: u32,
    pub max_hp: u32,
    pub active: bool,
    pub flags: u8,
    pub state: u8,
    pub ability: u8,
    pub state_ticks: u16,
    pub target_x: f32,
    pub target_z: f32,
    /// Server-only identity for viewer-specific flags; never directly encoded.
    pub target_player_id: Option<u32>,
}

#[derive(Debug, Clone)]
pub struct CombatEvent {
    pub id: u64,
    pub source_kind: u8,
    pub source_id: u32,
    pub target_kind: u8,
    pub target_id: u32,
    pub action: ActionKind,
    pub damage: u16,
    /// Bit 0 defeated, 1 blocked, 2 perfect, 3 dodged, 4 heal.
    pub flags: u8,
    pub world_x: f32,
    pub world_z: f32,
}

/// A cosmetic follower snapshot (v6 pet batch): visible to everyone, follows
/// its owner, never fights. `kind` indexes the bundle's sorted economy pet
/// ids; `flags` bit 0 means visible.
#[derive(Debug, Clone)]
pub struct PetSnapshot {
    pub owner_id: u32,
    pub x: f32,
    pub z: f32,
    pub kind: u8,
    pub flags: u8,
}

#[derive(Debug, Clone)]
pub struct Snapshot {
    pub tick: u64,
    pub ack_seq: u32,
    pub own_flags: u8,
    /// Server position immediately after applying ack_seq; stable while that
    /// input is repeated on later ticks so clients can replay newer inputs
    /// without counting the repeated movement twice.
    pub ack_x: f32,
    pub ack_z: f32,
    pub players: Vec<PlayerSnapshot>,
    pub monsters: Vec<MonsterSnapshot>,
    pub events: Vec<CombatEvent>,
    pub pets: Vec<PetSnapshot>,
}

/// P4: one ground drop owned by the killer (private loot in P1; shared loot
/// is a later social layer). `encounter` is the UUIDv7 kill identity that
/// gates the once-only pickup in `reward_claims` (cycle "loot").
#[derive(Debug, Clone)]
struct DropEntity {
    /// Read when shared-loot pickup lands (P4); reserved until then.
    #[allow(dead_code)]
    id: u64,
    encounter: uuid::Uuid,
    owner: [u8; 32],
    item: String,
    count: u8,
    x: f32,
    z: f32,
    expires_tick: u64,
}

#[derive(Debug)]
struct Player {
    mage: crate::mage_trial::PlayerTrial,
    inventory_schema: u8,
    inventory_namespace: String,
    item_instances: BTreeMap<String,crate::inventory_instances::ItemInstance>,
    gear_slots: BTreeMap<String,String>,
    inventory_valid: bool,
    death_revision: u32,
    revive_until_tick: u64,
    reward_receipts: VecDeque<String>,
    reward_mail: BTreeMap<String,BTreeMap<String,u32>>,
    mvp_rune_pity: u32,
    community: crate::community::Progress,
    device: crate::community::Device,
    id: u32,
    spawn_slot: usize,
    teleport_revision:u64,
    session_id: [u8; 32],
    epoch: u32,
    x: f32,
    z: f32,
    /// Authoritative height + vertical velocity (v6 jump batch).
    y: f32,
    vy: f32,
    grounded: bool,
    last_input_x: f32,
    last_input_z: f32,
    facing: f32,
    input_x: f32,
    input_z: f32,
    /// Sprint held on the latest applied input (v6 movement batch).
    sprinting: bool,
    hp: u16,
    max_hp: u16,
    level: u32,
    exp: u32,
    state_revision: u32,
    bag: BTreeMap<String, u8>,
    pouch: BTreeMap<String, u32>,
    /// Session wallet (D-14); in-memory, resets with the session.
    gold: u32,
    coin: u32,
    /// Equipped cosmetic ids (`skin`, `pet`); None means the default look.
    skin: Option<String>,
    pet: Option<String>,
    owned_cosmetics: BTreeSet<String>,
    quest_revision: u32,
    quest_id: String,
    quest_state: String,
    quest_objectives: BTreeMap<String, u32>,
    quest_step_ticks: BTreeMap<String, u64>,
    activated_windmarks: BTreeSet<String>,
    /// Stable social identity from the shared record (seed-once): the public
    /// handle used by friends/presence and the chat display name.
    handle: String,
    name: String,
    dialogue: Option<DialogueSession>,
    windmark_channel: Option<WindmarkChannel>,
    last_potion_at: Option<Instant>,
    recent_item_operations: VecDeque<(String, String, OpResultMsg)>,
    recent_quest_operations: VecDeque<(String, String, OpResultMsg)>,
    recent_store_operations: VecDeque<(String, String, OpResultMsg)>,
    recent_box_operations: VecDeque<(String, String, OpResultMsg)>,
    recent_equip_operations: VecDeque<(String, String, OpResultMsg)>,
    /// Generation of the shared [`CharacterStore`] record this player last
    /// loaded or published; a mismatch on resume means another instance
    /// advanced the record meanwhile and the world adopts it.
    store_generation: u64,
    /// The `state_revision` value last published to the shared store.
    synced_revision: Option<u32>,
    party_id: Option<u64>,
    connected: bool,
    last_sequence: u64,
    last_input_seq: u64,
    /// Queued inputs (sequence, x, z, facing, flags), capped at 3; the world
    /// applies exactly one per tick (V5-04 motion authority). Flags bit 0 is
    /// a jump edge, bit 1 holds sprint (v6 movement batch).
    input_queue: VecDeque<(u64, f32, f32, f32, u8)>,
    /// Timed power buffs (v6 batch): (kind 0 atk / 1 speed, mult, expires tick).
    buffs: Vec<(u8, f32, u64)>,
    /// Ticks since the queue ran dry while moving; stops after 5.
    repeat_ticks: u8,
    disconnected_at: Option<Instant>,
    last_attack_at: Option<Instant>,
    last_arc_slash_at: Option<Instant>,
    dodge_ready_tick: u64,
    dodge_start_tick: u64,
    dodge_end_tick: u64,
    dodge_start_seq: u64,
    dodge_boost_end_seq: u64,
    guarding: bool,
    guard_start_tick: u64,
    guard_end_tick: u64,
    guard_ready_tick: u64,
    perfect_counter_until_tick: u64,
    down: bool,
    down_until_tick: u64,
    /// Durable identity (V5-12): `Some` once the join ran through the storage
    /// worker. `None` (session-only mode / pre-persistence tests) skips every
    /// durable write.
    principal: Option<crate::storage::PrincipalId>,
    /// The `owner_epoch` this join claimed; every durable save is fenced with
    /// it. A rejection (a newer join claimed the character) sets
    /// `durable_disabled` until the session re-joins and re-claims.
    owner_epoch: u64,
    durable_disabled: bool,
    /// A durable save that could not be queued (channel full); retried on the
    /// next dirty tick instead of being lost.
    durable_dirty: bool,
    /// Earliest tick a degraded-mode retry may fire (bounded retries).
    durable_retry_at: u64,
    /// E07 job track + equipped gear + derived stats (golden formulas).
    job_level: u32,
    job_exp: u32,
    equipment: BTreeMap<String, String>,
    atk: u16,
    def: u16,
    stat_points: u32,
    allocated_str: u16,
    allocated_agi: u16,
    allocated_vit: u16,
    allocated_int: u16,
    allocated_dex: u16,
    allocated_luk: u16,
    recent_stat_operations: VecDeque<(String, String, OpResultMsg)>,
    equipment_refine: BTreeMap<String, u8>,
    recent_refine_operations: VecDeque<(String, String, OpResultMsg)>,
    sp: u16,
    max_sp: u16,
}

#[derive(Debug)]
struct KillTag {
    owner: u32,
    members: BTreeSet<u32>,
    last_damage_tick: u64,
}

#[derive(Debug,Clone)]
struct BossGrant {base:u32,job:u32,items:BTreeMap<String,u32>}

#[derive(Debug)]
struct Monster {
    tag: Option<KillTag>,
    encounter_id: uuid::Uuid,
    rewarded: bool,
    reward_prepared: bool,
    pending_rewards: BTreeMap<u32,BossGrant>,
    contributions: BTreeMap<u32, crate::combat_rules::Contribution>,
    phase: crate::combat_rules::EncounterPhase,
    id: u32,
    kind: u8,
    level: u8,
    rank: crate::content::MonsterRank,
    x: f32,
    z: f32,
    home_x: f32,
    home_z: f32,
    y: f32,
    home_y: f32,
    stuck_ticks: u16,
    leash_polygon: Vec<[f32;2]>,
    facing: f32,
    hp: u32,
    max_hp: u32,
    speed: f32,
    aggro: f32,
    leash: f32,
    splash_radius: f32,
    splash_damage: u16,
    splash_windup_ticks: u16,
    splash_active_ticks: u16,
    splash_recovery_ticks: u16,
    splash_cooldown_duration_ticks: u16,
    respawn_at: Option<Instant>,
    state: u8,
    ability: u8,
    state_ticks: u16,
    target_x: f32,
    target_z: f32,
    target_player_id: Option<u32>,
    ability_cooldown_ticks: u16,
}

impl Monster {
    fn reset_home(&mut self) {
        self.tag = None;
        self.rewarded = false;
        self.reward_prepared=false;
        self.pending_rewards.clear();
        self.contributions.clear();
        self.encounter_id = uuid::Uuid::new_v4();
        self.phase = crate::combat_rules::EncounterPhase::Reset;
        self.x = self.home_x;
        self.z = self.home_z;
        self.y = self.home_y;
        self.stuck_ticks=0;
        self.hp = self.max_hp;
        self.respawn_at = None;
        self.state = monster_state::IDLE;
        self.ability = 0;
        self.state_ticks = 0;
        self.target_x = self.home_x;
        self.target_z = self.home_z;
        self.target_player_id = None;
        self.ability_cooldown_ticks = 0;
    }
}

/// A cosmetic follower (v6 pet batch): follows its owner, visible to all,
/// never fights. Spawned while the owner has a pet cosmetic equipped.
#[derive(Debug, Clone)]
struct Pet {
    owner_id: u32,
    x: f32,
    z: f32,
    kind: u8,
}

pub struct World {
    pending_durable_ops: HashMap<u32,durable_guard::PendingOp>,
    durable_lookup_token: u64,
    deferred_op_results: Vec<(u32,OpResultMsg)>,
    mage_config: crate::mage_trial::Config,
    mage_capability: bool,
    vocation_id: String,
    pending_mage_events: Vec<(Vec<u32>,crate::mage_trial::CastState)>,
    store_owner:u64,
    community_runtime: community_runtime::Runtime,
    combat_roll: fn() -> u8,
    rune_roll: fn() -> Option<u16>,
    players: HashMap<u32, Player>,
    sessions: HashMap<[u8; 32], u32>,
    monsters: Vec<Monster>,
    pets: Vec<Pet>,
    static_colliders: Vec<StaticCollider>,
    city_traversal: Option<Arc<GroundedCity>>,
    player_radius: f32,
    player_height: f32,
    recent_events: VecDeque<(CombatEvent, u64)>,
    tick: u64,
    next_player_id: u32,
    next_event_id: u64,
    next_monster_id: u32,
    content_hash: u64,
    tick_hz: u8,
    zone_id: u16,
    world_limit: f32,
    player_speed: f32,
    player_hp: u16,
    /// V6 movement batch (manifest player block).
    jump_v: f32,
    gravity: f32,
    sprint_mult: f32,
    pet_follow_dist: f32,
    pet_speed_mult: f32,
    /// Sorted economy pet ids; wire kind is 1 + index (v6 pet batch).
    pet_kinds: Vec<String>,
    combat: CombatTuning,
    enemy_respawn: HashMap<u8, Duration>,
    potion_heal: u16,
    potion_carry: u8,
    potion_cooldown: Duration,
    enemy_exp: HashMap<u8, u32>,
    /// Resolved session economy (D-14): bundle table overlaid on defaults.
    economy: Economy,
    /// E07 vocation progression + equipment tuning (cloned into recompute).
    vocation: VocationStats,
    items: BTreeMap<String, crate::content::ItemTuning>,
    buffs: BTreeMap<String, crate::content::BuffTuning>,
    /// P4 per-enemy drop tables (kind -> entries).
    drop_tables: BTreeMap<u8, Vec<crate::content::EnemyDropTuning>>,
    /// Live ground drops owned by the killer.
    drops: Vec<DropEntity>,
    next_drop_id: u64,
    /// Player ids whose drops list changed since the last push.
    pending_drops: BTreeSet<u32>,
    route_npcs: BTreeMap<String, RouteNpc>,
    route_quests: BTreeMap<String, RouteQuest>,
    route_pois: BTreeMap<String, RoutePoint>,
    p1_quest_targets: BTreeMap<String, u32>,
    p1_hunt_kind: Option<u8>,
    pending_state_updates: BTreeSet<u32>,
    pending_notices: Vec<(u32, crate::cold::NoticeMsg)>,
    parties: HashMap<u64, Party>,
    party_codes: HashMap<String, u64>,
    next_party_id: u64,
    pending_party_updates: BTreeSet<u32>,
    /// Cross-instance wallet/bag/quest/op-cache store shared with every other
    /// world instance in the process.
    store: SharedCharacterStore,
    /// Content zone key used for durable checkpoint rows (V5-12).
    zone_key: String,
    /// Durable storage seam (V5-12): disabled until `attach_storage` runs, so
    /// tests and session-only boots keep the pre-persistence behavior.
    storage: StorageHandle,
    /// Durable-save rejections return here (drained by the room loop).
    storage_events: mpsc::UnboundedSender<StorageEvent>,
    /// Tower mode: floor state, curves and the bound session; `None` for the
    /// normal field worlds.
    tower: Option<TowerRuntime>,
    /// Floor milestones reached since the last drain (tower mode only); the
    /// room thread forwards them for best_floor persistence.
    tower_floor_events: Vec<u16>,
    /// V5-13 degraded mode: the durable write path reported the database
    /// unreachable. Valuable cold ops answer `storage_pending` until the next
    /// successful durable event clears this.
    storage_degraded: bool,
}

impl World {
    /// Build the normal-field simulation from validated content. No combat,
    /// movement or spawn numbers remain hard-coded (V5-03).
    pub fn new(content: &Content, store: SharedCharacterStore) -> Self {
        Self::build(content, store, None)
    }

    /// Build a tower-mode world: bound to one session, holding `start_floor`,
    /// with the floor's monster ring spawned around the arena. Same content,
    /// same curves (`content.tower`), own thread like any world instance.
    pub fn new_tower(
        content: &Content,
        store: SharedCharacterStore,
        session: [u8; 32],
        start_floor: u16,
    ) -> Self {
        let table = content
            .tower
            .clone()
            .expect("validated content includes the tower table");
        let enemy = content
            .enemy(&table.enemy)
            .expect("validated tower enemy exists")
            .clone();
        let runtime = TowerRuntime {
            session,
            floor: start_floor.clamp(1, table.max_floor),
            phase: TowerPhase::Fighting,
            advance_at_tick: 0,
            done: false,
            done_taken: false,
            table,
            enemy,
        };
        let mut world = Self::build(content, store, Some(runtime));
        world.tower_spawn_floor();
        world
    }

    fn build(content: &Content, store: SharedCharacterStore, tower: Option<TowerRuntime>) -> Self {
        let tower_mode = tower.is_some();
        let route: RouteBundle = serde_json::from_str(&content.bundle_json)
            .expect("validated content bundle route tables deserialize");
        let route_pois = route
            .zones
            .iter()
            .find(|zone| zone.id == content.zone_id)
            .map(|zone| zone.pois.clone())
            .unwrap_or_default();
        let p1_quest_targets = route
            .quests
            .get(P1_QUEST_ID)
            .expect("validated bundle includes the P1 quest")
            .objectives
            .iter()
            .map(|objective| (objective.id.clone(), objective.count))
            .collect();
        let p1_hunt_kind = route
            .quests
            .get(P1_QUEST_ID)
            .and_then(|quest| {
                quest
                    .objectives
                    .iter()
                    .find(|objective| objective.kind == "defeat")
            })
            .and_then(|objective| objective.target.as_deref())
            .and_then(|target| content.enemy(target))
            .map(|enemy| enemy.kind);
        let ability = |id: &str| {
            content
                .ability(id)
                .unwrap_or_else(|| panic!("content bundle missing ability {id}"))
        };
        let millis = |ms: u16| Duration::from_millis(u64::from(ms));
        let attack = ability("attack");
        let arc = ability("arc_slash");
        let dodge = ability("dodge");
        let guard = ability("guard");
        let potion = ability("potion");
        let combat = CombatTuning {
            attack_range: attack.range.unwrap_or(3.0),
            attack_damage: attack.damage.unwrap_or(25),
            attack_cooldown: millis(attack.cooldown_ms),
            arc_range: arc.range.unwrap_or(4.0),
            arc_damage: arc.damage.unwrap_or(45),
            arc_cooldown: millis(arc.cooldown_ms),
            dodge_cooldown: millis(dodge.cooldown_ms),
            dodge_cooldown_ticks: ((dodge.cooldown_ms + 25) / 50) as u64,
            dodge_duration_steps: ((dodge.duration_ms.unwrap_or(280) + 25) / 50) as u32,
            dodge_mult: dodge.speed_mult.unwrap_or(2.2),
            guard_cooldown: millis(guard.cooldown_ms),
            guard_cooldown_ticks: ((guard.cooldown_ms + 25) / 50) as u64,
            guard_max_hold_ticks: ((guard.max_hold_ms.unwrap_or(1500) + 25) / 50) as u64,
            guard_perfect_ticks: ((guard.perfect_ms.unwrap_or(300) + 25) / 50) as u64,
            guard_reduction_pct: guard.reduction_pct.unwrap_or(70),
        };
        let enemy_respawn = content
            .enemies
            .values()
            .map(|enemy| (enemy.kind, Duration::from_secs(enemy.respawn_s)))
            .collect();
        let enemy_exp = content
            .enemies
            .values()
            .map(|enemy| (enemy.kind, enemy.exp))
            .collect();
        // Tower worlds carry no field spawns: their monsters are the
        // per-floor ring spawned by `tower_spawn_floor`.
        let monsters = if tower.is_some() {
            Vec::new()
        } else {
            content
                .spawns
                .iter()
                .enumerate()
                .map(|(index, spawn)| {
                    let enemy = content
                        .enemy(&spawn.enemy)
                        .unwrap_or_else(|| panic!("content bundle missing enemy {}", spawn.enemy));
                    Monster {
                        tag: None, rewarded: false, reward_prepared:false, pending_rewards:BTreeMap::new(), encounter_id: uuid::Uuid::new_v4(), contributions: BTreeMap::new(), phase: crate::combat_rules::EncounterPhase::Dormant,
                        id: 101 + index as u32,
                        kind: enemy.kind,
                        level: enemy.level,
                        rank: enemy.rank,
                        x: spawn.x,
                        z: spawn.z,
                        home_x: spawn.x,
                        home_z: spawn.z,
                        y: content.zone_city_traversal.as_ref().and_then(|city|city.height_at(spawn.x,spawn.z)).unwrap_or(0.0),
                        home_y: content.zone_city_traversal.as_ref().and_then(|city|city.height_at(spawn.x,spawn.z)).unwrap_or(0.0),
                        stuck_ticks:0, leash_polygon:spawn.leash_polygon.clone(),
                        facing: 0.0,
                        hp: enemy.hp,
                        max_hp: enemy.hp,
                        speed: enemy.speed,
                        aggro: enemy.aggro,
                        leash: enemy.leash,
                        splash_radius: enemy.splash_radius,
                        splash_damage: enemy.splash_damage,
                        splash_windup_ticks: enemy.splash_windup_ms / 50,
                        splash_active_ticks: enemy.splash_active_ms / 50,
                        splash_recovery_ticks: enemy.splash_recovery_ms / 50,
                        splash_cooldown_duration_ticks: enemy.splash_cooldown_ms / 50,
                        respawn_at: None,
                        state: monster_state::IDLE,
                        ability: 0,
                        state_ticks: 0,
                        target_x: spawn.x,
                        target_z: spawn.z,
                        target_player_id: None,
                        ability_cooldown_ticks: 0,
                    }
                })
                .collect()
        };
        let fixture = CoordinateFixture::embedded();
        Self {
            mage_config:content.mage_pilot.clone(),
            pending_durable_ops:HashMap::new(),
            durable_lookup_token:0,
            deferred_op_results:Vec::new(),
            mage_capability:std::env::var("XEXORIA_MAGE_TRIAL").is_ok_and(|v|v=="1"),
            vocation_id:content.vocation_id.clone(),
            pending_mage_events:Vec::new(),
            store_owner:STORE_OWNERS.fetch_add(1,std::sync::atomic::Ordering::Relaxed),
            community_runtime: community_runtime::Runtime::default(),
            combat_roll: || draw_u8_range(0,99).unwrap_or(99),
            rune_roll: crate::combat_rules::random_basis_points,
            players: HashMap::new(),
            sessions: HashMap::new(),
            static_colliders: if tower_mode {
                Vec::new()
            } else {
                content
                    .zone_colliders
                    .iter()
                    .map(|collider| {
                        StaticCollider::from_center_dimensions(collider.center, collider.size)
                    })
                    .collect()
            },
            city_traversal: if tower_mode {
                None
            } else {
                content.zone_city_traversal.clone()
            },
            player_radius: fixture.player_radius(),
            player_height: fixture.player_height(),
            next_monster_id: 101 + monsters.len() as u32,
            monsters,
            recent_events: VecDeque::new(),
            tick: 0,
            next_player_id: 1,
            next_event_id: 1,
            content_hash: content.hash,
            tick_hz: content.tick_hz,
            zone_id: content.zone_id,
            world_limit: if tower_mode {
                TOWER_WORLD_HALF_EXTENT
            } else {
                content.zone_half_extent
            },
            player_speed: content.player_speed,
            player_hp: content.player_hp,
            jump_v: content.player_jump_v,
            gravity: content.player_gravity,
            sprint_mult: content.player_sprint_mult,
            pet_follow_dist: content.pet_follow_dist,
            pet_speed_mult: content.pet_speed_mult,
            pets: Vec::new(),
            pet_kinds: content
                .economy
                .as_ref()
                .map(|economy| {
                    let mut ids: Vec<String> = economy.pets.keys().cloned().collect();
                    ids.sort();
                    ids
                })
                .unwrap_or_default(),
            combat,
            enemy_respawn,
            potion_heal: potion.heal.expect("potion content requires heal"),
            potion_carry: potion.carry.expect("potion content requires carry"),
            potion_cooldown: millis(potion.cooldown_ms),
            enemy_exp,
            vocation: content.vocation.clone(),
            items: content.items.clone(),
            buffs: content.buffs.clone(),
            drop_tables: content
                .enemies
                .iter()
                .filter_map(|(id, enemy)| {
                    content
                        .drop_tables
                        .get(id)
                        .cloned()
                        .map(|table| (enemy.kind, table))
                })
                .collect(),
            drops: Vec::new(),
            next_drop_id: 1,
            pending_drops: BTreeSet::new(),
            economy: Economy::from_bundle(route.economy.as_ref()),
            route_npcs: route.npcs,
            route_quests: route.quests,
            route_pois,
            p1_quest_targets,
            p1_hunt_kind,
            pending_state_updates: BTreeSet::new(),
            pending_notices: Vec::new(),
            parties: HashMap::new(),
            party_codes: HashMap::new(),
            next_party_id: 1,
            pending_party_updates: BTreeSet::new(),
            store,
            zone_key: format!("zone-{}", content.zone_id),
            storage: StorageHandle::disabled(),
            storage_events: mpsc::unbounded_channel().0,
            storage_degraded: false,
            tower,
            tower_floor_events: Vec::new(),
        }
    }
}

/// The canonical first-join character seed for `content`, shared by the world
/// join path and the HTTP/social layer (a friend write before the first join
/// must not silently zero the wallet a first join would grant). Kept in sync
/// with `World::seed_character_record` by a unit test.
pub fn character_record_seed(content: &Content) -> CharacterRecord {
    let route: RouteBundle = serde_json::from_str(&content.bundle_json)
        .expect("validated content bundle route tables deserialize");
    let economy = Economy::from_bundle(route.economy.as_ref());
    let potion_carry = content
        .ability("potion")
        .and_then(|potion| potion.carry)
        .expect("potion content requires carry");
    CharacterRecord {
        gold: economy.start_gold,
        coin: economy.start_coin,
        level: 1,
        exp: 0,
        state_revision: 1,
        bag: BTreeMap::from([("trail_potion".to_string(), potion_carry)]),
        quest_revision: 1,
        quest_state: "not_started".to_string(),
        quest_objectives: P1_QUEST_OBJECTIVES
            .iter()
            .map(|objective| ((*objective).to_string(), 0))
            .collect(),
        ..CharacterRecord::default()
    }
}

impl World {
    pub fn join(&mut self, session_id: [u8; 32]) -> Result<Welcome, &'static str> {
        self.join_with(session_id, None)
    }

    /// Join with the durable character the socket task resolved (V5-12):
    /// `Some` carries the storage worker's record plus the freshly claimed
    /// `owner_epoch`; `None` keeps the session-only seed path.
    pub fn join_with(
        &mut self,
        session_id: [u8; 32],
        character: Option<JoinCharacter>,
    ) -> Result<Welcome, &'static str> {
        self.prune_expired_sessions();
        if session_id.iter().all(|byte| *byte == 0) {
            return Err("session_expired");
        }
        if let Some(player_id) = self.sessions.get(&session_id).copied() {
            // Preserve this room's accepted operations before a same-room takeover;
            // an older room cannot publish after another room claimed the lease.
            if self.owns_character(player_id) {self.push_store(player_id);}
            let player = self.players.get_mut(&player_id).ok_or("session_expired")?;
            // Takeover (R5): a new Join with a valid ticket for a connected
            // session takes over. The epoch bump fences out the old socket's
            // commands and cleanup; the room closes the old outputs. A stale
            // `session_active` lockout no longer exists.
            let takeover = player.connected;
            if !takeover
                && player
                    .disconnected_at
                    .is_some_and(|time| time.elapsed() > RESUME_GRACE)
            {
                return Err("session_expired");
            }
            let claimed=self.store.claim(session_id,self.store_owner,character.as_ref().map(|jc|jc.record.clone())).ok_or("session_expired")?;
            apply_character_record(player,&claimed);player.store_generation=claimed.generation;
            player.synced_revision=Some(player.state_revision);
            player.connected = true;
            player.epoch = player.epoch.wrapping_add(1).max(1);
            player.last_sequence = 0;
            player.last_input_seq = 0;
            player.input_x = 0.0;
            player.input_z = 0.0;
            player.last_input_x = player.x;
            player.last_input_z = player.z;
            player.input_queue.clear();
            player.repeat_ticks = 0;
            player.disconnected_at = None;
            player.dodge_ready_tick = 0;
            player.dodge_start_tick = 0;
            player.dodge_end_tick = 0;
            player.dodge_start_seq = 0;
            player.dodge_boost_end_seq = 0;
            player.guarding = false;
            player.guard_start_tick = 0;
            player.guard_end_tick = 0;
            player.guard_ready_tick = 0;
            player.perfect_counter_until_tick = 0;
            player.down = player.death_revision > 0 && player.hp == 0;
            player.down_until_tick = 0;
            // A join always re-claims the durable fence (V5-12): the socket
            // task loaded the character through the storage worker, so this
            // world now owns the newest epoch and may resume durable writes
            // (including after a SaveRejected disabled them).
            if let Some(jc) = character {
                apply_character_record(player,&jc.record);
                player.synced_revision=Some(player.state_revision);
                player.principal = Some(jc.principal);
                player.owner_epoch = jc.owner_epoch;
                player.durable_disabled = false;
            }
            // Cross-instance reconciliation: when another instance advanced
            // the shared record since this world last published it (tower
            // rewards earned elsewhere), adopt it instead of resuming stale
            // state. Position and hp stay local.
            if let Some(record) = self.store.peek(session_id)
                && record.generation != player.store_generation
            {
                apply_character_record(player, &record);
                player.store_generation = record.generation;
                player.synced_revision = Some(player.state_revision);
            }
            return Ok(Welcome {
                player_id,
                epoch: player.epoch,
                tick: self.tick,
                x: player.x,
                z: player.z,
                zone_id: self.zone_id,
                content_hash: self.content_hash,
                tick_hz: self.tick_hz,
            });
        }

        // Tower instances are bound to exactly one session: the bound session
        // may resume, but nobody else is admitted.
        if self.tower.is_some()
            && !self.sessions.is_empty()
            && !self.sessions.contains_key(&session_id)
        {
            return Err("room_full");
        }
        if self.players.len() >= MAX_PLAYERS {
            return Err("room_full");
        }
        let spawn_slot = (0..MAX_PLAYERS)
            .find(|slot| {
                if self
                    .players
                    .values()
                    .any(|player| player.spawn_slot == *slot)
                {
                    return false;
                }
                let (x, z) = spawn_position(*slot);
                x.abs() <= self.world_limit - self.player_radius
                    && z.abs() <= self.world_limit - self.player_radius
                    && if let Some(city) = &self.city_traversal {
                        city.height_at(x, z).is_some_and(|y| {
                            city.position_is_clear(
                                x,
                                y,
                                z,
                                self.player_radius,
                                self.player_height,
                                &self.static_colliders,
                            )
                        })
                    } else {
                        capsule_position_is_clear(
                            x,
                            z,
                            self.player_radius,
                            self.player_height,
                            &self.static_colliders,
                        )
                    }
            })
            .ok_or("room_full")?;
        let (x, z) = spawn_position(spawn_slot);
        let spawn_y = self
            .city_traversal
            .as_ref()
            .and_then(|city| city.height_at(x, z))
            .unwrap_or(0.0);
        let player_id = self.next_player_id;
        self.next_player_id = self.next_player_id.saturating_add(1);
        self.sessions.insert(session_id, player_id);
        // A player never seen in THIS instance keeps their cross-instance
        // state from the shared store; a first-ever session seeds the store.
        // With the durable seam live (V5-12) the seed is the record the
        // storage worker loaded for the principal — a restart resumes the
        // persisted character instead of a fresh one. Position always
        // follows the normal spawn path.
        let (mut record, join_character) = match character {
            Some(jc) => {
                let record=self.store.claim(session_id,self.store_owner,Some(jc.record.clone())).expect("canonical record present");
                (record, Some(jc))
            }
            None => {
                self.store.load_or_seed(session_id,||self.seed_character_record());
                (self.store.claim(session_id,self.store_owner,None).expect("seeded character"),None)
            },
        };
        record.community.ensure_season();
        let gear_slots=self.items.iter().filter(|(_,v)|!v.equip_slot.is_empty()).map(|(id,v)|(id.clone(),v.equip_slot.clone())).collect::<BTreeMap<_,_>>();
        if record.inventory_namespace.is_empty() {
            use sha2::Digest;
            let mut hash=sha2::Sha256::new();hash.update(b"xexoria-inventory-namespace-v1");if let Some(jc)=join_character.as_ref() {hash.update(jc.principal.as_bytes());} else {hash.update(session_id);}
            let digest=hash.finalize();let mut bytes=[0u8;16];bytes.copy_from_slice(&digest[..16]);record.inventory_namespace=uuid::Uuid::from_bytes(bytes).to_string();
        }
        if crate::inventory_instances::reconcile(&record.inventory_namespace,&mut record.inventory_schema,&mut record.item_instances,&record.bag,&record.equipment,&record.equipment_refine,&gear_slots).is_err() {
            self.sessions.remove(&session_id);
            return Err("inventory_unavailable");
        }
        if record.bag.values().filter(|n|**n>0).count()>12 || record.bag.keys().any(|id|id.len()>64) || uuid::Uuid::parse_str(&record.inventory_namespace).is_err() {
            self.sessions.remove(&session_id);return Err("inventory_unavailable");
        }
        if self.store.save_owned(session_id,&mut record,self.store_owner).is_none() {self.sessions.remove(&session_id);return Err("inventory_unavailable");}
        self.players.insert(
            player_id,
            Player {
                mage:crate::mage_trial::PlayerTrial::default(),
                inventory_schema: record.inventory_schema,
                inventory_namespace: record.inventory_namespace.clone(),
                item_instances: record.item_instances.clone(),
                gear_slots,
                inventory_valid: true,
                death_revision: record.death_revision,
                revive_until_tick: 0,
                reward_receipts: record.reward_receipts.clone(),
                reward_mail: record.reward_mail.clone(),
                mvp_rune_pity: record.mvp_rune_pity,
                id: player_id,
                spawn_slot,
                teleport_revision:0,
                session_id,
                epoch: 1,
                x,
                z,
                y: spawn_y,
                vy: 0.0,
                grounded: true,
                last_input_x: x,
                last_input_z: z,
                facing: 0.0,
                input_x: 0.0,
                input_z: 0.0,
                sprinting: false,
                buffs: Vec::new(),
                hp: if record.down {0} else {self.player_hp},
                max_hp: self.player_hp,
                level: record.level,
                exp: record.exp,
                job_level: record.job_level.max(1),
                job_exp: record.job_exp,
                equipment: record.equipment.clone(),
                atk: 0,
                def: 0,
                state_revision: record.state_revision,
                bag: record.bag,
                pouch: record.pouch,
                gold: record.gold,
                coin: record.coin,
                skin: record.skin,
                pet: record.pet,
                owned_cosmetics: record.owned_cosmetics,
                quest_revision: record.quest_revision,
                quest_id: record.quest_id,
                quest_state: record.quest_state,
                quest_objectives: record.quest_objectives,
                quest_step_ticks: record.quest_step_ticks,
                community: record.community,
                device: crate::community::Device::Unknown,
                activated_windmarks: record.activated_windmarks,
                handle: record.handle,
                name: record.name,
                dialogue: None,
                windmark_channel: None,
                last_potion_at: None,
                recent_item_operations: record.item_operations,
                recent_quest_operations: record.quest_operations,
                recent_store_operations: record.store_operations,
                recent_box_operations: record.box_operations,
                recent_equip_operations: record.equip_operations,
                stat_points: record.stat_points,
                allocated_str: record.allocated_str,
                allocated_agi: record.allocated_agi,
                allocated_vit: record.allocated_vit,
                allocated_int: record.allocated_int,
                allocated_dex: record.allocated_dex,
                allocated_luk: record.allocated_luk,
                recent_stat_operations: record.stat_operations,
                equipment_refine: record.equipment_refine,
                recent_refine_operations: record.refine_operations,
                sp: 0,
                max_sp: 0,
                store_generation: record.generation,
                synced_revision: None,
                party_id: None,
                connected: true,
                last_sequence: 0,
                last_input_seq: 0,
                input_queue: VecDeque::new(),
                repeat_ticks: 0,
                disconnected_at: None,
                last_attack_at: None,
                last_arc_slash_at: None,
                dodge_ready_tick: 0,
                dodge_start_tick: 0,
                dodge_end_tick: 0,
                dodge_start_seq: 0,
                dodge_boost_end_seq: 0,
                guarding: false,
                guard_start_tick: 0,
                guard_end_tick: 0,
                guard_ready_tick: 0,
                perfect_counter_until_tick: 0,
                down: record.down,
                down_until_tick: 0,
                principal: join_character.as_ref().map(|jc| jc.principal),
                owner_epoch: join_character
                    .as_ref()
                    .map(|jc| jc.owner_epoch)
                    .unwrap_or_default(),
                durable_disabled: false,
                durable_dirty: false,
                durable_retry_at: 0,
            },
        );
        self.pending_drops.insert(player_id);
        {
            let vocation = self.vocation.clone();
            let vocation_hp = self.player_hp;
            let items = self.items.clone();
            let base_attack = self.combat.attack_damage;
            let player = self.players.get_mut(&player_id).expect("just inserted");
            recompute_player_stats(player, &vocation, vocation_hp, &items, base_attack);
        }
        if self.character_state(player_id).and_then(|state|serde_json::to_string(&state).ok()).is_none_or(|json|json.len()>crate::cold::MAX_COLD_SERVER_BYTES) {
            self.players.remove(&player_id);self.sessions.remove(&session_id);self.pending_drops.remove(&player_id);return Err("inventory_unavailable");
        }
        Ok(Welcome {
            player_id,
            epoch: 1,
            tick: self.tick,
            x,
            z,
            zone_id: self.zone_id,
            content_hash: self.content_hash,
            tick_hz: self.tick_hz,
        })
    }

    /// The first-ever defaults for a session, used to seed the shared store
    /// (economy-table wallet, starting potion carry, fresh quest record).
    fn seed_character_record(&self) -> CharacterRecord {
        CharacterRecord {
            gold: self.economy.start_gold,
            coin: self.economy.start_coin,
            level: 1,
            exp: 0,
            job_level: 1,
            job_exp: 0,
            equipment: BTreeMap::new(),
            state_revision: 1,
            bag: BTreeMap::from([("trail_potion".to_string(), self.potion_carry)]),
            quest_revision: 1,
            quest_id: P1_QUEST_ID.to_string(),
            quest_state: "not_started".to_string(),
            quest_objectives: P1_QUEST_OBJECTIVES
                .iter()
                .map(|objective| ((*objective).to_string(), 0))
                .collect(),
            ..CharacterRecord::default()
        }
    }

    /// Publish one player's cross-instance fields to the shared store,
    /// recording the returned generation for resume reconciliation, and
    /// mirror the publish into durable storage (V5-12) through the worker.
    fn push_store(&mut self, player_id: u32) {
        if self.community_busy(player_id) { return; }
        let Some(player) = self.players.get_mut(&player_id) else {
            return;
        };
        // A failed durable ownership/operation fence requires a canonical rejoin.
        // Never publish its uncertain live record into the shared room cache.
        if player.durable_disabled {return;}
        let mut record = character_record_of(player);
        // Continue this world's generation line so other instances can tell
        // the record moved since their last load/push.
        record.generation = player.store_generation;
        let Some(generation) = self.store.save_owned(player.session_id, &mut record,self.store_owner) else {return;};
        player.store_generation = generation;
        player.synced_revision = Some(player.state_revision);
        let durable_request =
            player
                .principal
                .filter(|_| !player.durable_disabled)
                .map(|principal| {
                    (
                        principal,
                        player.session_id,
                        player.owner_epoch,
                        Checkpoint {
                            zone: self.zone_key.clone(),
                            x: player.x,
                            z: player.z,
                            hp: i32::from(player.hp),
                        },
                    )
                });
        match durable_request {
            Some((principal, session, owner_epoch, checkpoint)) => {
                let queued = self.storage.save_character(
                    principal,
                    session,
                    record,
                    Some(owner_epoch),
                    Some(checkpoint),
                    self.storage_events.clone(),
                );
                // A full worker queue is not a lost save: mark dirty and
                // retry on the next changed tick.
                let player = self.players.get_mut(&player_id).expect("player present");
                player.durable_dirty = !queued;
            }
            None => {
                if let Some(player) = self.players.get_mut(&player_id) {
                    player.durable_dirty = false;
                }
            }
        }
    }

    /// Publish every player whose cross-instance state changed since the last
    /// push (all such mutations bump `state_revision`), so the shared wallet
    /// is never more than one tick behind.
    fn sync_store(&mut self) {
        let player_ids: Vec<u32> = self.players.keys().copied().collect();
        for player_id in player_ids {
            let changed = self.players.get(&player_id).is_some_and(|player| {
                player.synced_revision != Some(player.state_revision)
                    || (player.durable_dirty && self.tick >= player.durable_retry_at)
            });
            if changed {
                self.push_store(player_id);
            }
        }
    }

    /// Current simulation tick (reported in Pong for RTT measurement).
    pub fn tick(&self) -> u64 {
        self.tick
    }

    /// Half-extent of this world's zone, from content (R9: the wire bound).
    pub fn zone_half_extent(&self) -> f32 {
        self.world_limit
    }

    /// E07: equip an owned weapon/armor item. The piece leaves the bag into
    /// its slot; the previously equipped piece returns to the bag (which must
    /// have room). Derived stats recompute; the op records durably.
    pub fn move_item_instance(&mut self,player_id:u32,request:crate::cold::MoveItemInstanceRequest)->Option<OpResultMsg> {
        let key=serde_json::to_string(&request).ok()?;
        self.move_item_instance_key(player_id,request,key)
    }

    fn move_item_instance_key(&mut self,player_id:u32,request:crate::cold::MoveItemInstanceRequest,key:String)->Option<OpResultMsg> {
        let player=self.players.get_mut(&player_id)?;
        if let Some(result)=replay_cached_op(&player.recent_equip_operations,&request.op_id,&key) {return Some(result);}
        let result=if self.storage_degraded {op_result(&request.op_id,"rejected","storage_pending",vec![])}
            else if !player.inventory_valid {op_result(&request.op_id,"rejected","inventory_unavailable",vec![])}
            else if player.state_revision!=request.expected_revision {op_result(&request.op_id,"rejected","stale_revision",vec![])}
            else if player.item_instances.get(&request.instance_id).and_then(|i|self.items.get(&i.def)).is_some_and(|t|u32::from(t.equip_level_min)>player.level) && request.to!="bag" {op_result(&request.op_id,"rejected","level_too_low",vec![])}
            else {
                match crate::inventory_instances::move_piece(&mut player.item_instances,&mut player.bag,&mut player.equipment,&mut player.equipment_refine,&player.gear_slots,&request.instance_id,&request.to) {
                    Err(reason)=>op_result(&request.op_id,"rejected",reason,vec![]),
                    Ok(())=>{recompute_player_stats(player,&self.vocation,self.player_hp,&self.items,self.combat.attack_damage);bump_state_revision(player);self.pending_state_updates.insert(player_id);op_result(&request.op_id,"accepted","item_moved",vec![])},
                }
            };
        remember_op(&mut player.recent_equip_operations,request.op_id.clone(),key.clone(),&result);
        if result.status=="accepted" && let Some(principal)=player.principal && !player.durable_disabled {
            submit_commit_op(&self.storage,&self.storage_events,player,principal,&self.zone_key,self.content_hash,"equip",&request.op_id,&key,&result,None,vec![]);
        }
        Some(result)
    }

    pub fn equip_item(&mut self,player_id:u32,request:crate::cold::EquipItemRequest)->Option<OpResultMsg> {
        let legacy_key=format!("legacy_equip:{}",request.item);
        let p=self.players.get_mut(&player_id)?;
        if let Some(result)=replay_cached_op(&p.recent_equip_operations,&request.op_id,&legacy_key) {return Some(result);}
        p.inventory_valid=crate::inventory_instances::reconcile(&p.inventory_namespace,&mut p.inventory_schema,&mut p.item_instances,&p.bag,&p.equipment,&p.equipment_refine,&p.gear_slots).is_ok();
        if !p.inventory_valid {return Some(op_result(&request.op_id,"rejected","inventory_unavailable",vec![]));}
        let Some(tuning)=self.items.get(&request.item) else {return Some(op_result(&request.op_id,"rejected","unknown_item",vec![]));};
        if !matches!(tuning.equip_slot.as_str(),"weapon"|"armor") {return Some(op_result(&request.op_id,"rejected","not_equipable",vec![]));}
        let candidates=p.item_instances.values().filter(|i|i.def==request.item&&i.location=="bag").map(|i|i.instance_id.clone()).collect::<Vec<_>>();
        if candidates.len()>1 {return Some(op_result(&request.op_id,"rejected","instance_required",vec![]));}
        let Some(id)=candidates.first() else {return Some(op_result(&request.op_id,"rejected","not_owned",vec![]));};
        let move_request=crate::cold::MoveItemInstanceRequest {t:"move_item_instance".into(),op_id:request.op_id,instance_id:id.clone(),expected_revision:p.state_revision,to:tuning.equip_slot.clone()};
        self.move_item_instance_key(player_id,move_request,legacy_key)
    }

    pub fn character_state(&self, player_id: u32) -> Option<CharacterStateMsg> {
        let player = self.players.get(&player_id)?;
        let levels = player.level.saturating_sub(1);
        let growth = u32::from(self.vocation.stat_growth_levels).max(1);
        let effective_str = u16::try_from(
            u32::from(self.vocation.stats.str_) + levels / growth + u32::from(player.allocated_str),
        )
        .unwrap_or(u16::MAX);
        let effective_agi = self.vocation.stats.agi.saturating_add(player.allocated_agi);
        let effective_vit = u16::try_from(
            u32::from(self.vocation.stats.vit) + levels / growth + u32::from(player.allocated_vit),
        )
        .unwrap_or(u16::MAX);
        let effective_int = self
            .vocation
            .stats
            .int_
            .saturating_add(player.allocated_int);
        let effective_dex = self.vocation.stats.dex.saturating_add(player.allocated_dex);
        let effective_luk = self.vocation.stats.luk.saturating_add(player.allocated_luk);
        if !player.inventory_valid {return None;}
        Some(CharacterStateMsg {
            vocation:Some(self.vocation_id.clone()),
            combat_profile:Some(if player.mage.enabled {"mage_trial"} else {"trailblade"}.into()),
            magic_power:player.mage.enabled.then(||self.mage_config.power(player.allocated_int,player.allocated_dex)),
            stats_base:Some(crate::cold::CharacterStats {str_:effective_str.saturating_sub(player.allocated_str),agi:self.vocation.stats.agi,vit:effective_vit.saturating_sub(player.allocated_vit),int_:self.vocation.stats.int_,dex:self.vocation.stats.dex,luk:self.vocation.stats.luk}),
            stats_allocated:Some(crate::cold::CharacterStats {str_:player.allocated_str,agi:player.allocated_agi,vit:player.allocated_vit,int_:player.allocated_int,dex:player.allocated_dex,luk:player.allocated_luk}),
            equipment_bonus:Some(self.equipment_bonus(player)),
            character_id: player.inventory_namespace.clone(),
            item_instances: player.item_instances.values().cloned().collect(),
            t: "character_state".to_string(),
            rev: player.state_revision,
            level: player.level,
            exp: player.exp,
            base_exp_next: self
                .vocation
                .exp_to_next(ExpTrack::Base, u16::try_from(player.level).unwrap_or(1)),
            job_level: player.job_level,
            job_exp: player.job_exp,
            job_exp_next: self
                .vocation
                .exp_to_next(ExpTrack::Job, u16::try_from(player.job_level).unwrap_or(1)),
            atk: player.atk,
            def: player.def,
            equipment: player
                .equipment
                .iter()
                .map(|(slot, item)| crate::cold::EquipEntry {
                    slot: slot.clone(),
                    item: item.clone(),
                })
                .collect(),
            hp: player.hp,
            max_hp: player.max_hp,
            sp: player.sp,
            max_sp: player.max_sp,
            bag: player
                .bag
                .iter()
                .filter(|(_, count)| **count > 0)
                .enumerate()
                .map(|(slot, (item, count))| BagEntry {
                    slot: slot as u8,
                    item: item.clone(),
                    count: *count,
                })
                .collect(),
            pouch: player.pouch.clone(),
            gold: player.gold,
            coin: player.coin,
            skin: player.skin.clone(),
            pet: player.pet.clone(),
            owned_cosmetics: player.owned_cosmetics.iter().cloned().collect(),
            handle: player.handle.clone(),
            name: player.name.clone(),
            stat_points: player.stat_points,
            stats: crate::cold::CharacterStats {
                str_: effective_str,
                agi: effective_agi,
                vit: effective_vit,
                int_: effective_int,
                dex: effective_dex,
                luk: effective_luk,
            },
            refine: player.equipment_refine.clone(),
        })
    }

    /// The player's chat display name (from the shared record, stable for the
    /// session). `None` when the player id is unknown to this instance.
    pub fn player_name(&self, player_id: u32) -> Option<String> {
        self.players
            .get(&player_id)
            .map(|player| player.name.clone())
    }

    pub fn quest_state(&self, player_id: u32) -> Option<QuestStateMsg> {
        let player = self.players.get(&player_id)?;
        Some(QuestStateMsg {
            t: "quest_state".to_string(),
            rev: player.quest_revision,
            quest: P1_QUEST_ID.to_string(),
            state: player.quest_state.clone(),
            objectives: player.quest_objectives.clone(),
            step_ticks: player.quest_step_ticks.clone(),
        })
    }

    pub fn interact(
        &mut self,
        player_id: u32,
        npc_id: &str,
    ) -> Result<crate::cold::DialogueMsg, &'static str> {
        let npc = self.route_npcs.get(npc_id).cloned().ok_or("unknown_npc")?;
        let quest = self
            .route_quests
            .get(P1_QUEST_ID)
            .cloned()
            .ok_or("unknown_quest")?;
        if npc.zone != self.zone_id {
            return Err("wrong_zone");
        }
        let is_quest_giver = quest.giver == npc_id;
        if !is_quest_giver && npc_id != "bovine_shaman" {
            return Err("unknown_npc");
        }
        let player = self.players.get_mut(&player_id).ok_or("session_expired")?;
        if !player.connected {
            return Err("session_expired");
        }
        if (player.x - npc.x).hypot(player.z - npc.z) > npc.radius {
            return Err("out_of_range");
        }
        if is_quest_giver && player.quest_state == "ready_to_claim" {
            player
                .quest_step_ticks
                .insert("returned".to_string(), self.tick);
            player.quest_revision = player.quest_revision.wrapping_add(1).max(1);
            self.pending_state_updates.insert(player_id);
        }

        let (text_key, choices) = if !is_quest_giver {
            (npc.dialogue.as_str(), Vec::new())
        } else {
            match player.quest_state.as_str() {
                "not_started" => (
                    "sella_greet",
                    vec![
                        crate::cold::ChoiceEntry {
                            id: "accept".to_string(),
                            label_key: "quest_accept".to_string(),
                        },
                        crate::cold::ChoiceEntry {
                            id: "later".to_string(),
                            label_key: "quest_later".to_string(),
                        },
                    ],
                ),
                "ready_to_claim" => (
                    "sella_farewell",
                    vec![
                        crate::cold::ChoiceEntry {
                            id: "claim".to_string(),
                            label_key: "quest_claim".to_string(),
                        },
                        crate::cold::ChoiceEntry {
                            id: "later".to_string(),
                            label_key: "quest_later".to_string(),
                        },
                    ],
                ),
                _ => (
                    if player.quest_state == "completed" {
                        "sella_farewell"
                    } else {
                        "sella_greet"
                    },
                    vec![crate::cold::ChoiceEntry {
                        id: "later".to_string(),
                        label_key: "quest_later".to_string(),
                    }],
                ),
            }
        };

        let mut random = [0_u8; 16];
        getrandom::fill(&mut random).map_err(|_| "entropy_unavailable")?;
        let token: String = random.iter().map(|byte| format!("{byte:02x}")).collect();
        player.dialogue = Some(DialogueSession {
            npc: npc_id.to_string(),
            token: token.clone(),
            expires_at: Instant::now() + Duration::from_secs(30),
        });
        Ok(crate::cold::DialogueMsg {
            t: "dialogue".to_string(),
            npc: npc_id.to_string(),
            token,
            text_key: text_key.to_string(),
            choices,
        })
    }

    pub fn choose(
        &mut self,
        player_id: u32,
        request: crate::cold::ChooseRequest,
    ) -> Result<crate::cold::DialogueClosedMsg, &'static str> {
        let is_quest_giver = self
            .route_quests
            .get(P1_QUEST_ID)
            .is_some_and(|quest| quest.giver == request.npc);
        let player = self.players.get_mut(&player_id).ok_or("session_expired")?;
        if !player.connected {
            return Err("session_expired");
        }
        let dialogue = player.dialogue.take().ok_or("stale_choice")?;
        if dialogue.expires_at <= Instant::now()
            || dialogue.npc != request.npc
            || dialogue.token != request.token
        {
            return Err("stale_choice");
        }
        if !is_quest_giver && request.choice != "later" {
            return Err("invalid_choice");
        }
        if request.choice == "accept" && player.quest_state == "not_started" {
            player.quest_state = "active".to_string();
            player
                .quest_step_ticks
                .insert("accepted".to_string(), self.tick);
            player.quest_revision = player.quest_revision.wrapping_add(1).max(1);
            self.pending_state_updates.insert(player_id);
            return Ok(crate::cold::DialogueClosedMsg {
                t: "dialogue_closed".to_string(),
                npc: request.npc,
                reason: "accepted".to_string(),
            });
        }
        if request.choice == "later" {
            return Ok(crate::cold::DialogueClosedMsg {
                t: "dialogue_closed".to_string(),
                npc: request.npc,
                reason: "later".to_string(),
            });
        }
        Err("invalid_choice")
    }

    pub fn start_windmark(
        &mut self,
        player_id: u32,
        marker: &str,
    ) -> Result<crate::cold::NoticeMsg, &'static str> {
        let position = self
            .route_pois
            .get(marker)
            .copied()
            .ok_or("unknown_marker")?;
        if !marker.starts_with("windmark_")
            || !self.route_quests.get(P1_QUEST_ID).is_some_and(|quest| {
                quest
                    .objectives
                    .iter()
                    .any(|objective| objective.kind == "activate" && objective.distinct)
            })
        {
            return Err("unknown_marker");
        }
        let player = self.players.get_mut(&player_id).ok_or("session_expired")?;
        if !player.connected {
            return Err("session_expired");
        }
        if player.quest_state != "active" {
            return Err("quest_inactive");
        }
        if player.activated_windmarks.contains(marker) {
            return Err("already_activated");
        }
        let expected_marker = format!(
            "windmark_{}",
            player.activated_windmarks.len().saturating_add(1)
        );
        if marker != expected_marker {
            return Err("wrong_order");
        }
        if player.windmark_channel.is_some() {
            return Err("busy");
        }
        if (player.x - position.x).hypot(player.z - position.z) > 2.0 {
            return Err("out_of_range");
        }
        player.windmark_channel = Some(WindmarkChannel {
            marker: marker.to_string(),
            position,
            start_x: player.x,
            start_z: player.z,
            ticks_left: 20,
        });
        Ok(crate::cold::NoticeMsg {
            t: "notice".to_string(),
            key: "windmark_channel_started".to_string(),
            params: serde_json::json!({ "marker": marker }),
        })
    }

    pub fn claim_quest(
        &mut self,
        player_id: u32,
        request: crate::cold::ClaimRequest,
    ) -> Option<OpResultMsg> {
        let player = self.players.get_mut(&player_id)?;
        if let Some((_, previous_quest, previous_result)) = player
            .recent_quest_operations
            .iter()
            .find(|(op_id, _, _)| op_id == &request.op_id)
        {
            if previous_quest == &request.quest {
                return Some(previous_result.clone());
            }
            return Some(op_result(
                &request.op_id,
                "rejected",
                "op_id_conflict",
                Vec::new(),
            ));
        }

        if self.storage_degraded {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "storage_pending",
                Vec::new(),
            ));
        }
        let result = if request.quest != P1_QUEST_ID {
            op_result(&request.op_id, "rejected", "unknown_quest", Vec::new())
        } else if !player.connected {
            op_result(&request.op_id, "rejected", "session_expired", Vec::new())
        } else if player.quest_state != "ready_to_claim" {
            op_result(&request.op_id, "rejected", "prerequisite", Vec::new())
        } else {
            let quest = self
                .route_quests
                .get(P1_QUEST_ID)
                .expect("validated P1 quest exists");
            let giver = self
                .route_npcs
                .get(&quest.giver)
                .expect("validated P1 quest giver exists");
            let in_range = (player.x - giver.x).hypot(player.z - giver.z) <= giver.radius;
            if !in_range {
                op_result(&request.op_id, "rejected", "out_of_range", Vec::new())
            } else if !can_grant_items(player,&quest.reward_items.iter().map(|r|(r.def.clone(),u32::from(r.count))).collect()) {
                op_result(&request.op_id, "rejected", "inventory_full", Vec::new())
            } else {
                let mut grants = Vec::with_capacity(quest.reward_items.len());
                for reward in &quest.reward_items {
                    let entry = player.bag.entry(reward.def.clone()).or_default();
                    *entry = entry.saturating_add(reward.count);
                    grants.push(crate::cold::GrantEntry {
                        def: reward.def.clone(),
                        count: u32::from(reward.count),
                    });
                }
                player.exp = player.exp.saturating_add(quest.reward_exp);
                while player.level < u32::from(self.vocation.max_base_level) {
                    let need = self
                        .vocation
                        .exp_to_next(ExpTrack::Base, u16::try_from(player.level).unwrap_or(1));
                    if player.exp < need {
                        break;
                    }
                    player.exp -= need;
                    player.level += 1;
                    player.stat_points = player.stat_points.saturating_add(3);
                }
                // D-14: claim gold rides the existing quest-reward path.
                player.gold = player.gold.saturating_add(self.economy.quest_claim_gold);
                player.quest_state = "completed".to_string();
                player
                    .quest_step_ticks
                    .insert("claimed".to_string(), self.tick);
                bump_state_revision(player);
                player.quest_revision = player.quest_revision.wrapping_add(1).max(1);
                self.pending_state_updates.insert(player_id);
                op_result(&request.op_id, "accepted", "none", grants)
            }
        };

        let op_id = request.op_id.clone();
        player.recent_quest_operations.push_back((
            request.op_id,
            request.quest.clone(),
            result.clone(),
        ));
        while player.recent_quest_operations.len() > 64 {
            player.recent_quest_operations.pop_front();
        }
        if result.status == "accepted"
            && let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            let extra_ledger = self
                .route_quests
                .get(P1_QUEST_ID)
                .map(|quest| {
                    vec![LedgerEntry::Exp {
                        delta: i64::from(quest.reward_exp),
                    }]
                })
                .unwrap_or_default();
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "quest",
                &op_id,
                &request.quest,
                &result,
                Some((request.quest.clone(), P1_ENTITLEMENT_CYCLE.to_string())),
                extra_ledger,
            );
        }
        Some(result)
    }

    pub fn take_pending_state_updates(&mut self) -> Vec<u32> {
        std::mem::take(&mut self.pending_state_updates)
            .into_iter()
            .collect()
    }

    pub fn take_pending_notices(&mut self) -> Vec<(u32, crate::cold::NoticeMsg)> {
        std::mem::take(&mut self.pending_notices)
    }

    pub fn interest_context(&self,player_id:u32)->crate::interest::InterestContext {let p=self.players.get(&player_id);crate::interest::InterestContext{realm:self.store_owner,zone:self.zone_id,epoch:p.map(|p|p.epoch).unwrap_or(0),teleport_revision:p.map(|p|p.teleport_revision).unwrap_or(0)}}

    pub fn interest_party(&self, player_id:u32) -> BTreeSet<u32> { self.players.get(&player_id).and_then(|p|p.party_id).and_then(|id|self.parties.get(&id)).map(|p|p.members.clone()).unwrap_or_default() }

    pub fn party_state(&self, player_id: u32) -> Option<crate::cold::PartyStateMsg> {
        let player = self.players.get(&player_id)?;
        let Some(party_id) = player.party_id else {
            return Some(crate::cold::PartyStateMsg {
                t: "party_state".to_string(),
                rev: 0,
                members: Vec::new(),
                leader: 0,
                code: String::new(),
                expires_s: 0,
            });
        };
        let party = self.parties.get(&party_id)?;
        let expires_s = party
            .code_expires_at
            .saturating_duration_since(Instant::now())
            .as_secs()
            .min(u64::from(u16::MAX)) as u16;
        Some(crate::cold::PartyStateMsg {
            t: "party_state".to_string(),
            rev: party.revision,
            members: party
                .members
                .iter()
                .map(|id| crate::cold::MemberEntry {
                    id: *id,
                    name: self
                        .players
                        .get(id)
                        .map_or_else(|| format!("Traveler {id}"), |member| member.name.clone()),
                })
                .collect(),
            leader: party.leader,
            code: if expires_s > 0 {
                party.code.clone()
            } else {
                String::new()
            },
            expires_s,
        })
    }

    pub fn create_party(&mut self, player_id: u32) -> Result<(), &'static str> {
        let player = self.players.get(&player_id).ok_or("session_expired")?;
        if !player.connected {
            return Err("session_expired");
        }
        if player.party_id.is_some() {
            return Err("already_in_party");
        }
        let mut random = [0_u8; 6];
        getrandom::fill(&mut random).map_err(|_| "entropy_unavailable")?;
        let alphabet = b"ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        let code: String = random
            .iter()
            .map(|byte| alphabet[usize::from(*byte) % alphabet.len()] as char)
            .collect();
        if self.party_codes.contains_key(&code) {
            return Err("code_collision");
        }
        let id = self.next_party_id;
        self.next_party_id = self.next_party_id.saturating_add(1);
        let mut members = BTreeSet::new();
        members.insert(player_id);
        let now = Instant::now();
        self.parties.insert(
            id,
            Party {
                leader: player_id,
                members,
                code: code.clone(),
                code_expires_at: now + Duration::from_secs(600),
                revision: 1,
            },
        );
        self.party_codes.insert(code, id);
        self.players
            .get_mut(&player_id)
            .expect("player checked")
            .party_id = Some(id);
        self.pending_party_updates.insert(player_id);
        Ok(())
    }

    pub fn join_party(&mut self, player_id: u32, code: &str) -> Result<(), &'static str> {
        let player = self.players.get(&player_id).ok_or("session_expired")?;
        if !player.connected {
            return Err("session_expired");
        }
        if player.party_id.is_some() {
            return Err("already_in_party");
        }
        let party_id = self.party_codes.get(code).copied().ok_or("party_expired")?;
        let party = self.parties.get_mut(&party_id).ok_or("party_expired")?;
        if party.code_expires_at <= Instant::now() {
            self.party_codes.remove(code);
            return Err("party_expired");
        }
        if party.members.len() >= 4 {
            return Err("party_full");
        }
        party.members.insert(player_id);
        party.revision = party.revision.wrapping_add(1).max(1);
        let members: Vec<u32> = party.members.iter().copied().collect();
        self.players
            .get_mut(&player_id)
            .expect("player checked")
            .party_id = Some(party_id);
        self.pending_party_updates.extend(members);
        Ok(())
    }

    pub fn leave_party(&mut self, player_id: u32) -> Result<(), &'static str> {
        let player = self.players.get(&player_id).ok_or("session_expired")?;
        if !player.connected {
            return Err("session_expired");
        }
        let Some(party_id) = player.party_id else {
            self.pending_party_updates.insert(player_id);
            return Ok(());
        };
        let Some(party) = self.parties.get_mut(&party_id) else {
            self.players
                .get_mut(&player_id)
                .expect("player checked")
                .party_id = None;
            self.pending_party_updates.insert(player_id);
            return Ok(());
        };
        party.members.remove(&player_id);
        if party.leader == player_id {
            party.leader = party.members.iter().next().copied().unwrap_or(0);
        }
        party.revision = party.revision.wrapping_add(1).max(1);
        let remaining: Vec<u32> = party.members.iter().copied().collect();
        if remaining.is_empty() {
            self.party_codes.remove(&party.code);
            self.parties.remove(&party_id);
        } else {
            self.pending_party_updates.extend(remaining);
        }
        self.players
            .get_mut(&player_id)
            .expect("player checked")
            .party_id = None;
        self.pending_party_updates.insert(player_id);
        Ok(())
    }

    pub fn take_pending_party_updates(&mut self) -> Vec<u32> {
        std::mem::take(&mut self.pending_party_updates)
            .into_iter()
            .collect()
    }

    /// Apply a bounded, idempotent P1a item use on the world owner.
    pub fn death_state(&self, player_id: u32) -> Option<crate::cold::NoticeMsg> {
        let player = self.players.get(&player_id)?;
        if player.death_revision==0 && !player.down {return None;}
        Some(crate::cold::NoticeMsg {
            t: "notice".into(), key: "death_state".into(),
            params: serde_json::json!({
                "revision": player.death_revision, "down": player.down,
                "cause": if player.down { "monster" } else { "none" },
                "penalty": {"base_exp":0,"job_exp":0,"gold":0},
                "costs": {"return_to_town":0}, "free_return":true,
                "auto_revive_at_ms":null,
                "invulnerable_until_ms": player.revive_until_tick.saturating_mul(50),
            }),
        })
    }

    pub fn return_to_town(&mut self, player_id: u32, request: crate::cold::ReturnToTownRequest) -> Option<OpResultMsg> {
        let key = format!("return_to_town:{}", request.death_revision);
        let player = self.players.get(&player_id)?;
        if let Some(cached) = replay_cached_op(&player.recent_item_operations, &request.op_id, &key) {
            return Some(cached);
        }
        let rejection = if self.storage_degraded || player.durable_disabled { Some("storage_pending") } else if !player.down { Some("not_ko") }
            else if player.death_revision != request.death_revision { Some("stale_death_state") } else { None };
        let (mut x, mut z) = self.route_pois.get("regroup").map(|p|(p.x,p.z)).unwrap_or((0.0,-20.0));
        if !capsule_position_is_clear(x,z,self.player_radius,self.player_height,&self.static_colliders) {
            if let Some(point)=(0..MAX_PLAYERS).map(spawn_position).find(|(sx,sz)|capsule_position_is_clear(*sx,*sz,self.player_radius,self.player_height,&self.static_colliders)) {
                (x,z)=point;
            } else { return Some(op_result(&request.op_id,"rejected","return_unavailable",vec![])); }
        }
        let player=self.players.get_mut(&player_id)?;
        let result=if let Some(reason)=rejection {op_result(&request.op_id,"rejected",reason,vec![])} else {
            player.teleport_revision=player.teleport_revision.wrapping_add(1);
            player.x=x;player.z=z;
            player.y=self.city_traversal.as_ref().and_then(|c|c.height_at(x,z)).unwrap_or(0.0);
            player.vy=0.0;player.grounded=true;player.hp=(player.max_hp/2).max(1);
            player.down=false;player.down_until_tick=0;player.revive_until_tick=self.tick.saturating_add(40);
            player.input_x=0.0;player.input_z=0.0;player.input_queue.clear();player.repeat_ticks=MAX_INPUT_REPEAT;
            player.last_input_x=x;player.last_input_z=z;
            bump_state_revision(player);
            self.pending_state_updates.insert(player_id);
            op_result(&request.op_id,"accepted","returned_to_town",vec![])
        };
        remember_op(&mut player.recent_item_operations,request.op_id.clone(),key.clone(),&result);
        if result.status=="accepted" && let Some(principal)=player.principal && !player.durable_disabled {
            submit_commit_op(&self.storage,&self.storage_events,player,principal,&self.zone_key,self.content_hash,
                "item",&request.op_id,&key,&result,None,vec![]);
        }
        if let Some(notice)=self.death_state(player_id) {self.pending_notices.push((player_id,notice));}
        Some(result)
    }

    pub fn use_item(&mut self, player_id: u32, request: UseItemRequest) -> Option<OpResultMsg> {
        let room_ms = self.tick.saturating_mul(50);
        let player = self.players.get_mut(&player_id)?;
        let before_hp = player.hp;
        let full_cooldown_ms = self.potion_cooldown.as_millis().min(u128::from(u16::MAX)) as u16;
        let remaining_cooldown_ms = player
            .last_potion_at
            .map(|last| {
                self.potion_cooldown
                    .saturating_sub(last.elapsed())
                    .as_millis()
                    .min(u128::from(u16::MAX)) as u16
            })
            .unwrap_or(0);
        if let Some((_, previous_item, previous_result)) = player
            .recent_item_operations
            .iter()
            .find(|(op_id, _, _)| op_id == &request.op_id)
        {
            if previous_item == &request.item {
                return Some(previous_result.clone());
            }
            return Some(OpResultMsg {
                t: "op_result".to_string(),
                op_id: request.op_id,
                status: "rejected".to_string(),
                reason: "op_id_conflict".to_string(),
                ends_at_ms: 0,
                grants: Vec::new(),
            });
        }

        // Potion use stays available while degraded (not an economy write);
        // its consumption persists through the bounded retry instead.
        // Power buffs (v6 batch) share the same idempotent op path.
        if player.down {return Some(op_result(&request.op_id,"rejected","dead",vec![]));}
        let result = if let Some(buff) = self.buffs.get(&request.item).cloned() {
            if player.bag.get(&request.item).copied().unwrap_or(0) == 0 {
                OpResultMsg {
                    t: "op_result".to_string(),
                    op_id: request.op_id.clone(),
                    status: "rejected".to_string(),
                    reason: "not_owned".to_string(),
                    ends_at_ms: 0,
                    grants: Vec::new(),
                }
            } else {
                let count = player.bag.get_mut(&request.item).expect("count checked");
                *count -= 1;
                let expires = self.tick.saturating_add(buff.duration_ticks);
                if let Some(slot) = player
                    .buffs
                    .iter_mut()
                    .find(|(kind, _, _)| *kind == buff.kind)
                {
                    *slot = (buff.kind, buff.mult, expires);
                } else {
                    player.buffs.push((buff.kind, buff.mult, expires));
                }
                bump_state_revision(player);
                OpResultMsg {
                    t: "op_result".to_string(),
                    op_id: request.op_id.clone(),
                    status: "accepted".to_string(),
                    reason: "none".to_string(),
                    ends_at_ms: 0,
                    grants: Vec::new(),
                }
            }
        } else if request.item != "trail_potion" {
            OpResultMsg {
                t: "op_result".to_string(),
                op_id: request.op_id.clone(),
                status: "rejected".to_string(),
                reason: "item_unavailable".to_string(),
                ends_at_ms: 0,
                grants: Vec::new(),
            }
        } else if player.hp >= player.max_hp {
            OpResultMsg {
                t: "op_result".to_string(),
                op_id: request.op_id.clone(),
                status: "rejected".to_string(),
                reason: "hp_full".to_string(),
                ends_at_ms: 0,
                grants: Vec::new(),
            }
        } else if player
            .last_potion_at
            .is_some_and(|last| last.elapsed() < self.potion_cooldown)
        {
            OpResultMsg {
                t: "op_result".to_string(),
                op_id: request.op_id.clone(),
                status: "rejected".to_string(),
                reason: "cooldown".to_string(),
                ends_at_ms: cooldown_deadline(room_ms, remaining_cooldown_ms),
                grants: Vec::new(),
            }
        } else if player.bag.get("trail_potion").copied().unwrap_or(0) == 0 {
            OpResultMsg {
                t: "op_result".to_string(),
                op_id: request.op_id.clone(),
                status: "rejected".to_string(),
                reason: "not_owned".to_string(),
                ends_at_ms: 0,
                grants: Vec::new(),
            }
        } else {
            let count = player.bag.get_mut("trail_potion").expect("count checked");
            *count -= 1;
            player.hp = player
                .hp
                .saturating_add(self.potion_heal)
                .min(player.max_hp);
            bump_state_revision(player);
            player.last_potion_at = Some(Instant::now());
            OpResultMsg {
                t: "op_result".to_string(),
                op_id: request.op_id.clone(),
                status: "accepted".to_string(),
                reason: "none".to_string(),
                ends_at_ms: cooldown_deadline(room_ms, full_cooldown_ms),
                grants: Vec::new(),
            }
        };

        if result.status == "accepted" && request.item == "trail_potion" {
            let healed=player.hp.saturating_sub(before_hp);
            // Only actual healing during an engaged encounter contributes; overheal and replay do not.
            for monster in self.monsters.iter_mut().filter(|m|m.rank==crate::content::MonsterRank::Boss && m.hp>0 && m.contributions.contains_key(&player_id) && (m.x-player.x).hypot(m.z-player.z)<=m.leash) {
                let c=monster.contributions.get_mut(&player_id).expect("participant");c.healing=c.healing.saturating_add(u64::from(healed));c.healing_ticks=c.healing_ticks.saturating_add(u64::from(healed>0));
            }
            self.pending_notices.push((player_id,crate::cold::NoticeMsg {t:"notice".into(),key:"heal".into(),params:serde_json::json!({"amount":player.hp.saturating_sub(before_hp),"hp":player.hp,"max_hp":player.max_hp,"source":"trail_potion"})}));
        }
        let op_id = request.op_id.clone();
        player.recent_item_operations.push_back((
            request.op_id,
            request.item.clone(),
            result.clone(),
        ));
        while player.recent_item_operations.len() > 64 {
            player.recent_item_operations.pop_front();
        }
        if result.status == "accepted"
            && let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            let extra_ledger = vec![LedgerEntry::Item {
                item: request.item.clone(),
                delta: -1,
            }];
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "item",
                &op_id,
                &request.item,
                &result,
                None,
                extra_ledger,
            );
        }
        Some(result)
    }

    /// D-14: server-authoritative store purchase from the session wallet.
    /// The id may be a bag item, a box def or a cosmetic. The full-bag rule is
    /// checked before any currency is consumed and a duplicate cosmetic is
    /// refused without charge.
    pub fn store_buy(&mut self, player_id: u32, request: StoreBuyRequest) -> Option<OpResultMsg> {
        let entry = self.economy.store_entry(&request.item).cloned();
        let cosmetic = entry
            .as_ref()
            .is_some_and(|entry| entry.cosmetic || self.economy.is_cosmetic(&entry.id));
        let player = self.players.get_mut(&player_id)?;
        if let Some(cached) = replay_cached_op(
            &player.recent_store_operations,
            &request.op_id,
            &request.item,
        ) {
            return Some(cached);
        }
        if self.storage_degraded {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "storage_pending",
                Vec::new(),
            ));
        }
        let result = match entry {
            None => op_result(&request.op_id, "rejected", "unknown_item", Vec::new()),
            Some(entry) => {
                if cosmetic {
                    if player.owned_cosmetics.contains(&entry.id) {
                        op_result(&request.op_id, "rejected", "already_owned", Vec::new())
                    } else if wallet_balance(player, entry.currency) < entry.price {
                        op_result(&request.op_id, "rejected", "insufficient_funds", Vec::new())
                    } else {
                        wallet_spend(player, entry.currency, entry.price);
                        player.owned_cosmetics.insert(entry.id.clone());
                        bump_state_revision(player);
                        self.pending_state_updates.insert(player_id);
                        op_result(
                            &request.op_id,
                            "accepted",
                            "none",
                            vec![crate::cold::GrantEntry {
                                def: entry.id,
                                count: 1,
                            }],
                        )
                    }
                } else if !can_grant_items(player,&BTreeMap::from([(entry.id.clone(),1)])) {
                    // Refusal happens before the wallet is touched.
                    op_result(&request.op_id, "rejected", "inventory_full", Vec::new())
                } else if wallet_balance(player, entry.currency) < entry.price {
                    op_result(&request.op_id, "rejected", "insufficient_funds", Vec::new())
                } else {
                    wallet_spend(player, entry.currency, entry.price);
                    let slot = player.bag.entry(entry.id.clone()).or_default();
                    *slot = slot.saturating_add(entry.count);
                    bump_state_revision(player);
                    self.pending_state_updates.insert(player_id);
                    op_result(
                        &request.op_id,
                        "accepted",
                        "none",
                        vec![crate::cold::GrantEntry {
                            def: entry.id,
                            count: u32::from(entry.count),
                        }],
                    )
                }
            }
        };
        let op_id = request.op_id.clone();
        remember_op(
            &mut player.recent_store_operations,
            request.op_id.clone(),
            request.item.clone(),
            &result,
        );
        if result.status == "accepted"
            && let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "store",
                &op_id,
                &request.item,
                &result,
                None,
                Vec::new(),
            );
        }
        Some(result)
    }

    /// D-14: open one owned box. The weighted roll is a cryptographically
    /// random integer walk (never floating point). A bag-item roll while the
    /// bag is full refuses the whole open without consuming the box; wallet
    /// and cosmetic rolls succeed regardless of the bag. A duplicate cosmetic
    /// converts to the `duplicate_cosmetic_coin` refund.
    pub fn box_open(&mut self, player_id: u32, request: BoxOpenRequest) -> Option<OpResultMsg> {
        let box_def = self.economy.box_def(&request.item).cloned();
        let duplicate_coin = self.economy.duplicate_cosmetic_coin;
        let player = self.players.get_mut(&player_id)?;
        if let Some(cached) =
            replay_cached_op(&player.recent_box_operations, &request.op_id, &request.item)
        {
            return Some(cached);
        }
        if self.storage_degraded {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "storage_pending",
                Vec::new(),
            ));
        }
        let result = match box_def {
            None => op_result(&request.op_id, "rejected", "unknown_item", Vec::new()),
            Some(def) => {
                if player.bag.get(&request.item).copied().unwrap_or(0) == 0 {
                    op_result(&request.op_id, "rejected", "not_owned", Vec::new())
                } else if def.rolls.is_empty() {
                    op_result(&request.op_id, "rejected", "box_invalid", Vec::new())
                } else {
                    let selected = if request.item == "mvp_chest" {
                        (self.rune_roll)().map(|point|if point < crate::combat_rules::rune_threshold(player.mvp_rune_pity) {0}else{1})
                    } else {roll_weighted(&def.rolls)};
                    match selected {
                        None => op_result(
                            &request.op_id,
                            "rejected",
                            "entropy_unavailable",
                            Vec::new(),
                        ),
                        Some(roll_index) => {
                            let roll = &def.rolls[roll_index];
                            match &roll.outcome {
                                RollOutcome::Gold(amount) => {
                                    consume_bag_item(player, &request.item);
                                    wallet_add(player, Currency::Gold, *amount);
                                    bump_state_revision(player);
                                    self.pending_state_updates.insert(player_id);
                                    op_result(
                                        &request.op_id,
                                        "accepted",
                                        "none",
                                        vec![crate::cold::GrantEntry {
                                            def: Currency::Gold.grant_key().to_string(),
                                            count: *amount,
                                        }],
                                    )
                                }
                                RollOutcome::Coin(amount) => {
                                    consume_bag_item(player, &request.item);
                                    wallet_add(player, Currency::Coin, *amount);
                                    bump_state_revision(player);
                                    self.pending_state_updates.insert(player_id);
                                    op_result(
                                        &request.op_id,
                                        "accepted",
                                        "none",
                                        vec![crate::cold::GrantEntry {
                                            def: Currency::Coin.grant_key().to_string(),
                                            count: *amount,
                                        }],
                                    )
                                }
                                RollOutcome::Item { id, min, max } => {
                                    match draw_u8_range(*min, *max) {
                                        None => op_result(
                                            &request.op_id,
                                            "rejected",
                                            "entropy_unavailable",
                                            Vec::new(),
                                        ),
                                        Some(count) => {
                                            if !can_grant_items(player,&BTreeMap::from([(id.clone(),u32::from(count))])) {
                                                // Refuse the whole open: nothing is
                                                // consumed.
                                                op_result(
                                                    &request.op_id,
                                                    "rejected",
                                                    "inventory_full",
                                                    Vec::new(),
                                                )
                                            } else {
                                                consume_bag_item(player, &request.item);
                                                let slot =
                                                    player.bag.entry(id.clone()).or_default();
                                                *slot = slot.saturating_add(count);
                                                bump_state_revision(player);
                                                self.pending_state_updates.insert(player_id);
                                                op_result(
                                                    &request.op_id,
                                                    "accepted",
                                                    "none",
                                                    vec![crate::cold::GrantEntry {
                                                        def: id.clone(),
                                                        count: u32::from(count),
                                                    }],
                                                )
                                            }
                                        }
                                    }
                                }
                                RollOutcome::Cosmetic(id) => {
                                    consume_bag_item(player, &request.item);
                                    if player.owned_cosmetics.contains(id) {
                                        wallet_add(player, Currency::Coin, duplicate_coin);
                                        bump_state_revision(player);
                                        self.pending_state_updates.insert(player_id);
                                        op_result(
                                            &request.op_id,
                                            "accepted",
                                            "duplicate_cosmetic",
                                            vec![crate::cold::GrantEntry {
                                                def: Currency::Coin.grant_key().to_string(),
                                                count: duplicate_coin,
                                            }],
                                        )
                                    } else {
                                        player.owned_cosmetics.insert(id.clone());
                                        bump_state_revision(player);
                                        self.pending_state_updates.insert(player_id);
                                        op_result(
                                            &request.op_id,
                                            "accepted",
                                            "none",
                                            vec![crate::cold::GrantEntry {
                                                def: id.clone(),
                                                count: 1,
                                            }],
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        };
        let op_id = request.op_id.clone();
        if result.status == "accepted" && request.item == "mvp_chest" {
            if result.grants.iter().any(|g|g.def=="sunmeadow_rune") {player.mvp_rune_pity=0;}
            else {player.mvp_rune_pity=player.mvp_rune_pity.saturating_add(1).min(4750);}
        }
        remember_op(
            &mut player.recent_box_operations,
            request.op_id.clone(),
            request.item.clone(),
            &result,
        );
        if result.status == "accepted"
            && let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            // The opened box is consumed even for cosmetic/coin outcomes.
            let extra_ledger = vec![LedgerEntry::Item {
                item: request.item.clone(),
                delta: -1,
            }];
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "box",
                &op_id,
                &request.item,
                &result,
                None,
                extra_ledger,
            );
        }
        Some(result)
    }

    /// D-14: equip an owned cosmetic, or reset the pet slot with
    /// `default`/`none`. Idempotent: the revision only moves when the
    /// equipped value actually changes.
    pub fn cosmetics_equip(
        &mut self,
        player_id: u32,
        request: CosmeticsEquipRequest,
    ) -> Option<OpResultMsg> {
        let player = self.players.get_mut(&player_id)?;
        let key = format!("{}:{}", request.slot, request.id);
        if let Some(cached) =
            replay_cached_op(&player.recent_equip_operations, &request.op_id, &key)
        {
            return Some(cached);
        }
        let result = match request.slot.as_str() {
            "skin" => {
                if !player.owned_cosmetics.contains(&request.id) {
                    op_result(&request.op_id, "rejected", "not_owned", Vec::new())
                } else {
                    if player.skin.as_deref() != Some(request.id.as_str()) {
                        player.skin = Some(request.id.clone());
                        bump_state_revision(player);
                        self.pending_state_updates.insert(player_id);
                    }
                    op_result(&request.op_id, "accepted", "none", Vec::new())
                }
            }
            "pet" => {
                if request.id == "default" || request.id == "none" {
                    if player.pet.is_some() {
                        player.pet = None;
                        bump_state_revision(player);
                        self.pending_state_updates.insert(player_id);
                    }
                    op_result(&request.op_id, "accepted", "none", Vec::new())
                } else if !player.owned_cosmetics.contains(&request.id) {
                    op_result(&request.op_id, "rejected", "not_owned", Vec::new())
                } else {
                    if player.pet.as_deref() != Some(request.id.as_str()) {
                        player.pet = Some(request.id.clone());
                        bump_state_revision(player);
                        self.pending_state_updates.insert(player_id);
                    }
                    op_result(&request.op_id, "accepted", "none", Vec::new())
                }
            }
            // Unreachable through the cold path (the slot is validated there).
            _ => op_result(&request.op_id, "rejected", "unknown_slot", Vec::new()),
        };
        remember_op(
            &mut player.recent_equip_operations,
            request.op_id.clone(),
            key,
            &result,
        );
        Some(result)
    }

    /// Last input sequence applied for a player (0 when unknown). The room
    /// stamps it into each per-connection snapshot as `ack_seq` (V5-04).
    pub fn last_input_seq(&self, player_id: u32) -> u32 {
        self.players
            .get(&player_id)
            .map(|player| player.last_input_seq as u32)
            .unwrap_or(0)
    }

    /// Position after the last applied input (the client replay anchor).
    pub fn last_input_position(&self, player_id: u32) -> Option<(f32, f32)> {
        self.players
            .get(&player_id)
            .map(|player| (player.last_input_x, player.last_input_z))
    }

    /// Input flag bits (v6 movement batch): bit 0 is a jump edge (applies
    /// once, only while grounded), bit 1 holds sprint.
    pub fn update_input(
        &mut self,
        player_id: u32,
        epoch: u32,
        sequence: u64,
        x: f32,
        z: f32,
        facing: f32,
        flags: u8,
    ) -> bool {
        if !x.is_finite()
            || !z.is_finite()
            || !facing.is_finite()
            || x.abs() > 100.0
            || z.abs() > 100.0
        {
            return false;
        }
        let Some(player) = self.players.get_mut(&player_id) else {
            return false;
        };
        if !player.connected || player.epoch != epoch || sequence <= player.last_sequence {
            return false;
        }
        player.last_sequence = sequence;
        let mut normalized_x = x.clamp(-1.0, 1.0);
        let mut normalized_z = z.clamp(-1.0, 1.0);
        let length = (normalized_x * normalized_x + normalized_z * normalized_z).sqrt();
        if length > 1.0 {
            normalized_x /= length;
            normalized_z /= length;
        }
        // Queue for tick application (cap 3, oldest dropped); ack happens on
        // apply, not on receipt, so the client can replay (V5-04).
        if player.input_queue.len() >= MAX_QUEUED_INPUTS {
            player.input_queue.pop_front();
        }
        player
            .input_queue
            .push_back((sequence, normalized_x, normalized_z, facing, flags));
        true
    }

    /// Hunt-credit helper lands in V5-09 with party dungeons; marked, not removed.
    #[allow(dead_code)]
    fn eligible_party_members(&self, killer_id: u32, target_x: f32, target_z: f32) -> Vec<u32> {
        let Some(killer) = self.players.get(&killer_id) else {
            return Vec::new();
        };
        let members: Vec<u32> = killer
            .party_id
            .and_then(|party_id| self.parties.get(&party_id))
            .map(|party| party.members.iter().copied().collect())
            .unwrap_or_else(|| vec![killer_id]);
        let now = Instant::now();
        members
            .into_iter()
            .filter(|member_id| {
                self.players.get(member_id).is_some_and(|member| {
                    let connected_or_grace = member.connected
                        || member
                            .disconnected_at
                            .is_some_and(|at| now.saturating_duration_since(at) <= RESUME_GRACE);
                    connected_or_grace
                        && member.level.abs_diff(killer.level) <= 15
                        && (member.x - target_x).hypot(member.z - target_z) <= 30.0
                })
            })
            .collect()
    }

    #[cfg(test)]
    fn credit_kill(&mut self, killer_id: u32, kind: u8, target_x: f32, target_z: f32) {
        self.credit_kill_for(killer_id,kind,target_x,target_z,0,None);
    }

    fn credit_boss(&mut self, index: usize) {
        if self.monsters[index].rewarded {return;}
        let monster=&self.monsters[index];
        let (id,kind,x,z,hp,receipt)=(monster.id,monster.kind,monster.x,monster.z,monster.max_hp,monster.encounter_id.to_string());
        if !monster.reward_prepared {
            // Eligibility, party shares and random rolls freeze once at death. Retries never reroll.
            let contributors=monster.contributions.clone();
            let mut ids=contributors.iter().filter(|(_,c)|c.eligible(hp)).filter_map(|(id,_)|self.players.get(id).filter(|p|p.connected || p.disconnected_at.is_some_and(|at|at.elapsed()<=RESUME_GRACE)).map(|_|*id)).collect::<Vec<_>>();ids.sort_unstable();
            let eligible=contributors.into_iter().filter(|(id,_)|ids.binary_search(id).is_ok()).collect();
            let mvp=crate::combat_rules::mvp(&eligible,hp);
            let exp=self.enemy_exp.get(&kind).copied().unwrap_or(0);
            let n=ids.len().max(1) as u32;
            let mut groups:BTreeMap<(Option<u64>,u32),Vec<u32>>=BTreeMap::new();
            for pid in &ids {let party=self.players[pid].party_id;groups.entry((party,if party.is_none(){*pid}else{0})).or_default().push(*pid);}
            let mut shares=BTreeMap::new();
            for group in groups.values() {let pool=group.iter().map(|pid|exp/n+u32::from(ids.binary_search(pid).unwrap()<(exp%n) as usize)).sum();shares.extend(crate::combat_rules::split_exp(pool,group));}
            let table=self.drop_tables.get(&kind).cloned().unwrap_or_default();
            let mut grants=BTreeMap::new();
            for pid in ids {
                let mut items=BTreeMap::new();
                for _ in 0..if Some(pid)==mvp {2}else{1} {
                    if !table.is_empty() {
                        let roll=u32::from((self.combat_roll)()).min(99);let total=table.iter().map(|e|u32::from(e.chance_pct)).sum::<u32>();let mut point=roll.saturating_mul(total)/100;
                        for entry in &table {if point<u32::from(entry.chance_pct) {*items.entry(entry.item.clone()).or_insert(0u32)+=u32::from(draw_u8_range(entry.min,entry.max).unwrap_or(entry.min));break;}point=point.saturating_sub(u32::from(entry.chance_pct));}
                    }
                }
                if Some(pid)==mvp {*items.entry("mvp_chest".into()).or_insert(0)+=1;}
                let share=shares.get(&pid).copied().unwrap_or(0);grants.insert(pid,BossGrant {base:share.saturating_add(if Some(pid)==mvp {exp/4}else{0}),job:share,items});
            }
            self.monsters[index].pending_rewards=grants;self.monsters[index].reward_prepared=true;
            let name=mvp.and_then(|pid|self.players.get(&pid).map(|p|p.name.clone())).unwrap_or_default();
            for pid in self.players.keys().copied().collect::<Vec<_>>() {self.pending_notices.push((pid,crate::cold::NoticeMsg {t:"notice".into(),key:"boss_defeated".into(),params:serde_json::json!({"encounter_id":receipt,"monster_id":id,"mvp_name":name,"x":x,"z":z})}));}
        }
        if self.storage_degraded {return;}
        let grants=self.monsters[index].pending_rewards.clone();
        for (pid,grant) in grants {
            let Some(player)=self.players.get(&pid) else {continue;};
            if player.reward_receipts.contains(&receipt) {self.monsters[index].pending_rewards.remove(&pid);continue;}
            if player.durable_disabled || !self.owns_character(pid) || !player.inventory_valid {continue;}
            let fits=can_grant_items(player,&grant.items);
            if !fits && player.reward_mail.len()>=256 {continue;}
            self.grant_kill_progress(pid,grant.base,grant.job,id,kind,x,z);
            let player=self.players.get_mut(&pid).unwrap();
            if fits {for (item,count) in &grant.items {*player.bag.entry(item.clone()).or_default()+=*count as u8;}} else {player.reward_mail.insert(receipt.clone(),grant.items.clone());}
            player.reward_receipts.push_back(receipt.clone());while player.reward_receipts.len()>256 {player.reward_receipts.pop_front();}
            bump_state_revision(player);self.pending_state_updates.insert(pid);
            self.pending_notices.push((pid,crate::cold::NoticeMsg {t:"notice".into(),key:"reward_receipt".into(),params:serde_json::json!({"receipt_id":receipt,"status":if fits {"granted"} else {"pending"},"items":grant.items,"monster_id":id,"kind":kind})}));
            if let Some(principal)=player.principal && !player.durable_disabled {
                let result=op_result(&receipt,"accepted",if fits {"boss_reward_granted"} else {"boss_reward_pending"},vec![]);
                let ledger=if fits {grant.items.iter().map(|(item,count)|LedgerEntry::Item {item:item.clone(),delta:i64::from(*count)}).collect()} else {vec![]};
                submit_commit_op(&self.storage,&self.storage_events,player,principal,&self.zone_key,self.content_hash,"item",&receipt,"boss_reward",&result,Some((receipt.clone(),"boss".into())),ledger);
            }
            self.monsters[index].pending_rewards.remove(&pid);
        }
        self.monsters[index].rewarded=self.monsters[index].pending_rewards.is_empty();
    }

    pub fn claim_reward(&mut self, player_id:u32, request:crate::cold::ClaimRewardRequest) -> Option<OpResultMsg> {
        let player=self.players.get_mut(&player_id)?;
        let key=format!("claim_reward:{}",request.receipt_id);
        if let Some(result)=replay_cached_op(&player.recent_item_operations,&request.op_id,&key) {return Some(result);}
        let items=player.reward_mail.get(&request.receipt_id).cloned();
        let result=if self.storage_degraded {op_result(&request.op_id,"rejected","storage_pending",vec![])} else if let Some(items)=items {
            if !can_grant_items(player,&items) {op_result(&request.op_id,"rejected","inventory_full",vec![])} else {
                for (item,count) in &items {*player.bag.entry(item.clone()).or_default()+=*count as u8;}
                player.reward_mail.remove(&request.receipt_id);bump_state_revision(player);self.pending_state_updates.insert(player_id);
                op_result(&request.op_id,"accepted","reward_claimed",items.iter().map(|(def,count)|crate::cold::GrantEntry {def:def.clone(),count:*count}).collect())
            }
        } else {op_result(&request.op_id,"rejected","unknown_reward",vec![])};
        remember_op(&mut player.recent_item_operations,request.op_id.clone(),key.clone(),&result);
        if result.status=="accepted" && let Some(principal)=player.principal && !player.durable_disabled {
            let ledger=result.grants.iter().map(|g|LedgerEntry::Item {item:g.def.clone(),delta:i64::from(g.count)}).collect();
            submit_commit_op(&self.storage,&self.storage_events,player,principal,&self.zone_key,self.content_hash,"item",&request.op_id,&key,&result,None,ledger);
        }
        Some(result)
    }

    fn grant_kill_progress(&mut self, member_id:u32, awarded_exp:u32, awarded_job:u32, monster_id:u32, kind:u8, target_x:f32,target_z:f32) {
        let hunt_kind = self.p1_hunt_kind;
        let quest_targets = self.p1_quest_targets.clone();
        let vocation = self.vocation.clone();
        let vocation_hp = self.player_hp;
        let items = self.items.clone();
        let base_attack = self.combat.attack_damage;
            if let Some(member) = self.players.get_mut(&member_id) {
                let before_level=member.level;let before_job=member.job_level;
                member.community.xp = member.community.xp.saturating_add(10).min(2000);
                self.community_runtime.dirty.insert(member_id);
                member.exp = member.exp.saturating_add(awarded_exp);
                while member.level < u32::from(vocation.max_base_level) {
                    let need = vocation
                        .exp_to_next(ExpTrack::Base, u16::try_from(member.level).unwrap_or(1));
                    if member.exp < need {
                        break;
                    }
                    member.exp -= need;
                    member.level += 1;
                    member.stat_points = member.stat_points.saturating_add(3);
                }
                member.job_exp = member.job_exp.saturating_add(awarded_job);
                while member.job_level < u32::from(vocation.max_job_level) {
                    let need = vocation
                        .exp_to_next(ExpTrack::Job, u16::try_from(member.job_level).unwrap_or(1));
                    if member.job_exp < need {
                        break;
                    }
                    member.job_exp -= need;
                    member.job_level += 1;
                }
                recompute_player_stats(member, &vocation, vocation_hp, &items, base_attack);
                *member.pouch.entry("dew_bead".to_string()).or_default() += 1;
                bump_state_revision(member);
                if Some(kind) == hunt_kind
                    && member.quest_state == "active"
                    && member.quest_objectives.get("hunt").copied().unwrap_or(0)
                        < quest_targets.get("hunt").copied().unwrap_or(0)
                {
                    *member
                        .quest_objectives
                        .entry("hunt".to_string())
                        .or_default() += 1;
                    let count = member.quest_objectives.get("hunt").copied().unwrap_or(0);
                    member
                        .quest_step_ticks
                        .insert(format!("hunt_{count}"), self.tick);
                    refresh_quest_state(member, &quest_targets);
                    member.quest_revision = member.quest_revision.wrapping_add(1).max(1);
                }
                self.pending_notices.push((member_id,crate::cold::NoticeMsg {t:"notice".into(),key:"exp_gain".into(),params:serde_json::json!({"base":awarded_exp,"job":awarded_job,"monster_id":monster_id,"kind":kind,"x":target_x,"z":target_z,"level_up":member.level>before_level,"job_level_up":member.job_level>before_job})}));
                self.pending_state_updates.insert(member_id);
            }
    }

    fn credit_kill_for(&mut self, killer_id: u32, kind: u8, target_x: f32, target_z: f32, monster_id: u32, tag_members: Option<BTreeSet<u32>>) {
        let enemy_exp = self.enemy_exp.get(&kind).copied().unwrap_or(0);
        let kill_gold = self.economy.kill_gold;
        let mut credited_members = if let Some(members)=tag_members {
            let owner_level=self.players.get(&killer_id).map(|p|p.level);
            members.into_iter().filter(|id|self.players.get(id).is_some_and(|p|(p.connected || p.disconnected_at.is_some_and(|at|at.elapsed()<=RESUME_GRACE)) && owner_level.is_some_and(|level|level.abs_diff(p.level)<=15) && (p.x-target_x).hypot(p.z-target_z)<=30.0)).collect()
        } else {self.eligible_party_members(killer_id,target_x,target_z)};
        credited_members.sort_unstable();
        let count = credited_members.len();
        let exp_pool = enemy_exp.saturating_mul(100 + 10 * count.saturating_sub(1).min(3) as u32) / 100;
        for (ordinal, member_id) in credited_members.into_iter().enumerate() {
            let awarded_exp = exp_pool / count as u32 + u32::from((ordinal as u32) < exp_pool % count as u32);
            self.grant_kill_progress(member_id,awarded_exp,awarded_exp,monster_id,kind,target_x,target_z);
        }
        // D-14: kill gold rides the existing defeat credit, paid to the killer.
        if let Some(killer) = self.players.get_mut(&killer_id) {
            killer.gold = killer.gold.saturating_add(kill_gold);
            killer.state_revision = killer.state_revision.wrapping_add(1).max(1);
            self.pending_state_updates.insert(killer_id);
        }
        // P4: roll the kill's drop table; drops are private to the killer.
        let drop_entries = self.drop_tables.get(&kind).cloned().unwrap_or_default();
        if !drop_entries.is_empty() {
            let mut spawned = false;
            for entry in drop_entries {
                let roll = crate::world::draw_u8_range(1, 100).unwrap_or(0);
                if roll > entry.chance_pct {
                    continue;
                }
                let Some(count) = crate::world::draw_u8_range(entry.min, entry.max) else {
                    continue;
                };
                if self.drops.len() >= MAX_DROPS {
                    self.drops.remove(0);
                }
                let drop = DropEntity {
                    id: self.next_drop_id,
                    encounter: uuid::Uuid::now_v7(),
                    owner: killer_id_session_of(&self.players, killer_id),
                    item: entry.item.clone(),
                    count,
                    x: target_x,
                    z: target_z,
                    expires_tick: self.tick + DROP_TTL_TICKS,
                };
                self.next_drop_id += 1;
                self.drops.push(drop);
                spawned = true;
            }
            if spawned {
                self.pending_drops.insert(killer_id);
            }
        }
    }

    /// The killer's drops list (private loot): only the owner sees them.
    pub fn drops_state(&self, player_id: u32) -> Option<crate::cold::DropsMsg> {
        let player = self.players.get(&player_id)?;
        let entries = self
            .drops
            .iter()
            .filter(|drop| drop.owner == player.session_id)
            .map(|drop| crate::cold::DropEntry {
                encounter: drop.encounter.to_string(),
                item: drop.item.clone(),
                count: u32::from(drop.count),
                x: drop.x,
                z: drop.z,
            })
            .collect();
        Some(crate::cold::DropsMsg {
            t: "drops".to_string(),
            entries,
        })
    }

    pub fn take_pending_drops(&mut self) -> Vec<u32> {
        std::mem::take(&mut self.pending_drops)
            .into_iter()
            .collect()
    }

    /// Expire stale drops each tick; owners get a refresh push.
    fn expire_drops(&mut self) {
        let before = self.drops.len();
        self.drops.retain(|drop| self.tick < drop.expires_tick);
        if self.drops.len() != before {
            for player in self.players.values() {
                self.pending_drops.insert(player.id);
            }
        }
    }

    /// P4: pick up one of the player's own drops within reach. The bag must
    /// have room BEFORE the drop is consumed (S12.4 full-bag rule); the grant
    /// records durably through CommitOp with the encounter as the
    /// once-per-character entitlement (cycle "loot").
    pub fn pickup_drop(
        &mut self,
        player_id: u32,
        request: crate::cold::PickupDropRequest,
    ) -> Option<OpResultMsg> {
        let player = self.players.get_mut(&player_id)?;
        if let Some(cached) = replay_cached_op(
            &player.recent_item_operations,
            &request.op_id,
            &request.encounter,
        ) {
            return Some(cached);
        }
        if self.storage_degraded {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "storage_pending",
                Vec::new(),
            ));
        }
        let result = match self.drops.iter().position(|drop| {
            drop.encounter.to_string() == request.encounter && drop.owner == player.session_id
        }) {
            None => op_result(&request.op_id, "rejected", "unknown_drop", Vec::new()),
            Some(index) => {
                let drop = self.drops[index].clone();
                let dist = (player.x - drop.x).hypot(player.z - drop.z);
                if dist > DROP_PICKUP_RANGE {
                    op_result(&request.op_id, "rejected", "out_of_range", Vec::new())
                } else if !can_grant_items(player,&BTreeMap::from([(drop.item.clone(),u32::from(drop.count))])) {
                    op_result(&request.op_id, "rejected", "inventory_full", Vec::new())
                } else {
                    *player.bag.entry(drop.item.clone()).or_default() = player
                        .bag
                        .get(&drop.item)
                        .copied()
                        .unwrap_or(0)
                        .saturating_add(drop.count);
                    self.drops.remove(index);
                    bump_state_revision(player);
                    self.pending_state_updates.insert(player_id);
                    self.pending_drops.insert(player_id);
                    op_result(
                        &request.op_id,
                        "accepted",
                        "none",
                        vec![crate::cold::GrantEntry {
                            def: drop.item.clone(),
                            count: u32::from(drop.count),
                        }],
                    )
                }
            }
        };
        let accepted = result.status == "accepted";
        let encounter = request.encounter.clone();
        let item = self
            .drops
            .iter()
            .find(|drop| drop.encounter.to_string() == request.encounter)
            .map(|drop| (drop.item.clone(), drop.count))
            .unwrap_or_else(|| {
                // The drop was consumed: read the grant from the result.
                (
                    result
                        .grants
                        .first()
                        .map(|grant| grant.def.clone())
                        .unwrap_or_default(),
                    result
                        .grants
                        .first()
                        .map(|grant| grant.count as u8)
                        .unwrap_or(0),
                )
            });
        remember_op(
            &mut player.recent_item_operations,
            request.op_id.clone(),
            request.encounter.clone(),
            &result,
        );
        if accepted
            && let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            let extra_ledger = vec![LedgerEntry::Item {
                item: item.0.clone(),
                delta: i64::from(item.1),
            }];
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "loot",
                &request.op_id,
                &request.encounter,
                &result,
                Some((encounter, "loot".to_string())),
                extra_ledger,
            );
        }
        Some(result)
    }

    /// Allocate status points into STR, AGI, VIT, INT, DEX, or LUK.
    /// Deducts `stat_points`, increases the allocated stat, recomputes derived
    /// stats (ATK, DEF, MAX_HP), and records through CommitOp if persistent.
    pub fn stat_allocate(
        &mut self,
        player_id: u32,
        request: crate::cold::StatAllocateRequest,
    ) -> Option<OpResultMsg> {
        let key=format!("{}:{}",request.stat,request.points);
        let player = self.players.get_mut(&player_id)?;
        if let Some(cached) = replay_cached_op(
            &player.recent_stat_operations,
            &request.op_id,
            &key,
        ) {
            return Some(cached);
        }
        if self.storage_degraded {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "storage_pending",
                Vec::new(),
            ));
        }
        let points = request.points;
        if player.stat_points < points {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "insufficient_stat_points",
                Vec::new(),
            ));
        }
        let points_u16 = u16::try_from(points).unwrap_or(0);
        match request.stat.as_str() {
            "str" => player.allocated_str = player.allocated_str.saturating_add(points_u16),
            "agi" => player.allocated_agi = player.allocated_agi.saturating_add(points_u16),
            "vit" => player.allocated_vit = player.allocated_vit.saturating_add(points_u16),
            "int" => player.allocated_int = player.allocated_int.saturating_add(points_u16),
            "dex" => player.allocated_dex = player.allocated_dex.saturating_add(points_u16),
            "luk" => player.allocated_luk = player.allocated_luk.saturating_add(points_u16),
            _ => {
                return Some(op_result(
                    &request.op_id,
                    "rejected",
                    "invalid_stat",
                    Vec::new(),
                ));
            }
        }
        player.stat_points -= points;
        let vocation = self.vocation.clone();
        let vocation_hp = self.player_hp;
        let items = self.items.clone();
        let base_attack = self.combat.attack_damage;
        recompute_player_stats(player, &vocation, vocation_hp, &items, base_attack);
        bump_state_revision(player);
        self.pending_state_updates.insert(player_id);

        let result = op_result(&request.op_id, "accepted", "allocated", Vec::new());
        remember_op(
            &mut player.recent_stat_operations,
            request.op_id.clone(),
            key.clone(),
            &result,
        );

        if let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "stat_allocate",
                &request.op_id,
                &key,
                &result,
                None,
                Vec::new(),
            );
        }

        Some(result)
    }

    /// Refine equipped gear (+1 to +10) in weapon or armor slot.
    /// Deducts gold, rolls refine success, increases refine level, recomputes
    /// derived stats (ATK, DEF, MAX_HP), and records through CommitOp if persistent.
    pub fn refine_item(
        &mut self,
        player_id: u32,
        request: crate::cold::RefineItemRequest,
    ) -> Option<OpResultMsg> {
        let key=serde_json::to_string(&request).ok()?;
        let player = self.players.get_mut(&player_id)?;
        if let Some(cached) = replay_cached_op(
            &player.recent_refine_operations,
            &request.op_id,
            &key,
        ) {
            return Some(cached);
        }
        if self.storage_degraded {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "storage_pending",
                Vec::new(),
            ));
        }

        let slot = request.slot.as_str();
        if !player.equipment.contains_key(slot) {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "no_item_equipped",
                Vec::new(),
            ));
        }

        if !player.inventory_valid {return Some(op_result(&request.op_id,"rejected","inventory_unavailable",vec![]));}
        let Some(instance_id)=request.instance_id.as_deref() else {return Some(op_result(&request.op_id,"rejected","instance_required",vec![]));};
        if request.expected_revision!=Some(player.state_revision) {return Some(op_result(&request.op_id,"rejected","stale_revision",vec![]));}
        let Some(piece)=player.item_instances.get(instance_id) else {return Some(op_result(&request.op_id,"rejected","not_owned",vec![]));};
        if piece.location!=slot || player.equipment.get(slot)!=Some(&piece.def) {return Some(op_result(&request.op_id,"rejected","wrong_slot",vec![]));}

        let current_refine = player.equipment_refine.get(slot).copied().unwrap_or(0);
        if current_refine >= 10 {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "max_refine_reached",
                Vec::new(),
            ));
        }

        // Cost scales with refine level: (current + 1) * 30 gold
        let cost = u32::from(current_refine + 1).saturating_mul(30);
        if player.gold < cost {
            return Some(op_result(
                &request.op_id,
                "rejected",
                "insufficient_gold",
                Vec::new(),
            ));
        }

        player.gold -= cost;

        // Safe limit is +4 (100% success rate from +0 to +4)
        // Beyond +4: 70%, 60%, 50%, 40%, 30%, 20%
        let success = if current_refine < 4 {
            true
        } else {
            use std::hash::{Hash, Hasher};
            let mut hasher = std::collections::hash_map::DefaultHasher::new();
            request.op_id.hash(&mut hasher);
            self.tick.hash(&mut hasher);
            player_id.hash(&mut hasher);
            current_refine.hash(&mut hasher);
            let roll = (hasher.finish() % 100) as u8;
            let success_threshold = match current_refine {
                4 => 70,
                5 => 60,
                6 => 50,
                7 => 40,
                8 => 30,
                _ => 20,
            };
            roll < success_threshold
        };

        let (status, reason, next_refine) = if success {
            let next = current_refine + 1;
            player.equipment_refine.insert(slot.to_string(), next);
            ("accepted", "refine_success", next)
        } else {
            // Failed: drops by 1 refine level down to safe limit (4)
            let next = current_refine.saturating_sub(1).max(4);
            player.equipment_refine.insert(slot.to_string(), next);
            ("accepted", "refine_failed", next)
        };
        player.item_instances.get_mut(instance_id).expect("validated piece").refine=next_refine;

        let vocation = self.vocation.clone();
        let vocation_hp = self.player_hp;
        let items = self.items.clone();
        let base_attack = self.combat.attack_damage;
        recompute_player_stats(player, &vocation, vocation_hp, &items, base_attack);
        bump_state_revision(player);
        self.pending_state_updates.insert(player_id);

        let result = op_result(
            &request.op_id,
            status,
            reason,
            vec![crate::cold::GrantEntry {
                def: format!("{slot}_refine_{next_refine}"),
                count: 1,
            }],
        );
        remember_op(
            &mut player.recent_refine_operations,
            request.op_id.clone(),
            key.clone(),
            &result,
        );

        if let Some(principal) = player.principal.as_ref()
            && !player.durable_disabled
        {
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                player,
                *principal,
                &self.zone_key,
                self.content_hash,
                "refine_item",
                &request.op_id,
                &key,
                &result,
                None,
                Vec::new(),
            );
        }

        Some(result)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn apply_action(
        &mut self,
        player_id: u32,
        epoch: u32,
        sequence: u64,
        action: ActionKind,
        aim: f32,
        _target_id: u32,
        _view_tick: u32,
    ) -> ActionOutcome {
        if !self.owns_character(player_id)||self.community_busy(player_id) {return ActionOutcome::rejected(RejectReason::Busy,0);}
        // Commands can arrive after a KO and before the next AI tick. Release a dead,
        // departed or inactive owner before this hit can finish the previous tag.
        self.reset_stale_combat_tags();
        fn remaining(last: Option<Instant>, cooldown: Duration) -> u16 {
            last.map(|at| {
                cooldown
                    .saturating_sub(at.elapsed())
                    .as_millis()
                    .min(u128::from(u16::MAX)) as u16
            })
            .unwrap_or(0)
        }

        let room_ms = self.tick.saturating_mul(50);
        let now = Instant::now();
        let Some(player) = self.players.get_mut(&player_id) else {
            return ActionOutcome::rejected(RejectReason::NoTarget, 0);
        };
        if !player.connected || player.epoch != epoch || sequence <= player.last_sequence {
            return ActionOutcome::rejected(RejectReason::NoTarget, 0);
        }
        if player.hp == 0 || player.down {
            return ActionOutcome::rejected(RejectReason::Dead, 0);
        }
        player.last_sequence = sequence;

        if action == ActionKind::SplashHop {
            return ActionOutcome::rejected(RejectReason::NotAllowed, 0);
        }

        if player.mage.enabled && matches!(action,ActionKind::Attack|ActionKind::ArcSlash)
            && (player.mage.pending.is_some()||self.tick<player.mage.recovery_tick) {
            return ActionOutcome::rejected(RejectReason::Busy,0);
        }

        if action == ActionKind::Guard {
            if self.tick < player.guard_ready_tick {
                let remaining_ticks = player.guard_ready_tick.saturating_sub(self.tick);
                let remaining_ms = (remaining_ticks * 50).min(u16::MAX as u64) as u16;
                return ActionOutcome::rejected(
                    RejectReason::Cooldown,
                    cooldown_deadline(room_ms, remaining_ms),
                );
            }
            if player.guarding {
                return ActionOutcome::rejected(RejectReason::Busy, 0);
            }
            player.guarding = true;
            player.guard_start_tick = self.tick;
            player.guard_end_tick = self.tick + self.combat.guard_max_hold_ticks;
            player.guard_ready_tick = self.tick + self.combat.guard_cooldown_ticks;
            return ActionOutcome::accepted(cooldown_deadline(
                room_ms,
                u16::try_from(self.combat.guard_cooldown.as_millis().min(65000)).unwrap_or(65000),
            ));
        }

        if action == ActionKind::Dodge {
            if self.tick + 1 < player.dodge_ready_tick {
                let remaining_ticks = player.dodge_ready_tick.saturating_sub(self.tick);
                let remaining_ms = (remaining_ticks * 50).min(u16::MAX as u64) as u16;
                return ActionOutcome::rejected(
                    RejectReason::Cooldown,
                    cooldown_deadline(room_ms, remaining_ms),
                );
            }
            player.guarding = false;
            player.dodge_ready_tick = self.tick + self.combat.dodge_cooldown_ticks;
            player.dodge_start_tick = self.tick.saturating_add(1);
            player.dodge_end_tick = player.dodge_start_tick.saturating_add(u64::from(
                self.combat.dodge_duration_steps.saturating_sub(1),
            ));
            player.dodge_start_seq = sequence;
            player.dodge_boost_end_seq = sequence + self.combat.dodge_duration_steps as u64;
            return ActionOutcome::accepted(cooldown_deadline(
                room_ms,
                u16::try_from(self.combat.dodge_cooldown.as_millis().min(65000)).unwrap_or(65000),
            ));
        }

        let (range, base_damage, cooldown, full_ms, max_targets, half_arc) = match action {
            ActionKind::Attack => (
                self.combat.attack_range,
                player.atk,
                self.combat.attack_cooldown,
                u16::try_from(self.combat.attack_cooldown.as_millis().min(65000)).unwrap_or(65000),
                1,
                std::f32::consts::FRAC_PI_4,
            ),
            ActionKind::ArcSlash => (
                self.combat.arc_range,
                player.atk.saturating_add(
                    self.combat
                        .arc_damage
                        .saturating_sub(self.combat.attack_damage),
                ),
                self.combat.arc_cooldown,
                u16::try_from(self.combat.arc_cooldown.as_millis().min(65000)).unwrap_or(65000),
                3,
                std::f32::consts::FRAC_PI_3,
            ),
            ActionKind::Dodge | ActionKind::Guard | ActionKind::SplashHop => unreachable!(),
        };

        let last_action = match action {
            ActionKind::Attack => player.last_attack_at,
            ActionKind::ArcSlash => player.last_arc_slash_at,
            _ => None,
        };
        let left = remaining(last_action, cooldown);
        if left > 0 {
            return ActionOutcome::rejected(
                RejectReason::Cooldown,
                cooldown_deadline(room_ms, left),
            );
        }

        if action == ActionKind::ArcSlash && player.sp < 8 {
            return ActionOutcome::rejected(
                RejectReason::Cooldown,
                cooldown_deadline(room_ms, 500),
            );
        }

        let player_x = player.x;
        let player_z = player.z;
        let effective_facing = if aim.is_finite() { aim } else { player.facing };

        let mut candidates: Vec<(usize, f32)> = self
            .monsters
            .iter()
            .enumerate()
            .filter(|(_, monster)| monster.respawn_at.is_none() && monster.hp > 0)
            .filter_map(|(index, monster)| {
                let dx = monster.x - player_x;
                let dz = monster.z - player_z;
                let dist = (dx * dx + dz * dz).sqrt();
                if dist > range {
                    return None;
                }
                let angle_to_target = dx.atan2(dz);
                let diff = angle_diff(angle_to_target, effective_facing);
                if diff <= half_arc {
                    Some((index, dist))
                } else {
                    None
                }
            })
            .collect();

        if candidates.is_empty() {
            let any_in_range = self.monsters.iter().any(|monster| {
                monster.respawn_at.is_none()
                    && monster.hp > 0
                    && (monster.x - player_x).hypot(monster.z - player_z) <= range
            });
            if any_in_range {
                return ActionOutcome::rejected(RejectReason::OutOfRange, 0);
            } else {
                return ActionOutcome::rejected(RejectReason::NoTarget, 0);
            }
        }

        candidates.sort_by(|a, b| a.1.total_cmp(&b.1));
        let targets: Vec<usize> = candidates
            .into_iter()
            .take(max_targets)
            .map(|(i, _)| i)
            .collect();

        let is_counter =
            action == ActionKind::Attack && player.perfect_counter_until_tick > self.tick;
        if is_counter {
            player.perfect_counter_until_tick = 0;
        }

        match action {
            ActionKind::Attack => {
                player.last_attack_at = Some(now);
                player.sp = player.sp.saturating_add(1).min(player.max_sp);
                self.pending_state_updates.insert(player_id);
            }
            ActionKind::ArcSlash => {
                player.last_arc_slash_at = Some(now);
                player.sp = player.sp.saturating_sub(8);
                self.pending_state_updates.insert(player_id);
            }
            _ => (),
        }

        let tag_members = player.party_id.and_then(|id|self.parties.get(&id)).map(|p|p.members.clone()).unwrap_or_else(|| BTreeSet::from([player_id]));
        let attacker_level = player.level;
        let mut kills = Vec::new();
        let mut new_events: Vec<CombatEvent> = Vec::new();

        for target_index in targets {
            let monster = &mut self.monsters[target_index];
            if monster.rank == crate::content::MonsterRank::Boss && !monster.contributions.contains_key(&player_id) && monster.contributions.len() >= crate::combat_rules::CONTRIBUTOR_LIMIT { continue; }
            let miss_chance=crate::combat_rules::miss_percent(attacker_level,u32::from(monster.level));
            let missed = miss_chance > 0 && miss_chance > (self.combat_roll)();
            let in_recovery_or_stagger =
                monster.state == monster_state::RECOVERY || monster.state == monster_state::STAGGER;
            let mult = if in_recovery_or_stagger { 1.5 } else { 1.0 };
            let mut damage = (base_damage as f32 * mult).round() as u16;
            if is_counter && !missed {
                damage = damage.saturating_mul(2);
                monster.state = monster_state::STAGGER;
                monster.state_ticks = 20;
            }

            if missed { damage=0; }
            let (target_id, world_x, world_z) = (monster.id, monster.x, monster.z);
            let (defeated, kill) = self.mutate_monster_damage(target_index, player_id, damage, &tag_members, now);
            if let Some(kill) = kill { kills.push(kill); }

            let event = CombatEvent {
                id: self.next_event_id,
                source_kind: 0,
                source_id: player_id,
                target_kind: 0,
                target_id,
                action,
                damage,
                flags: if missed { crate::combat_rules::MISS } else { u8::from(defeated) | if is_counter { 4 } else { 0 } | if is_counter || in_recovery_or_stagger { crate::combat_rules::CRIT } else { 0 } },
                world_x,
                world_z,
            };
            self.next_event_id = self.next_event_id.saturating_add(1);
            new_events.push(event);
        }

        for event in new_events {
            self.recent_events.push_back((event, self.tick + 10));
        }

        self.credit_defeats(kills);

        ActionOutcome::accepted(cooldown_deadline(room_ms, full_ms))
    }

    pub fn disconnect(&mut self, player_id: u32, epoch: u32) {
        if let Some(player) = self.players.get_mut(&player_id)
            && player.epoch == epoch
        {
            player.connected = false;
            player.input_x = 0.0;
            player.input_z = 0.0;
            player.dialogue = None;
            player.windmark_channel = None;
            player.disconnected_at = Some(Instant::now());
            player.dodge_ready_tick = 0;
            player.dodge_start_tick = 0;
            player.dodge_end_tick = 0;
            player.dodge_start_seq = 0;
            player.dodge_boost_end_seq = 0;
            player.guarding = false;
            player.guard_start_tick = 0;
            player.guard_end_tick = 0;
            player.perfect_counter_until_tick = 0;
        }
    }

    fn update_monsters(&mut self) {
        let players_alive: Vec<(u32, f32, f32)> = self
            .players
            .values()
            .filter(|p| p.connected && !p.down && p.hp > 0 && p.revive_until_tick <= self.tick)
            .map(|p| (p.id, p.x, p.z))
            .collect();

        for monster_index in 0..self.monsters.len() {
            let monster = &mut self.monsters[monster_index];
            if monster.hp == 0 || monster.respawn_at.is_some() {
                continue;
            }
            if let Some(tag)=&monster.tag {
                let owner_present=tag.members.iter().any(|id| self.players.get(id).is_some_and(|p|p.connected && !p.down && (p.x-monster.home_x).hypot(p.z-monster.home_z)<=monster.leash));
                if !owner_present || self.tick.saturating_sub(tag.last_damage_tick)>=crate::combat_rules::TAG_IDLE_TICKS {monster.reset_home();continue;}
            }
            if monster.rank==crate::content::MonsterRank::Boss && monster.target_player_id.is_some() {
                if let Some(id)=monster.target_player_id.filter(|id|monster.contributions.contains_key(id)||monster.contributions.len()<crate::combat_rules::CONTRIBUTOR_LIMIT) {let c=monster.contributions.entry(id).or_default();c.tank_ticks=c.tank_ticks.saturating_add(1);}
            }
            if monster.rank==crate::content::MonsterRank::Boss && !monster.contributions.is_empty() && !monster.contributions.keys().any(|id|self.players.get(id).is_some_and(|p|p.connected&&!p.down&&(p.x-monster.home_x).hypot(p.z-monster.home_z)<=monster.leash)) {monster.reset_home();continue;}
            let before = (monster.x, monster.z);
            let before_y=monster.y;
            if !monster.leash_polygon.is_empty() && !crate::grounded_city::overlaps_polygon(monster.x,monster.z,0.0,&monster.leash_polygon) {monster.reset_home();continue;}

            monster.ability_cooldown_ticks = monster.ability_cooldown_ticks.saturating_sub(1);

            match monster.state {
                monster_state::IDLE => {
                    let nearest_player = players_alive
                        .iter()
                        .map(|(id, px, pz)| {
                            let dist = (monster.x - px).hypot(monster.z - pz);
                            (*id, dist, *px, *pz)
                        })
                        .filter(|(_, dist, _, _)| *dist <= monster.aggro)
                        .min_by(|a, b| a.1.total_cmp(&b.1));

                    if let Some((target_id, _, _, _)) = nearest_player {
                        monster.target_player_id = Some(target_id);
                        monster.state = monster_state::APPROACH;
                        monster.state_ticks = 0;
                    } else if (monster.x - monster.home_x).hypot(monster.z - monster.home_z) > 0.5 {
                        let step = (monster.speed * 0.5) * FIXED_DT;
                        let dx = monster.home_x - monster.x;
                        let dz = monster.home_z - monster.z;
                        let dist = dx.hypot(dz).max(0.001);
                        monster.x += (dx / dist) * step;
                        monster.z += (dz / dist) * step;
                        monster.facing = dx.atan2(dz);
                    }
                }
                monster_state::APPROACH => {
                    let dist_from_home =
                        (monster.x - monster.home_x).hypot(monster.z - monster.home_z);
                    if dist_from_home > monster.leash {
                        monster.reset_home();
                        continue;
                    }

                    let target = monster
                        .target_player_id
                        .and_then(|id| players_alive.iter().find(|(pid, _, _)| *pid == id));

                    let Some(&(_, px, pz)) = target else {
                        monster.target_player_id = None;
                        monster.state = monster_state::IDLE;
                        continue;
                    };

                    if !monster.leash_polygon.is_empty()&&!crate::grounded_city::overlaps_polygon(px,pz,0.0,&monster.leash_polygon){monster.reset_home();continue;}
                    let p_dist = (px - monster.x).hypot(pz - monster.z);
                    if p_dist > monster.aggro * 1.5 {
                        monster.target_player_id = None;
                        monster.state = monster_state::IDLE;
                        continue;
                    }

                    if p_dist <= 2.5 && monster.ability_cooldown_ticks == 0 {
                        monster.state = monster_state::WINDUP;
                        monster.ability = 5;
                        monster.state_ticks = monster.splash_windup_ticks;
                        monster.target_x = px;
                        monster.target_z = pz;
                        monster.facing = (px - monster.x).atan2(pz - monster.z);
                    } else {
                        let step = monster.speed * FIXED_DT;
                        let dx = px - monster.x;
                        let dz = pz - monster.z;
                        let dist = p_dist.max(0.001);
                        monster.x += (dx / dist) * step;
                        monster.z += (dz / dist) * step;
                        monster.facing = dx.atan2(dz);
                    }
                }
                monster_state::WINDUP => {
                    monster.state_ticks = monster.state_ticks.saturating_sub(1);
                    if monster.state_ticks == 0 {
                        monster.state = monster_state::ACTIVE;
                        monster.state_ticks = monster.splash_active_ticks;
                    }
                }
                monster_state::ACTIVE => {
                    let next=move_monster_capsule(self.city_traversal.as_deref(),Position{x:monster.x,y:monster.y,z:monster.z},monster.target_x-monster.x,monster.target_z-monster.z,self.player_radius,self.player_height,&self.static_colliders,self.world_limit);
                    monster.x=next.x;monster.y=next.y;monster.z=next.z;
                    let target_x = monster.x;
                    let target_z = monster.z;
                    let monster_id = monster.id;
                    let splash_radius = monster.splash_radius;
                    let splash_damage = monster.splash_damage;
                    let mut monster_staggered = false;

                    let mut player_hits = Vec::new();
                    for (pid, player) in &mut self.players {
                        if !player.connected || player.down || player.hp == 0 {
                            continue;
                        }
                        let p_dist = (player.x - target_x).hypot(player.z - target_z);
                        if p_dist <= splash_radius {
                            let is_dodging = player.dodge_start_tick != 0
                                && self.tick >= player.dodge_start_tick
                                && self.tick <= player.dodge_end_tick;
                            if is_dodging {
                                player_hits.push((*pid, 0, 8, false, false));
                            } else if player.guarding {
                                let (guard_x,guard_z)=if (target_x-player.x).hypot(target_z-player.z)<0.001 {before}else{(target_x,target_z)};
                                let angle_to_monster =
                                    (guard_x - player.x).atan2(guard_z - player.z);
                                let in_cone = angle_diff(angle_to_monster, player.facing)
                                    <= std::f32::consts::FRAC_PI_2;
                                if in_cone {
                                    let guard_ticks =
                                        self.tick.saturating_sub(player.guard_start_tick);
                                    if guard_ticks <= self.combat.guard_perfect_ticks {
                                        monster_staggered = true;
                                        player_hits.push((*pid, 0, 4 | 2, false, true));
                                    } else {
                                        let red = self.combat.guard_reduction_pct as f32 / 100.0;
                                        let dmg =
                                            (splash_damage as f32 * (1.0 - red)).round() as u16;
                                        let defeated = player.hp <= dmg;
                                        player_hits.push((*pid, dmg, 2, defeated, false));
                                    }
                                } else {
                                    let dmg = splash_damage.saturating_sub(player.def).max(1);
                                    let defeated = player.hp <= dmg;
                                    player_hits.push((*pid, dmg, 0, defeated, false));
                                }
                            } else {
                                let dmg = splash_damage.saturating_sub(player.def).max(1);
                                let defeated = player.hp <= dmg;
                                player_hits.push((*pid, dmg, 0, defeated, false));
                            }
                        }
                    }

                    for (pid, mut dmg, mut flags, mut defeated, mut perfect) in player_hits {
                        let level=self.players.get(&pid).map(|p|p.level).unwrap_or(1);
                        if flags & 8 == 0 && crate::combat_rules::miss_percent(u32::from(self.monsters[monster_index].level),level) > 0 && crate::combat_rules::miss_percent(u32::from(self.monsters[monster_index].level),level) > (self.combat_roll)() {dmg=0;flags=crate::combat_rules::MISS;defeated=false;perfect=false;}
                        if self.monsters[monster_index].rank==crate::content::MonsterRank::Boss && dmg>0 && (self.monsters[monster_index].contributions.contains_key(&pid)||self.monsters[monster_index].contributions.len()<crate::combat_rules::CONTRIBUTOR_LIMIT) {
                            let c=self.monsters[monster_index].contributions.entry(pid).or_default();c.taken=c.taken.saturating_add(u64::from(dmg));
                        }
                        let (px, pz) = {
                            let player = self.players.get_mut(&pid).expect("player exists");
                            player.hp = player.hp.saturating_sub(dmg);
                            if dmg > 0 {
                                player.windmark_channel = None;
                            }
                            if perfect {
                                player.perfect_counter_until_tick = self.tick + 40;
                            }
                            if defeated {
                                player.down = true;
                                player.death_revision = player.death_revision.wrapping_add(1).max(1);
                                player.down_until_tick = u64::MAX;
                                player.input_queue.clear();
                                player.input_x = 0.0; player.input_z = 0.0;
                                player.guarding = false;
                            }
                            if dmg > 0 {
                                player.state_revision =
                                    player.state_revision.wrapping_add(1).max(1);
                                self.pending_state_updates.insert(pid);
                            }
                            (player.x, player.z)
                        };

                        let event = CombatEvent {
                            id: self.next_event_id,
                            source_kind: 1,
                            source_id: monster_id,
                            target_kind: 1,
                            target_id: pid,
                            action: ActionKind::SplashHop,
                            damage: dmg,
                            flags: flags | u8::from(defeated),
                            world_x: px,
                            world_z: pz,
                        };
                        self.next_event_id = self.next_event_id.saturating_add(1);
                        self.recent_events.push_back((event, self.tick + 10));
                        if defeated && let Some(notice)=self.death_state(pid) { self.pending_notices.push((pid,notice)); }
                    }

                    let monster = &mut self.monsters[monster_index];
                    monster.ability_cooldown_ticks = monster.splash_cooldown_duration_ticks;
                    if monster_staggered {
                        monster.state = monster_state::STAGGER;
                        monster.state_ticks = 20;
                    } else {
                        monster.state = monster_state::RECOVERY;
                        monster.state_ticks = monster.splash_recovery_ticks;
                    }
                }
                monster_state::RECOVERY => {
                    monster.state_ticks = monster.state_ticks.saturating_sub(1);
                    if monster.state_ticks == 0 {
                        monster.state = monster_state::IDLE;
                    }
                }
                monster_state::STAGGER => {
                    monster.state_ticks = monster.state_ticks.saturating_sub(1);
                    if monster.state_ticks == 0 {
                        monster.state = monster_state::IDLE;
                    }
                }
                _ => {
                    monster.state = monster_state::IDLE;
                }
            }
            let monster = &mut self.monsters[monster_index];
            let requested=(monster.x-before.0).hypot(monster.z-before.1);
            let next=move_monster_capsule(self.city_traversal.as_deref(),Position{x:before.0,y:before_y,z:before.1},monster.x-before.0,monster.z-before.1,self.player_radius,self.player_height,&self.static_colliders,self.world_limit);
            if !monster.leash_polygon.is_empty()&&!crate::grounded_city::overlaps_polygon(next.x,next.z,0.0,&monster.leash_polygon){monster.reset_home();continue;}
            monster.x=next.x;monster.y=next.y;monster.z=next.z;
            if monster.state==monster_state::APPROACH&&requested>0.005&&(monster.x-before.0).hypot(monster.z-before.1)<0.002 {monster.stuck_ticks=monster.stuck_ticks.saturating_add(1);}else{monster.stuck_ticks=0;}
            if monster.stuck_ticks>=40 {monster.reset_home();}

        }
    }

    pub fn advance(&mut self) -> Snapshot {
        self.tick = self.tick.saturating_add(1);
        self.advance_community();
        let now = Instant::now();
        for index in 0..self.monsters.len() {if self.monsters[index].rank==crate::content::MonsterRank::Boss && self.monsters[index].hp==0 && !self.monsters[index].rewarded {self.credit_boss(index);}}
        for monster in &mut self.monsters {
            if monster.respawn_at.is_some_and(|at| at <= now) && (monster.rank!=crate::content::MonsterRank::Boss || monster.rewarded) {
                monster.reset_home();
            }
        }

        for player in self.players.values_mut() {
            if !player.connected {
                continue;
            }

            if player.down {
                player.input_queue.clear();
                player.input_x = 0.0;
                player.input_z = 0.0;
                continue;
            }

            if player.guarding && self.tick >= player.guard_end_tick {
                player.guarding = false;
            }

            let mut applied_input = false;
            if let Some((sequence, x, z, facing, flags)) = player.input_queue.pop_front() {
                if x != 0.0 || z != 0.0 {
                    player.guarding = false;
                }
                player.input_x = x;
                player.input_z = z;
                player.facing = facing;
                player.last_input_seq = sequence;
                player.repeat_ticks = 0;
                applied_input = true;
                // Jump is an edge: it fires once, only while grounded.
                if self.city_traversal.is_none()
                    && flags & crate::wire::INPUT_FLAG_JUMP != 0
                    && player.grounded
                {
                    player.vy = self.jump_v;
                    player.grounded = false;
                }
                player.sprinting = flags & crate::wire::INPUT_FLAG_SPRINT != 0;
            } else if player.repeat_ticks < MAX_INPUT_REPEAT
                && (player.input_x != 0.0 || player.input_z != 0.0)
            {
                player.repeat_ticks += 1;
            } else {
                player.input_x = 0.0;
                player.input_z = 0.0;
                player.repeat_ticks = 0;
                player.sprinting = false;
            }
            // Timed power buffs fall off by tick; speed buffs multiply below.
            player
                .buffs
                .retain(|(_, _, expires_tick)| *expires_tick > self.tick);
            let speed_buff = player
                .buffs
                .iter()
                .filter(|(kind, _, _)| *kind == BUFF_SPEED)
                .map(|(_, mult, _)| *mult)
                .fold(1.0_f32, f32::max);
            // Speed follows the accepted input timeline; an older queued input
            // cannot gain dodge motion merely because the room timer started.
            // Invulnerability and cooldown remain on the authoritative clock.
            let dodging = player.dodge_start_seq != 0
                && player.last_input_seq > player.dodge_start_seq
                && player.last_input_seq <= player.dodge_boost_end_seq;
            let mut speed = self.player_speed * speed_buff;
            if dodging {
                speed *= self.combat.dodge_mult;
            }
            if player.sprinting {
                speed *= self.sprint_mult;
            }
            let world_limit = self.world_limit;
            if let Some(city) = &self.city_traversal {
                let next = city.move_capsule(
                    Position {
                        x: player.x,
                        y: player.y,
                        z: player.z,
                    },
                    player.input_x * speed * FIXED_DT,
                    player.input_z * speed * FIXED_DT,
                    self.player_radius,
                    self.player_height,
                    &self.static_colliders,
                    world_limit,
                );
                player.x = next.x;
                player.y = next.y;
                player.z = next.z;
                player.vy = 0.0;
                player.grounded = true;
            } else {
                (player.x, player.z) = move_capsule(
                    player.x,
                    player.z,
                    player.input_x * speed * FIXED_DT,
                    player.input_z * speed * FIXED_DT,
                    self.player_radius,
                    self.player_height,
                    &self.static_colliders,
                    world_limit,
                );
            }
            // Flat rooms retain jump physics. City mode is explicitly ground-only:
            // the XZ wire has no jump reconciliation and cannot claim air traversal.
            if !player.grounded {
                player.vy -= self.gravity * FIXED_DT;
                player.y += player.vy * FIXED_DT;
                if player.y <= 0.0 {
                    player.y = 0.0;
                    player.vy = 0.0;
                    player.grounded = true;
                }
            }
            if applied_input {
                player.last_input_x = player.x;
                player.last_input_z = player.z;
            }
            if self.tick % 40 == 0 && player.sp < player.max_sp && player.hp > 0 && !player.down {
                let regen = 1 + (player.allocated_int / 10).max(1);
                player.sp = player.sp.saturating_add(regen).min(player.max_sp);
                self.pending_state_updates.insert(player.id);
            }
        }

        self.sync_pets();
        self.advance_mage_casts();
        self.expire_durable_lookups();
        self.update_monsters();

        let quest_targets = self.p1_quest_targets.clone();
        let mut changed_players = Vec::new();
        let mut notices = Vec::new();
        for (player_id, player) in &mut self.players {
            let Some(mut channel) = player.windmark_channel.take() else {
                continue;
            };
            if !player.connected
                || (player.x - channel.start_x).hypot(player.z - channel.start_z) > 0.1
                || (player.x - channel.position.x).hypot(player.z - channel.position.z) > 2.0
            {
                notices.push((
                    *player_id,
                    crate::cold::NoticeMsg {
                        t: "notice".to_string(),
                        key: "windmark_channel_interrupted".to_string(),
                        params: serde_json::json!({ "marker": channel.marker }),
                    },
                ));
                continue;
            }
            channel.ticks_left = channel.ticks_left.saturating_sub(1);
            if channel.ticks_left > 0 {
                player.windmark_channel = Some(channel);
                continue;
            }
            player.activated_windmarks.insert(channel.marker.clone());
            player
                .quest_step_ticks
                .insert(channel.marker.clone(), self.tick);
            *player
                .quest_objectives
                .entry("windmark".to_string())
                .or_default() += 1;
            player.quest_objectives.insert(channel.marker.clone(), 1);
            refresh_quest_state(player, &quest_targets);
            player.quest_revision = player.quest_revision.wrapping_add(1).max(1);
            changed_players.push(*player_id);
            notices.push((
                *player_id,
                crate::cold::NoticeMsg {
                    t: "notice".to_string(),
                    key: "windmark_activated".to_string(),
                    params: serde_json::json!({ "marker": channel.marker }),
                },
            ));
        }
        self.pending_state_updates.extend(changed_players);
        self.pending_notices.extend(notices);
        self.prune_expired_sessions();
        self.expire_drops();
        self.tower_progress();
        self.sync_store();

        let players = self
            .players
            .values()
            .map(|player| PlayerSnapshot {
                id: player.id,
                x: player.x,
                z: player.z,
                y: player.y,
                facing: player.facing,
                hp: player.hp,
                max_hp: player.max_hp,
                connected: player.connected,
                down: player.down,
                dodging: player.dodge_start_tick != 0
                    && self.tick >= player.dodge_start_tick
                    && self.tick <= player.dodge_end_tick,
                guarding: player.guarding,
                anim: if player.down {
                    4
                } else if player.guarding {
                    3
                } else {
                    0
                },
            })
            .collect();

        let monsters = self
            .monsters
            .iter()
            .map(|monster| {
                let active = monster.respawn_at.is_none() && monster.hp > 0;
                MonsterSnapshot {
                    id: monster.id,
                    kind: monster.kind,
                    x: monster.x,
                    z: monster.z,
                    facing: monster.facing,
                    hp: monster.hp,
                    max_hp: monster.max_hp,
                    active,
                    flags: u8::from(active) | if monster.target_player_id.is_some() { 2 } else { 0 },
                    state: monster.state,
                    ability: monster.ability,
                    state_ticks: monster.state_ticks,
                    target_x: monster.target_x,
                    target_z: monster.target_z,
                    target_player_id: monster.target_player_id,
                }
            })
            .collect();

        self.recent_events
            .retain(|(_, expiry_tick)| *expiry_tick > self.tick);
        while self.recent_events.len() > MAX_RECENT_EVENTS {
            self.recent_events.pop_front();
        }
        let events = self
            .recent_events
            .iter()
            .map(|(event, _)| event.clone())
            .collect();

        let pets = self
            .pets
            .iter()
            .map(|pet| PetSnapshot {
                owner_id: pet.owner_id,
                x: pet.x,
                z: pet.z,
                kind: pet.kind,
                flags: 1,
            })
            .collect();

        Snapshot {
            tick: self.tick,
            ack_seq: 0,
            own_flags: 0,
            ack_x: 0.0,
            ack_z: 0.0,
            players,
            monsters,
            events,
            pets,
        }
    }

    /// Wire kind for an equipped pet cosmetic: 1 + index into the sorted
    /// economy pet ids (deterministic on both peers from the same bundle).
    fn pet_kind(&self, cosmetic_id: &str) -> Option<u8> {
        self.pet_kinds
            .iter()
            .position(|id| id == cosmetic_id)
            .filter(|index| *index < 254)
            .map(|index| (index + 1) as u8)
    }

    /// Spawn, despawn and walk cosmetic followers (v6 pet batch). Pets chase
    /// their owner until inside follow distance, sliding on collision like
    /// players; they never fight, collide with actors, or block movement.
    fn sync_pets(&mut self) {
        let mut wanted: Vec<(u32, f32, f32, u8)> = Vec::new();
        for player in self.players.values() {
            if !player.connected {
                continue;
            }
            let Some(cosmetic) = player.pet.as_deref() else {
                continue;
            };
            let Some(kind) = self.pet_kind(cosmetic) else {
                continue;
            };
            wanted.push((player.id, player.x, player.z, kind));
        }
        self.pets.retain(|pet| {
            wanted
                .iter()
                .any(|(id, _, _, kind)| *id == pet.owner_id && *kind == pet.kind)
        });
        for (owner_id, x, z, kind) in &wanted {
            if !self.pets.iter().any(|pet| pet.owner_id == *owner_id) {
                self.pets.push(Pet {
                    owner_id: *owner_id,
                    x: *x,
                    z: *z,
                    kind: *kind,
                });
            }
        }
        let follow = self.pet_follow_dist;
        let speed = self.player_speed * self.pet_speed_mult;
        let height = self.player_height;
        let limit = self.world_limit;
        let owners: HashMap<u32, (f32, f32)> =
            wanted.iter().map(|(id, x, z, _)| (*id, (*x, *z))).collect();
        for pet in self.pets.iter_mut() {
            let Some((ox, oz)) = owners.get(&pet.owner_id).copied() else {
                continue;
            };
            let dx = ox - pet.x;
            let dz = oz - pet.z;
            let dist = dx.hypot(dz);
            if dist <= follow {
                continue;
            }
            let step = (speed * FIXED_DT).min(dist - follow * 0.5);
            if step <= 0.0 {
                continue;
            }
            let (nx, nz) = if let Some(city) = &self.city_traversal {
                let y = city.height_at(pet.x, pet.z).unwrap_or(0.0);
                let next = city.move_capsule(
                    Position {
                        x: pet.x,
                        y,
                        z: pet.z,
                    },
                    dx / dist * step,
                    dz / dist * step,
                    0.2,
                    height,
                    &self.static_colliders,
                    limit,
                );
                (next.x, next.z)
            } else {
                move_capsule(
                    pet.x,
                    pet.z,
                    dx / dist * step,
                    dz / dist * step,
                    0.2,
                    height,
                    &self.static_colliders,
                    limit,
                )
            };
            pet.x = nx;
            pet.z = nz;
        }
    }

    fn prune_expired_sessions(&mut self) {
        self.prune_expired_sessions_at(Instant::now());
    }

    /// Wire the durable seam after construction (room layer). Worlds built
    /// directly in tests never attach and keep session-only behavior.
    pub fn attach_storage(
        &mut self,
        storage: StorageHandle,
        storage_events: mpsc::UnboundedSender<StorageEvent>,
    ) {
        self.storage = storage;
        self.storage_events = storage_events;
    }

    /// Durable-save outcomes, drained by the room loop every tick.
    pub fn handle_storage_event(&mut self, event: StorageEvent) {
        match event {
            StorageEvent::OperationChecked{session,token,result}=>self.complete_durable_lookup(session,token,result),
            StorageEvent::ExchangeFinished { id, accepted } => self.finish_exchange(&id, accepted),
            StorageEvent::ExchangeRetry { id } => self.retry_exchange(&id),
            StorageEvent::SaveRejected {
                session, record, ..
            } => {
                let Some(player_id) = self.sessions.get(&session).copied() else {
                    return;
                };
                let Some(player) = self.players.get_mut(&player_id) else {
                    return;
                };
                // A newer join claimed the character (second tab / device):
                // adopt the authoritative durable state, stop submitting
                // fenced saves from this world until it re-joins and
                // re-claims, and resync the client so the HUD shows the
                // winning wallet. The rejection's epoch belongs to the live
                // owner — this world never adopts it.
                player.durable_disabled = true;
                player.durable_dirty = false;
                apply_character_record(player, &record);
                player.synced_revision = Some(player.state_revision);
                self.pending_state_updates.insert(player_id);
            }
            StorageEvent::SaveAccepted { session } => {
                self.storage_degraded = false;
                if let Some(player_id) = self.sessions.get(&session).copied()
                    && let Some(player) = self.players.get_mut(&player_id)
                {
                    player.durable_dirty = false;
                }
            }
            StorageEvent::StorageDegraded { session } => {
                self.storage_degraded = true;
                // Bounded retry: re-push the record on a later tick so a
                // recovered database picks the write up (never per-tick).
                if let Some(player_id) = self.sessions.get(&session).copied()
                    && let Some(player) = self.players.get_mut(&player_id)
                {
                    player.durable_dirty = true;
                    player.durable_retry_at = self.tick + DURABLE_RETRY_TICKS;
                }
            }
            StorageEvent::OpPersisted {session,op_id} => {
                self.finish_durable_guard(session,&op_id);
                self.storage_degraded = false;
            }
            StorageEvent::OpReplayed {session,op_id,..} | StorageEvent::OpConflict {session,op_id} => {
                self.fail_durable_guard(session,&op_id);
            }
        }
    }

    fn prune_expired_sessions_at(&mut self, now: Instant) {
        let expired: Vec<u32> = self
            .players
            .values()
            .filter(|player| {
                !self.community_busy(player.id) && !player.connected
                    && player
                        .disconnected_at
                        .is_some_and(|time| now.saturating_duration_since(time) > RESUME_GRACE)
            })
            .map(|player| player.id)
            .collect();
        for player_id in expired {
            if let Some(player) = self.players.remove(&player_id) {
                self.community_forget(player_id);
                // Final flush so the shared store holds the latest wallet,
                // bag and quest record even if this instance dies now —
                // mirrored into durable storage (V5-12).
                let mut record = character_record_of(&player);
                record.generation = player.store_generation;
                  let owned=!player.durable_disabled && self.store.save_owned(player.session_id, &mut record,self.store_owner).is_some();
                if let Some(principal) = player.principal
                    && owned
                    && !player.durable_disabled
                {
                    let checkpoint = Checkpoint {
                        zone: self.zone_key.clone(),
                        x: player.x,
                        z: player.z,
                        hp: i32::from(player.hp),
                    };
                    self.storage.save_character(
                        principal,
                        player.session_id,
                        record,
                        Some(player.owner_epoch),
                        Some(checkpoint),
                        self.storage_events.clone(),
                    );
                }
                if let Some(runtime) = self.tower.as_mut()
                    && player.session_id == runtime.session
                {
                    // The bound session abandoned the tower: tear down the
                    // instance instead of leaking the slot against the cap.
                    runtime.done = true;
                }
                self.sessions.remove(&player.session_id);
                if let Some(party_id) = player.party_id {
                    let mut remove_party = None;
                    if let Some(party) = self.parties.get_mut(&party_id) {
                        party.members.remove(&player_id);
                        if party.leader == player_id {
                            party.leader = party.members.iter().next().copied().unwrap_or(0);
                        }
                        party.revision = party.revision.wrapping_add(1).max(1);
                        if party.members.is_empty() {
                            remove_party = Some(party.code.clone());
                        } else {
                            self.pending_party_updates
                                .extend(party.members.iter().copied());
                        }
                    }
                    if let Some(code) = remove_party {
                        self.parties.remove(&party_id);
                        self.party_codes.remove(&code);
                    }
                }
            }
        }
    }
}

impl World {
    /// The tower floor this instance is on (0 outside tower mode).
    pub fn current_floor(&self) -> u16 {
        self.tower.as_ref().map_or(0, |runtime| runtime.floor)
    }

    /// True exactly once per tower instance when it must be torn down: the
    /// 100th floor was cleared, or the bound session abandoned the instance.
    pub fn take_tower_completed(&mut self) -> bool {
        match self.tower.as_mut() {
            Some(runtime) if runtime.done && !runtime.done_taken => {
                runtime.done_taken = true;
                true
            }
            _ => false,
        }
    }

    /// Floor milestones reached since the last drain (each new floor entered,
    /// and `max_floor` on completion); the room thread forwards them so the
    /// session's best floor persists in the auth manager.
    pub fn take_tower_floor_events(&mut self) -> Vec<u16> {
        std::mem::take(&mut self.tower_floor_events)
    }

    /// Spawn the current floor's monster ring: `count(floor)` copies of the
    /// tower enemy scaled by the floor curves, no respawn, ids from the
    /// instance-wide counter.
    fn tower_spawn_floor(&mut self) {
        let (enemy, count, hp_mult, exp_mult) = {
            let Some(runtime) = self.tower.as_ref() else {
                return;
            };
            let floor = runtime.floor;
            (
                runtime.enemy.clone(),
                usize::from(runtime.table.count(floor)).clamp(1, MAX_MONSTERS),
                runtime.table.hp_mult(floor),
                runtime.table.exp_mult(floor),
            )
        };
        let hp = ((enemy.hp as f32 * hp_mult)
            .round()
            .min(u32::MAX as f32)) as u32;
        let exp = (enemy.exp as f32 * exp_mult).round() as u32;
        let mut next_id = self.next_monster_id;
        self.monsters.clear();
        // Kill credit reads the scaled exp from the per-kind table.
        self.enemy_exp.insert(enemy.kind, exp);
        for index in 0..count {
            let angle = (index as f32) * std::f32::consts::TAU / count as f32;
            let x = TOWER_ARENA_RADIUS * angle.cos();
            let z = TOWER_ARENA_RADIUS * angle.sin();
            self.monsters.push(Monster {
                tag: None, rewarded: false, reward_prepared:false, pending_rewards:BTreeMap::new(), encounter_id: uuid::Uuid::new_v4(), contributions: BTreeMap::new(), phase: crate::combat_rules::EncounterPhase::Dormant,
                id: next_id,
                kind: enemy.kind,
                        level: enemy.level,
                        rank: enemy.rank,
                x,
                z,
                home_x: x,
                home_z: z,
                y:0.0,home_y:0.0,stuck_ticks:0,leash_polygon:vec![],
                facing: 0.0,
                hp,
                max_hp: hp,
                speed: enemy.speed,
                aggro: enemy.aggro,
                leash: enemy.leash,
                splash_radius: enemy.splash_radius,
                splash_damage: enemy.splash_damage,
                splash_windup_ticks: enemy.splash_windup_ms / 50,
                splash_active_ticks: enemy.splash_active_ms / 50,
                splash_recovery_ticks: enemy.splash_recovery_ms / 50,
                splash_cooldown_duration_ticks: enemy.splash_cooldown_ms / 50,
                respawn_at: None,
                state: monster_state::IDLE,
                ability: 0,
                state_ticks: 0,
                target_x: x,
                target_z: z,
                target_player_id: None,
                ability_cooldown_ticks: 0,
            });
            next_id = next_id.saturating_add(1);
        }
        self.next_monster_id = next_id;
    }

    /// Tower-only: when every monster of the floor is defeated, pay the floor
    /// gold (and the milestone box, full-bag rules applying) into the shared
    /// wallet and start the advance grace.
    fn tower_check_clear(&mut self) {
        let Some(runtime) = self.tower.as_ref() else {
            return;
        };
        if runtime.phase != TowerPhase::Fighting {
            return;
        }
        if self.monsters.iter().any(|monster| monster.hp > 0) {
            return;
        }
        let floor = runtime.floor;
        let session = runtime.session;
        let reward_gold = runtime.table.reward_gold(floor);
        let box_item = runtime.table.box_item.clone();
        let box_every_floors = runtime.table.box_every_floors;
        {
            let runtime = self.tower.as_mut().expect("tower runtime checked above");
            runtime.phase = TowerPhase::Cleared;
            runtime.advance_at_tick = self.tick + TOWER_ADVANCE_TICKS;
        }
        if let Some(&player_id) = self.sessions.get(&session) {
            if let Some(player) = self.players.get_mut(&player_id) {
                player.gold = player.gold.saturating_add(reward_gold);
                // Full-bag rule: a skipped box is dropped, never destructive.
                if floor % box_every_floors == 0 && bag_has_room(&player.bag, &[box_item.as_str()])
                {
                    *player.bag.entry(box_item).or_default() += 1;
                }
                bump_state_revision(player);
            }
            // Land the reward in the shared wallet immediately, not just on
            // the next tick sync.
            self.push_store(player_id);
            self.pending_state_updates.insert(player_id);
        }
    }

    /// Tower-only tick hook: after the cleared-floor grace, spawn the next
    /// floor; past the top, pay the final reward and complete the instance.
    fn tower_progress(&mut self) {
        let advance = {
            let Some(runtime) = self.tower.as_ref() else {
                return;
            };
            if runtime.phase != TowerPhase::Cleared || self.tick < runtime.advance_at_tick {
                return;
            }
            if runtime.floor >= runtime.table.max_floor {
                None
            } else {
                Some(runtime.floor + 1)
            }
        };
        let session = self
            .tower
            .as_ref()
            .expect("tower runtime checked above")
            .session;
        match advance {
            None => {
                let (final_reward, box_item, max_floor) = {
                    let runtime = self.tower.as_ref().expect("tower runtime checked above");
                    (
                        runtime.table.final_reward.clone(),
                        runtime.table.box_item.clone(),
                        runtime.table.max_floor,
                    )
                };
                if let Some(&player_id) = self.sessions.get(&session) {
                    if let Some(player) = self.players.get_mut(&player_id) {
                        player.gold = player.gold.saturating_add(final_reward.gold);
                        player.coin = player.coin.saturating_add(final_reward.coin);
                        for _ in 0..final_reward.boxes {
                            // Same full-bag rule: dropped boxes never destroy
                            // existing loot.
                            if bag_has_room(&player.bag, &[box_item.as_str()]) {
                                *player.bag.entry(box_item.clone()).or_default() += 1;
                            }
                        }
                        bump_state_revision(player);
                    }
                    self.push_store(player_id);
                    self.pending_state_updates.insert(player_id);
                    self.pending_notices.push((
                        player_id,
                        crate::cold::NoticeMsg {
                            t: "notice".to_string(),
                            key: "tower_complete".to_string(),
                            params: serde_json::json!({ "floor": max_floor }),
                        },
                    ));
                }
                self.tower_floor_events.push(max_floor);
                let runtime = self.tower.as_mut().expect("tower runtime checked above");
                runtime.phase = TowerPhase::Complete;
                runtime.done = true;
            }
            Some(next_floor) => {
                {
                    let runtime = self.tower.as_mut().expect("tower runtime checked above");
                    runtime.floor = next_floor;
                }
                self.tower_spawn_floor();
                if let Some(&player_id) = self.sessions.get(&session) {
                    self.pending_notices.push((
                        player_id,
                        crate::cold::NoticeMsg {
                            t: "notice".to_string(),
                            key: "tower_floor".to_string(),
                            params: serde_json::json!({ "floor": next_floor }),
                        },
                    ));
                }
                self.tower_floor_events.push(next_floor);
                let runtime = self.tower.as_mut().expect("tower runtime checked above");
                runtime.phase = TowerPhase::Fighting;
            }
        }
    }
}

fn move_monster_capsule(city:Option<&GroundedCity>,mut p:Position,dx:f32,dz:f32,radius:f32,height:f32,boxes:&[StaticCollider],limit:f32)->Position {
    let steps=((dx.hypot(dz)/0.75).ceil() as usize).clamp(1,8);
    for _ in 0..steps {if let Some(city)=city {p=city.move_capsule(p,dx/steps as f32,dz/steps as f32,radius,height,boxes,limit);}else{(p.x,p.z)=move_capsule(p.x,p.z,dx/steps as f32,dz/steps as f32,radius,height,boxes,limit);}}
    p
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_session_id(value: u64) -> [u8; 32] {
        let mut session_id = [0_u8; 32];
        session_id[..8].copy_from_slice(&value.to_le_bytes());
        session_id
    }

    fn test_store() -> crate::character::SharedCharacterStore {
        crate::character::CharacterStore::shared()
    }

    fn test_world() -> World {
        World::new(&crate::content::test_content(), test_store())
    }

    fn isolate_city_route_from_combat(world: &mut World) {
        for monster in &mut world.monsters {
            monster.x = 250.0;
            monster.z = 250.0;
            monster.home_x = 250.0;
            monster.home_z = 250.0;
            monster.target_x = 250.0;
            monster.target_z = 250.0;
        }
    }

    fn walk_city_waypoints(world: &mut World, welcome: &Welcome, points: &[(f32, f32)]) {
        let mut sequence = 1;
        let step = world.player_speed * FIXED_DT;
        for &(target_x, target_z) in points {
            let player = &world.players[&welcome.player_id];
            let budget =
                (((target_x - player.x).hypot(target_z - player.z) / step).ceil() as u64) + 32;
            for _ in 0..budget {
                let player = &world.players[&welcome.player_id];
                let dx = target_x - player.x;
                let dz = target_z - player.z;
                let distance = dx.hypot(dz);
                if distance <= 0.005 {
                    break;
                }
                let scale = (distance / step).min(1.0) / distance;
                assert!(world.update_input(
                    welcome.player_id,
                    welcome.epoch,
                    sequence,
                    dx * scale,
                    dz * scale,
                    0.0,
                    0
                ));
                sequence += 1;
                world.advance();
                let player = &world.players[&welcome.player_id];
                let city = world
                    .city_traversal
                    .as_ref()
                    .expect("admitted city traversal");
                let support = city
                    .height_at(player.x, player.z)
                    .expect("route has authored support");
                assert!(
                    (player.y - support).abs() < 0.0001,
                    "feet/support divergence at ({},{})",
                    player.x,
                    player.z
                );
                assert!(
                    city.position_is_clear(
                        player.x,
                        player.y,
                        player.z,
                        world.player_radius,
                        world.player_height,
                        &world.static_colliders
                    ),
                    "route penetrated a semantic blocker at ({},{})",
                    player.x,
                    player.z
                );
            }
            let player = &world.players[&welcome.player_id];
            assert!(
                (target_x - player.x).hypot(target_z - player.z) <= 0.005,
                "city route stopped at ({},{}), target ({target_x},{target_z})",
                player.x,
                player.z
            );
        }
    }

    #[test]
    fn authored_city_support_is_shared_and_used_for_spawn_input_dash_and_pet() {
        let mut content = crate::content::test_content();
        let mut input = crate::grounded_city::tests::fixture();
        for vertex in &mut input.surfaces[0].vertices {
            vertex[1] = 3.0;
        }
        let field = Arc::new(GroundedCity::parse(&input, content.zone_half_extent).unwrap());
        content.zone_city_traversal = Some(field.clone());
        let mut world = World::new(&content, test_store());
        let other = World::new(&content, test_store());
        assert!(Arc::ptr_eq(
            world.city_traversal.as_ref().unwrap(),
            other.city_traversal.as_ref().unwrap()
        ));
        let welcome = world.join(test_session_id(879)).unwrap();
        assert_eq!(world.players[&welcome.player_id].y, 3.0);
        assert!(world.update_input(
            welcome.player_id,
            welcome.epoch,
            1,
            1.0,
            0.0,
            0.0,
            crate::wire::INPUT_FLAG_JUMP
        ));
        world.advance();
        let player = &world.players[&welcome.player_id];
        assert!(player.x > welcome.x);
        assert_eq!(player.y, 3.0);
        assert!(player.grounded);
        assert_eq!(player.vy, 0.0);
        let player = world.players.get_mut(&welcome.player_id).unwrap();
        player.dodge_start_tick = world.tick;
        player.dodge_end_tick = world.tick + 5;
        let previous_x = player.x;
        world.advance();
        assert!(world.players[&welcome.player_id].x > previous_x);
        assert_eq!(world.players[&welcome.player_id].y, 3.0);
        let pet_id = world.pet_kinds[0].clone();
        world.players.get_mut(&welcome.player_id).unwrap().pet = Some(pet_id);
        world.advance();
        assert_eq!(world.pets.len(), 1);
        world.pets[0].x = world.players[&welcome.player_id].x - 3.0;
        let old_pet_x = world.pets[0].x;
        world.advance();
        assert!(world.pets[0].x > old_pet_x);
        let tower = World::new_tower(&content, test_store(), test_session_id(879), 1);
        assert!(tower.city_traversal.is_none());
    }

    #[test]
    fn flat_room_jump_physics_remains_enabled_without_city_traversal() {
        let mut content = crate::content::test_content();
        content.zone_city_traversal = None;
        let mut world = World::new(&content, test_store());
        let welcome = world.join(test_session_id(880)).unwrap();
        assert!(world.city_traversal.is_none());
        assert!(world.update_input(
            welcome.player_id,
            welcome.epoch,
            1,
            0.0,
            0.0,
            0.0,
            crate::wire::INPUT_FLAG_JUMP
        ));
        world.advance();
        let player = &world.players[&welcome.player_id];
        assert!(player.y > 0.0 && player.vy > 0.0);
        assert!(!player.grounded);
    }

    fn world_with_splash_winding_up() -> (World, Welcome) {
        let mut world = test_world();
        let welcome = world.join(test_session_id(88)).expect("player joins");
        for monster in &mut world.monsters {
            monster.hp = 0;
        }
        let monster = &mut world.monsters[0];
        monster.hp = monster.max_hp;
        monster.x = 10.0;
        monster.z = 10.0;
        monster.home_x = 10.0;
        monster.home_z = 10.0;
        monster.target_x = 10.0;
        monster.target_z = 10.0;
        let player = world.players.get_mut(&welcome.player_id).unwrap();
        player.x = 9.0;
        player.z = 10.0;

        world.advance(); // Idle -> approach
        world.advance(); // Approach -> 900 ms windup
        assert_eq!(world.monsters[0].state, monster_state::WINDUP);
        (world, welcome)
    }

    #[test]
    fn puddlekin_splash_damage_is_server_owned_and_resyncs_hp() {
        let (mut world, welcome) = world_with_splash_winding_up();
        let mut impact = None;
        for _ in 0..19 {
            let snapshot = world.advance();
            if snapshot
                .events
                .iter()
                .any(|event| event.action == ActionKind::SplashHop)
            {
                impact = Some(snapshot);
            }
        }

        let snapshot = impact.expect("windup produces an impact event");
        let event = snapshot
            .events
            .iter()
            .find(|event| event.action == ActionKind::SplashHop)
            .unwrap();
        assert_eq!(
            (event.source_kind, event.target_kind, event.target_id),
            (1, 1, welcome.player_id)
        );
        assert_eq!(event.damage, 15, "18 splash minus DEF 3 (VIT/2)");
        assert_eq!(world.players[&welcome.player_id].hp, 145);
        assert!(
            world
                .take_pending_state_updates()
                .contains(&welcome.player_id)
        );
        assert_eq!(world.character_state(welcome.player_id).unwrap().hp, 145);
        let impact_id = event.id;
        let (snapshot_tx, snapshot_rx) = tokio::sync::watch::channel(snapshot.clone());
        for _ in 0..9 {
            let replay = world.advance();
            assert!(replay.events.iter().any(|event| event.id == impact_id));
            snapshot_tx
                .send(replay)
                .expect("paused writer slot stays connected");
        }
        assert!(
            snapshot_rx
                .borrow()
                .events
                .iter()
                .any(|event| event.id == impact_id)
        );
        let expired = world.advance();
        snapshot_tx
            .send(expired.clone())
            .expect("paused writer slot stays connected");
        assert!(!expired.events.iter().any(|event| event.id == impact_id));
        assert!(
            !snapshot_rx
                .borrow()
                .events
                .iter()
                .any(|event| event.id == impact_id)
        );
    }

    #[test]
    fn quickstep_avoids_splash_on_the_server_tick_window() {
        let (mut world, welcome) = world_with_splash_winding_up();
        for _ in 0..13 {
            world.advance();
        }
        assert_eq!(world.monsters[0].state_ticks, 5);
        let outcome = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            1,
            ActionKind::Dodge,
            0.0,
            0,
            world.tick() as u32,
        );
        assert!(outcome.accepted);

        let mut evade = None;
        for _ in 0..6 {
            let snapshot = world.advance();
            if snapshot
                .events
                .iter()
                .any(|event| event.flags & (1 << 3) != 0)
            {
                evade = Some(snapshot);
            }
        }
        let snapshot = evade.expect("active Quickstep emits an evade event");
        assert_eq!(world.players[&welcome.player_id].hp, 160);
        assert!(
            snapshot
                .players
                .iter()
                .any(|player| player.id == welcome.player_id && player.dodging)
        );
        let after_window = world.advance();
        assert!(
            after_window
                .players
                .iter()
                .any(|player| player.id == welcome.player_id && !player.dodging)
        );
    }

    #[test]
    fn quickstep_survives_a_150ms_round_trip_command_delay_in_100_scripted_trials() {
        for trial in 0..100 {
            let (mut world, welcome) = world_with_splash_winding_up();
            for _ in 0..11 {
                world.advance();
            }
            assert_eq!(world.monsters[0].state_ticks, 7);

            // The warning snapshot is observed with 7 ticks left. A 150 ms
            // round trip is conservatively rounded up to three 50 ms ticks
            // before the dodge command reaches the world owner.
            for _ in 0..3 {
                world.advance();
            }
            let outcome = world.apply_action(
                welcome.player_id,
                welcome.epoch,
                1,
                ActionKind::Dodge,
                0.0,
                0,
                world.tick() as u32,
            );
            assert!(
                outcome.accepted,
                "trial {trial}: dodge is accepted in the window"
            );

            let mut evaded = false;
            for _ in 0..5 {
                let snapshot = world.advance();
                evaded |= snapshot.events.iter().any(|event| {
                    event.action == ActionKind::SplashHop && event.flags & (1 << 3) != 0
                });
            }
            assert!(evaded, "trial {trial}: 150 ms round trip avoids Splash Hop");
            assert_eq!(
                world.players[&welcome.player_id].hp, 160,
                "trial {trial}: no splash damage (full derived HP)"
            );
        }
    }

    #[test]
    fn perfect_guard_deflects_splash_and_opens_a_counter() {
        let (mut world, welcome) = world_with_splash_winding_up();
        for _ in 0..13 {
            world.advance();
        }
        let outcome = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            1,
            ActionKind::Guard,
            0.0,
            0,
            world.tick() as u32,
        );
        assert!(outcome.accepted);

        let mut deflect = None;
        for _ in 0..6 {
            let snapshot = world.advance();
            if snapshot
                .events
                .iter()
                .any(|event| event.flags & (1 << 2) != 0)
            {
                deflect = Some(snapshot);
            }
        }
        let snapshot = deflect.expect("perfect guard emits a deflect event");
        let event = snapshot
            .events
            .iter()
            .find(|event| event.flags & (1 << 2) != 0)
            .unwrap();
        assert_eq!(event.damage, 0);
        assert_eq!(world.players[&welcome.player_id].hp, 160);
        assert_eq!(world.monsters[0].state, monster_state::STAGGER);
    }

    fn connected_flag(world: &mut World, player_id: u32) -> Option<bool> {
        world.advance();
        world
            .players
            .values()
            .find(|player| player.id == player_id)
            .map(|player| player.connected)
    }

    #[test]
    fn disconnect_with_a_stale_epoch_is_a_no_op() {
        // R4: cleanup fenced with the wrong epoch must not disturb the player.
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("join");
        world.disconnect(welcome.player_id, welcome.epoch.wrapping_add(1));
        assert_eq!(connected_flag(&mut world, welcome.player_id), Some(true));
        world.disconnect(welcome.player_id, welcome.epoch);
        assert_eq!(connected_flag(&mut world, welcome.player_id), Some(false));
    }

    #[test]
    fn rejoin_while_connected_takes_over_with_a_new_epoch() {
        // R5: no session_active lockout; the epoch bump invalidates the old
        // socket's commands and cleanup.
        let mut world = test_world();
        let session = test_session_id(1);
        let first = world.join(session).expect("join");
        let second = world.join(session).expect("takeover");
        assert_eq!(second.player_id, first.player_id);
        assert!(second.epoch > first.epoch);
        // Old-epoch input and disconnect are both fenced out.
        assert!(!world.update_input(first.player_id, first.epoch, 1, 1.0, 0.0, 0.0, 0));
        world.disconnect(first.player_id, first.epoch);
        assert_eq!(connected_flag(&mut world, first.player_id), Some(true));
        // New-epoch input flows again.
        assert!(world.update_input(second.player_id, second.epoch, 1, 1.0, 0.0, 0.0, 0));
    }

    #[test]
    fn input_queue_applies_one_per_tick_and_acks_on_apply() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        assert!(world.update_input(welcome.player_id, welcome.epoch, 1, 1.0, 0.0, 0.0, 0));
        assert!(world.update_input(welcome.player_id, welcome.epoch, 2, 1.0, 0.0, 0.0, 0));
        assert!(world.update_input(welcome.player_id, welcome.epoch, 3, 1.0, 0.0, 0.0, 0));
        // Nothing applied yet: ack is still zero before the first tick.
        assert_eq!(world.last_input_seq(welcome.player_id), 0);
        world.advance();
        assert_eq!(world.last_input_seq(welcome.player_id), 1);
        world.advance();
        assert_eq!(world.last_input_seq(welcome.player_id), 2);
        world.advance();
        assert_eq!(world.last_input_seq(welcome.player_id), 3);
        let ack_position = world.last_input_position(welcome.player_id).unwrap();
        world.advance();
        let repeated = world.last_input_position(welcome.player_id).unwrap();
        assert_eq!(repeated, ack_position);
        assert!(world.players[&welcome.player_id].x > repeated.0);
    }

    #[test]
    fn input_queue_caps_at_three_oldest_dropped() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        for sequence in 1..=5 {
            assert!(world.update_input(
                welcome.player_id,
                welcome.epoch,
                sequence,
                1.0,
                0.0,
                0.0,
                0
            ));
        }
        world.advance();
        assert_eq!(world.last_input_seq(welcome.player_id), 3);
        world.advance();
        assert_eq!(world.last_input_seq(welcome.player_id), 4);
        world.advance();
        // Sequences 1-2 were dropped as oldest; the rest apply one per tick.
        assert_eq!(world.last_input_seq(welcome.player_id), 5);
    }

    #[test]
    fn missing_inputs_repeat_five_ticks_then_stop() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        let start_x = welcome.x;
        assert!(world.update_input(welcome.player_id, welcome.epoch, 1, 1.0, 0.0, 0.0, 0));
        let mut positions = Vec::new();
        for _ in 0..8 {
            world.advance();
            positions.push(
                world
                    .players
                    .get(&welcome.player_id)
                    .expect("player present")
                    .x,
            );
        }
        // One apply + five repeats move; the 7th and 8th ticks hold still.
        assert!(positions[0] > start_x);
        assert!(positions[5] > positions[0]);
        assert_eq!(positions[6], positions[5]);
        assert_eq!(positions[7], positions[6]);
    }

    #[test]
    fn world_tuning_comes_from_the_bundle() {
        let world = test_world();
        assert_eq!(world.player_hp, 100);
        assert!((world.player_speed - 4.5).abs() < f32::EPSILON);
        assert_eq!(world.combat.attack_cooldown, Duration::from_millis(400));
        assert_eq!(world.combat.arc_damage, 45);
        // P4 plus the two authored southbound terrain cells add thirteen field spawns.
        assert_eq!(world.monsters.len(), 13);
        assert!(
            world
                .monsters
                .iter()
                .all(|monster| [1, 2, 3, 4].contains(&monster.kind))
        );
    }

    #[test]
    fn http_seed_template_matches_the_world_first_join_seed() {
        let content = crate::content::test_content();
        let world = test_world();
        let from_world = world.seed_character_record();
        let from_fn = character_record_seed(&content);
        assert_eq!(from_world.gold, from_fn.gold);
        assert_eq!(from_world.coin, from_fn.coin);
        assert_eq!(from_world.level, from_fn.level);
        assert_eq!(from_world.bag, from_fn.bag);
        assert_eq!(from_world.quest_revision, from_fn.quest_revision);
        assert_eq!(from_world.quest_state, from_fn.quest_state);
        assert_eq!(from_world.quest_objectives, from_fn.quest_objectives);
        assert_eq!(from_world.state_revision, from_fn.state_revision);
    }

    #[test]
    fn joining_stamps_the_stable_identity_and_character_state_carries_it() {
        let mut session = [0_u8; 32];
        session[0] = 0xa1;
        session[1] = 0xb2;
        session[2] = 0xc3;
        session[3] = 0xd4;
        session[30] = 0x12;
        session[31] = 0x34;
        let mut world = test_world();
        let welcome = world.join(session).expect("first join seeds the record");
        assert_eq!(
            world.player_name(welcome.player_id).as_deref(),
            Some("Traveler-1234")
        );
        let state = world.character_state(welcome.player_id).expect("state");
        assert_eq!(state.handle, "a1b2c3d4");
        assert_eq!(state.name, "Traveler-1234");

        // Expire the player fully, then rejoin: the identity is seed-once in
        // the shared store and survives the fresh spawn.
        world.disconnect(welcome.player_id, welcome.epoch);
        world.prune_expired_sessions_at(Instant::now() + RESUME_GRACE + Duration::from_secs(1));
        assert!(!world.sessions.contains_key(&session));
        let rejoin = world.join(session).expect("rejoin after expiry");
        let state = world.character_state(rejoin.player_id).expect("state");
        assert_eq!(state.handle, "a1b2c3d4");
        assert_eq!(state.name, "Traveler-1234");
    }

    #[test]
    fn movement_is_server_integrated_and_axes_are_normalized() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        assert!(world.update_input(welcome.player_id, welcome.epoch, 1, 1.0, 1.0, 0.0, 0));
        let snapshot = world.advance();
        let player = snapshot
            .players
            .iter()
            .find(|p| p.id == welcome.player_id)
            .unwrap();
        let distance = ((player.x - welcome.x).powi(2) + (player.z - welcome.z).powi(2)).sqrt();
        assert!((distance - world.player_speed * FIXED_DT).abs() < 0.001);
    }

    #[test]
    fn spawn_slots_reuse_bounded_positions_across_256_expired_sessions() {
        let mut world = test_world();
        let mut previous_id = 0;
        let mut first_position = None;

        for cycle in 0..256 {
            let session_id = test_session_id(cycle as u64 + 1);
            let welcome = world
                .join(session_id)
                .expect("a free spawn slot is available");
            let position = (welcome.x, welcome.z);
            assert!(welcome.player_id > previous_id);
            previous_id = welcome.player_id;
            assert!(welcome.x.abs() <= world.world_limit - world.player_radius);
            assert!(welcome.z.abs() <= world.world_limit - world.player_radius);
            assert!(capsule_position_is_clear(
                welcome.x,
                welcome.z,
                world.player_radius,
                world.player_height,
                &world.static_colliders,
            ));
            assert_eq!(world.players[&welcome.player_id].spawn_slot, 0);
            assert_eq!(first_position.get_or_insert(position), &position);

            if cycle < 255 {
                world.disconnect(welcome.player_id, welcome.epoch);
                let disconnected_at = world.players[&welcome.player_id]
                    .disconnected_at
                    .expect("disconnect timestamp is recorded");
                world.prune_expired_sessions_at(
                    disconnected_at + RESUME_GRACE + Duration::from_millis(1),
                );
                assert!(!world.players.contains_key(&welcome.player_id));
                assert!(!world.sessions.contains_key(&session_id));
            }
        }
    }

    #[test]
    fn concurrent_players_receive_unique_bounded_clear_spawn_slots() {
        let mut world = test_world();
        let welcomes: Vec<_> = (0..MAX_PLAYERS)
            .map(|index| {
                world
                    .join(test_session_id(index as u64 + 1))
                    .expect("all room slots are available")
            })
            .collect();

        for (index, welcome) in welcomes.iter().enumerate() {
            assert!(welcome.x.abs() <= world.world_limit - world.player_radius);
            assert!(welcome.z.abs() <= world.world_limit - world.player_radius);
            assert!(capsule_position_is_clear(
                welcome.x,
                welcome.z,
                world.player_radius,
                world.player_height,
                &world.static_colliders,
            ));
            for other in welcomes.iter().skip(index + 1) {
                let distance = (welcome.x - other.x).hypot(welcome.z - other.z);
                assert!(distance > 2.0 * world.player_radius);
            }
        }
        assert_eq!(world.join(test_session_id(MAX_PLAYERS as u64 + 1)).unwrap_err(), "room_full");
    }

    #[test]
    fn authoritative_player_can_walk_from_spawn_through_the_city_gate() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        assert_eq!((welcome.x, welcome.z), (-3.0, -3.0));
        assert_eq!(
            world.static_colliders.len(),
            24,
            "Sunmeadow props remain active after the two legacy gate boxes retire"
        );
        assert_eq!(
            world.city_traversal.as_ref().unwrap().stats.blocker_count,
            401
        );
        isolate_city_route_from_combat(&mut world);
        // The gate leads beside an actual canal: use its dry east-bank apron.
        walk_city_waypoints(&mut world, &welcome, &[(10.1, -2.0), (10.1, 40.0)]);

        let player = &world.players[&welcome.player_id];
        assert!(
            player.z > 24.0 + world.player_radius,
            "player stopped before gate: z={}",
            player.z
        );
        assert!(capsule_position_is_clear(
            player.x,
            player.z,
            world.player_radius,
            world.player_height,
            &world.static_colliders,
        ));
    }

    #[test]
    fn southbound_cells_are_flat_reachable_and_authored_trees_block_movement() {
        let world = test_world();
        assert_eq!(world.zone_half_extent(), 308.0);
        assert_eq!(world.static_colliders.len(), 24);
        let mut x = -3.0;
        let mut z = -3.0;
        for _ in 0..556 {
            (x, z) = move_capsule(
                x,
                z,
                0.0,
                -0.225,
                world.player_radius,
                world.player_height,
                &world.static_colliders,
                world.world_limit,
            );
        }
        assert!(z < -127.0, "southbound route stopped at z={z}");
        assert!(capsule_position_is_clear(
            x,
            z,
            world.player_radius,
            world.player_height,
            &world.static_colliders,
        ));

        let (_, tree_stop_z) = move_capsule(
            -23.0,
            -75.0,
            0.0,
            -3.0,
            world.player_radius,
            world.player_height,
            &world.static_colliders,
            world.world_limit,
        );
        assert!(
            tree_stop_z > -77.1 && tree_stop_z < -76.7,
            "tree collider failed at z={tree_stop_z}"
        );
        assert!(capsule_position_is_clear(
            -23.0,
            tree_stop_z,
            world.player_radius,
            world.player_height,
            &world.static_colliders,
        ));
    }

    #[test]
    fn meadow_stone_posts_stop_players_but_leave_the_trail_open() {
        let world = test_world();
        for x in [-6.4, 6.4] {
            for z in [-85.0, -121.0] {
                let (stop_x, stop_z) = move_capsule(
                    x,
                    z + 3.0,
                    0.0,
                    -3.0,
                    world.player_radius,
                    world.player_height,
                    &world.static_colliders,
                    world.world_limit,
                );
                assert!(stop_z > z + 0.45, "stone post was penetrated at ({x}, {z})");
                assert!(capsule_position_is_clear(
                    stop_x,
                    stop_z,
                    world.player_radius,
                    world.player_height,
                    &world.static_colliders,
                ));
            }
        }
        // Traverse both pairs through the authored central trail.
        let (mut x, mut z) = (0.0, -80.0);
        for _ in 0..200 {
            (x, z) = move_capsule(
                x,
                z,
                0.0,
                -0.225,
                world.player_radius,
                world.player_height,
                &world.static_colliders,
                world.world_limit,
            );
        }
        assert!(
            z < -124.0,
            "stone posts obstructed the central trail at {z}"
        );
    }

    #[test]
    fn authoritative_player_walks_from_regular_spawn_through_gate_to_plaza_anchor() {
        let mut world = test_world();
        world.join(test_session_id(21)).expect("first spawn slot");
        world.join(test_session_id(22)).expect("second spawn slot");
        let welcome = world.join(test_session_id(23)).expect("third spawn slot");
        assert_eq!((welcome.x, welcome.z), (1.0, -3.0));
        assert_eq!(world.world_limit, 308.0);
        assert_eq!(
            world.static_colliders.len(),
            24,
            "authored Sunmeadow prop colliders remain without legacy gate boxes"
        );
        isolate_city_route_from_combat(&mut world);

        const CITY_GATE_Z: f32 = 24.0;
        const PLAZA_ANCHOR_Z: f32 = 176.0;
        walk_city_waypoints(
            &mut world,
            &welcome,
            &[
                (10.1, -2.0),
                (10.1, 140.0),
                (20.0, 156.0),
                (20.0, PLAZA_ANCHOR_Z),
            ],
        );

        let player = &world.players[&welcome.player_id];
        assert!(
            player.z > CITY_GATE_Z + world.player_radius,
            "did not clear the gate: z={}",
            player.z
        );
        assert!(
            player.z >= PLAZA_ANCHOR_Z - 0.005,
            "did not reach the plaza: z={}",
            player.z
        );
        assert!(player.z - PLAZA_ANCHOR_Z <= world.player_speed * FIXED_DT + 0.01);
        assert!(
            (player.x - 20.0).abs() < 0.005,
            "dry-bank route must end beside the fountain, not inside it"
        );
        assert!(player.z <= world.world_limit - world.player_radius);
        assert!(capsule_position_is_clear(
            player.x,
            player.z,
            world.player_radius,
            world.player_height,
            &world.static_colliders,
        ));
    }

    #[test]
    fn sustained_server_input_cannot_penetrate_either_city_gate_wing() {
        for side in [-1.0_f32, 1.0] {
            let mut world = test_world();
            let welcome = world
                .join(test_session_id(if side < 0.0 { 11 } else { 12 }))
                .expect("player joins");
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = side * 10.1;
            player.z = 24.0;
            player.y = world
                .city_traversal
                .as_ref()
                .unwrap()
                .height_at(player.x, player.z)
                .unwrap();
            isolate_city_route_from_combat(&mut world);

            for sequence in 1..=200 {
                assert!(world.update_input(
                    welcome.player_id,
                    welcome.epoch,
                    sequence,
                    side,
                    0.0,
                    0.0,
                    0,
                ));
                world.advance();
            }

            let player = &world.players[&welcome.player_id];
            assert!(world.city_traversal.as_ref().unwrap().position_is_clear(
                player.x,
                player.y,
                player.z,
                world.player_radius,
                world.player_height,
                &world.static_colliders,
            ));
            assert_eq!(player.z, 24.0);
            assert!(
                player.x * side > 10.5,
                "initially clear dry-bank start never progressed: x={}",
                player.x
            );
            // Measured inner boundary of each authored gate pier is |X|=11.5m.
            // Radius clearance proves the semantic mesh, not a retired box, stops input.
            let clearance = 11.5 - player.x.abs();
            assert!(
                clearance >= world.player_radius - 0.001,
                "gate pier penetrated at x={}",
                player.x
            );
            assert!(
                clearance < world.player_radius + 0.2,
                "stopped short of the actual gate pier at x={}",
                player.x
            );
        }
    }

    #[test]
    fn sustained_input_cannot_cross_the_mesh_derived_gate_curtain_walls() {
        for side in [-1.0_f32, 1.0] {
            let mut world = test_world();
            let welcome = world
                .join(test_session_id(if side < 0.0 { 91 } else { 92 }))
                .unwrap();
            isolate_city_route_from_combat(&mut world);
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = side * 30.0;
            player.z = 20.0;
            player.y = world
                .city_traversal
                .as_ref()
                .unwrap()
                .height_at(player.x, player.z)
                .unwrap();
            for sequence in 1..=200 {
                assert!(world.update_input(
                    welcome.player_id,
                    welcome.epoch,
                    sequence,
                    0.0,
                    1.0,
                    0.0,
                    0
                ));
                world.advance();
            }
            let player = &world.players[&welcome.player_id];
            let clearance = 22.3 - player.z;
            assert_eq!(player.x, side * 30.0);
            assert!(
                player.z > 21.0,
                "dry approach never reached the curtain wall"
            );
            assert!(
                clearance >= world.player_radius - 0.001,
                "curtain wall penetrated at z={}",
                player.z
            );
            assert!(
                clearance < world.player_radius + 0.2,
                "stopped before the real wall boundary at z={}",
                player.z
            );
            assert!(world.city_traversal.as_ref().unwrap().position_is_clear(
                player.x,
                player.y,
                player.z,
                world.player_radius,
                world.player_height,
                &world.static_colliders
            ));
        }
    }

    #[test]
    fn server_clamps_player_at_authored_zone_edge() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(13)).expect("player joins");
        let max_center = world.world_limit - world.player_radius;
        let player = world.players.get_mut(&welcome.player_id).unwrap();
        player.x = 0.0;
        player.z = max_center - 1.0;

        for sequence in 1..=32 {
            assert!(world.update_input(
                welcome.player_id,
                welcome.epoch,
                sequence,
                0.0,
                1.0,
                0.0,
                0,
            ));
            world.advance();
        }

        let player = &world.players[&welcome.player_id];
        assert!(player.z <= max_center + 0.001);
        assert!((player.z - max_center).abs() < 0.001);
    }

    #[test]
    fn stale_sequence_and_epoch_are_rejected() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        assert!(world.update_input(welcome.player_id, welcome.epoch, 3, 1.0, 0.0, 0.0, 0));
        assert!(!world.update_input(welcome.player_id, welcome.epoch, 3, -1.0, 0.0, 0.0, 0));
        assert!(!world.update_input(welcome.player_id, welcome.epoch + 1, 4, -1.0, 0.0, 0.0, 0));
        assert!(!world.update_input(welcome.player_id, welcome.epoch, 5, f32::NAN, 0.0, 0.0, 0));
    }

    #[test]
    fn server_owns_damage_and_emits_a_combat_event() {
        let mut world = test_world();
        world.tick = 123;
        let welcome = world.join(test_session_id(1)).expect("first player joins");
        let (mx,mz)=(world.monsters[0].x,world.monsters[0].z);
        let player = world.players.get_mut(&welcome.player_id).unwrap();
        player.x = mx-2.5;
        player.z = mz-2.0;
        let outcome = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            1,
            ActionKind::ArcSlash,
            0.0,
            0,
            0,
        );
        assert!(outcome.accepted);
        assert_eq!(outcome.ends_at_ms, world.tick * 50 + 5000);
        let snapshot = world.advance();
        assert_eq!(snapshot.events.len(), 1);
        // E07: arc damage rides the derived ATK (45) + arc differential (20).
        assert_eq!(snapshot.events[0].damage, 65);
        assert!(snapshot.monsters.iter().any(|monster| monster.hp == 25));
    }

    #[test]
    fn action_deadlines_use_room_clock_for_instant_and_tick_cooldowns() {
        let mut world = test_world();
        world.tick = 200;
        let welcome = world.join(test_session_id(93)).unwrap();
        let (mx,mz)=(world.monsters[0].x,world.monsters[0].z);
        let player = world.players.get_mut(&welcome.player_id).unwrap();
        player.x = mx;
        player.z = mz-2.0;
        let attack = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            1,
            ActionKind::Attack,
            0.0,
            0,
            0,
        );
        assert!(attack.accepted);
        assert_eq!(attack.ends_at_ms, 10_400);
        world
            .players
            .get_mut(&welcome.player_id)
            .unwrap()
            .last_attack_at = Some(Instant::now() - Duration::from_millis(200));
        let rejected = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            2,
            ActionKind::Attack,
            0.0,
            0,
            0,
        );
        assert!(!rejected.accepted);
        assert_eq!(rejected.reason, crate::wire::reason::COOLDOWN);
        assert!(rejected.ends_at_ms > 10_000 && rejected.ends_at_ms <= 10_200);
        let guard = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            3,
            ActionKind::Guard,
            0.0,
            0,
            0,
        );
        assert!(guard.accepted);
        assert_eq!(guard.ends_at_ms, 16_000);
        world.tick += 1;
        let rejected_guard = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            4,
            ActionKind::Guard,
            0.0,
            0,
            0,
        );
        assert!(!rejected_guard.accepted);
        assert_eq!(rejected_guard.ends_at_ms, guard.ends_at_ms);
        let dodge = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            5,
            ActionKind::Dodge,
            0.0,
            0,
            0,
        );
        assert!(dodge.accepted);
        assert_eq!(dodge.ends_at_ms, 10_950);
        world.tick += 1;
        let rejected_dodge = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            6,
            ActionKind::Dodge,
            0.0,
            0,
            0,
        );
        assert!(!rejected_dodge.accepted);
        assert_eq!(rejected_dodge.ends_at_ms, dodge.ends_at_ms);
        let stale = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            6,
            ActionKind::Attack,
            0.0,
            0,
            0,
        );
        assert!(!stale.accepted);
        assert_eq!(stale.ends_at_ms, 0);
    }

    #[test]
    fn reconnect_restores_session_and_invalidates_the_old_epoch() {
        let mut world = test_world();
        let session_id = test_session_id(1);
        let first = world.join(session_id).expect("first player joins");
        world.disconnect(first.player_id, first.epoch);
        let resumed = world
            .join(session_id)
            .expect("disconnected session resumes");
        assert_eq!(resumed.player_id, first.player_id);
        assert_ne!(resumed.epoch, first.epoch);
        assert!(!world.update_input(first.player_id, first.epoch, 99, 1.0, 0.0, 0.0, 0));
    }

    #[test]
    fn character_state_and_potion_use_are_server_owned_and_idempotent() {
        let mut world = test_world();
        let session = test_session_id(44);
        let first = world.join(session).expect("first player joins");
        let initial = world
            .character_state(first.player_id)
            .expect("profile exists");
        // E07: max_hp = vocation 100 + VIT 6 * 10 = 160 (golden formula).
        assert_eq!(
            (initial.level, initial.exp, initial.hp, initial.max_hp),
            (1, 0, 160, 160)
        );
        assert_eq!(initial.bag[0].item, "trail_potion");
        assert_eq!(initial.bag[0].count, 3);
        assert_eq!(
            world.quest_state(first.player_id).unwrap().state,
            "not_started"
        );

        world.players.get_mut(&first.player_id).unwrap().hp = 50;
        let request = UseItemRequest {
            item: "trail_potion".to_string(),
            op_id: "00000000-0000-4000-8000-000000000001".to_string(),
        };
        world.tick = 321;
        let first_result = world.use_item(first.player_id, request.clone()).unwrap();
        assert_eq!(first_result.status, "accepted");
        assert_eq!(first_result.ends_at_ms, world.tick * 50 + 10_000);
        let after_use = world.character_state(first.player_id).unwrap();
        assert_eq!(after_use.hp, 90);
        assert_eq!(after_use.bag[0].count, 2);
        assert_eq!(after_use.rev, initial.rev + 1);

        world.tick += 10;
        let retry = world.use_item(first.player_id, request.clone()).unwrap();
        assert_eq!(retry.status, "accepted");
        assert_eq!(
            retry.ends_at_ms, first_result.ends_at_ms,
            "replay must not renew the countdown"
        );
        assert_eq!(
            world.character_state(first.player_id).unwrap().bag[0].count,
            2
        );
        let conflict = world
            .use_item(
                first.player_id,
                UseItemRequest {
                    item: "gale_seed".to_string(),
                    ..request
                },
            )
            .unwrap();
        assert_eq!(conflict.reason, "op_id_conflict");
        assert_eq!(conflict.ends_at_ms, 0);
        let cooldown = world
            .use_item(
                first.player_id,
                UseItemRequest {
                    item: "trail_potion".to_string(),
                    op_id: "00000000-0000-4000-8000-000000000002".to_string(),
                },
            )
            .unwrap();
        assert_eq!(cooldown.reason, "cooldown");
        assert!(cooldown.ends_at_ms > world.tick * 50);
        assert!(cooldown.ends_at_ms <= world.tick * 50 + 10_000);
        world.tick += 10;
        let replayed_rejection = world
            .use_item(
                first.player_id,
                UseItemRequest {
                    item: "trail_potion".to_string(),
                    op_id: "00000000-0000-4000-8000-000000000002".to_string(),
                },
            )
            .unwrap();
        assert_eq!(replayed_rejection.ends_at_ms, cooldown.ends_at_ms);

        world.disconnect(first.player_id, first.epoch);
        let resumed = world.join(session).expect("session resumes");
        assert_eq!(resumed.player_id, first.player_id);
        let restored = world.character_state(resumed.player_id).unwrap();
        assert_eq!(restored.hp, 90);
        assert_eq!(restored.bag[0].count, 2);
        assert_eq!(restored.rev, after_use.rev);
    }

    #[test]
    fn bovine_shaman_city_dialogue_checks_range_zone_and_session() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(9101)).expect("traveler joins");
        let npc = world.route_npcs["bovine_shaman"].clone();
        assert_eq!((npc.x, npc.z, npc.radius), (20.0, 156.0, 3.0));
        assert!(matches!(
            world.interact(welcome.player_id, "bovine_shaman"),
            Err("out_of_range")
        ));
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = npc.x;
            player.z = npc.z - npc.radius + 0.1;
        }
        let greeting = world
            .interact(welcome.player_id, "bovine_shaman")
            .expect("city elder is in range");
        assert_eq!(greeting.npc, "bovine_shaman");
        assert_eq!(greeting.text_key, "bovine_shaman_greet");
        assert!(greeting.choices.is_empty());
        assert_eq!(greeting.token.len(), 32);
        let session = world.players[&welcome.player_id].dialogue.as_ref().unwrap();
        assert!(session.expires_at > Instant::now());
        assert!(session.expires_at <= Instant::now() + Duration::from_secs(30));

        world.route_npcs.get_mut("bovine_shaman").unwrap().zone = world.zone_id + 1;
        assert!(matches!(
            world.interact(welcome.player_id, "bovine_shaman"),
            Err("wrong_zone")
        ));
        world.route_npcs.get_mut("bovine_shaman").unwrap().zone = world.zone_id;
        world.disconnect(welcome.player_id, welcome.epoch);
        assert!(matches!(
            world.interact(welcome.player_id, "bovine_shaman"),
            Err("session_expired")
        ));
        assert!(matches!(
            world.interact(u32::MAX, "bovine_shaman"),
            Err("session_expired")
        ));
    }

    #[test]
    fn bovine_shaman_greeting_does_not_change_quest_progress_or_rewards() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(9102)).expect("traveler joins");
        for state in ["not_started", "active", "ready_to_claim", "completed"] {
            {
                let player = world.players.get_mut(&welcome.player_id).unwrap();
                player.x = 20.0;
                player.z = 156.0;
                player.quest_state = state.to_string();
                player.quest_revision = 31;
                player.quest_objectives.insert("hunt".to_string(), 2);
                player.quest_step_ticks.insert("accepted".to_string(), 42);
            }
            let before_quest =
                serde_json::to_value(world.quest_state(welcome.player_id).unwrap()).unwrap();
            let before_character =
                serde_json::to_value(world.character_state(welcome.player_id).unwrap()).unwrap();
            let greeting = world.interact(welcome.player_id, "bovine_shaman").unwrap();
            assert!(greeting.choices.is_empty());
            assert_eq!(greeting.text_key, "bovine_shaman_greet");
            assert_eq!(
                serde_json::to_value(world.quest_state(welcome.player_id).unwrap()).unwrap(),
                before_quest
            );
            assert_eq!(
                serde_json::to_value(world.character_state(welcome.player_id).unwrap()).unwrap(),
                before_character
            );
        }
    }

    #[test]
    fn bovine_shaman_valid_token_cannot_accept_or_claim_sellas_quest() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(9103)).expect("traveler joins");
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = 20.0;
            player.z = 156.0;
        }
        let before = serde_json::to_value(world.quest_state(welcome.player_id).unwrap()).unwrap();
        for choice in ["accept", "claim"] {
            let greeting = world.interact(welcome.player_id, "bovine_shaman").unwrap();
            assert!(matches!(
                world.choose(
                    welcome.player_id,
                    crate::cold::ChooseRequest {
                        npc: "bovine_shaman".to_string(),
                        token: greeting.token,
                        choice: choice.to_string()
                    }
                ),
                Err("invalid_choice")
            ));
            assert_eq!(
                serde_json::to_value(world.quest_state(welcome.player_id).unwrap()).unwrap(),
                before
            );
        }
        let greeting = world.interact(welcome.player_id, "bovine_shaman").unwrap();
        assert!(matches!(
            world.choose(
                welcome.player_id,
                crate::cold::ChooseRequest {
                    npc: "sella".to_string(),
                    token: greeting.token,
                    choice: "accept".to_string()
                }
            ),
            Err("stale_choice")
        ));
        let greeting = world.interact(welcome.player_id, "bovine_shaman").unwrap();
        let closed = world
            .choose(
                welcome.player_id,
                crate::cold::ChooseRequest {
                    npc: "bovine_shaman".to_string(),
                    token: greeting.token,
                    choice: "later".to_string(),
                },
            )
            .expect("generic conversation can be dismissed");
        assert_eq!(closed.reason, "later");
        assert_eq!(
            serde_json::to_value(world.quest_state(welcome.player_id).unwrap()).unwrap(),
            before
        );
    }

    #[test]
    fn sella_route_requires_ordered_objectives_and_claim_is_idempotent() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(55)).expect("traveler joins");
        assert!(matches!(
            world.interact(welcome.player_id, "sella"),
            Err("out_of_range")
        ));
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = 2.0;
            player.z = -14.0;
        }
        let stale_dialogue = world
            .interact(welcome.player_id, "sella")
            .expect("Sella is in range");
        assert_eq!(stale_dialogue.text_key, "sella_greet");
        world
            .players
            .get_mut(&welcome.player_id)
            .unwrap()
            .dialogue
            .as_mut()
            .unwrap()
            .expires_at = Instant::now() - Duration::from_secs(1);
        assert!(matches!(
            world.choose(
                welcome.player_id,
                crate::cold::ChooseRequest {
                    npc: "sella".to_string(),
                    token: stale_dialogue.token,
                    choice: "accept".to_string(),
                }
            ),
            Err("stale_choice")
        ));
        let dialogue = world
            .interact(welcome.player_id, "sella")
            .expect("expired dialogue can be reopened");
        let closed = world
            .choose(
                welcome.player_id,
                crate::cold::ChooseRequest {
                    npc: "sella".to_string(),
                    token: dialogue.token,
                    choice: "accept".to_string(),
                },
            )
            .expect("offer accepted");
        assert_eq!(closed.reason, "accepted");
        assert_eq!(
            world.quest_state(welcome.player_id).unwrap().state,
            "active"
        );
        assert!(matches!(
            world.start_windmark(welcome.player_id, "windmark_2"),
            Err("wrong_order")
        ));

        for marker in ["windmark_1", "windmark_2", "windmark_3"] {
            let point = world.route_pois[marker];
            {
                let player = world.players.get_mut(&welcome.player_id).unwrap();
                player.x = point.x;
                player.z = point.z;
            }
            world
                .start_windmark(welcome.player_id, marker)
                .expect("marker starts an activation channel");
            for _ in 0..20 {
                world.advance();
            }
        }
        assert_eq!(
            world.quest_state(welcome.player_id).unwrap().objectives["windmark"],
            3
        );
        assert!(matches!(
            world.start_windmark(welcome.player_id, "windmark_1"),
            Err("already_activated")
        ));

        for index in 0..3 {
            let (x, z) = {
                let monster = &mut world.monsters[index];
                monster.hp = 25;
                (monster.x - 2.0, monster.z)
            };
            {
                let player = world.players.get_mut(&welcome.player_id).unwrap();
                player.x = x;
                player.z = z;
                player.facing = std::f32::consts::FRAC_PI_2;
                player.last_attack_at = None;
            }
            let result = world.apply_action(
                welcome.player_id,
                welcome.epoch,
                index as u64 + 1,
                ActionKind::Attack,
                std::f32::consts::FRAC_PI_2,
                0,
                world.tick() as u32,
            );
            assert!(result.accepted, "hunt attack {index} should be accepted");
        }
        let quest = world.quest_state(welcome.player_id).unwrap();
        assert_eq!(quest.state, "ready_to_claim");
        assert_eq!(quest.objectives["hunt"], 3);
        let profile = world.character_state(welcome.player_id).unwrap();
        assert_eq!((profile.level, profile.exp), (1, 27));
        assert_eq!(profile.pouch["dew_bead"], 3);

        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = 2.0;
            player.z = -14.0;
            for index in 0..11 {
                player.bag.insert(format!("fixture_item_{index}"), 1);
            }
        }
        let full = world
            .claim_quest(
                welcome.player_id,
                crate::cold::ClaimRequest {
                    quest: P1_QUEST_ID.to_string(),
                    op_id: "123e4567-e89b-42d3-a456-426614174010".to_string(),
                },
            )
            .unwrap();
        assert_eq!(full.reason, "inventory_full");
        assert_eq!(
            world.quest_state(welcome.player_id).unwrap().state,
            "ready_to_claim"
        );

        world
            .players
            .get_mut(&welcome.player_id)
            .unwrap()
            .bag
            .clear();
        world
            .players
            .get_mut(&welcome.player_id)
            .unwrap()
            .bag
            .insert("trail_potion".to_string(), 3);
        let claim = world
            .claim_quest(
                welcome.player_id,
                crate::cold::ClaimRequest {
                    quest: P1_QUEST_ID.to_string(),
                    op_id: "123e4567-e89b-42d3-a456-426614174011".to_string(),
                },
            )
            .unwrap();
        assert_eq!(claim.status, "accepted");
        assert_eq!(claim.grants[0].def, "gale_seed");
        assert_eq!(
            world.quest_state(welcome.player_id).unwrap().state,
            "completed"
        );
        let after_claim = world.character_state(welcome.player_id).unwrap();
        assert_eq!((after_claim.level, after_claim.exp), (2, 17));
        assert_eq!(
            after_claim
                .bag
                .iter()
                .find(|entry| entry.item == "gale_seed")
                .unwrap()
                .count,
            1
        );

        let retry = world
            .claim_quest(
                welcome.player_id,
                crate::cold::ClaimRequest {
                    quest: P1_QUEST_ID.to_string(),
                    op_id: "123e4567-e89b-42d3-a456-426614174011".to_string(),
                },
            )
            .unwrap();
        assert_eq!(retry.status, claim.status);
        assert_eq!(retry.reason, claim.reason);
        assert_eq!(retry.grants[0].def, claim.grants[0].def);
        assert_eq!(
            world
                .character_state(welcome.player_id)
                .unwrap()
                .bag
                .iter()
                .find(|entry| entry.item == "gale_seed")
                .unwrap()
                .count,
            1
        );
    }

    #[test]
    fn party_invites_and_kill_credit_share_state_with_nearby_eligible_members() {
        let mut world = test_world();
        let first = world
            .join(test_session_id(61))
            .expect("first traveler joins");
        let second = world
            .join(test_session_id(62))
            .expect("second traveler joins");
        let third = world
            .join(test_session_id(63))
            .expect("third traveler joins");
        let fourth = world
            .join(test_session_id(64))
            .expect("fourth traveler joins");
        let fifth = world
            .join(test_session_id(65))
            .expect("fifth traveler joins");
        world
            .create_party(first.player_id)
            .expect("leader creates party");
        let party = world.party_state(first.player_id).unwrap();
        assert_eq!(party.members.len(), 1);
        assert_eq!(party.leader, first.player_id);
        assert_eq!(party.code.len(), 6);
        assert_eq!(
            party
                .members
                .iter()
                .find(|member| member.id == first.player_id)
                .unwrap()
                .name,
            world.players.get(&first.player_id).unwrap().name,
        );
        world
            .join_party(second.player_id, &party.code)
            .expect("second traveler joins by code");
        assert_eq!(
            world
                .party_state(first.player_id)
                .unwrap()
                .members
                .iter()
                .find(|member| member.id == second.player_id)
                .unwrap()
                .name,
            world.players.get(&second.player_id).unwrap().name,
        );
        world
            .join_party(third.player_id, &party.code)
            .expect("third traveler joins by code");
        world
            .join_party(fourth.player_id, &party.code)
            .expect("fourth traveler joins by code");
        assert_eq!(world.party_state(first.player_id).unwrap().members.len(), 4);
        assert_eq!(
            world.join_party(fifth.player_id, &party.code),
            Err("party_full")
        );
        assert_eq!(
            world.party_state(second.player_id).unwrap().leader,
            first.player_id
        );

        for welcome in [&first, &second, &third, &fourth] {
            {
                let player = world.players.get_mut(&welcome.player_id).unwrap();
                player.x = 2.0;
                player.z = -14.0;
            }
            let dialogue = world
                .interact(welcome.player_id, "sella")
                .expect("Sella offers the quest in range");
            world
                .choose(
                    welcome.player_id,
                    crate::cold::ChooseRequest {
                        npc: "sella".to_string(),
                        token: dialogue.token,
                        choice: "accept".to_string(),
                    },
                )
                .expect("each member accepts the quest");
        }
        let (x, z) = {
            let monster = &mut world.monsters[0];
            monster.hp = 25;
            (monster.x - 2.0, monster.z)
        };
        for player_id in [
            first.player_id,
            second.player_id,
            third.player_id,
            fourth.player_id,
        ] {
            let member = world.players.get_mut(&player_id).unwrap();
            member.x = x;
            member.z = z;
            member.facing = std::f32::consts::FRAC_PI_2;
        }
        let killed = world.apply_action(
            first.player_id,
            first.epoch,
            1,
            ActionKind::Attack,
            std::f32::consts::FRAC_PI_2,
            0,
            0,
        );
        assert!(killed.accepted);
        for player_id in [
            first.player_id,
            second.player_id,
            third.player_id,
            fourth.player_id,
        ] {
            let state = world.character_state(player_id).unwrap();
            assert_eq!(state.exp, if player_id==fourth.player_id {2}else{3});
            assert_eq!(state.pouch["dew_bead"], 1);
            assert_eq!(world.quest_state(player_id).unwrap().objectives["hunt"], 1);
        }

        let (x, z) = {
            let monster = &mut world.monsters[1];
            monster.hp = 25;
            (monster.x - 2.0, monster.z)
        };
        for player_id in [first.player_id, second.player_id, fourth.player_id] {
            let member = world.players.get_mut(&player_id).unwrap();
            member.x = x;
            member.z = z;
            member.facing = std::f32::consts::FRAC_PI_2;
        }
        let distant = world.players.get_mut(&third.player_id).unwrap();
        distant.x = 25.0;
        distant.z = 25.0;
        distant.quest_state = "not_started".to_string();
        world.disconnect(fourth.player_id, fourth.epoch);
        world
            .players
            .get_mut(&first.player_id)
            .unwrap()
            .last_attack_at = None;
        let group_kill = world.apply_action(
            first.player_id,
            first.epoch,
            2,
            ActionKind::Attack,
            std::f32::consts::FRAC_PI_2,
            0,
            0,
        );
        assert!(group_kill.accepted);
        for player_id in [first.player_id, second.player_id, fourth.player_id] {
            assert_eq!(
                world.character_state(player_id).unwrap().pouch["dew_bead"],
                2
            );
            assert_eq!(world.quest_state(player_id).unwrap().objectives["hunt"], 2);
        }
        assert_eq!(
            world.character_state(third.player_id).unwrap().pouch["dew_bead"],
            1
        );
        assert_eq!(
            world.quest_state(third.player_id).unwrap().state,
            "not_started"
        );
        assert_eq!(
            world.quest_state(third.player_id).unwrap().objectives["hunt"],
            1
        );
        world.leave_party(second.player_id).expect("member leaves");
        assert!(
            world
                .party_state(second.player_id)
                .unwrap()
                .members
                .is_empty()
        );
        assert_eq!(world.party_state(first.player_id).unwrap().members.len(), 3);
    }

    #[test]
    fn party_invite_code_expires_after_ten_minutes_without_disbanding_the_party() {
        let mut world = test_world();
        let leader = world.join(test_session_id(71)).expect("leader connects");
        let guest = world.join(test_session_id(72)).expect("guest connects");
        world
            .create_party(leader.player_id)
            .expect("party is created");
        let initial = world.party_state(leader.player_id).unwrap();
        assert!((1..=600).contains(&initial.expires_s));
        let party_id = world
            .players
            .get(&leader.player_id)
            .unwrap()
            .party_id
            .unwrap();
        world.parties.get_mut(&party_id).unwrap().code_expires_at =
            Instant::now() - Duration::from_secs(1);

        let expired = world.party_state(leader.player_id).unwrap();
        assert_eq!(expired.expires_s, 0);
        assert!(expired.code.is_empty());
        assert_eq!(
            world.join_party(guest.player_id, &initial.code),
            Err("party_expired")
        );
        assert_eq!(
            world.party_state(leader.player_id).unwrap().members.len(),
            1
        );
    }

    #[test]
    fn dodge_boost_rides_input_sequence_and_cooldown_is_tick_based() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(7)).expect("player connects");
        let initial_x = welcome.x;

        // Apply 2 normal inputs (seq 1, 2)
        world.update_input(welcome.player_id, welcome.epoch, 1, 1.0, 0.0, 0.0, 0);
        world.advance();
        world.update_input(welcome.player_id, welcome.epoch, 2, 1.0, 0.0, 0.0, 0);
        let snap2 = world.advance();
        let normal_step = snap2.players[0].x - initial_x;
        assert!(!snap2.players[0].dodging);

        // Execute Dodge at action seq 3
        let dodge = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            3,
            ActionKind::Dodge,
            0.0,
            0,
            0,
        );
        assert!(dodge.accepted);

        // Inputs seq 4..=9 (6 steps, 280ms duration) must get dodge speed boost (2.2x)
        let mut before_x = snap2.players[0].x;
        for seq in 4..=9 {
            world.update_input(welcome.player_id, welcome.epoch, seq, 1.0, 0.0, 0.0, 0);
            let snap = world.advance();
            assert!(snap.players[0].dodging, "seq {seq} should be dodging");
            let step = snap.players[0].x - before_x;
            assert!(
                (step - normal_step * 2.2 / 2.0).abs() < 1e-3,
                "step {step} vs expected {}",
                normal_step * 2.2 / 2.0
            );
            before_x = snap.players[0].x;
        }

        // Input seq 10 should be back to normal speed (dodging = false)
        world.update_input(welcome.player_id, welcome.epoch, 10, 1.0, 0.0, 0.0, 0);
        let snap10 = world.advance();
        assert!(!snap10.players[0].dodging);
        let normal_step2 = snap10.players[0].x - before_x;
        assert!((normal_step2 - normal_step / 2.0).abs() < 1e-3);

        // Immediate dodge retry should be rejected with Cooldown
        let retry = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            11,
            ActionKind::Dodge,
            0.0,
            0,
            0,
        );
        assert!(!retry.accepted);
        assert_eq!(retry.reason, RejectReason::Cooldown.code());

        // Advance to 1 tick before cooldown expires: accepted with 1-tick early tolerance (no boundary rejection)
        let ready_tick = world.players[&welcome.player_id].dodge_ready_tick;
        while world.tick + 1 < ready_tick {
            world.advance();
        }
        let edge_dodge = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            12,
            ActionKind::Dodge,
            0.0,
            0,
            0,
        );
        assert!(edge_dodge.accepted, "edge dodge must be accepted");
    }

    // -- D-14 session economy ------------------------------------------------

    fn test_op_id(value: u32) -> String {
        format!("00000000-0000-4000-8000-{value:012}")
    }

    /// A world whose economy table is customized before the player joins, so
    /// the wallet seeds from the customized table. Starts from the defaults so
    /// bundle-authored tables do not leak into the scenario.
    fn economy_world(customize: impl FnOnce(&mut World)) -> (World, Welcome) {
        let mut world = test_world();
        world.economy = Economy::default();
        customize(&mut world);
        let welcome = world.join(test_session_id(70)).expect("traveler joins");
        (world, welcome)
    }

    fn store_entry(id: &str, price: u32) -> StoreEntry {
        StoreEntry {
            id: id.to_string(),
            cosmetic: false,
            currency: Currency::Gold,
            price,
            count: 1,
        }
    }

    fn cosmetic_entry(id: &str, price: u32) -> StoreEntry {
        StoreEntry {
            cosmetic: true,
            ..store_entry(id, price)
        }
    }

    fn fill_bag(world: &mut World, player_id: u32) {
        let player = world.players.get_mut(&player_id).unwrap();
        for index in 0..11 {
            player.bag.insert(format!("fixture_item_{index}"), 1);
        }
    }

    fn bag_count(world: &World, player_id: u32, item: &str) -> u8 {
        world.players[&player_id]
            .bag
            .get(item)
            .copied()
            .unwrap_or(0)
    }

    #[test]
    fn economy_table_reads_defensively_from_the_bundle() {
        let defaults = Economy::from_bundle(None);
        assert_eq!(
            (
                defaults.start_gold,
                defaults.start_coin,
                defaults.kill_gold,
                defaults.quest_claim_gold,
                defaults.duplicate_cosmetic_coin
            ),
            (250, 10, 5, 100, 25)
        );
        assert!(defaults.store.is_empty() && defaults.boxes.is_empty());

        let value = serde_json::json!({
            "starting": {"gold": 500, "coin": 40},
            "kill_gold": 7,
            "cosmetics": ["skin_loose"],
            "skins": {"skin_ember": {"tunic": "#a83a4e"}},
            "pets": {"pet_wisp": {}},
            "store": [
                {"item": "trail_potion", "currency": "gold", "price": 40},
                {"item": "gale_seed", "price": 60, "count": 2, "currency": "coin"},
                {"cosmetic": "skin_ember", "currency": "coin", "price": 5},
                {"malformed": true}
            ],
            "boxes": {
                "wooden_box": {"table": [
                    {"weight": 2, "gold": 30},
                    {"cosmetic": "skin_ember"},
                    {"weight": 1, "item": "trail_potion", "min": 1, "max": 3},
                    {"weight": 1, "item": "gale_seed", "count": 2},
                    {"no_outcome": true}
                ]},
                "broken": {"table": []}
            },
            "unknown_key": {"ignored": true}
        });
        let economy = Economy::from_bundle(Some(&value));
        assert_eq!(economy.start_gold, 500);
        assert_eq!(economy.start_coin, 40);
        assert_eq!(economy.kill_gold, 7);
        assert_eq!(economy.quest_claim_gold, 100);
        assert_eq!(economy.duplicate_cosmetic_coin, 25);
        // Cosmetic ids come from the skins/pets tables plus a flat fallback.
        assert!(economy.is_cosmetic("skin_ember"));
        assert!(economy.is_cosmetic("pet_wisp"));
        assert!(economy.is_cosmetic("skin_loose"));
        assert!(!economy.is_cosmetic("trail_potion"));
        assert_eq!(economy.store.len(), 3);
        assert_eq!(economy.store[0].id, "trail_potion");
        assert_eq!(economy.store[0].currency, Currency::Gold);
        assert!(!economy.store[0].cosmetic);
        assert_eq!(economy.store[1].count, 2);
        assert_eq!(economy.store[2].currency, Currency::Coin);
        assert!(economy.store[2].cosmetic);
        assert_eq!(economy.boxes.len(), 2);
        let wooden = economy.box_def("wooden_box").expect("wooden_box parsed");
        assert_eq!(wooden.rolls.len(), 4);
        assert_eq!(wooden.rolls[1].weight, 1);
        assert!(matches!(
            wooden.rolls[1].outcome,
            RollOutcome::Cosmetic(ref id) if id == "skin_ember"
        ));
        assert!(matches!(
            wooden.rolls[2].outcome,
            RollOutcome::Item { min: 1, max: 3, .. }
        ));
        assert!(matches!(
            wooden.rolls[3].outcome,
            RollOutcome::Item { min: 2, max: 2, .. }
        ));
        assert_eq!(
            economy.box_def("broken").expect("broken box parsed").rolls,
            Vec::<BoxRoll>::new()
        );

        // A wrong-typed scalar falls back to that field's default only.
        let bad = serde_json::json!({"kill_gold": "lots", "boxes": "nope", "store": 7});
        let economy = Economy::from_bundle(Some(&bad));
        assert_eq!(economy.kill_gold, 5);
        assert!(economy.boxes.is_empty() && economy.store.is_empty());
    }

    #[test]
    fn world_loads_the_authored_economy_from_the_bundle() {
        // The authored content/source/economy.json reaches the world through
        // the canonical bundle's economy object.
        let world = test_world();
        assert!(
            world
                .economy
                .store
                .iter()
                .any(|entry| entry.id == "trail_potion")
        );
        assert!(world.economy.box_def("meadow_box").is_some());
        assert!(world.economy.is_cosmetic("skin_crimson"));
        assert!(world.economy.is_cosmetic("pet_sprout"));
    }

    #[test]
    fn joining_seeds_the_wallet_from_the_economy_table() {
        let (world, welcome) = economy_world(|world| {
            world.economy.start_gold = 500;
            world.economy.start_coin = 40;
        });
        let state = world.character_state(welcome.player_id).unwrap();
        assert_eq!((state.gold, state.coin), (500, 40));
        assert_eq!(state.skin, None);
        assert_eq!(state.pet, None);
        assert!(state.owned_cosmetics.is_empty());

        // Without a bundle economy key the defaults seed the wallet.
        let mut world = test_world();
        let welcome = world.join(test_session_id(71)).expect("traveler joins");
        let state = world.character_state(welcome.player_id).unwrap();
        assert_eq!((state.gold, state.coin), (250, 10));
    }

    #[test]
    fn store_buy_spends_gold_and_grants_the_bag_item_idempotently() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.store.push(store_entry("trail_potion", 40));
            world.economy.store.push(store_entry("gale_seed", 40));
        });
        let request = StoreBuyRequest {
            item: "trail_potion".to_string(),
            op_id: test_op_id(1),
        };
        let result = world.store_buy(welcome.player_id, request.clone()).unwrap();
        assert_eq!(result.status, "accepted");
        assert_eq!(result.grants[0].def, "trail_potion");
        assert_eq!(result.grants[0].count, 1);
        let after = world.character_state(welcome.player_id).unwrap();
        assert_eq!(after.gold, 210);
        assert_eq!(bag_count(&world, welcome.player_id, "trail_potion"), 4);
        assert_eq!(after.rev, 2);
        assert!(
            world
                .take_pending_state_updates()
                .contains(&welcome.player_id)
        );

        // Same op_id replays the cached result without a second charge.
        let replay = world.store_buy(welcome.player_id, request.clone()).unwrap();
        assert_eq!(replay.status, "accepted");
        assert_eq!(replay.grants, result.grants);
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 210);
        assert_eq!(bag_count(&world, welcome.player_id, "trail_potion"), 4);

        // Same op_id with a different item is a conflict.
        let conflict = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "gale_seed".to_string(),
                    op_id: test_op_id(1),
                },
            )
            .unwrap();
        assert_eq!(conflict.reason, "op_id_conflict");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 210);
    }

    #[test]
    fn store_buy_refuses_insufficient_funds_without_changes() {
        let (mut world, welcome) =
            economy_world(|world| world.economy.store.push(store_entry("gale_seed", 40)));
        world.players.get_mut(&welcome.player_id).unwrap().gold = 10;
        let result = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "gale_seed".to_string(),
                    op_id: test_op_id(2),
                },
            )
            .unwrap();
        assert_eq!(result.status, "rejected");
        assert_eq!(result.reason, "insufficient_funds");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 10);
        assert_eq!(bag_count(&world, welcome.player_id, "gale_seed"), 0);

        // Unknown store ids are refused without touching the wallet.
        let unknown = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "no_such_item".to_string(),
                    op_id: test_op_id(3),
                },
            )
            .unwrap();
        assert_eq!(unknown.reason, "unknown_item");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 10);
    }

    #[test]
    fn store_buy_refuses_an_owned_cosmetic_without_charge() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.store.push(cosmetic_entry("skin_ember", 100));
            world.economy.cosmetics.push("skin_ember".to_string());
        });
        world
            .players
            .get_mut(&welcome.player_id)
            .unwrap()
            .owned_cosmetics
            .insert("skin_ember".to_string());
        let result = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "skin_ember".to_string(),
                    op_id: test_op_id(4),
                },
            )
            .unwrap();
        assert_eq!(result.status, "rejected");
        assert_eq!(result.reason, "already_owned");
        let state = world.character_state(welcome.player_id).unwrap();
        assert_eq!(state.gold, 250);
        assert_eq!(state.owned_cosmetics, vec!["skin_ember".to_string()]);
    }

    #[test]
    fn store_buy_checks_the_full_bag_before_consuming_and_grants_boxes() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.store.push(store_entry("gale_seed", 40));
            world.economy.store.push(store_entry("wooden_box", 100));
            world.economy.boxes.push(BoxDef {
                id: "wooden_box".to_string(),
                rolls: vec![BoxRoll {
                    weight: 1,
                    outcome: RollOutcome::Gold(30),
                }],
            });
        });
        fill_bag(&mut world, welcome.player_id);
        let result = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "gale_seed".to_string(),
                    op_id: test_op_id(5),
                },
            )
            .unwrap();
        assert_eq!(result.reason, "inventory_full");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 250);
        assert_eq!(bag_count(&world, welcome.player_id, "gale_seed"), 0);

        // A box def bought from the store lands as a bag item.
        let box_purchase = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "wooden_box".to_string(),
                    op_id: test_op_id(6),
                },
            )
            .unwrap();
        assert_eq!(box_purchase.status, "rejected");
        assert_eq!(box_purchase.reason, "inventory_full");

        // With bag room the same purchase stores one box.
        world
            .players
            .get_mut(&welcome.player_id)
            .unwrap()
            .bag
            .retain(|item, _| item == "trail_potion");
        let purchase = world
            .store_buy(
                welcome.player_id,
                StoreBuyRequest {
                    item: "wooden_box".to_string(),
                    op_id: test_op_id(7),
                },
            )
            .unwrap();
        assert_eq!(purchase.status, "accepted");
        assert_eq!(purchase.grants[0].def, "wooden_box");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 150);
        assert_eq!(bag_count(&world, welcome.player_id, "wooden_box"), 1);
    }

    #[test]
    fn weighted_pick_walks_integer_weights_without_floats() {
        let rolls = |weights: &[u32]| -> Vec<BoxRoll> {
            weights
                .iter()
                .map(|weight| BoxRoll {
                    weight: *weight,
                    outcome: RollOutcome::Gold(1),
                })
                .collect()
        };
        let table = rolls(&[40, 30, 20, 10]);
        assert_eq!(weighted_pick(&table, 0), Some(0));
        assert_eq!(weighted_pick(&table, 39), Some(0));
        assert_eq!(weighted_pick(&table, 40), Some(1));
        assert_eq!(weighted_pick(&table, 69), Some(1));
        assert_eq!(weighted_pick(&table, 70), Some(2));
        assert_eq!(weighted_pick(&table, 89), Some(2));
        assert_eq!(weighted_pick(&table, 90), Some(3));
        assert_eq!(weighted_pick(&table, 99), Some(3));
        // Values wrap through the modulo of the total weight.
        assert_eq!(weighted_pick(&table, 100), Some(0));
        assert_eq!(weighted_pick(&table, 199), Some(3));
        // Zero-weight rolls never win; an all-zero table has no pick.
        let zeroed = rolls(&[0, 0, 5]);
        assert_eq!(weighted_pick(&zeroed, 0), Some(2));
        assert_eq!(weighted_pick(&zeroed, 4), Some(2));
        assert_eq!(weighted_pick(&rolls(&[0, 0]), 7), None);
        assert_eq!(weighted_pick(&[], 7), None);
    }

    #[test]
    fn box_open_pays_wallet_grants_and_consumes_one_box_idempotently() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.boxes.push(BoxDef {
                id: "wooden_box".to_string(),
                rolls: vec![BoxRoll {
                    weight: 1,
                    outcome: RollOutcome::Gold(30),
                }],
            });
        });
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.bag.insert("wooden_box".to_string(), 2);
        }
        let request = BoxOpenRequest {
            item: "wooden_box".to_string(),
            op_id: test_op_id(8),
        };
        let result = world.box_open(welcome.player_id, request.clone()).unwrap();
        assert_eq!(result.status, "accepted");
        assert_eq!(result.grants[0].def, "gold");
        assert_eq!(result.grants[0].count, 30);
        let after = world.character_state(welcome.player_id).unwrap();
        assert_eq!(after.gold, 280);
        assert_eq!(bag_count(&world, welcome.player_id, "wooden_box"), 1);
        assert_eq!(after.rev, 2);

        // Same op_id replays without consuming the second box.
        let replay = world.box_open(welcome.player_id, request.clone()).unwrap();
        assert_eq!(replay.grants, result.grants);
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 280);
        assert_eq!(bag_count(&world, welcome.player_id, "wooden_box"), 1);

        // Same op_id over a different box is a conflict.
        world.economy.boxes.push(BoxDef {
            id: "iron_box".to_string(),
            rolls: vec![BoxRoll {
                weight: 1,
                outcome: RollOutcome::Coin(2),
            }],
        });
        let conflict = world
            .box_open(
                welcome.player_id,
                BoxOpenRequest {
                    item: "iron_box".to_string(),
                    op_id: test_op_id(8),
                },
            )
            .unwrap();
        assert_eq!(conflict.reason, "op_id_conflict");
        assert_eq!(bag_count(&world, welcome.player_id, "wooden_box"), 1);
    }

    #[test]
    fn box_open_requires_a_known_and_owned_box() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.boxes.push(BoxDef {
                id: "wooden_box".to_string(),
                rolls: vec![BoxRoll {
                    weight: 1,
                    outcome: RollOutcome::Gold(30),
                }],
            });
        });
        let unknown = world
            .box_open(
                welcome.player_id,
                BoxOpenRequest {
                    item: "iron_box".to_string(),
                    op_id: test_op_id(9),
                },
            )
            .unwrap();
        assert_eq!(unknown.reason, "unknown_item");
        let not_owned = world
            .box_open(
                welcome.player_id,
                BoxOpenRequest {
                    item: "wooden_box".to_string(),
                    op_id: test_op_id(10),
                },
            )
            .unwrap();
        assert_eq!(not_owned.reason, "not_owned");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 250);
    }

    #[test]
    fn box_open_refuses_a_bag_item_roll_when_the_bag_is_full() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.boxes.push(BoxDef {
                id: "wooden_box".to_string(),
                rolls: vec![BoxRoll {
                    weight: 1,
                    outcome: RollOutcome::Item {
                        id: "gale_seed".to_string(),
                        min: 1,
                        max: 1,
                    },
                }],
            });
        });
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.bag.insert("wooden_box".to_string(), 1);
        }
        fill_bag(&mut world, welcome.player_id);
        let result = world
            .box_open(
                welcome.player_id,
                BoxOpenRequest {
                    item: "wooden_box".to_string(),
                    op_id: test_op_id(11),
                },
            )
            .unwrap();
        assert_eq!(result.status, "rejected");
        assert_eq!(result.reason, "inventory_full");
        // Nothing was consumed and nothing was granted.
        assert_eq!(bag_count(&world, welcome.player_id, "wooden_box"), 1);
        assert_eq!(bag_count(&world, welcome.player_id, "gale_seed"), 0);
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 250);
    }

    #[test]
    fn box_open_converts_a_duplicate_cosmetic_into_coin_even_with_a_full_bag() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.cosmetics.push("skin_ember".to_string());
            world.economy.boxes.push(BoxDef {
                id: "wooden_box".to_string(),
                rolls: vec![BoxRoll {
                    weight: 1,
                    outcome: RollOutcome::Cosmetic("skin_ember".to_string()),
                }],
            });
        });
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.bag.insert("wooden_box".to_string(), 1);
            player.owned_cosmetics.insert("skin_ember".to_string());
        }
        fill_bag(&mut world, welcome.player_id);
        let result = world
            .box_open(
                welcome.player_id,
                BoxOpenRequest {
                    item: "wooden_box".to_string(),
                    op_id: test_op_id(12),
                },
            )
            .unwrap();
        assert_eq!(result.status, "accepted");
        assert_eq!(result.reason, "duplicate_cosmetic");
        assert_eq!(result.grants[0].def, "coin");
        assert_eq!(result.grants[0].count, 25);
        let after = world.character_state(welcome.player_id).unwrap();
        assert_eq!((after.gold, after.coin), (250, 35));
        assert_eq!(after.owned_cosmetics, vec!["skin_ember".to_string()]);
        assert_eq!(bag_count(&world, welcome.player_id, "wooden_box"), 0);
    }

    #[test]
    fn cosmetics_equip_updates_owned_slots_and_rejects_unknown_ids() {
        let (mut world, welcome) = economy_world(|world| {
            world.economy.cosmetics.push("skin_ember".to_string());
            world.economy.cosmetics.push("pet_wisp".to_string());
        });
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.owned_cosmetics.insert("skin_ember".to_string());
            player.owned_cosmetics.insert("pet_wisp".to_string());
        }
        let equip = |world: &mut World, slot: &str, id: &str, op: u32| {
            world
                .cosmetics_equip(
                    welcome.player_id,
                    CosmeticsEquipRequest {
                        slot: slot.to_string(),
                        id: id.to_string(),
                        op_id: test_op_id(op),
                    },
                )
                .unwrap()
        };
        let before_rev = world.character_state(welcome.player_id).unwrap().rev;

        let skin = equip(&mut world, "skin", "skin_ember", 1);
        assert_eq!(skin.status, "accepted");
        let state = world.character_state(welcome.player_id).unwrap();
        assert_eq!(state.skin.as_deref(), Some("skin_ember"));
        assert_eq!(state.rev, before_rev + 1);
        assert!(
            world
                .take_pending_state_updates()
                .contains(&welcome.player_id)
        );

        // Re-equipping the same cosmetic (new op_id) changes nothing.
        assert_eq!(
            equip(&mut world, "skin", "skin_ember", 2).status,
            "accepted"
        );
        assert_eq!(
            world.character_state(welcome.player_id).unwrap().rev,
            state.rev
        );

        let pet = equip(&mut world, "pet", "pet_wisp", 3);
        assert_eq!(pet.status, "accepted");
        assert_eq!(
            world.character_state(welcome.player_id).unwrap().pet,
            Some("pet_wisp".to_string())
        );

        // `none` resets the pet slot; resetting again changes nothing.
        assert_eq!(equip(&mut world, "pet", "none", 4).status, "accepted");
        assert_eq!(world.character_state(welcome.player_id).unwrap().pet, None);
        let rev_after_reset = world.character_state(welcome.player_id).unwrap().rev;
        assert_eq!(equip(&mut world, "pet", "default", 5).status, "accepted");
        assert_eq!(
            world.character_state(welcome.player_id).unwrap().rev,
            rev_after_reset
        );

        // Unknown cosmetics are refused for both slots.
        assert_eq!(
            equip(&mut world, "skin", "skin_ghost", 6).reason,
            "not_owned"
        );
        assert_eq!(equip(&mut world, "pet", "pet_ghost", 7).reason, "not_owned");

        // The same op_id replays its cached result; with a different key it
        // is a conflict.
        let replay = equip(&mut world, "skin", "skin_ember", 1);
        assert_eq!(replay.status, "accepted");
        let conflict = equip(&mut world, "pet", "pet_wisp", 1);
        assert_eq!(conflict.reason, "op_id_conflict");
    }

    #[test]
    fn defeats_grant_kill_gold_to_the_killer() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(72)).expect("traveler joins");
        assert_eq!(world.character_state(welcome.player_id).unwrap().gold, 250);
        let (x, z) = {
            let monster = &mut world.monsters[0];
            monster.hp = 25;
            (monster.x - 2.0, monster.z)
        };
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = x;
            player.z = z;
            player.facing = std::f32::consts::FRAC_PI_2;
        }
        let outcome = world.apply_action(
            welcome.player_id,
            welcome.epoch,
            1,
            ActionKind::Attack,
            std::f32::consts::FRAC_PI_2,
            0,
            0,
        );
        assert!(outcome.accepted, "the killing blow is accepted");
        let state = world.character_state(welcome.player_id).unwrap();
        assert_eq!(state.gold, 255);
        assert_eq!((state.level, state.exp), (1, 9));
    }

    #[test]
    fn quest_claims_grant_claim_gold_alongside_the_rewards() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(73)).expect("traveler joins");
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = 2.0;
            player.z = -14.0;
            player.quest_state = "ready_to_claim".to_string();
        }
        let claim = world
            .claim_quest(
                welcome.player_id,
                crate::cold::ClaimRequest {
                    quest: P1_QUEST_ID.to_string(),
                    op_id: test_op_id(14),
                },
            )
            .unwrap();
        assert_eq!(claim.status, "accepted");
        let after = world.character_state(welcome.player_id).unwrap();
        assert_eq!(after.gold, 350);
        assert_eq!(
            after
                .bag
                .iter()
                .find(|entry| entry.item == "gale_seed")
                .unwrap()
                .count,
            1
        );
    }

    // -- shared character store ----------------------------------------------

    #[test]
    fn shared_store_carries_wallet_bag_and_op_cache_across_worlds() {
        let store = test_store();
        let content = crate::content::test_content();
        let mut world_a = World::new(&content, store.clone());
        let session = test_session_id(81);
        let welcome_a = world_a.join(session).expect("first world join");

        // Buy a potion in world A (economy store: trail_potion, 40 gold) and
        // let the tick sync publish the record.
        let request = StoreBuyRequest {
            item: "trail_potion".to_string(),
            op_id: test_op_id(21),
        };
        let result = world_a
            .store_buy(welcome_a.player_id, request.clone())
            .unwrap();
        assert_eq!(result.status, "accepted");
        for _ in 0..2 {
            world_a.advance();
        }

        // A SECOND world instance sharing the store admits the same session
        // as a fresh player: wallet, bag and quest record survive the switch.
        let mut world_b = World::new(&content, store.clone());
        let welcome_b = world_b.join(session).expect("second world joins");
        assert_eq!(
            (welcome_b.x, welcome_b.z),
            spawn_position(0),
            "position follows the normal spawn path"
        );
        let state = world_b.character_state(welcome_b.player_id).unwrap();
        assert_eq!(
            state.gold, 225,
            "trail_potion costs 25 gold in the authored table"
        );
        assert_eq!(state.coin, 10);
        assert_eq!(bag_count(&world_b, welcome_b.player_id, "trail_potion"), 4);
        assert_eq!(state.hp, 160, "hp is transient: a fresh join starts full");
        assert_eq!(
            world_b.quest_state(welcome_b.player_id).unwrap().state,
            "not_started"
        );

        // The op cache survives too: replaying the same purchase never
        // charges twice.
        let replay = world_b.store_buy(welcome_b.player_id, request).unwrap();
        assert_eq!(replay.status, "accepted");
        assert_eq!(
            world_b.character_state(welcome_b.player_id).unwrap().gold,
            225
        );

        // World B buys the meadow box (60 gold) and publishes it.
        let box_result = world_b
            .store_buy(
                welcome_b.player_id,
                StoreBuyRequest {
                    item: "meadow_box".to_string(),
                    op_id: test_op_id(22),
                },
            )
            .unwrap();
        assert_eq!(box_result.status, "accepted");
        for _ in 0..2 {
            world_b.advance();
        }

        // World A resuming adopts world B's newer record (the generation
        // moved): the box and wallet cross the instance switch.
        let resumed = world_a.join(session).expect("world A resumes");
        assert_eq!(resumed.player_id, welcome_a.player_id);
        let state = world_a.character_state(resumed.player_id).unwrap();
        assert_eq!(state.gold, 225 - 60);
        assert_eq!(bag_count(&world_a, resumed.player_id, "meadow_box"), 1);
        assert_eq!(bag_count(&world_a, resumed.player_id, "trail_potion"), 4);
    }

    // -- tower ----------------------------------------------------------------

    /// Strike tower monster `index` until it falls: teleport the player next
    /// to it, reset the attack cooldown, repeat with fresh sequences (the
    /// world never advances, so monsters never act back).
    fn tower_kill(world: &mut World, welcome: &Welcome, index: usize) {
        let mut strikes = 0;
        while world.monsters[index].hp > 0 {
            let (x, z) = {
                let monster = &mut world.monsters[index];
                (monster.x - 2.0, monster.z)
            };
            {
                let player = world.players.get_mut(&welcome.player_id).unwrap();
                player.x = x;
                player.z = z;
                player.facing = std::f32::consts::FRAC_PI_2;
                player.last_attack_at = None;
            }
            let sequence = world.players[&welcome.player_id].last_sequence + 1;
            let outcome = world.apply_action(
                welcome.player_id,
                welcome.epoch,
                sequence,
                ActionKind::Attack,
                std::f32::consts::FRAC_PI_2,
                0,
                world.tick() as u32,
            );
            assert!(outcome.accepted, "tower strike must be accepted");
            strikes += 1;
            assert!(strikes <= 64, "tower monster dies within its hp budget");
        }
    }

    #[test]
    fn tower_instances_keep_their_arena_bound_without_field_city_colliders() {
        let content = crate::content::test_content();
        let session = test_session_id(89);
        let world = World::new_tower(&content, test_store(), session, 1);
        assert_eq!(world.zone_half_extent(), TOWER_WORLD_HALF_EXTENT);
        assert!(world.static_colliders.is_empty());
    }

    #[test]
    fn tower_floor_one_spawns_three_monsters_at_base_scaling() {
        let content = crate::content::test_content();
        let tower = content.tower.as_ref().expect("tower table");
        let session = test_session_id(90);
        let mut world = World::new_tower(&content, test_store(), session, 1);
        assert_eq!(world.current_floor(), 1);
        let welcome = world.join(session).expect("tower session joins");
        assert_eq!(welcome.epoch, 1);

        // Floor 1: count(1) = 3 monsters of the tower enemy at 1.0x hp, and
        // no field spawns.
        assert_eq!(world.monsters.len(), usize::from(tower.count(1)));
        assert_eq!(world.monsters.len(), 3);
        let puddlekin = content.enemy("puddlekin").expect("tower enemy");
        let ids: BTreeSet<u32> = world.monsters.iter().map(|m| m.id).collect();
        assert_eq!(ids.len(), world.monsters.len());
        for monster in &world.monsters {
            assert_eq!(monster.kind, puddlekin.kind);
            assert_eq!(
                monster.max_hp,
                (puddlekin.hp as f32 * tower.hp_mult(1)).round() as u32
            );
            assert!(monster.respawn_at.is_none());
        }
        // Kill credit uses the floor-scaled exp table.
        assert!((tower.exp_mult(1) - 1.0).abs() < f32::EPSILON);
        assert_eq!(world.enemy_exp[&puddlekin.kind], puddlekin.exp);
        // No milestone is reported for the floor the instance starts on.
        assert!(world.take_tower_floor_events().is_empty());
    }

    #[test]
    fn tower_clear_advances_floor_after_the_grace_and_pays_the_shared_wallet() {
        let content = crate::content::test_content();
        let tower = content.tower.clone().expect("tower table");
        let store = test_store();
        let session = test_session_id(91);
        let mut world = World::new_tower(&content, store.clone(), session, 1);
        let welcome = world.join(session).expect("tower session joins");

        // Kill two of three; the dead pair stays dead past the normal respawn
        // window (tower sets fight once per floor).
        tower_kill(&mut world, &welcome, 0);
        tower_kill(&mut world, &welcome, 1);
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            player.x = 0.0;
            player.z = -24.0; // far beyond aggro while the floor waits
        }
        for _ in 0..(15 * 20 + 5) {
            world.advance();
        }
        assert_eq!(world.monsters[0].hp, 0, "tower monsters never respawn");
        assert_eq!(world.monsters[1].hp, 0, "tower monsters never respawn");
        assert!(world.monsters[2].hp > 0);
        assert_eq!(world.tower.as_ref().unwrap().phase, TowerPhase::Fighting);

        // The last kill clears the floor: the reward lands in the shared
        // wallet immediately.
        tower_kill(&mut world, &welcome, 2);
        let expected_gold = 250 + 3 * world.economy.kill_gold + tower.reward_gold(1);
        let state = world.character_state(welcome.player_id).unwrap();
        assert_eq!(state.gold, expected_gold);
        let puddlekin_exp = content.enemy("puddlekin").expect("tower enemy").exp;
        assert_eq!(state.exp, 3 * puddlekin_exp);
        assert_eq!(
            store.peek(session).expect("shared record").gold,
            expected_gold,
            "the floor reward reaches the shared wallet with the clear"
        );
        assert_eq!(world.tower.as_ref().unwrap().phase, TowerPhase::Cleared);

        // After the ~2 s grace, floor 2 spawns with the floor-2 curve and the
        // floor notice is emitted for the player.
        for _ in 0..(TOWER_ADVANCE_TICKS + 2) {
            world.advance();
        }
        assert_eq!(world.current_floor(), 2);
        assert_eq!(world.monsters.len(), usize::from(tower.count(2)));
        let floor_two_hp = ((content.enemy("puddlekin").expect("tower enemy").hp as f32)
            * tower.hp_mult(2))
        .round() as u32;
        assert!(
            world
                .monsters
                .iter()
                .all(|monster| monster.max_hp == floor_two_hp)
        );
        assert_eq!(
            world.enemy_exp[&1_u8],
            (puddlekin_exp as f32 * tower.exp_mult(2)).round() as u32
        );
        let notices = world.take_pending_notices();
        assert!(
            notices
                .iter()
                .any(|(_, notice)| notice.key == "tower_floor" && notice.params["floor"] == 2)
        );
        assert_eq!(world.take_tower_floor_events(), vec![2]);
        assert!(!world.take_tower_completed());
    }

    #[test]
    fn tower_floor_ten_box_grant_respects_the_full_bag_without_destroying_loot() {
        let content = crate::content::test_content();
        let tower = content.tower.clone().expect("tower table");
        let session = test_session_id(95);
        let mut world = World::new_tower(&content, test_store(), session, 10);
        let welcome = world.join(session).expect("tower session joins");
        assert_eq!(world.current_floor(), 10);
        assert_eq!(world.monsters.len(), usize::from(tower.count(10)));

        // Fill the bag to its cap with distinct fixtures.
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            for index in 0..11 {
                player.bag.insert(format!("fixture_item_{index}"), 1);
            }
        }
        assert_eq!(world.players[&welcome.player_id].bag.len(), 12);

        for index in 0..world.monsters.len() {
            tower_kill(&mut world, &welcome, index);
        }
        let expected_gold = 250 + world.monsters.len() as u32 * 5 + tower.reward_gold(10);
        assert_eq!(
            world.character_state(welcome.player_id).unwrap().gold,
            expected_gold
        );
        // The box is dropped (skipped), the bag is untouched.
        assert_eq!(bag_count(&world, welcome.player_id, "meadow_box"), 0);
        {
            let bag = &world.players[&welcome.player_id].bag;
            assert_eq!(bag.len(), 12, "nothing was destroyed by the skipped box");
            for index in 0..11 {
                assert_eq!(bag[&format!("fixture_item_{index}")], 1);
            }
        }

        // With a slot free, clearing floor 20 lands the box.
        {
            let player = world.players.get_mut(&welcome.player_id).unwrap();
            for index in 0..11 {
                player.bag.remove(&format!("fixture_item_{index}"));
            }
        }
        {
            let runtime = world.tower.as_mut().unwrap();
            runtime.floor = 20;
            runtime.phase = TowerPhase::Fighting;
        }
        world.tower_spawn_floor();
        assert_eq!(world.monsters.len(), usize::from(tower.count(20)));
        for index in 0..world.monsters.len() {
            tower_kill(&mut world, &welcome, index);
        }
        assert_eq!(bag_count(&world, welcome.player_id, "meadow_box"), 1);
    }

    #[test]
    fn tower_completion_at_floor_100_grants_final_reward_notice_and_done() {
        let content = crate::content::test_content();
        let tower = content.tower.clone().expect("tower table");
        let store = test_store();
        let session = test_session_id(96);
        let mut world = World::new_tower(&content, store.clone(), session, tower.max_floor);
        let welcome = world.join(session).expect("tower session joins");
        assert_eq!(world.current_floor(), 100);
        assert_eq!(world.monsters.len(), usize::from(tower.count(100)));
        // hp at floor 100 matches the formula.
        let floor_hp = ((content.enemy("puddlekin").expect("tower enemy").hp as f32)
            * tower.hp_mult(100))
        .round() as u32;
        assert!(
            world
                .monsters
                .iter()
                .all(|monster| monster.max_hp == floor_hp)
        );

        for index in 0..world.monsters.len() {
            tower_kill(&mut world, &welcome, index);
        }
        for _ in 0..(TOWER_ADVANCE_TICKS + 2) {
            world.advance();
        }

        // final_reward with the same bag rules, plus the floor-100 rewards.
        let state = world.character_state(welcome.player_id).unwrap();
        let expected_gold = 250
            + u32::from(tower.count(100)) * 5
            + tower.reward_gold(100)
            + tower.final_reward.gold;
        assert_eq!(state.gold, expected_gold);
        assert_eq!(state.coin, 10 + tower.final_reward.coin);
        assert_eq!(
            bag_count(&world, welcome.player_id, "meadow_box"),
            1 + tower.final_reward.boxes as u8,
            "the floor-100 box plus the final boxes"
        );
        assert_eq!(
            store.peek(session).expect("shared record").gold,
            expected_gold
        );
        let notices = world.take_pending_notices();
        assert!(
            notices
                .iter()
                .any(|(_, notice)| notice.key == "tower_complete" && notice.params["floor"] == 100)
        );
        // The milestone persists best_floor = 100 via the floor events, and
        // the instance is marked complete exactly once.
        assert_eq!(world.take_tower_floor_events(), vec![100]);
        assert!(world.take_tower_completed());
        assert!(!world.take_tower_completed());
        assert_eq!(world.tower.as_ref().unwrap().phase, TowerPhase::Complete);
    }

    #[test]
    fn tower_instances_admit_only_their_bound_session() {
        let content = crate::content::test_content();
        let session = test_session_id(92);
        let mut world = World::new_tower(&content, test_store(), session, 1);
        assert!(world.join(session).is_ok());
        assert_eq!(
            world.join(test_session_id(93)).err(),
            Some("room_full"),
            "tower instances are bound to one session"
        );
        // The bound session still resumes.
        assert!(world.join(session).is_ok());
    }

    #[test]
    fn tower_instance_tears_down_when_the_bound_session_is_pruned() {
        let content = crate::content::test_content();
        let session = test_session_id(94);
        let mut world = World::new_tower(&content, test_store(), session, 1);
        let welcome = world.join(session).expect("tower session joins");
        world.disconnect(welcome.player_id, welcome.epoch);
        let disconnected_at = world.players[&welcome.player_id]
            .disconnected_at
            .expect("disconnect recorded");
        world.prune_expired_sessions_at(disconnected_at + RESUME_GRACE + Duration::from_millis(1));
        assert!(
            world.take_tower_completed(),
            "an abandoned tower instance is torn down instead of leaking its cap slot"
        );
    }
    // ---- E07 golden formulas + dual progression ----

    fn e07_vocation() -> crate::content::VocationStats {
        crate::content::test_content().vocation
    }

    #[test]
    fn e07_golden_formulas_hold() {
        let vocation = e07_vocation();
        let items = crate::content::test_content().items;
        let vocation_hp = 100;
        // Base: STR 10, VIT 6 → ATK = 25 + 20 + 0 + 0 = 45; HP = 100 + 60 = 160; DEF = 0 + 3; SP = 30 + 0 = 30.
        let (atk, def, max_hp, max_sp) = compute_derived(
            &vocation,
            vocation_hp,
            1,
            1,
            &BTreeMap::new(),
            &BTreeMap::new(),
            &items,
            25,
            AllocatedStats::default(),
        );
        assert_eq!((atk, def, max_hp, max_sp), (45, 3, 160, 30));

        // Equipped: blade +8 ATK, vest +5 DEF +20 HP.
        let equipment = BTreeMap::from([
            ("weapon".to_string(), "frontier_blade".to_string()),
            ("armor".to_string(), "frontier_vest".to_string()),
        ]);
        let (atk, def, max_hp, _) = compute_derived(
            &vocation,
            vocation_hp,
            1,
            1,
            &equipment,
            &BTreeMap::new(),
            &items,
            25,
            AllocatedStats::default(),
        );
        assert_eq!((atk, def, max_hp), (53, 8, 180));

        // Refined +4: weapon +20 ATK, armor +8 DEF +100 HP.
        let refine = BTreeMap::from([("weapon".to_string(), 4_u8), ("armor".to_string(), 4_u8)]);
        let (atk_r, def_r, max_hp_r, _) = compute_derived(
            &vocation,
            vocation_hp,
            1,
            1,
            &equipment,
            &refine,
            &items,
            25,
            AllocatedStats::default(),
        );
        assert_eq!((atk_r, def_r, max_hp_r), (53 + 20, 8 + 8, 180 + 100));

        // Level growth: +1 STR and +1 VIT per 10 base levels; job level adds +1 ATK each.
        let (atk, def, max_hp, _) = compute_derived(
            &vocation,
            vocation_hp,
            51,
            11,
            &BTreeMap::new(),
            &BTreeMap::new(),
            &items,
            25,
            AllocatedStats::default(),
        );
        assert_eq!(atk, 25 + (10 + 5) * 2 + 10);
        assert_eq!(def, (6 + 5) / 2);
        assert_eq!(max_hp, 100 + (6 + 5) * 10);
        assert!(items.contains_key("frontier_blade"), "item tuning exists");
    }

    #[test]
    fn e07_dual_exp_levels_up_both_tracks() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(200)).expect("join");
        let player_id = welcome.player_id;
        // 12 kills x 9 exp = 108: base 100 → level 2 (exp 8); job 80 → job 2 (exp 28).
        for _ in 0..12 {
            world.credit_kill(player_id, 1, 0.0, 0.0);
        }
        let player = world.players.get(&player_id).expect("player");
        assert_eq!(player.level, 2, "base curve 100 at level 1");
        assert_eq!(player.exp, 8);
        assert_eq!(player.job_level, 2, "job curve 80 at job level 1");
        assert_eq!(player.job_exp, 28);
        // Derived HP grew with the level (+1 VIT per 10 levels would not tick
        // at level 2, so HP stays 160; the formula is pinned by the other test).
        assert_eq!(player.max_hp, 160);
    }

    #[test]
    fn e07_equip_flow_round_trips_and_recomputes_stats() {
        let mut world = test_world();
        let welcome = world.join(test_session_id(201)).expect("join");
        let player_id = welcome.player_id;
        let atk_before = world.players[&player_id].atk;
        assert_eq!(atk_before, 45, "base ATK formula");

        // Buy the blade (gold 250 -> 170) and equip it.
        let op = crate::cold::StoreBuyRequest {
            item: "frontier_blade".to_string(),
            op_id: "buy-1".to_string(),
        };
        let result = world.store_buy(player_id, op).expect("buy");
        assert_eq!(result.status, "accepted");
        let result = world
            .equip_item(
                player_id,
                crate::cold::EquipItemRequest {
                    item: "frontier_blade".to_string(),
                    op_id: "equip-1".to_string(),
                },
            )
            .expect("equip");
        assert_eq!(result.status, "accepted");
        let player = world.players.get(&player_id).expect("player");
        assert_eq!(
            player.equipment.get("weapon").map(String::as_str),
            Some("frontier_blade")
        );
        assert_eq!(player.bag.get("frontier_blade").copied(), None);
        assert_eq!(player.atk, atk_before + 8, "weapon ATK joins the formula");

        // Same op_id replays the cached result (idempotent).
        let replay = world
            .equip_item(
                player_id,
                crate::cold::EquipItemRequest {
                    item: "frontier_blade".to_string(),
                    op_id: "equip-1".to_string(),
                },
            )
            .expect("replay");
        assert_eq!(replay.op_id, "equip-1");
        assert_eq!(
            world.players[&player_id].atk,
            atk_before + 8,
            "replay does not double-apply"
        );

        // Re-equip the same item while equipped: the bag no longer has it.
        let second = world
            .equip_item(
                player_id,
                crate::cold::EquipItemRequest {
                    item: "frontier_blade".to_string(),
                    op_id: "equip-2".to_string(),
                },
            )
            .expect("second equip");
        assert_eq!(second.status, "rejected");
        assert_eq!(second.reason, "not_owned");

        // Armor: vest raises DEF and MAXHP.
        let result = world
            .store_buy(
                player_id,
                crate::cold::StoreBuyRequest {
                    item: "frontier_vest".to_string(),
                    op_id: "buy-2".to_string(),
                },
            )
            .expect("buy vest");
        assert_eq!(result.status, "accepted");
        let def_before = world.players[&player_id].def;
        let hp_before = world.players[&player_id].max_hp;
        let result = world
            .equip_item(
                player_id,
                crate::cold::EquipItemRequest {
                    item: "frontier_vest".to_string(),
                    op_id: "equip-3".to_string(),
                },
            )
            .expect("equip vest");
        assert_eq!(result.status, "accepted");
        let player = world.players.get(&player_id).expect("player");
        assert_eq!(player.def, def_before + 5);
        assert_eq!(player.max_hp, hp_before + 20);
        assert_eq!(
            player.equipment.get("armor").map(String::as_str),
            Some("frontier_vest")
        );
    }

    #[test]
    fn drop_pickup_round_trips_and_validates_range_and_capacity() {
        let mut world = test_world();
        let session = test_session_id(205);
        let welcome = world.join(session).expect("join");
        let player_id = welcome.player_id;

        // Position player at (0, 0)
        let player = world.players.get_mut(&player_id).unwrap();
        player.x = 0.0;
        player.z = 0.0;
        let start_potions = player.bag.get("trail_potion").copied().unwrap_or(0);

        // 1. Drop within range (x: 1.0, z: 0.0, dist = 1.0 <= DROP_PICKUP_RANGE)
        let enc1 = uuid::Uuid::now_v7();
        world.drops.push(DropEntity {
            id: world.next_drop_id,
            encounter: enc1,
            owner: session,
            item: "trail_potion".to_string(),
            count: 2,
            x: 1.0,
            z: 0.0,
            expires_tick: world.tick + DROP_TTL_TICKS,
        });
        world.next_drop_id += 1;

        let res1 = world
            .pickup_drop(
                player_id,
                crate::cold::PickupDropRequest {
                    encounter: enc1.to_string(),
                    op_id: "pick-1".to_string(),
                },
            )
            .expect("pickup 1");
        assert_eq!(res1.status, "accepted");
        assert_eq!(res1.op_id, "pick-1");
        assert_eq!(
            world.players[&player_id].bag.get("trail_potion").copied(),
            Some(start_potions + 2)
        );
        assert!(world.drops.iter().all(|d| d.encounter != enc1));

        // Replay of same op_id is idempotent
        let replay = world
            .pickup_drop(
                player_id,
                crate::cold::PickupDropRequest {
                    encounter: enc1.to_string(),
                    op_id: "pick-1".to_string(),
                },
            )
            .expect("replay pick 1");
        assert_eq!(replay.status, "accepted");
        assert_eq!(
            world.players[&player_id].bag.get("trail_potion").copied(),
            Some(start_potions + 2)
        );

        // 2. Drop out of range (dist = 5.0 > 2.0)
        let enc2 = uuid::Uuid::now_v7();
        world.drops.push(DropEntity {
            id: world.next_drop_id,
            encounter: enc2,
            owner: session,
            item: "dew_bead".to_string(),
            count: 1,
            x: 5.0,
            z: 0.0,
            expires_tick: world.tick + DROP_TTL_TICKS,
        });
        world.next_drop_id += 1;

        let res2 = world
            .pickup_drop(
                player_id,
                crate::cold::PickupDropRequest {
                    encounter: enc2.to_string(),
                    op_id: "pick-2".to_string(),
                },
            )
            .expect("pickup 2");
        assert_eq!(res2.status, "rejected");
        assert_eq!(res2.reason, "out_of_range");

        // 3. Drop with full bag (when picking up a new item)
        // Fill bag with 12 distinct items
        for i in 0..12 {
            world
                .players
                .get_mut(&player_id)
                .unwrap()
                .bag
                .insert(format!("dummy_item_{i}"), 1);
        }
        let enc3 = uuid::Uuid::now_v7();
        world.drops.push(DropEntity {
            id: world.next_drop_id,
            encounter: enc3,
            owner: session,
            item: "rare_crystal".to_string(),
            count: 1,
            x: 0.5,
            z: 0.0,
            expires_tick: world.tick + DROP_TTL_TICKS,
        });
        world.next_drop_id += 1;

        let res3 = world
            .pickup_drop(
                player_id,
                crate::cold::PickupDropRequest {
                    encounter: enc3.to_string(),
                    op_id: "pick-3".to_string(),
                },
            )
            .expect("pickup 3");
        assert_eq!(res3.status, "rejected");
        assert_eq!(res3.reason, "inventory_full");
    }

    #[test]
    fn stat_allocate_round_trips_and_recomputes_derived_stats() {
        let mut world = test_world();
        let session = test_session_id(206);
        let welcome = world.join(session).expect("join");
        let player_id = welcome.player_id;

        let state = world.character_state(player_id).expect("character_state");
        assert_eq!(state.stat_points, 0);
        assert_eq!(state.stats.str_, 10);
        assert_eq!(state.stats.vit, 6);
        assert_eq!(state.atk, 45);
        assert_eq!(state.def, 3);
        assert_eq!(state.max_hp, 160);

        // 1. Without points: allocation rejected
        let res_fail = world
            .stat_allocate(
                player_id,
                crate::cold::StatAllocateRequest {
                    stat: "str".to_string(),
                    points: 1,
                    op_id: "stat-fail".to_string(),
                },
            )
            .expect("alloc fail");
        assert_eq!(res_fail.status, "rejected");
        assert_eq!(res_fail.reason, "insufficient_stat_points");

        // 2. Award 10 stat points
        world.players.get_mut(&player_id).unwrap().stat_points = 10;

        // Allocate 5 points to STR -> ATK = 45 + (5 * 2) = 55
        let res_str = world
            .stat_allocate(
                player_id,
                crate::cold::StatAllocateRequest {
                    stat: "str".to_string(),
                    points: 5,
                    op_id: "stat-1".to_string(),
                },
            )
            .expect("alloc str");
        assert_eq!(res_str.status, "accepted");
        let p = &world.players[&player_id];
        assert_eq!(p.stat_points, 5);
        assert_eq!(p.allocated_str, 5);
        assert_eq!(p.atk, 55);

        // Replay of stat-1 is idempotent
        let replay = world
            .stat_allocate(
                player_id,
                crate::cold::StatAllocateRequest {
                    stat: "str".to_string(),
                    points: 5,
                    op_id: "stat-1".to_string(),
                },
            )
            .expect("replay");
        assert_eq!(replay.status, "accepted");
        assert_eq!(world.players[&player_id].stat_points, 5);

        // Allocate 4 points to VIT -> VIT 6+4=10. DEF = 10/2 = 5 (+2 DEF). MaxHP = 100 + 100 = 200 (+40 HP).
        let res_vit = world
            .stat_allocate(
                player_id,
                crate::cold::StatAllocateRequest {
                    stat: "vit".to_string(),
                    points: 4,
                    op_id: "stat-2".to_string(),
                },
            )
            .expect("alloc vit");
        assert_eq!(res_vit.status, "accepted");
        let p = &world.players[&player_id];
        assert_eq!(p.stat_points, 1);
        assert_eq!(p.allocated_vit, 4);
        assert_eq!(p.def, 5);
        assert_eq!(p.max_hp, 200);

        // 3. Verify character_state wire packet carries the updated stats
        let state2 = world.character_state(player_id).expect("character_state 2");
        assert_eq!(state2.stat_points, 1);
        assert_eq!(state2.stats.str_, 15);
        assert_eq!(state2.stats.vit, 10);
        assert_eq!(state2.atk, 55);
        assert_eq!(state2.def, 5);
        assert_eq!(state2.max_hp, 200);
    }

    #[test]
    fn refine_item_round_trips_and_recomputes_derived_stats() {
        let mut world=test_world();let id=world.join(test_session_id(207)).unwrap().player_id;
        let p=world.players.get_mut(&id).unwrap();p.bag.insert("frontier_blade".into(),1);p.gold=500;bump_state_revision(p);
        world.equip_item(id,crate::cold::EquipItemRequest {item:"frontier_blade".into(),op_id:uuid::Uuid::new_v4().to_string()}).unwrap();
        let p=&world.players[&id];let piece=p.item_instances.values().find(|i|i.location=="weapon").unwrap().instance_id.clone();let atk=p.atk;
        let request=crate::cold::RefineItemRequest {slot:"weapon".into(),op_id:uuid::Uuid::new_v4().to_string(),instance_id:Some(piece.clone()),expected_revision:Some(p.state_revision)};
        assert_eq!(world.refine_item(id,request.clone()).unwrap().reason,"refine_success");
        assert_eq!(world.players[&id].gold,470);assert_eq!(world.players[&id].atk,atk+5);assert_eq!(world.players[&id].item_instances[&piece].refine,1);
        assert_eq!(world.refine_item(id,request).unwrap().status,"accepted");assert_eq!(world.players[&id].gold,470);
        let state=world.character_state(id).unwrap();assert_eq!(state.refine["weapon"],1);assert_eq!(state.item_instances.iter().find(|i|i.instance_id==piece).unwrap().refine,1);
    }

    #[test]
    fn sp_depletion_and_natural_regeneration() {
        let mut world = test_world();
        let session = test_session_id(208);
        let welcome = world.join(session).expect("join");
        let player_id = welcome.player_id;

        let p = &world.players[&player_id];
        assert_eq!(p.sp, 30);
        assert_eq!(p.max_sp, 30);

        // Position player 1.0m south of monster 0, facing north (0.0)
        world.monsters[0].hp = 1000;
        let mx = world.monsters[0].x;
        let mz = world.monsters[0].z;
        let player = world.players.get_mut(&player_id).unwrap();
        player.x = mx;
        player.z = mz - 1.0;
        player.facing = 0.0;

        // ArcSlash consumes 8 SP
        let outcome =
            world.apply_action(player_id, welcome.epoch, 1, ActionKind::ArcSlash, 0.0, 0, 0);
        assert_eq!(outcome.accepted, true);
        assert_eq!(world.players[&player_id].sp, 22);

        // Reset cooldown and execute 2 more times (22 -> 14 -> 6)
        world.players.get_mut(&player_id).unwrap().last_arc_slash_at = None;
        let o2 = world.apply_action(player_id, welcome.epoch, 2, ActionKind::ArcSlash, 0.0, 0, 0);
        assert_eq!(o2.accepted, true);
        assert_eq!(world.players[&player_id].sp, 14);

        world.players.get_mut(&player_id).unwrap().last_arc_slash_at = None;
        let o3 = world.apply_action(player_id, welcome.epoch, 3, ActionKind::ArcSlash, 0.0, 0, 0);
        assert_eq!(o3.accepted, true);
        assert_eq!(world.players[&player_id].sp, 6);

        // 4th ArcSlash rejected because 6 SP < 8 SP
        world.players.get_mut(&player_id).unwrap().last_arc_slash_at = None;
        let o4 = world.apply_action(player_id, welcome.epoch, 4, ActionKind::ArcSlash, 0.0, 0, 0);
        assert_eq!(o4.accepted, false);
        assert_eq!(o4.reason, RejectReason::Cooldown.code());
        assert_eq!(world.players[&player_id].sp, 6);

        // Attack restores 1 SP
        world.players.get_mut(&player_id).unwrap().last_attack_at = None;
        let o_atk = world.apply_action(player_id, welcome.epoch, 5, ActionKind::Attack, 0.0, 0, 0);
        assert_eq!(o_atk.accepted, true);
        assert_eq!(world.players[&player_id].sp, 7);

        // Advance 40 ticks for natural SP regen
        for _ in 0..40 {
            world.advance();
        }
        // Regens 1 + 1 = 2 SP (7 + 2 = 9)
        assert_eq!(world.players[&player_id].sp, 9);
    }
    #[test]
    fn monster_chase_uses_player_polygon_blockers_and_stuck_watchdog() {
        let mut content=crate::content::test_content();
        let mut field=crate::grounded_city::tests::fixture();
        field.blockers.push(crate::grounded_city::BlockerInput{id:"monster_test_wall".into(),kind:"wall".into(),polygon_xz:vec![[-0.1,-4.0],[0.1,-4.0],[0.1,4.0],[-0.1,4.0]],y_min:0.0,y_max:4.0});
        content.zone_city_traversal=Some(Arc::new(GroundedCity::parse(&field,content.zone_half_extent).unwrap()));
        let mut world=World::new(&content,test_store());let welcome=world.join(test_session_id(9991)).unwrap();
        for monster in &mut world.monsters {monster.hp=0;}
        let monster=&mut world.monsters[0];monster.hp=monster.max_hp;monster.x=-1.0;monster.z=0.0;monster.y=0.0;monster.home_x=-1.0;monster.home_z=0.0;monster.home_y=0.0;monster.aggro=20.0;monster.leash=30.0;
        let encounter=monster.encounter_id;
        let player=world.players.get_mut(&welcome.player_id).unwrap();player.x=8.0;player.z=0.0;player.y=0.0;
        for _ in 0..160 {world.advance();assert!(world.monsters[0].x<=-0.4,"monster cannot pass the same wall as players");}
        assert_ne!(world.monsters[0].encounter_id,encounter,"blocked pursuit resets after forty ticks");
    }
    #[test]
    fn monster_leash_polygon_resets_pursuit_and_combat_state() {
        let mut world=test_world();let welcome=world.join(test_session_id(9992)).unwrap();
        for monster in &mut world.monsters{monster.hp=0;}
        let m=&mut world.monsters[0];m.hp=m.max_hp;m.x=-1.0;m.z=0.0;m.home_x=-1.0;m.home_z=0.0;m.y=0.0;m.home_y=0.0;m.aggro=20.0;m.leash=30.0;m.leash_polygon=vec![[-2.0,-2.0],[2.0,-2.0],[2.0,2.0],[-2.0,2.0]];m.state=monster_state::APPROACH;m.target_player_id=Some(welcome.player_id);m.contributions.insert(welcome.player_id,crate::combat_rules::Contribution::default());
        let p=world.players.get_mut(&welcome.player_id).unwrap();p.x=8.0;p.z=0.0;
        world.advance();let m=&world.monsters[0];assert_eq!((m.x,m.z),(-1.0,0.0));assert_eq!(m.state,monster_state::IDLE);assert_eq!(m.target_player_id,None);assert!(m.contributions.is_empty());
    }

    #[test]
    fn queued_inputs_before_dodge_never_gain_its_sequence_speed_boost() {
        let mut world=test_world();world.city_traversal=None;world.static_colliders.clear();let welcome=world.join(test_session_id(9993)).unwrap();
        for monster in &mut world.monsters{monster.hp=0;}
        world.update_input(welcome.player_id,welcome.epoch,1,1.0,0.0,0.0,0);
        world.update_input(welcome.player_id,welcome.epoch,2,1.0,0.0,0.0,0);
        assert!(world.apply_action(welcome.player_id,welcome.epoch,3,ActionKind::Dodge,0.0,0,0).accepted);
        let step=world.player_speed*FIXED_DT;let start=world.players[&welcome.player_id].x;
        world.advance();assert!((world.players[&welcome.player_id].x-start-step).abs()<0.0001);
        world.update_input(welcome.player_id,welcome.epoch,4,1.0,0.0,0.0,0);
        world.advance();assert!((world.players[&welcome.player_id].x-start-step*2.0).abs()<0.0001);
        world.advance();assert!((world.players[&welcome.player_id].x-start-step*(2.0+world.combat.dodge_mult)).abs()<0.0001);
        // Missing-input repetition is already capped; it does not extend the
        // invulnerability timer or keep moving forever without fresh input.
        for _ in 0..20 {world.advance();}let stopped=world.players[&welcome.player_id].x;world.advance();assert_eq!(world.players[&welcome.player_id].x,stopped);
    }

}
