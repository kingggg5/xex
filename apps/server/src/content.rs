//! Content bundle v0 (V5-03).
//!
//! `content/source/` is the authored source of truth (tuning, zones, quests,
//! dialogue). It builds to `content/build/<hash>/bundle.json`: canonical JSON
//! (sorted keys, compact) whose FNV-1a-64 hash names its directory. The server
//! loads the built bundle, verifies the hash, and refuses to boot otherwise;
//! the client loads the same bytes and compares against `Welcome.content_hash`.
//!
//! Validation follows the system-design catalog §2 (import boundary): unique
//! IDs, valid references, finite bounded numbers, no cyclic quest
//! prerequisites, and matching th/en localization keys.

use crate::grounded_city::{CityTraversalInput, GroundedCity};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Arc;

/// P1 zone bound, single-sourced here (multi-zone play makes it dynamic).
/// Splits the difference the plan allows: the old hard-coded 56 m field now
/// lives in zone data instead of code.
pub const ZONE_HALF_EXTENT: f32 = 308.0;

#[derive(Debug, Clone, PartialEq)]
pub enum ContentError {
    Io(String),
    Parse(String),
    Validation(String),
    HashMismatch { expected: String, actual: String },
}

impl std::fmt::Display for ContentError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(message) => write!(formatter, "content IO: {message}"),
            Self::Parse(message) => write!(formatter, "content parse: {message}"),
            Self::Validation(message) => write!(formatter, "content invalid: {message}"),
            Self::HashMismatch { expected, actual } => write!(
                formatter,
                "content hash mismatch: dir {expected} != computed {actual}"
            ),
        }
    }
}

// ---------------------------------------------------------------------------
// Source schema (mirrors content/source/*.json)
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct ManifestFile {
    schema: u32,
    #[allow(dead_code)]
    name: String,
    #[allow(dead_code)]
    version: String,
    tick_hz: u8,
    min_protocol: u8,
    player: ManifestPlayer,
}

#[derive(Debug, Deserialize, Clone)]
struct ManifestPlayer {
    #[allow(dead_code)]
    hp: u16,
    #[allow(dead_code)]
    speed: f32,
    jump_v: f32,
    gravity: f32,
    sprint_mult: f32,
    pet_follow_dist: f32,
    pet_speed_mult: f32,
}

#[derive(Debug, Deserialize)]
struct ZonesFile {
    zones: Vec<ZoneRaw>,
}

#[derive(Debug, Deserialize)]
struct ZoneRaw {
    id: u16,
    #[allow(dead_code)]
    key: String,
    name_key: String,
    half_extent: f32,
    monster_spawns: Vec<SpawnRaw>,
    pois: Vec<PoiRaw>,
    #[serde(default)]
    static_colliders: Vec<ZoneColliderRaw>,
    #[serde(default)]
    terrain_cells: Vec<TerrainCellRaw>,
    #[serde(default)]
    world_props: Vec<WorldPropRaw>,
    #[serde(default)]
    world_routes: Vec<WorldRouteRaw>,
    #[serde(default)]
    city_traversal: Option<CityTraversalInput>,
}

#[derive(Debug, Deserialize, Clone)]
struct TerrainCellRaw {
    id: String,
    asset: String,
    bounds_xz: [f32; 4],
    surface_y: f32,
    walkable: bool,
    neighbors: TerrainNeighborsRaw,
}

#[derive(Debug, Deserialize, Clone)]
struct TerrainNeighborsRaw {
    north: Option<String>,
    east: Option<String>,
    south: Option<String>,
    west: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct WorldPropRaw {
    id: String,
    cell: String,
    kind: String,
    x: f32,
    z: f32,
    height: f32,
    scale: f32,
    yaw: f32,
    collider_size: [f32; 3],
}

#[derive(Debug, Deserialize, Clone)]
struct WorldRouteRaw {
    id: String,
    width: f32,
    points: Vec<[f32; 2]>,
}

#[derive(Debug, Deserialize, Clone)]
struct ZoneColliderRaw {
    id: String,
    center: [f32; 3],
    size: [f32; 3],
}

#[derive(Debug, Deserialize, Clone)]
struct SpawnRaw {
    enemy: String,
    x: f32,
    z: f32,
    #[serde(default)]
    leash_polygon: Vec<[f32;2]>,
}

#[derive(Debug, Deserialize, Clone)]
struct PoiRaw {
    id: String,
    x: f32,
    z: f32,
}

#[derive(Debug, Deserialize)]
struct AbilitiesFile {
    abilities: Vec<AbilityRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct AbilityRaw {
    id: String,
    cooldown_ms: u16,
    #[serde(default)]
    range: Option<f32>,
    #[serde(default)]
    damage: Option<u16>,
    #[serde(default)]
    targets: Option<u8>,
    #[serde(default)]
    arc_deg: Option<u16>,
    #[serde(default)]
    windup_ms: Option<u16>,
    #[serde(default)]
    active_ms: Option<u16>,
    #[serde(default)]
    recovery_ms: Option<u16>,
    #[serde(default)]
    duration_ms: Option<u16>,
    #[serde(default)]
    speed_mult: Option<f32>,
    #[serde(default)]
    reduction_pct: Option<u8>,
    #[serde(default)]
    perfect_ms: Option<u16>,
    #[serde(default)]
    max_hold_ms: Option<u16>,
    #[serde(default)]
    heal: Option<u16>,
    #[serde(default)]
    carry: Option<u8>,
}

#[derive(Debug, Deserialize)]
struct EnemiesFile {
    enemies: Vec<EnemyRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct EnemyRaw {
    id: String,
    kind: u8,
    name_key: String,
    hp: u32,
    level: u8,
        #[serde(default)]
    rank: MonsterRank,
    speed: f32,
    aggro: f32,
    leash: f32,
    respawn_s: u64,
    exp: u32,
    splash_radius: f32,
    splash_damage: u16,
    splash_windup_ms: u16,
    splash_active_ms: u16,
    splash_recovery_ms: u16,
    splash_cooldown_ms: u16,
    /// P4: drop table rolled on kill (each entry rolls independently).
    #[serde(default)]
    drops: Vec<EnemyDropRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct EnemyDropRaw {
    item: String,
    /// Whole-percent chance (1..=100); each entry rolls independently.
    chance_pct: u8,
    min: u8,
    max: u8,
}

#[derive(Debug, Deserialize)]
struct NpcsFile {
    npcs: Vec<NpcRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct NpcRaw {
    id: String,
    zone: u16,
    x: f32,
    z: f32,
    facing: f32,
    radius: f32,
    role: String,
    name_key: String,
    dialogue: String,
}

#[derive(Debug, Deserialize)]
struct QuestsFile {
    quests: Vec<QuestRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct QuestRaw {
    id: String,
    name_key: String,
    giver: String,
    #[serde(default)]
    requires: Vec<String>,
    objectives: Vec<ObjectiveRaw>,
    reward: RewardRaw,
}

#[derive(Debug, Deserialize, Clone)]
struct ObjectiveRaw {
    id: String,
    kind: String,
    #[serde(default)]
    target: Option<String>,
    count: u32,
    #[serde(default)]
    distinct: bool,
}

#[derive(Debug, Deserialize, Clone)]
struct RewardRaw {
    exp: u32,
    #[serde(default)]
    items: Vec<RewardItemRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct RewardItemRaw {
    #[serde(rename = "def")]
    item_def: String,
    count: u8,
}

#[derive(Debug, Deserialize)]
struct ItemsFile {
    items: Vec<ItemRaw>,
}

#[derive(Debug, Deserialize, Clone)]
struct ItemRaw {
    id: String,
    #[serde(rename = "type")]
    kind: String,
    name_key: String,
    desc_key: String,
    stack: u8,
    #[serde(default)]
    heal: Option<u16>,
    // Consumable power buffs (v6 batch): kind atk|speed, multiplier, seconds.
    #[serde(default)]
    buff_kind: Option<String>,
    #[serde(default)]
    buff_mult: Option<f32>,
    #[serde(default)]
    buff_duration_s: Option<u16>,
    // E07 equipment fields (weapon/armor only).
    #[serde(default)]
    pub equip_slot: Option<String>,
    #[serde(default)]
    pub atk: Option<u16>,
    #[serde(default)]
    pub def: Option<u16>,
    #[serde(default)]
    pub hp: Option<u16>,
    #[serde(default)]
    pub equip_level_min: Option<u16>,
}

#[derive(Debug, Deserialize)]
struct VocationsFile {
    vocations: Vec<VocationRaw>,
}

/// P4: validated drop entry for one enemy kind.
#[derive(Debug, Clone)]
pub struct EnemyDropTuning {
    pub item: String,
    pub chance_pct: u8,
    pub min: u8,
    pub max: u8,
}

/// E07: validated equipment stats for one item id (zero values = no bonus).
#[derive(Debug, Clone, Serialize, Default)]
pub struct ItemTuning {
    pub equip_slot: String,
    pub atk: u16,
    pub def: u16,
    pub hp: u16,
    pub equip_level_min: u16,
}

/// V6 buff item tuning: timed power effect applied by `use_item`.
/// `kind` is 0 for attack, 1 for move speed.
#[derive(Debug, Clone, Serialize)]
pub struct BuffTuning {
    pub kind: u8,
    pub mult: f32,
    pub duration_ticks: u64,
}

// ---------------------------------------------------------------------------
// Economy (D-14 session preview: wallet, store, cosmetics, boxes)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomyTable {
    pub starting: EconomyStarting,
    pub kill_gold: u32,
    pub quest_claim_gold: u32,
    pub duplicate_cosmetic_coin: u32,
    pub store: Vec<EconomyStoreEntry>,
    pub skins: BTreeMap<String, EconomySkin>,
    pub pets: BTreeMap<String, EconomyPet>,
    pub boxes: BTreeMap<String, EconomyBox>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomyStarting {
    pub gold: u32,
    pub coin: u32,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomyStoreEntry {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub item: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cosmetic: Option<String>,
    pub currency: String,
    pub price: u32,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomySkin {
    pub tunic: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomyPet {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tint: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomyBox {
    pub table: Vec<EconomyBoxRoll>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TowerTable {
    pub max_floor: u16,
    pub enemy: String,
    pub box_item: String,
    pub per_floor: TowerPerFloor,
    pub box_every_floors: u16,
    pub final_reward: TowerFinalReward,
    pub instances_cap: u16,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TowerPerFloor {
    pub hp_mult_base: f32,
    pub hp_mult_per_floor: f32,
    pub count_base: u16,
    pub count_per_floor: f32,
    pub exp_mult_per_floor: f32,
    pub reward_gold_base: u32,
    pub reward_gold_per_floor: f32,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TowerFinalReward {
    pub gold: u32,
    pub coin: u32,
    pub boxes: u16,
}

impl TowerTable {
    /// Difficulty curve, 1-based floor: hp multiplier at floor `floor`.
    pub fn hp_mult(&self, floor: u16) -> f32 {
        self.per_floor.hp_mult_base + self.per_floor.hp_mult_per_floor * (floor - 1) as f32
    }

    /// Monster count at floor `floor`.
    pub fn count(&self, floor: u16) -> u16 {
        (self.per_floor.count_base as f32 + self.per_floor.count_per_floor * (floor - 1) as f32)
            .round() as u16
    }

    /// EXP multiplier at floor `floor`.
    pub fn exp_mult(&self, floor: u16) -> f32 {
        1.0 + self.per_floor.exp_mult_per_floor * (floor - 1) as f32
    }

    /// Gold granted for clearing floor `floor`.
    pub fn reward_gold(&self, floor: u16) -> u32 {
        (self.per_floor.reward_gold_base as f32
            + self.per_floor.reward_gold_per_floor * (floor - 1) as f32)
            .round() as u32
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EconomyBoxRoll {
    pub weight: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gold: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub coin: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub item: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub min: Option<u8>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max: Option<u8>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cosmetic: Option<String>,
}

#[derive(Debug, Deserialize, Clone, Default, Serialize)]
pub struct StatBlock {
    #[serde(rename = "str", default)]
    pub str_: u16,
    #[serde(rename = "agi", default)]
    pub agi: u16,
    #[serde(rename = "vit", default)]
    pub vit: u16,
    #[serde(rename = "int", default)]
    pub int_: u16,
    #[serde(rename = "dex", default)]
    pub dex: u16,
    #[serde(rename = "luk", default)]
    pub luk: u16,
}

/// E07 dual-exp growth curves (golden formula: exp_to_next(level) =
/// base + per_level * (level - 1)); caps bound both tracks.
#[derive(Debug, Deserialize, Clone, Default, Serialize)]
pub struct ExpCurve {
    #[serde(default = "default_curve_base")]
    pub base: u32,
    #[serde(default = "default_curve_per_level")]
    pub per_level: u32,
}

fn default_curve_base() -> u32 {
    100
}

fn default_curve_per_level() -> u32 {
    20
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct VocationStats {
    #[serde(flatten)]
    pub stats: StatBlock,
    #[serde(default = "default_max_base_level")]
    pub max_base_level: u16,
    #[serde(default = "default_max_job_level")]
    pub max_job_level: u16,
    #[serde(default)]
    pub base_exp: ExpCurve,
    #[serde(default)]
    pub job_exp: ExpCurve,
    /// One primary stat grows +1 every N base levels (golden formula).
    #[serde(default = "default_stat_growth_levels")]
    pub stat_growth_levels: u16,
}

fn default_max_base_level() -> u16 {
    99
}

fn default_max_job_level() -> u16 {
    50
}

fn default_stat_growth_levels() -> u16 {
    10
}

impl VocationStats {
    pub fn exp_to_next(&self, track: ExpTrack, level: u16) -> u32 {
        let curve = match track {
            ExpTrack::Base => &self.base_exp,
            ExpTrack::Job => &self.job_exp,
        };
        curve.base.saturating_add(
            curve
                .per_level
                .saturating_mul(u32::from(level.saturating_sub(1))),
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpTrack {
    Base,
    Job,
}

#[derive(Debug, Deserialize)]
struct VocationRaw {
    id: String,
    name_key: String,
    hp: u16,
    speed: f32,
    #[serde(default)]
    stats: Option<VocationStats>,
}

// ---------------------------------------------------------------------------
// Validated runtime content
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct AbilityTuning {
    pub id: String,
    pub cooldown_ms: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub range: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub damage: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub targets: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub arc_deg: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub windup_ms: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub active_ms: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recovery_ms: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub speed_mult: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reduction_pct: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub perfect_ms: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_hold_ms: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub heal: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub carry: Option<u8>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum MonsterRank {
    #[default]
    Normal,
    Elite,
    Boss,
}

#[derive(Debug, Clone, Serialize)]
pub struct EnemyTuning {
    pub id: String,
    pub kind: u8,
    pub hp: u32,
    pub level: u8,
        pub rank: MonsterRank,
    pub speed: f32,
    pub aggro: f32,
    pub leash: f32,
    pub respawn_s: u64,
    pub exp: u32,
    pub splash_radius: f32,
    pub splash_damage: u16,
    pub splash_windup_ms: u16,
    pub splash_active_ms: u16,
    pub splash_recovery_ms: u16,
    pub splash_cooldown_ms: u16,
}

#[derive(Debug, Clone, Serialize)]
pub struct SpawnTuning {
    pub enemy: String,
    pub x: f32,
    pub z: f32,
    #[serde(skip_serializing_if="Vec::is_empty")]
    pub leash_polygon: Vec<[f32;2]>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ZoneColliderTuning {
    pub id: String,
    pub center: [f32; 3],
    pub size: [f32; 3],
}

#[derive(Debug, Clone)]
pub struct Content {
    pub mage_pilot: crate::mage_trial::Config,
    pub vocation_id: String,
    pub hash: u64,
    pub tick_hz: u8,
    pub player_hp: u16,
    pub player_speed: f32,
    pub zone_id: u16,
    pub zone_half_extent: f32,
    pub zone_colliders: Vec<ZoneColliderTuning>,
    pub zone_terrain_cells: Vec<TerrainCellTuning>,
    /// Indexed support/collision shared by field rooms. Absent preserves flat-room behavior.
    pub zone_city_traversal: Option<Arc<GroundedCity>>,
    pub abilities: HashMap<String, AbilityTuning>,
    pub enemies: HashMap<String, EnemyTuning>,
    pub enemy_kinds: HashMap<u8, String>,
    pub spawns: Vec<SpawnTuning>,
    /// Canonical bundle bytes (what the hash covers and the client fetches).
    pub bundle_json: String,
    /// E07 vocation progression: stats, dual-exp curves and level caps
    /// (from vocations[0]; P1 has exactly one vocation, validated).
    pub vocation: VocationStats,
    /// E07 equipment tuning per item id (weapon/armor only).
    pub items: BTreeMap<String, ItemTuning>,
    /// V6 power-buff tuning per consumable item id.
    pub buffs: BTreeMap<String, BuffTuning>,
    /// V6 player physics + pet follow tuning (manifest player block).
    pub player_jump_v: f32,
    pub player_gravity: f32,
    pub player_sprint_mult: f32,
    pub pet_follow_dist: f32,
    pub pet_speed_mult: f32,
    /// P4 drop tables per enemy id (mapped to kinds in the world).
    pub drop_tables: BTreeMap<String, Vec<EnemyDropTuning>>,
    /// Session-preview economy table (D-14).
    pub economy: Option<EconomyTable>,
    /// Tower curve table (100 floors).
    pub tower: Option<TowerTable>,
}

impl Content {
    pub fn ability(&self, id: &str) -> Option<&AbilityTuning> {
        self.abilities.get(id)
    }

    pub fn enemy(&self, id: &str) -> Option<&EnemyTuning> {
        self.enemies.get(id)
    }

    pub fn buff(&self, id: &str) -> Option<&BuffTuning> {
        self.buffs.get(id)
    }

    pub fn hash_hex(&self) -> String {
        format!("{:016x}", self.hash)
    }
}

// ---------------------------------------------------------------------------
// Loading and validation
// ---------------------------------------------------------------------------

fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

fn finite_in(value: f32, min: f32, max: f32) -> bool {
    value.is_finite() && value >= min && value <= max
}

fn read_json(path: &Path) -> Result<serde_json::Value, ContentError> {
    // Authored traversal can be large. Bound source bytes before serde allocates
    // vectors; typed geometry and spatial-index budgets are checked below.
    let text = if path.file_name().is_some_and(|name| name == "zones.json") {
        read_bounded_content_text(path)?
    } else {
        std::fs::read_to_string(path)
            .map_err(|error| ContentError::Io(format!("{}: {error}", path.display())))?
    };
    serde_json::from_str(&text)
        .map_err(|error| ContentError::Parse(format!("{}: {error}", path.display())))
}

fn read_bounded_content_text(path: &Path) -> Result<String, ContentError> {
    const LIMIT: u64 = 32 * 1024 * 1024;
    let file = std::fs::File::open(path)
        .map_err(|error| ContentError::Io(format!("{}: {error}", path.display())))?;
    let mut bytes = Vec::new();
    file.take(LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| ContentError::Io(format!("{}: {error}", path.display())))?;
    if bytes.len() as u64 > LIMIT {
        return Err(ContentError::Validation(format!(
            "{} exceeds 32 MiB content-byte budget",
            path.display()
        )));
    }
    String::from_utf8(bytes)
        .map_err(|error| ContentError::Parse(format!("{}: {error}", path.display())))
}

fn parse<T>(value: serde_json::Value, path: &Path) -> Result<T, ContentError>
where
    T: for<'de> Deserialize<'de>,
{
    serde_json::from_value(value)
        .map_err(|error| ContentError::Parse(format!("{}: {error}", path.display())))
}

struct SourceBundle {
    mage_pilot: crate::mage_trial::Config,
    manifest: ManifestFile,
    zones: Vec<ZoneRaw>,
    abilities: Vec<AbilityRaw>,
    enemies: Vec<EnemyRaw>,
    npcs: Vec<NpcRaw>,
    quests: Vec<QuestRaw>,
    items: Vec<ItemRaw>,
    vocations: Vec<VocationRaw>,
    economy: EconomyTable,
    tower: TowerTable,
    dialogue_th: BTreeMap<String, String>,
    dialogue_en: BTreeMap<String, String>,
}

fn load_source(dir: &Path) -> Result<SourceBundle, ContentError> {
    let file = |name: &str| dir.join(name);
    let mage_path=file("mage-pilot.json");
    let mage_pilot=if mage_path.exists() {parse(read_json(&mage_path)?,&mage_path)?} else {crate::mage_trial::Config::default()};
    let manifest: ManifestFile = parse(read_json(&file("manifest.json"))?, &file("manifest.json"))?;
    let zones: ZonesFile = parse(read_json(&file("zones.json"))?, &file("zones.json"))?;
    let abilities: AbilitiesFile =
        parse(read_json(&file("abilities.json"))?, &file("abilities.json"))?;
    let enemies: EnemiesFile = parse(read_json(&file("enemies.json"))?, &file("enemies.json"))?;
    let npcs: NpcsFile = parse(read_json(&file("npcs.json"))?, &file("npcs.json"))?;
    let quests: QuestsFile = parse(read_json(&file("quests.json"))?, &file("quests.json"))?;
    let items: ItemsFile = parse(read_json(&file("items.json"))?, &file("items.json"))?;
    let vocations: VocationsFile =
        parse(read_json(&file("vocations.json"))?, &file("vocations.json"))?;
    let economy: EconomyTable = parse(read_json(&file("economy.json"))?, &file("economy.json"))?;
    let tower: TowerTable = parse(read_json(&file("tower.json"))?, &file("tower.json"))?;
    let dialogue_th: BTreeMap<String, String> = parse(
        read_json(&file("dialogue/th.json"))?,
        &file("dialogue/th.json"),
    )?;
    let dialogue_en: BTreeMap<String, String> = parse(
        read_json(&file("dialogue/en.json"))?,
        &file("dialogue/en.json"),
    )?;
    Ok(SourceBundle {
        mage_pilot,
        manifest,
        zones: zones.zones,
        abilities: abilities.abilities,
        enemies: enemies.enemies,
        npcs: npcs.npcs,
        quests: quests.quests,
        items: items.items,
        vocations: vocations.vocations,
        economy,
        tower,
        dialogue_th,
        dialogue_en,
    })
}

fn parse_hex_color(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 7 && bytes[0] == b'#' && bytes[1..].iter().all(|byte| byte.is_ascii_hexdigit())
}

fn validate_economy(
    source: &SourceBundle,
    item_ids: &BTreeMap<String, String>,
) -> Result<(), ContentError> {
    let invalid = |message: String| ContentError::Validation(message);
    let economy = &source.economy;
    for entry in &economy.store {
        let both = entry.item.is_some() && entry.cosmetic.is_some();
        let neither = entry.item.is_none() && entry.cosmetic.is_none();
        if both || neither {
            return Err(invalid(
                "economy store entry needs exactly one of item/cosmetic".to_string(),
            ));
        }
        if !["gold", "coin"].contains(&entry.currency.as_str()) {
            return Err(invalid(
                "economy store entry has unknown currency".to_string(),
            ));
        }
        if let Some(item) = &entry.item
            && !item_ids.contains_key(item)
        {
            return Err(invalid(format!(
                "economy store references unknown item {item}"
            )));
        }
        if let Some(cosmetic) = &entry.cosmetic
            && !economy.skins.contains_key(cosmetic)
            && !economy.pets.contains_key(cosmetic)
        {
            return Err(invalid(format!(
                "economy store references unknown cosmetic {cosmetic}"
            )));
        }
    }
    for (id, skin) in &economy.skins {
        if !parse_hex_color(&skin.tunic) {
            return Err(invalid(format!("skin {id} tunic must be #rrggbb")));
        }
    }
    for (id, pet) in &economy.pets {
        if let Some(tint) = &pet.tint
            && !parse_hex_color(tint)
        {
            return Err(invalid(format!("pet {id} tint must be #rrggbb")));
        }
    }
    for (id, def) in &economy.boxes {
        let Some(item) = source.items.iter().find(|item| &item.id == id) else {
            return Err(invalid(format!("box {id} has no item definition")));
        };
        if item.kind != "box" {
            return Err(invalid(format!("box {id} item type must be box")));
        }
        let total: u32 = def.table.iter().map(|roll| roll.weight).sum();
        if total != 100 {
            return Err(invalid(format!(
                "box {id} weights sum to {total}, expected 100"
            )));
        }
        for roll in &def.table {
            if roll.weight == 0 {
                return Err(invalid(format!("box {id} has a zero-weight roll")));
            }
            let outcomes = [
                roll.gold.is_some(),
                roll.coin.is_some(),
                roll.item.is_some(),
                roll.cosmetic.is_some(),
            ];
            if outcomes.iter().filter(|present| **present).count() != 1 {
                return Err(invalid(format!("box {id} roll needs exactly one outcome")));
            }
            if let Some(item) = &roll.item {
                if !item_ids.contains_key(item) {
                    return Err(invalid(format!("box {id} references unknown item {item}")));
                }
                let min = roll.min.unwrap_or(1);
                let max = roll.max.unwrap_or(1);
                if min == 0 || max < min {
                    return Err(invalid(format!("box {id} roll has bad min/max")));
                }
            }
            if (roll.min.is_some() || roll.max.is_some()) && roll.item.is_none() {
                return Err(invalid(format!(
                    "box {id} roll has min/max without an item"
                )));
            }
            if let Some(cosmetic) = &roll.cosmetic
                && !economy.skins.contains_key(cosmetic)
                && !economy.pets.contains_key(cosmetic)
            {
                return Err(invalid(format!(
                    "box {id} references unknown cosmetic {cosmetic}"
                )));
            }
        }
    }
    Ok(())
}

fn validate(source: &SourceBundle) -> Result<(), ContentError> {
    let invalid = |message: String| ContentError::Validation(message);

    if source.manifest.schema != 1 {
        return Err(invalid("manifest.schema must be 1".to_string()));
    }
    if !(1..=60).contains(&source.manifest.tick_hz) {
        return Err(invalid("manifest.tick_hz out of range".to_string()));
    }
    if source.manifest.min_protocol > crate::wire::PROTOCOL_VERSION {
        return Err(invalid(
            "manifest.min_protocol exceeds server protocol".to_string(),
        ));
    }
    // Player physics + pet follow tuning (v6 movement batch).
    let physics = &source.manifest.player;
    if !finite_in(physics.jump_v, 1.0, 20.0)
        || !finite_in(physics.gravity, 1.0, 60.0)
        || !finite_in(physics.sprint_mult, 1.0, 3.0)
        || !finite_in(physics.pet_follow_dist, 0.5, 5.0)
        || !finite_in(physics.pet_speed_mult, 1.0, 3.0)
    {
        return Err(invalid(
            "manifest.player has bad physics tuning".to_string(),
        ));
    }

    // Localization parity first: every key below must resolve in both.
    let th_keys: BTreeSet<&String> = source.dialogue_th.keys().collect();
    let en_keys: BTreeSet<&String> = source.dialogue_en.keys().collect();
    if th_keys != en_keys {
        let missing_th: Vec<&String> = en_keys.difference(&th_keys).copied().collect();
        let missing_en: Vec<&String> = th_keys.difference(&en_keys).copied().collect();
        return Err(invalid(format!(
            "dialogue key mismatch: missing th {missing_th:?}, missing en {missing_en:?}"
        )));
    }
    for (key, text) in source.dialogue_th.iter().chain(source.dialogue_en.iter()) {
        if text.is_empty() || text.len() > 500 {
            return Err(invalid(format!("dialogue key {key} has bad length")));
        }
    }
    let text_key = |key: &str| -> Result<(), ContentError> {
        if source.dialogue_en.contains_key(key) {
            Ok(())
        } else {
            Err(invalid(format!("missing localization key {key}")))
        }
    };

    // Zones.
    if source.zones.is_empty() {
        return Err(invalid("at least one zone is required".to_string()));
    }
    let mut zone_ids = BTreeSet::new();
    for zone in &source.zones {
        if zone.id == 0 || !zone_ids.insert(zone.id) {
            return Err(invalid(format!("duplicate zone id {}", zone.id)));
        }
        if !(4.0..=4096.0).contains(&zone.half_extent) || !zone.half_extent.is_finite() {
            return Err(invalid(format!("zone {} has bad half_extent", zone.id)));
        }
        if let Some(input) = &zone.city_traversal {
            GroundedCity::parse(input, zone.half_extent)
                .map_err(|error| invalid(format!("zone {} city traversal: {error}", zone.id)))?;
        }
        if zone.static_colliders.len() > 512 {
            return Err(invalid(format!(
                "zone {} has too many static colliders",
                zone.id
            )));
        }
        let mut collider_ids = BTreeSet::new();
        for collider in &zone.static_colliders {
            if !valid_id(&collider.id) || !collider_ids.insert(collider.id.clone()) {
                return Err(invalid(format!(
                    "zone {} has a bad or duplicate static collider id",
                    zone.id
                )));
            }
            if collider
                .center
                .iter()
                .any(|coordinate| !finite_in(*coordinate, -8192.0, 8192.0))
                || collider
                    .size
                    .iter()
                    .any(|dimension| !finite_in(*dimension, 0.01, 8192.0))
            {
                return Err(invalid(format!(
                    "static collider {} has invalid coordinates or size",
                    collider.id
                )));
            }
            for axis in [0, 2] {
                if collider.center[axis].abs() + collider.size[axis] * 0.5 > zone.half_extent {
                    return Err(invalid(format!(
                        "static collider {} outside zone {}",
                        collider.id, zone.id
                    )));
                }
            }
        }
        if zone.static_colliders.len() + zone.world_props.len() > 512 {
            return Err(invalid(format!(
                "zone {} has too many static and authored-prop colliders",
                zone.id
            )));
        }

        let mut terrain_cell_ids = BTreeSet::new();
        for cell in &zone.terrain_cells {
            let [min_x, max_x, min_z, max_z] = cell.bounds_xz;
            if !valid_id(&cell.id)
                || !terrain_cell_ids.insert(cell.id.clone())
                || !valid_id(&cell.asset)
                || !cell.asset.starts_with("env_")
                || cell.asset.contains('/')
                || cell.asset.contains('\\')
            {
                return Err(invalid(format!(
                    "zone {} has a bad or duplicate terrain cell id/asset",
                    zone.id
                )));
            }
            if ![min_x, max_x, min_z, max_z]
                .into_iter()
                .all(|coordinate| finite_in(coordinate, -zone.half_extent, zone.half_extent))
                || !finite_in(cell.surface_y, -0.001, 0.001)
                || !cell.walkable
                || (max_x - min_x - 64.0).abs() > 0.001
                || (max_z - min_z - 64.0).abs() > 0.001
            {
                return Err(invalid(format!(
                    "terrain cell {} must be a walkable flat 64 m square inside zone {}",
                    cell.id, zone.id
                )));
            }
        }
        for (index, cell) in zone.terrain_cells.iter().enumerate() {
            let a = cell.bounds_xz;
            for other in zone.terrain_cells.iter().skip(index + 1) {
                let b = other.bounds_xz;
                let overlaps_x = a[0] < b[1] - 0.001 && b[0] < a[1] - 0.001;
                let overlaps_z = a[2] < b[3] - 0.001 && b[2] < a[3] - 0.001;
                if overlaps_x && overlaps_z {
                    return Err(invalid(format!(
                        "terrain cells {} and {} overlap",
                        cell.id, other.id
                    )));
                }
            }
            for (direction, neighbor_id) in [
                ("north", cell.neighbors.north.as_deref()),
                ("east", cell.neighbors.east.as_deref()),
                ("south", cell.neighbors.south.as_deref()),
                ("west", cell.neighbors.west.as_deref()),
            ] {
                let Some(neighbor_id) = neighbor_id else {
                    continue;
                };
                if neighbor_id == "starter_field"
                    && direction == "north"
                    && (a[3] + 64.0).abs() <= 0.001
                {
                    continue;
                }
                let Some(neighbor) = zone
                    .terrain_cells
                    .iter()
                    .find(|candidate| candidate.id == neighbor_id)
                else {
                    return Err(invalid(format!(
                        "terrain cell {} references unknown {direction} neighbor {neighbor_id}",
                        cell.id
                    )));
                };
                let reciprocal = match direction {
                    "north" => neighbor.neighbors.south.as_deref(),
                    "east" => neighbor.neighbors.west.as_deref(),
                    "south" => neighbor.neighbors.north.as_deref(),
                    _ => neighbor.neighbors.east.as_deref(),
                };
                let b = neighbor.bounds_xz;
                let edges_match = match direction {
                    "north" => {
                        (a[3] - b[2]).abs() <= 0.001
                            && (a[0] - b[0]).abs() <= 0.001
                            && (a[1] - b[1]).abs() <= 0.001
                    }
                    "east" => {
                        (a[1] - b[0]).abs() <= 0.001
                            && (a[2] - b[2]).abs() <= 0.001
                            && (a[3] - b[3]).abs() <= 0.001
                    }
                    "south" => {
                        (a[2] - b[3]).abs() <= 0.001
                            && (a[0] - b[0]).abs() <= 0.001
                            && (a[1] - b[1]).abs() <= 0.001
                    }
                    _ => {
                        (a[0] - b[1]).abs() <= 0.001
                            && (a[2] - b[2]).abs() <= 0.001
                            && (a[3] - b[3]).abs() <= 0.001
                    }
                };
                if reciprocal != Some(cell.id.as_str())
                    || !edges_match
                    || (cell.surface_y - neighbor.surface_y).abs() > 0.001
                {
                    return Err(invalid(format!(
                        "terrain seam {} -> {} is not reciprocal and height-aligned",
                        cell.id, neighbor.id
                    )));
                }
            }
        }

        let mut prop_ids = collider_ids.clone();
        for prop in &zone.world_props {
            let Some(cell) = zone.terrain_cells.iter().find(|cell| cell.id == prop.cell) else {
                return Err(invalid(format!(
                    "world prop {} references unknown terrain cell",
                    prop.id
                )));
            };
            let [min_x, max_x, min_z, max_z] = cell.bounds_xz;
            if !valid_id(&prop.id)
                || !prop_ids.insert(prop.id.clone())
                || !matches!(
                    prop.kind.as_str(),
                    "tree_a"
                        | "tree_b"
                        | "tree_c"
                        | "bush"
                        | "trail_marker"
                        | "broken_cart"
                        | "stone_pillar"
                )
                || !finite_in(prop.x, min_x, max_x)
                || !finite_in(prop.z, min_z, max_z)
                || !finite_in(prop.height, 0.3, 20.0)
                || !finite_in(prop.scale, 0.25, 3.0)
                || !finite_in(prop.yaw, -100.0, 100.0)
                || prop
                    .collider_size
                    .iter()
                    .any(|dimension| !finite_in(*dimension, 0.1, 20.0))
                || prop.x - prop.collider_size[0] * 0.5 < min_x
                || prop.x + prop.collider_size[0] * 0.5 > max_x
                || prop.z - prop.collider_size[2] * 0.5 < min_z
                || prop.z + prop.collider_size[2] * 0.5 > max_z
            {
                return Err(invalid(format!(
                    "world prop {} has invalid cell geometry or collider",
                    prop.id
                )));
            }
        }

        let mut route_ids = BTreeSet::new();
        for route in &zone.world_routes {
            if !valid_id(&route.id)
                || !route_ids.insert(route.id.clone())
                || !finite_in(route.width, 1.0, 20.0)
                || route.points.len() < 2
                || route.points.iter().any(|point| {
                    !finite_in(point[0], -zone.half_extent, zone.half_extent)
                        || !finite_in(point[1], -zone.half_extent, zone.half_extent)
                })
            {
                return Err(invalid(format!(
                    "world route {} has invalid points or width",
                    route.id
                )));
            }
            if !route.points.iter().any(|point| {
                zone.terrain_cells.iter().any(|cell| {
                    let b = cell.bounds_xz;
                    point[0] >= b[0] && point[0] <= b[1] && point[1] >= b[2] && point[1] <= b[3]
                })
            }) {
                return Err(invalid(format!(
                    "world route {} does not enter an authored terrain cell",
                    route.id
                )));
            }
        }
        text_key(&zone.name_key)?;
        let mut poi_ids = BTreeSet::new();
        for poi in &zone.pois {
            if !valid_id(&poi.id) || !poi_ids.insert(poi.id.clone()) {
                return Err(invalid(format!("zone {} has bad poi id", zone.id)));
            }
            if poi.x.abs() > zone.half_extent || poi.z.abs() > zone.half_extent {
                return Err(invalid(format!("poi {} outside zone {}", poi.id, zone.id)));
            }
        }
    }

    // Enemies.
    let mut enemy_ids = BTreeSet::new();
    let mut enemy_kinds = BTreeSet::new();
    for enemy in &source.enemies {
        if !valid_id(&enemy.id) || !enemy_ids.insert(enemy.id.clone()) {
            return Err(invalid(format!("bad enemy id {}", enemy.id)));
        }
        if enemy.kind == 0 || !enemy_kinds.insert(enemy.kind) {
            return Err(invalid(format!("bad enemy kind {}", enemy.id)));
        }
        text_key(&enemy.name_key)?;
        if !(1..=99).contains(&enemy.level) {
            return Err(invalid(format!("enemy {} has bad level", enemy.id)));
        }
        if enemy.hp == 0 || enemy.respawn_s == 0 || enemy.respawn_s > 3600 {
            return Err(invalid(format!("enemy {} has bad hp/respawn", enemy.id)));
        }
        if !finite_in(enemy.speed, 0.1, 30.0)
            || !finite_in(enemy.aggro, 1.0, 60.0)
            || !finite_in(enemy.leash, enemy.aggro, 200.0)
        {
            return Err(invalid(format!("enemy {} has bad movement", enemy.id)));
        }
        if enemy.exp > 1_000_000 {
            return Err(invalid(format!("enemy {} has bad exp", enemy.id)));
        }
        if !finite_in(enemy.splash_radius, 0.5, 10.0)
            || enemy.splash_damage == 0
            || enemy.splash_windup_ms < 100
            || enemy.splash_active_ms == 0
            || enemy.splash_recovery_ms == 0
            || u32::from(enemy.splash_cooldown_ms)
                < u32::from(enemy.splash_windup_ms) + u32::from(enemy.splash_active_ms)
            || [
                enemy.splash_windup_ms,
                enemy.splash_active_ms,
                enemy.splash_recovery_ms,
                enemy.splash_cooldown_ms,
            ]
            .iter()
            .any(|duration| *duration % 50 != 0)
        {
            return Err(invalid(format!("enemy {} has bad splash attack", enemy.id)));
        }
        for drop in &enemy.drops {
            if !source.items.iter().any(|item| item.id == drop.item) {
                return Err(invalid(format!(
                    "enemy {} drops unknown item {}",
                    enemy.id, drop.item
                )));
            }
            if !(1..=100).contains(&drop.chance_pct) {
                return Err(invalid(format!("enemy {} has a bad drop chance", enemy.id)));
            }
            if drop.min == 0 || drop.max < drop.min || drop.max > 99 {
                return Err(invalid(format!("enemy {} has a bad drop count", enemy.id)));
            }
        }
    }

    // Zone spawns reference enemies and sit inside the zone.
    for zone in &source.zones {
        if zone.monster_spawns.len() > 64 {
            return Err(invalid(format!("zone {} exceeds 64 monsters before AOI", zone.id)));
        }
        let city=zone.city_traversal.as_ref().map(|input|GroundedCity::parse(input,zone.half_extent)).transpose().map_err(|error|invalid(format!("zone {} traversal: {error}",zone.id)))?;
        let fixture=crate::coordinate_fixture::CoordinateFixture::embedded();
        let blockers=zone_colliders(zone).iter().map(|c|crate::coordinate_fixture::StaticCollider::from_center_dimensions(c.center,c.size)).collect::<Vec<_>>();
        for spawn in &zone.monster_spawns {
            if !spawn.leash_polygon.is_empty() && (!(3..=32).contains(&spawn.leash_polygon.len()) || spawn.leash_polygon.iter().flatten().any(|v|!v.is_finite()||v.abs()>zone.half_extent) || !crate::grounded_city::valid_convex_polygon(&spawn.leash_polygon) || !crate::grounded_city::overlaps_polygon(spawn.x,spawn.z,0.0,&spawn.leash_polygon)) {return Err(invalid(format!("spawn of {} has invalid leash polygon",spawn.enemy)));}
            if !source.enemies.iter().any(|enemy| enemy.id == spawn.enemy) {
                return Err(invalid(format!("spawn of unknown enemy {}", spawn.enemy)));
            }
            if spawn.x.abs() > zone.half_extent || spawn.z.abs() > zone.half_extent {
                return Err(invalid(format!("spawn of {} outside zone", spawn.enemy)));
            }
            if !spawn.x.is_finite() || !spawn.z.is_finite() {
                return Err(invalid("spawn has non-finite coordinates".to_string()));
            }
            if let Some(city)=&city {if !city.height_at(spawn.x,spawn.z).is_some_and(|y|city.position_is_clear(spawn.x,y,spawn.z,fixture.player_radius(),fixture.player_height(),&blockers)){return Err(invalid(format!("spawn of {} intersects grounded collider or lacks support",spawn.enemy)));}}
            if !crate::coordinate_fixture::capsule_position_is_clear(spawn.x,spawn.z,fixture.player_radius(),fixture.player_height(),&blockers) {
                return Err(invalid(format!("spawn of {} intersects a collider",spawn.enemy)));
            }
        }
    }

    // Abilities.
    let mut ability_ids = BTreeSet::new();
    for ability in &source.abilities {
        if !valid_id(&ability.id) || !ability_ids.insert(ability.id.clone()) {
            return Err(invalid(format!("bad ability id {}", ability.id)));
        }
        if !(100..=60000).contains(&ability.cooldown_ms) {
            return Err(invalid(format!("ability {} has bad cooldown", ability.id)));
        }
        let check = |value: Option<f32>, min: f32, max: f32| {
            value.is_none_or(|number| finite_in(number, min, max))
        };
        if !check(ability.range, 0.5, 50.0)
            || !check(ability.speed_mult, 0.5, 10.0)
            || ability.damage.is_some_and(|damage| damage > 10000)
            || ability
                .targets
                .is_some_and(|targets| targets == 0 || targets > 8)
            || ability.arc_deg.is_some_and(|arc| arc == 0 || arc > 360)
            || ability.reduction_pct.is_some_and(|pct| pct > 100)
            || ability.heal.is_some_and(|heal| heal > 10000)
            || ability.carry.is_some_and(|carry| carry == 0)
        {
            return Err(invalid(format!("ability {} has bad numbers", ability.id)));
        }
        for time in [
            ability.windup_ms,
            ability.active_ms,
            ability.recovery_ms,
            ability.duration_ms,
            ability.perfect_ms,
            ability.max_hold_ms,
        ] {
            if time.is_some_and(|ms| ms > 60000) {
                return Err(invalid(format!("ability {} has bad timing", ability.id)));
            }
        }
    }
    for required in ["attack", "arc_slash", "dodge", "guard", "potion"] {
        if !ability_ids.contains(required) {
            return Err(invalid(format!("missing ability {required}")));
        }
    }

    // NPCs.
    let mut npc_ids = BTreeSet::new();
    for npc in &source.npcs {
        if !valid_id(&npc.id) || !npc_ids.insert(npc.id.clone()) {
            return Err(invalid(format!("bad npc id {}", npc.id)));
        }
        let Some(zone) = source.zones.iter().find(|zone| zone.id == npc.zone) else {
            return Err(invalid(format!("npc {} in unknown zone", npc.id)));
        };
        if !npc.x.is_finite()
            || !npc.z.is_finite()
            || !npc.facing.is_finite()
            || npc.x.abs() > zone.half_extent
            || npc.z.abs() > zone.half_extent
        {
            return Err(invalid(format!("npc {} has bad placement", npc.id)));
        }
        if !finite_in(npc.radius, 0.5, 10.0) {
            return Err(invalid(format!("npc {} has bad radius", npc.id)));
        }
        if !["guide", "shop", "trainer", "transit"].contains(&npc.role.as_str()) {
            return Err(invalid(format!("npc {} has bad role", npc.id)));
        }
        text_key(&npc.name_key)?;
        if !valid_id(&npc.dialogue) {
            return Err(invalid(format!("npc {} has bad dialogue id", npc.id)));
        }
    }

    // Items.
    let mut item_ids = BTreeMap::new();
    for item in &source.items {
        if !valid_id(&item.id)
            || item_ids
                .insert(item.id.clone(), item.kind.clone())
                .is_some()
        {
            return Err(invalid(format!("bad item id {}", item.id)));
        }
        if !["consumable", "material", "quest", "weapon", "armor", "box"]
            .contains(&item.kind.as_str())
        {
            return Err(invalid(format!("item {} has bad type", item.id)));
        }
        text_key(&item.name_key)?;
        text_key(&item.desc_key)?;
        if item.stack == 0 {
            return Err(invalid(format!("item {} has bad stack", item.id)));
        }
        if item.heal.is_some_and(|heal| heal == 0 || heal > 10000) {
            return Err(invalid(format!("item {} has bad heal", item.id)));
        }
        // Buff consumables carry exactly one effect: heal XOR buff.
        let has_buff =
            item.buff_kind.is_some() || item.buff_mult.is_some() || item.buff_duration_s.is_some();
        if item.kind == "consumable" && has_buff {
            let kind_ok = item
                .buff_kind
                .as_deref()
                .is_some_and(|kind| kind == "atk" || kind == "speed");
            let mult_ok = item
                .buff_mult
                .is_some_and(|mult| mult.is_finite() && mult > 1.0 && mult <= 3.0);
            let dur_ok = item
                .buff_duration_s
                .is_some_and(|dur| (1..=600).contains(&dur));
            if item.heal.is_some() || !kind_ok || !mult_ok || !dur_ok {
                return Err(invalid(format!("item {} has a bad buff", item.id)));
            }
        } else if has_buff {
            return Err(invalid(format!(
                "item {} carries buff fields without being consumable",
                item.id
            )));
        }
        // E07 equipment rules: only weapon/armor items may carry equip data,
        // and a weapon/armor must declare its slot.
        let equipment_kind = item.kind == "weapon" || item.kind == "armor";
        if let Some(slot) = &item.equip_slot {
            if !equipment_kind || !["weapon", "armor"].contains(&slot.as_str()) {
                return Err(invalid(format!("item {} has a bad equip slot", item.id)));
            }
            if (item.kind == "weapon" && slot != "weapon")
                || (item.kind == "armor" && slot != "armor")
            {
                return Err(invalid(format!(
                    "item {} equip slot does not match its type",
                    item.id
                )));
            }
        } else if equipment_kind {
            return Err(invalid(format!(
                "equipment item {} needs an equip_slot",
                item.id
            )));
        }
        if item.atk.is_some_and(|atk| atk > 10000)
            || item.def.is_some_and(|def| def > 10000)
            || item.hp.is_some_and(|hp| hp > 60000)
        {
            return Err(invalid(format!(
                "item {} has out-of-range equip stats",
                item.id
            )));
        }
        if (item.atk.is_some() || item.def.is_some() || item.hp.is_some()) && !equipment_kind {
            return Err(invalid(format!(
                "item {} carries equip stats without being equipment",
                item.id
            )));
        }
        if item
            .equip_level_min
            .is_some_and(|level| level == 0 || level > 275)
        {
            return Err(invalid(format!(
                "item {} has a bad equip_level_min",
                item.id
            )));
        }
    }

    // Economy (D-14): store rows, cosmetics and loot boxes cross-referenced.
    validate_economy(source, &item_ids)?;

    // Tower: curve ranges and cross-references.
    let tower = &source.tower;
    if !(1..=1000).contains(&tower.max_floor) {
        return Err(invalid("tower.max_floor out of range".to_string()));
    }
    if !enemy_ids.contains(&tower.enemy) {
        return Err(invalid(format!("tower enemy {} is unknown", tower.enemy)));
    }
    if item_ids.get(&tower.box_item).map(|kind| kind.as_str()) != Some("box") {
        return Err(invalid(format!(
            "tower box_item {} must be an item of type box",
            tower.box_item
        )));
    }
    let per = &tower.per_floor;
    if per.hp_mult_base < 0.0
        || !per.hp_mult_base.is_finite()
        || !(0.0..=100.0).contains(&per.hp_mult_per_floor)
    {
        return Err(invalid("tower hp multipliers out of range".to_string()));
    }
    if per.count_base == 0 || per.count_base > 64 || per.count_per_floor < 0.0 {
        return Err(invalid("tower monster counts out of range".to_string()));
    }
    if tower.box_every_floors == 0 || tower.box_every_floors > tower.max_floor {
        return Err(invalid("tower.box_every_floors out of range".to_string()));
    }
    if !(1..=256).contains(&tower.instances_cap) {
        return Err(invalid("tower.instances_cap out of range".to_string()));
    }

    // Quests (+ cycle check over requires).
    let mut quest_ids = BTreeSet::new();
    for quest in &source.quests {
        if !valid_id(&quest.id) || !quest_ids.insert(quest.id.clone()) {
            return Err(invalid(format!("bad quest id {}", quest.id)));
        }
        text_key(&quest.name_key)?;
        if !source.npcs.iter().any(|npc| npc.id == quest.giver) {
            return Err(invalid(format!("quest {} has unknown giver", quest.id)));
        }
        if quest.objectives.is_empty() {
            return Err(invalid(format!("quest {} has no objectives", quest.id)));
        }
        for objective in &quest.objectives {
            if !valid_id(&objective.id) || objective.count == 0 || objective.count > 9999 {
                return Err(invalid(format!("quest {} has bad objective", quest.id)));
            }
            if !["activate", "defeat", "talk", "collect"].contains(&objective.kind.as_str()) {
                return Err(invalid(format!(
                    "quest {} has bad objective kind",
                    quest.id
                )));
            }
            if let Some(target) = &objective.target {
                let known = source.enemies.iter().any(|enemy| &enemy.id == target)
                    || source.npcs.iter().any(|npc| &npc.id == target)
                    || source.items.iter().any(|item| &item.id == target);
                if !known {
                    return Err(invalid(format!(
                        "quest {} objective targets unknown {}",
                        quest.id, target
                    )));
                }
            }
        }
        if quest.reward.exp > 1_000_000 {
            return Err(invalid(format!("quest {} has bad reward exp", quest.id)));
        }
        for grant in &quest.reward.items {
            if !source.items.iter().any(|item| item.id == grant.item_def) {
                return Err(invalid(format!(
                    "quest {} rewards unknown item {}",
                    quest.id, grant.item_def
                )));
            }
            if grant.count == 0 {
                return Err(invalid(format!("quest {} has bad grant count", quest.id)));
            }
        }
    }
    // Cycle detection over mandatory prerequisites.
    let quest_map: HashMap<String, &QuestRaw> = source
        .quests
        .iter()
        .map(|quest| (quest.id.clone(), quest))
        .collect();
    for quest in &source.quests {
        for required in &quest.requires {
            if !quest_map.contains_key(required) {
                return Err(invalid(format!(
                    "quest {} requires unknown {}",
                    quest.id, required
                )));
            }
        }
    }
    let mut visiting = BTreeSet::new();
    let mut done = BTreeSet::new();
    fn visit(
        id: &str,
        map: &HashMap<String, &QuestRaw>,
        visiting: &mut BTreeSet<String>,
        done: &mut BTreeSet<String>,
    ) -> Result<(), String> {
        if done.contains(id) {
            return Ok(());
        }
        if !visiting.insert(id.to_string()) {
            return Err(format!("cyclic quest prerequisite at {id}"));
        }
        if let Some(quest) = map.get(id) {
            for required in &quest.requires {
                visit(required, map, visiting, done)?;
            }
        }
        visiting.remove(id);
        done.insert(id.to_string());
        Ok(())
    }
    for quest in &source.quests {
        visit(&quest.id, &quest_map, &mut visiting, &mut done).map_err(ContentError::Validation)?;
    }

    // Vocations.
    if source.vocations.is_empty() {
        return Err(invalid("at least one vocation is required".to_string()));
    }
    let mut vocation_ids = BTreeSet::new();
    for vocation in &source.vocations {
        if !valid_id(&vocation.id) || !vocation_ids.insert(vocation.id.clone()) {
            return Err(invalid(format!("bad vocation id {}", vocation.id)));
        }
        text_key(&vocation.name_key)?;
        if vocation.hp == 0 || vocation.hp > 60000 || !finite_in(vocation.speed, 0.5, 30.0) {
            return Err(invalid(format!("vocation {} has bad stats", vocation.id)));
        }
        if let Some(stats) = &vocation.stats {
            let total = stats.stats.str_
                + stats.stats.agi
                + stats.stats.vit
                + stats.stats.int_
                + stats.stats.dex
                + stats.stats.luk;
            if total == 0 || total > 300 {
                return Err(invalid(format!(
                    "vocation {} has bad base stat totals",
                    vocation.id
                )));
            }
            if stats.max_base_level == 0
                || stats.max_base_level > 275
                || stats.max_job_level == 0
                || stats.max_job_level > 99
            {
                return Err(invalid(format!(
                    "vocation {} has bad level caps",
                    vocation.id
                )));
            }
            if stats.base_exp.base == 0
                || stats.base_exp.per_level > 1_000_000
                || stats.job_exp.base == 0
                || stats.job_exp.per_level > 1_000_000
            {
                return Err(invalid(format!(
                    "vocation {} has bad exp curves",
                    vocation.id
                )));
            }
            if stats.stat_growth_levels == 0 || stats.stat_growth_levels > 100 {
                return Err(invalid(format!(
                    "vocation {} has bad stat growth",
                    vocation.id
                )));
            }
        } else {
            return Err(invalid(format!(
                "vocation {} needs a stats block (E07)",
                vocation.id
            )));
        }
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Canonical bundle (what the hash covers)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
struct CanonicalBundle {
    mage_pilot: crate::mage_trial::Config,
    schema: u32,
    name: String,
    version: String,
    tick_hz: u8,
    player: CanonicalPlayer,
    zones: Vec<CanonicalZone>,
    abilities: BTreeMap<String, AbilityTuning>,
    enemies: BTreeMap<String, EnemyRef>,
    npcs: BTreeMap<String, CanonicalNpc>,
    quests: BTreeMap<String, CanonicalQuest>,
    items: BTreeMap<String, CanonicalItem>,
    vocations: BTreeMap<String, CanonicalVocation>,
    economy: EconomyTable,
    tower: TowerTable,
    dialogue: BTreeMap<String, BTreeMap<String, String>>,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalPlayer {
    hp: u16,
    speed: f32,
    jump_v: f32,
    gravity: f32,
    sprint_mult: f32,
    pet_follow_dist: f32,
    pet_speed_mult: f32,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalZone {
    id: u16,
    key: String,
    name_key: String,
    half_extent: f32,
    static_colliders: Vec<ZoneColliderTuning>,
    monster_spawns: Vec<SpawnTuning>,
    pois: BTreeMap<String, CanonicalPoi>,
    terrain_cells: Vec<TerrainCellTuning>,
    world_props: Vec<WorldPropTuning>,
    world_routes: Vec<WorldRouteTuning>,
    #[serde(skip_serializing_if = "Option::is_none")]
    city_traversal: Option<CityTraversalInput>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TerrainCellTuning {
    pub id: String,
    pub asset: String,
    pub bounds_xz: [f32; 4],
    pub surface_y: f32,
    pub walkable: bool,
    pub neighbors: TerrainNeighborsTuning,
}

#[derive(Debug, Clone, Serialize)]
pub struct TerrainNeighborsTuning {
    pub north: Option<String>,
    pub east: Option<String>,
    pub south: Option<String>,
    pub west: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct WorldPropTuning {
    pub id: String,
    pub cell: String,
    pub kind: String,
    pub x: f32,
    pub z: f32,
    pub height: f32,
    pub scale: f32,
    pub yaw: f32,
    pub collider_size: [f32; 3],
}

#[derive(Debug, Clone, Serialize)]
struct WorldRouteTuning {
    id: String,
    width: f32,
    points: Vec<[f32; 2]>,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalPoi {
    x: f32,
    z: f32,
}

#[derive(Debug, Clone, Serialize)]
struct EnemyRef {
    kind: u8,
    name_key: String,
    hp: u32,
    level: u8,
        rank: MonsterRank,
    speed: f32,
    aggro: f32,
    leash: f32,
    respawn_s: u64,
    exp: u32,
    splash_radius: f32,
    splash_damage: u16,
    splash_windup_ms: u16,
    splash_active_ms: u16,
    splash_recovery_ms: u16,
    splash_cooldown_ms: u16,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalNpc {
    zone: u16,
    x: f32,
    z: f32,
    facing: f32,
    radius: f32,
    role: String,
    name_key: String,
    dialogue: String,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalQuest {
    name_key: String,
    giver: String,
    requires: Vec<String>,
    objectives: Vec<CanonicalObjective>,
    reward_exp: u32,
    reward_items: Vec<CanonicalGrant>,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalObjective {
    id: String,
    kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    target: Option<String>,
    count: u32,
    distinct: bool,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalGrant {
    #[serde(rename = "def")]
    item_def: String,
    count: u8,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalItem {
    #[serde(rename = "type")]
    kind: String,
    name_key: String,
    desc_key: String,
    stack: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    heal: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    buff_kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    buff_mult: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    buff_duration_s: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    equip_slot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    atk: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    def: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    hp: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    equip_level_min: Option<u16>,
}

#[derive(Debug, Clone, Serialize)]
struct CanonicalVocation {
    name_key: String,
    hp: u16,
    speed: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    stats: Option<VocationStats>,
}

fn canonicalize(source: &SourceBundle) -> CanonicalBundle {
    CanonicalBundle {
        mage_pilot: source.mage_pilot.clone(),
        schema: source.manifest.schema,
        name: "aetherfield-content-v0".to_string(),
        version: "0.1.0".to_string(),
        tick_hz: source.manifest.tick_hz,
        player: CanonicalPlayer {
            hp: source.vocations[0].hp,
            speed: source.vocations[0].speed,
            jump_v: source.manifest.player.jump_v,
            gravity: source.manifest.player.gravity,
            sprint_mult: source.manifest.player.sprint_mult,
            pet_follow_dist: source.manifest.player.pet_follow_dist,
            pet_speed_mult: source.manifest.player.pet_speed_mult,
        },
        zones: source
            .zones
            .iter()
            .map(|zone| CanonicalZone {
                id: zone.id,
                key: zone.key.clone(),
                name_key: zone.name_key.clone(),
                half_extent: zone.half_extent,
                static_colliders: zone_colliders(zone),
                city_traversal: zone.city_traversal.clone(),
                monster_spawns: zone
                    .monster_spawns
                    .iter()
                    .map(|spawn| SpawnTuning {
                        enemy: spawn.enemy.clone(),
                        x: spawn.x,
                        z: spawn.z,
                        leash_polygon: spawn.leash_polygon.clone(),
                    })
                    .collect(),
                pois: zone
                    .pois
                    .iter()
                    .map(|poi| (poi.id.clone(), CanonicalPoi { x: poi.x, z: poi.z }))
                    .collect(),
                terrain_cells: zone
                    .terrain_cells
                    .iter()
                    .map(|cell| TerrainCellTuning {
                        id: cell.id.clone(),
                        asset: cell.asset.clone(),
                        bounds_xz: cell.bounds_xz,
                        surface_y: cell.surface_y,
                        walkable: cell.walkable,
                        neighbors: TerrainNeighborsTuning {
                            north: cell.neighbors.north.clone(),
                            east: cell.neighbors.east.clone(),
                            south: cell.neighbors.south.clone(),
                            west: cell.neighbors.west.clone(),
                        },
                    })
                    .collect(),
                world_props: zone
                    .world_props
                    .iter()
                    .map(|prop| WorldPropTuning {
                        id: prop.id.clone(),
                        cell: prop.cell.clone(),
                        kind: prop.kind.clone(),
                        x: prop.x,
                        z: prop.z,
                        height: prop.height,
                        scale: prop.scale,
                        yaw: prop.yaw,
                        collider_size: prop.collider_size,
                    })
                    .collect(),
                world_routes: zone
                    .world_routes
                    .iter()
                    .map(|route| WorldRouteTuning {
                        id: route.id.clone(),
                        width: route.width,
                        points: route.points.clone(),
                    })
                    .collect(),
            })
            .collect(),
        abilities: source
            .abilities
            .iter()
            .map(|ability| {
                (
                    ability.id.clone(),
                    AbilityTuning {
                        id: ability.id.clone(),
                        cooldown_ms: ability.cooldown_ms,
                        range: ability.range,
                        damage: ability.damage,
                        targets: ability.targets,
                        arc_deg: ability.arc_deg,
                        windup_ms: ability.windup_ms,
                        active_ms: ability.active_ms,
                        recovery_ms: ability.recovery_ms,
                        duration_ms: ability.duration_ms,
                        speed_mult: ability.speed_mult,
                        reduction_pct: ability.reduction_pct,
                        perfect_ms: ability.perfect_ms,
                        max_hold_ms: ability.max_hold_ms,
                        heal: ability.heal,
                        carry: ability.carry,
                    },
                )
            })
            .collect(),
        enemies: source
            .enemies
            .iter()
            .map(|enemy| {
                (
                    enemy.id.clone(),
                    EnemyRef {
                        kind: enemy.kind,
                        name_key: enemy.name_key.clone(),
                        hp: enemy.hp,
                        level: enemy.level,
                        rank: enemy.rank,
                        speed: enemy.speed,
                        aggro: enemy.aggro,
                        leash: enemy.leash,
                        respawn_s: enemy.respawn_s,
                        exp: enemy.exp,
                        splash_radius: enemy.splash_radius,
                        splash_damage: enemy.splash_damage,
                        splash_windup_ms: enemy.splash_windup_ms,
                        splash_active_ms: enemy.splash_active_ms,
                        splash_recovery_ms: enemy.splash_recovery_ms,
                        splash_cooldown_ms: enemy.splash_cooldown_ms,
                    },
                )
            })
            .collect(),
        npcs: source
            .npcs
            .iter()
            .map(|npc| {
                (
                    npc.id.clone(),
                    CanonicalNpc {
                        zone: npc.zone,
                        x: npc.x,
                        z: npc.z,
                        facing: npc.facing,
                        radius: npc.radius,
                        role: npc.role.clone(),
                        name_key: npc.name_key.clone(),
                        dialogue: npc.dialogue.clone(),
                    },
                )
            })
            .collect(),
        quests: source
            .quests
            .iter()
            .map(|quest| {
                (
                    quest.id.clone(),
                    CanonicalQuest {
                        name_key: quest.name_key.clone(),
                        giver: quest.giver.clone(),
                        requires: quest.requires.clone(),
                        objectives: quest
                            .objectives
                            .iter()
                            .map(|objective| CanonicalObjective {
                                id: objective.id.clone(),
                                kind: objective.kind.clone(),
                                target: objective.target.clone(),
                                count: objective.count,
                                distinct: objective.distinct,
                            })
                            .collect(),
                        reward_exp: quest.reward.exp,
                        reward_items: quest
                            .reward
                            .items
                            .iter()
                            .map(|grant| CanonicalGrant {
                                item_def: grant.item_def.clone(),
                                count: grant.count,
                            })
                            .collect(),
                    },
                )
            })
            .collect(),
        items: source
            .items
            .iter()
            .map(|item| {
                (
                    item.id.clone(),
                    CanonicalItem {
                        kind: item.kind.clone(),
                        name_key: item.name_key.clone(),
                        desc_key: item.desc_key.clone(),
                        stack: item.stack,
                        heal: item.heal,
                        buff_kind: item.buff_kind.clone(),
                        buff_mult: item.buff_mult,
                        buff_duration_s: item.buff_duration_s,
                        equip_slot: item.equip_slot.clone(),
                        atk: item.atk,
                        def: item.def,
                        hp: item.hp,
                        equip_level_min: item.equip_level_min,
                    },
                )
            })
            .collect(),
        vocations: source
            .vocations
            .iter()
            .map(|vocation| {
                (
                    vocation.id.clone(),
                    CanonicalVocation {
                        name_key: vocation.name_key.clone(),
                        hp: vocation.hp,
                        speed: vocation.speed,
                        stats: vocation.stats.clone(),
                    },
                )
            })
            .collect(),
        economy: source.economy.clone(),
        tower: source.tower.clone(),
        dialogue: BTreeMap::from([
            ("en".to_string(), source.dialogue_en.clone()),
            ("th".to_string(), source.dialogue_th.clone()),
        ]),
    }
}

fn zone_colliders(zone: &ZoneRaw) -> Vec<ZoneColliderTuning> {
    let mut colliders = zone
        .static_colliders
        .iter()
        .map(|collider| ZoneColliderTuning {
            id: collider.id.clone(),
            center: collider.center,
            size: collider.size,
        })
        .collect::<Vec<_>>();
    colliders.extend(zone.world_props.iter().map(|prop| ZoneColliderTuning {
        id: prop.id.clone(),
        center: [prop.x, prop.collider_size[1] * 0.5, prop.z],
        size: prop.collider_size,
    }));
    colliders
}

pub fn fnv1a64(bytes: &[u8]) -> u64 {
    let mut hash = 14695981039346656037_u64;
    for byte in bytes {
        hash = (hash ^ u64::from(*byte)).wrapping_mul(1099511628211);
    }
    hash
}

/// Build validated runtime content from a source directory.
pub fn build_from_source(dir: &Path) -> Result<Content, ContentError> {
    let source = load_source(dir)?;
    source.mage_pilot.validate().map_err(|reason|ContentError::Validation(reason.into()))?;
    validate(&source)?;
    let canonical = canonicalize(&source);
    let bundle_json = serde_json::to_string(&canonical)
        .map_err(|error| ContentError::Parse(format!("canonicalize: {error}")))?;
    let hash = fnv1a64(bundle_json.as_bytes());
    let zone = &source.zones[0];
    let zone_terrain_cells = canonical.zones[0].terrain_cells.clone();
    let zone_city_traversal = zone
        .city_traversal
        .as_ref()
        .map(|input| {
            GroundedCity::parse(input, zone.half_extent)
                .map(Arc::new)
                .map_err(|error| {
                    ContentError::Validation(format!("zone {} city traversal: {error}", zone.id))
                })
        })
        .transpose()?;
    Ok(Content {
        mage_pilot: source.mage_pilot.clone(),
        vocation_id: source.vocations[0].id.clone(),
        hash,
        tick_hz: source.manifest.tick_hz,
        vocation: source.vocations[0]
            .stats
            .clone()
            .expect("validated vocations carry a stats block (E07)"),
        drop_tables: source
            .enemies
            .iter()
            .filter(|enemy| !enemy.drops.is_empty())
            .map(|enemy| {
                (
                    enemy.id.clone(),
                    enemy
                        .drops
                        .iter()
                        .map(|drop| EnemyDropTuning {
                            item: drop.item.clone(),
                            chance_pct: drop.chance_pct,
                            min: drop.min,
                            max: drop.max,
                        })
                        .collect(),
                )
            })
            .collect(),
        items: source
            .items
            .iter()
            .filter_map(|item| {
                let slot = item.equip_slot.clone()?;
                Some((
                    item.id.clone(),
                    ItemTuning {
                        equip_slot: slot,
                        atk: item.atk.unwrap_or(0),
                        def: item.def.unwrap_or(0),
                        hp: item.hp.unwrap_or(0),
                        equip_level_min: item.equip_level_min.unwrap_or(1),
                    },
                ))
            })
            .collect(),
        player_hp: source.vocations[0].hp,
        player_speed: source.vocations[0].speed,
        player_jump_v: source.manifest.player.jump_v,
        player_gravity: source.manifest.player.gravity,
        player_sprint_mult: source.manifest.player.sprint_mult,
        pet_follow_dist: source.manifest.player.pet_follow_dist,
        pet_speed_mult: source.manifest.player.pet_speed_mult,
        buffs: source
            .items
            .iter()
            .filter_map(|item| {
                let kind = match item.buff_kind.as_deref() {
                    Some("atk") => 0,
                    Some("speed") => 1,
                    _ => return None,
                };
                Some((
                    item.id.clone(),
                    BuffTuning {
                        kind,
                        mult: item.buff_mult.unwrap_or(1.0),
                        duration_ticks: u64::from(item.buff_duration_s.unwrap_or(0))
                            * u64::from(source.manifest.tick_hz),
                    },
                ))
            })
            .collect(),
        zone_id: zone.id,
        zone_half_extent: zone.half_extent,
        zone_colliders: zone_colliders(zone),
        zone_terrain_cells,
        zone_city_traversal,
        abilities: canonical
            .abilities
            .into_iter()
            .map(|(id, ability)| {
                (
                    id,
                    AbilityTuning {
                        id: ability.id,
                        cooldown_ms: ability.cooldown_ms,
                        range: ability.range,
                        damage: ability.damage,
                        targets: ability.targets,
                        arc_deg: ability.arc_deg,
                        windup_ms: ability.windup_ms,
                        active_ms: ability.active_ms,
                        recovery_ms: ability.recovery_ms,
                        duration_ms: ability.duration_ms,
                        speed_mult: ability.speed_mult,
                        reduction_pct: ability.reduction_pct,
                        perfect_ms: ability.perfect_ms,
                        max_hold_ms: ability.max_hold_ms,
                        heal: ability.heal,
                        carry: ability.carry,
                    },
                )
            })
            .collect(),
        enemies: canonical
            .enemies
            .into_iter()
            .map(|(id, enemy)| {
                (
                    id.clone(),
                    EnemyTuning {
                        id,
                        kind: enemy.kind,
                        hp: enemy.hp,
                        level: enemy.level,
                        rank: enemy.rank,
                        speed: enemy.speed,
                        aggro: enemy.aggro,
                        leash: enemy.leash,
                        respawn_s: enemy.respawn_s,
                        exp: enemy.exp,
                        splash_radius: enemy.splash_radius,
                        splash_damage: enemy.splash_damage,
                        splash_windup_ms: enemy.splash_windup_ms,
                        splash_active_ms: enemy.splash_active_ms,
                        splash_recovery_ms: enemy.splash_recovery_ms,
                        splash_cooldown_ms: enemy.splash_cooldown_ms,
                    },
                )
            })
            .collect(),
        enemy_kinds: source
            .enemies
            .iter()
            .map(|enemy| (enemy.kind, enemy.id.clone()))
            .collect(),
        spawns: zone
            .monster_spawns
            .iter()
            .map(|spawn| SpawnTuning {
                enemy: spawn.enemy.clone(),
                x: spawn.x,
                z: spawn.z,
                leash_polygon: spawn.leash_polygon.clone(),
            })
            .collect(),
        economy: Some(source.economy),
        tower: Some(source.tower),
        bundle_json,
    })
}

fn candidate_roots() -> Vec<PathBuf> {
    // Tests run with CWD = apps/server; the server runs from the repo root.
    ["content", "../content", "../../content"]
        .iter()
        .map(PathBuf::from)
        .collect()
}

fn find_dir(name: &str) -> Option<PathBuf> {
    candidate_roots()
        .iter()
        .map(|root| root.join(name))
        .find(|path| path.is_dir())
}

/// Load the built bundle: exactly one `content/build/<hash>/` directory must
/// exist, and its name must equal the hash of its `bundle.json`.
pub fn load_built() -> Result<Content, ContentError> {
    let build = find_dir("build").ok_or_else(|| {
        ContentError::Io(
            "content/build missing: run `cargo run --manifest-path apps/server/Cargo.toml --bin build_content`"
                .to_string(),
        )
    })?;
    let mut dirs = Vec::new();
    let entries = std::fs::read_dir(&build)
        .map_err(|error| ContentError::Io(format!("{}: {error}", build.display())))?;
    for entry in entries {
        let entry = entry.map_err(|error| ContentError::Io(error.to_string()))?;
        if entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false) {
            dirs.push(entry.file_name().to_string_lossy().to_string());
        }
    }
    if dirs.len() != 1 {
        return Err(ContentError::Validation(format!(
            "expected exactly one built bundle in {}, found {}",
            build.display(),
            dirs.len()
        )));
    }
    let bundle_path = build.join(&dirs[0]).join("bundle.json");
    let text = read_bounded_content_text(&bundle_path)?;
    // The built bundle is authoritative bytes: re-validate structure, then
    // confirm the directory hash.
    let actual = fnv1a64(text.as_bytes());
    let actual_hex = format!("{actual:016x}");
    if actual_hex != dirs[0] {
        return Err(ContentError::HashMismatch {
            expected: dirs[0].clone(),
            actual: actual_hex,
        });
    }
    let source_dir = find_dir("source").ok_or_else(|| {
        ContentError::Io("content/source missing next to content/build".to_string())
    })?;
    let content = build_from_source(&source_dir)?;
    if content.hash != actual {
        return Err(ContentError::HashMismatch {
            expected: actual_hex,
            actual: format!("{:016x}", content.hash),
        });
    }
    Ok(content)
}

/// Load + validate straight from source (unit tests and the build tool).
pub fn load_source_dir(dir: &Path) -> Result<Content, ContentError> {
    build_from_source(dir)
}

#[cfg(test)]
pub fn test_content() -> Content {
    let root = find_dir("source").expect("content/source discoverable from apps/server");
    build_from_source(&root).expect("test content validates")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn optional_city_traversal_is_validated_and_hash_covered() {
        let mut source = load_source(&test_source_root()).unwrap();
        source.zones[0].city_traversal = None;
        let absent = serde_json::to_string(&canonicalize(&source)).unwrap();
        assert!(source.zones[0].city_traversal.is_none());
        assert!(!absent.contains("city_traversal"));
        source.zones[0].city_traversal = Some(crate::grounded_city::tests::fixture());
        validate(&source).unwrap();
        let included = serde_json::to_string(&canonicalize(&source)).unwrap();
        assert_ne!(fnv1a64(absent.as_bytes()), fnv1a64(included.as_bytes()));
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&included).unwrap()["zones"][0]["city_traversal"]
                ["schema"],
            "xexoria.city-traversal/1"
        );
        source.zones[0].city_traversal.as_mut().unwrap().surfaces[0].kind = "roof".into();
        assert!(validate(&source).is_err());
    }

    #[test]
    fn bundle_builds_and_hashes_stably() {
        let first = test_content();
        let second = test_content();
        assert_eq!(first.hash, second.hash);
        assert_ne!(first.hash, 0);
        assert_eq!(first.bundle_json, second.bundle_json);
        // Golden pin: any content edit changes the wire-visible hash, so the
        // v4 golden welcome must be regenerated alongside.
        assert_eq!(first.hash_hex().len(), 16);
    }

    #[test]
    fn tuning_comes_from_data_not_code() {
        let content = test_content();
        let attack = content.ability("attack").expect("attack tuning");
        assert_eq!(
            (attack.cooldown_ms, attack.damage, attack.range),
            (400, Some(25), Some(3.0))
        );
        let arc = content.ability("arc_slash").expect("arc tuning");
        assert_eq!(
            (arc.cooldown_ms, arc.damage, arc.targets),
            (5000, Some(45), Some(3))
        );
        let dodge = content.ability("dodge").expect("dodge tuning");
        assert_eq!(dodge.cooldown_ms, 900);
        let puddlekin = content.enemy("puddlekin").expect("puddlekin tuning");
        assert_eq!(
            (puddlekin.kind, puddlekin.hp, puddlekin.respawn_s),
            (1, 90, 15)
        );
        assert_eq!(
            content.spawns.len(),
            13,
            "the two Sunmeadow cells add three authored encounters"
        );
        assert_eq!((content.player_hp, content.player_speed), (100, 4.5));
        assert_eq!((content.zone_id, content.zone_half_extent), (1, 308.0));
        assert_eq!(content.zone_colliders.len(), 24);
        assert_eq!(
            content
                .zone_city_traversal
                .as_ref()
                .unwrap()
                .stats
                .blocker_count,
            401
        );
        assert_eq!(content.zone_terrain_cells.len(), 2);
        assert_eq!(
            content.zone_terrain_cells[0].bounds_xz,
            [-64.0, 0.0, -128.0, -64.0]
        );
        assert_eq!(
            content.zone_terrain_cells[0].neighbors.east.as_deref(),
            Some("sunmeadow_c8_r6")
        );
        let zone: serde_json::Value = serde_json::from_str(&content.bundle_json).unwrap();
        assert_eq!(
            zone["zones"][0]["static_colliders"]
                .as_array()
                .unwrap()
                .len(),
            24
        );
        let colliders = zone["zones"][0]["static_colliders"].as_array().unwrap();
        assert!(!colliders.iter().any(|collider| matches!(
            collider["id"].as_str(),
            Some("town_gate_west_wing" | "town_gate_east_wing")
        )));
        let semantic = zone["zones"][0]["city_traversal"]["blockers"]
            .as_array()
            .unwrap();
        let gate: Vec<_> = semantic
            .iter()
            .filter(|blocker| {
                blocker["id"]
                    .as_str()
                    .is_some_and(|id| id.starts_with("gate ") || id.starts_with("town gate "))
            })
            .collect();
        assert_eq!(
            gate.len(),
            15,
            "mesh-derived gate blockers replace the retired broad boxes"
        );
        for id in [
            "gate east pier",
            "gate west pier",
            "gate curtain wall block",
            "gate curtain wall block.003",
        ] {
            assert!(
                gate.iter()
                    .any(|blocker| blocker["id"] == id && blocker["kind"] == "solid_structure"),
                "missing solid gate component {id}"
            );
        }
        assert_eq!(
            zone["zones"][0]["pois"]["city_gate"],
            serde_json::json!({ "x": 0.0, "z": 24.0 })
        );
        assert_eq!(
            zone["zones"][0]["world_routes"][0]["id"],
            "southbound_trail"
        );
        assert_eq!(
            zone["zones"][0]["static_colliders"]
                .as_array()
                .unwrap()
                .iter()
                .find(|collider| collider["id"] == "sunmeadow_windstone")
                .unwrap()["center"],
            serde_json::json!([-9.5, 1.3, -97.5])
        );
        assert_eq!(
            zone["zones"][0]["terrain_cells"][1]["neighbors"]["west"],
            "sunmeadow_c7_r6"
        );
    }

    #[test]
    fn validator_rejects_bad_bundles() {
        // Each case builds a full source tree in-memory through the public
        // loader by copying the real tree to a temp dir and breaking one file.
        type BreakFn = Box<dyn Fn(&mut serde_json::Value)>;
        let cases: Vec<(&str, BreakFn)> = vec![
            (
                "duplicate ability id",
                Box::new(|root| {
                    root["abilities"][1]["id"] = serde_json::json!("attack");
                }),
            ),
            (
                "dangling quest giver",
                Box::new(|root| {
                    root["quests"][0]["giver"] = serde_json::json!("nobody");
                }),
            ),
            (
                "dangling reward item",
                Box::new(|root| {
                    root["quests"][0]["reward"]["items"][0]["def"] = serde_json::json!("nope");
                }),
            ),
            (
                "quest cycle",
                Box::new(|root| {
                    root["quests"][0]["requires"] = serde_json::json!(["three_windmarks"]);
                }),
            ),
            (
                "huge coordinate",
                Box::new(|root| {
                    root["zones"][0]["pois"][0]["x"] = serde_json::json!(1e30);
                }),
            ),
            (
                "more than 64 monster spawns",
                Box::new(|root| {
                    let spawn = root["zones"][0]["monster_spawns"][0].clone();
                    root["zones"][0]["monster_spawns"] = serde_json::json!(vec![spawn; 65]);
                }),
            ),
            (
                "spawn outside zone",
                Box::new(|root| {
                    root["zones"][0]["monster_spawns"][0]["x"] = serde_json::json!(999.0);
                }),
            ),
            (
                "duplicate zone collider id",
                Box::new(|root| {
                    root["zones"][0]["static_colliders"] = serde_json::json!([
                        {"id":"validator_wall","center":[-30.0,1.0,24.0],"size":[1.0,2.0,1.0]},
                        {"id":"validator_wall","center":[30.0,1.0,24.0],"size":[1.0,2.0,1.0]}
                    ]);
                }),
            ),
            (
                "zone collider outside zone",
                Box::new(|root| {
                    root["zones"][0]["static_colliders"] = serde_json::json!([
                        {"id":"validator_wall","center":[0.0,1.0,0.0],"size":[700.0,2.0,1.0]}
                    ]);
                }),
            ),
            (
                "zone collider with zero height",
                Box::new(|root| {
                    root["zones"][0]["static_colliders"] = serde_json::json!([
                        {"id":"validator_wall","center":[0.0,1.0,0.0],"size":[1.0,0.0,1.0]}
                    ]);
                }),
            ),
            (
                "city traversal outside reduced zone extent",
                Box::new(|root| {
                    root["zones"][0]["half_extent"] = serde_json::json!(128.0);
                }),
            ),
            (
                "terrain cells with a non reciprocal seam",
                Box::new(|root| {
                    root["zones"][0]["terrain_cells"][1]["neighbors"]["west"] =
                        serde_json::json!(null);
                }),
            ),
            (
                "terrain cell with the wrong size",
                Box::new(|root| {
                    root["zones"][0]["terrain_cells"][0]["bounds_xz"][1] = serde_json::json!(2.0);
                }),
            ),
            (
                "world prop outside its terrain cell",
                Box::new(|root| {
                    root["zones"][0]["world_props"][0]["x"] = serde_json::json!(-63.5);
                }),
            ),
            (
                "missing th key",
                Box::new(|root| {
                    root["dialogue_th"]
                        .as_object_mut()
                        .unwrap()
                        .remove("quest_accept");
                }),
            ),
            (
                "bad cooldown",
                Box::new(|root| {
                    root["abilities"][0]["cooldown_ms"] = serde_json::json!(50);
                }),
            ),
            (
                "leash below aggro",
                Box::new(|root| {
                    root["enemies"][0]["leash"] = serde_json::json!(2.0);
                }),
            ),
            (
                "economy unknown currency",
                Box::new(|root| {
                    root["economy"]["store"][0]["currency"] = serde_json::json!("gems");
                }),
            ),
            (
                "economy bad weight sum",
                Box::new(|root| {
                    root["economy"]["boxes"]["meadow_box"]["table"][0]["weight"] =
                        serde_json::json!(31);
                }),
            ),
            (
                "economy unknown store item",
                Box::new(|root| {
                    root["economy"]["store"][0]["item"] = serde_json::json!("nope");
                }),
            ),
            (
                "economy unknown box cosmetic",
                Box::new(|root| {
                    root["economy"]["boxes"]["meadow_box"]["table"][4]["cosmetic"] =
                        serde_json::json!("skin_nope");
                }),
            ),
            (
                "tower unknown enemy",
                Box::new(|root| {
                    root["tower"]["enemy"] = serde_json::json!("dragon_lord");
                }),
            ),
            (
                "tower zero count base",
                Box::new(|root| {
                    root["tower"]["per_floor"]["count_base"] = serde_json::json!(0);
                }),
            ),
            (
                "tower box item not a box",
                Box::new(|root| {
                    root["tower"]["box_item"] = serde_json::json!("dew_bead");
                }),
            ),
        ];
        for (name, break_it) in cases {
            let dir = copy_source_to_temp(name);
            // Load each table generically: rebuild the SourceBundle from the
            // broken tree through load_source + validate.
            let mut tree = read_tree(&dir);
            break_it(&mut tree);
            write_tree(&dir, &tree);
            let result = build_from_source(&dir.join("source"));
            assert!(result.is_err(), "validator accepted {name}: {result:?}");
            std::fs::remove_dir_all(&dir).ok();
        }
    }

    #[test]
    fn monster_budget_accepts_64_and_rejects_65() {
        let dir=copy_source_to_temp("monster-budget-go");
        let mut tree=read_tree(&dir);
        let spawn=tree["zones"][0]["monster_spawns"][0].clone();
        tree["zones"][0]["monster_spawns"]=serde_json::json!(vec![spawn.clone();64]);
        write_tree(&dir,&tree);
        assert!(build_from_source(&dir.join("source")).is_ok());
        tree["zones"][0]["monster_spawns"]=serde_json::json!(vec![spawn;65]);
        write_tree(&dir,&tree);
        assert!(build_from_source(&dir.join("source")).is_err());
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn economy_loads_from_source() {
        let content = test_content();
        let economy = content.economy.as_ref().expect("economy table present");
        assert_eq!(economy.starting.gold, 250);
        assert_eq!(economy.starting.coin, 10);
        assert!(economy.kill_gold > 0);
        assert!(economy.quest_claim_gold > 0);
        assert!(!economy.store.is_empty());
        for (id, def) in &economy.boxes {
            let total: u32 = def.table.iter().map(|roll| roll.weight).sum();
            assert_eq!(total, 100, "box {id} weights must sum to 100");
        }
        // The box-only cosmetic exists but is not sold in the store.
        assert!(economy.skins.contains_key("skin_rose"));
        assert!(
            economy
                .store
                .iter()
                .all(|entry| entry.cosmetic != Some("skin_rose".to_string()))
        );
    }

    #[test]
    fn tower_loads_and_curves_scale() {
        let content = test_content();
        let tower = content.tower.as_ref().expect("tower table present");
        assert_eq!(tower.max_floor, 100);
        assert_eq!(tower.count(1), 3);
        assert_eq!(tower.count(100), 11);
        assert!(
            (tower.hp_mult(100) - 12.88).abs() < 0.01,
            "hp at floor 100: {}",
            tower.hp_mult(100)
        );
        assert_eq!(tower.reward_gold(1), 5);
        assert!(tower.reward_gold(100) > 100);
        assert_eq!(tower.box_item, "meadow_box");
    }

    #[test]
    fn tower_file_is_required() {
        let dir = copy_source_to_temp("missing-tower");
        std::fs::remove_file(dir.join("source").join("tower.json")).unwrap();
        let result = build_from_source(&dir.join("source"));
        assert!(result.is_err(), "missing tower.json must refuse to build");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn economy_file_is_required() {
        let dir = copy_source_to_temp("missing-economy");
        std::fs::remove_file(dir.join("source").join("economy.json")).unwrap();
        let result = build_from_source(&dir.join("source"));
        assert!(result.is_err(), "missing economy.json must refuse to build");
        std::fs::remove_dir_all(&dir).ok();
    }

    // -- test-only filesystem helpers ---------------------------------------

    fn test_source_root() -> PathBuf {
        super::find_dir("source").expect("content/source discoverable")
    }

    fn read_tree(temp: &Path) -> serde_json::Value {
        let mut map = serde_json::Map::new();
        for (file, inner) in [
            ("manifest.json", None),
            ("zones.json", Some("zones")),
            ("abilities.json", Some("abilities")),
            ("enemies.json", Some("enemies")),
            ("npcs.json", Some("npcs")),
            ("quests.json", Some("quests")),
            ("items.json", Some("items")),
            ("vocations.json", Some("vocations")),
            ("economy.json", None),
            ("tower.json", None),
        ] {
            let text = std::fs::read_to_string(temp.join("source").join(file)).unwrap();
            let parsed: serde_json::Value = serde_json::from_str(&text).unwrap();
            let key = file.trim_end_matches(".json");
            map.insert(
                key.to_string(),
                match inner {
                    Some(table) => parsed[table].clone(),
                    None => parsed,
                },
            );
        }
        for lang in ["th", "en"] {
            let text =
                std::fs::read_to_string(temp.join("source").join(format!("dialogue/{lang}.json")))
                    .unwrap();
            map.insert(
                format!("dialogue_{lang}"),
                serde_json::from_str(&text).unwrap(),
            );
        }
        serde_json::Value::Object(map)
    }

    fn write_tree(temp: &Path, tree: &serde_json::Value) {
        let map = tree.as_object().unwrap();
        for file in [
            "manifest.json",
            "zones.json",
            "abilities.json",
            "enemies.json",
            "npcs.json",
            "quests.json",
            "items.json",
            "vocations.json",
            "economy.json",
            "tower.json",
        ] {
            let key = file.trim_end_matches(".json");
            // Re-wrap table files in their top-level object shape.
            let wrapped = match key {
                "manifest" => map[key].clone(),
                "zones" => serde_json::json!({"zones": map[key]}),
                "abilities" => serde_json::json!({"abilities": map[key]}),
                "enemies" => serde_json::json!({"enemies": map[key]}),
                "npcs" => serde_json::json!({"npcs": map[key]}),
                "quests" => serde_json::json!({"quests": map[key]}),
                "items" => serde_json::json!({"items": map[key]}),
                "vocations" => serde_json::json!({"vocations": map[key]}),
                "economy" => map[key].clone(),
                "tower" => map[key].clone(),
                _ => unreachable!(),
            };
            std::fs::write(
                temp.join("source").join(file),
                serde_json::to_string_pretty(&wrapped).unwrap(),
            )
            .unwrap();
        }
        for lang in ["th", "en"] {
            std::fs::write(
                temp.join("source").join(format!("dialogue/{lang}.json")),
                serde_json::to_string_pretty(&map[&format!("dialogue_{lang}")]).unwrap(),
            )
            .unwrap();
        }
    }

    fn copy_dir(source: &Path, dest: &Path) {
        std::fs::create_dir_all(dest).unwrap();
        for entry in std::fs::read_dir(source).unwrap() {
            let entry = entry.unwrap();
            let target = dest.join(entry.file_name());
            if entry.file_type().unwrap().is_dir() {
                copy_dir(&entry.path(), &target);
            } else {
                std::fs::copy(entry.path(), target).unwrap();
            }
        }
    }

    fn copy_source_to_temp(name: &str) -> PathBuf {
        let temp = std::env::temp_dir().join(format!(
            "aetherfield-content-{name_slug}-{pid}",
            name_slug = name
                .chars()
                .map(|character| if character.is_ascii_alphanumeric() {
                    character
                } else {
                    '_'
                })
                .collect::<String>(),
            pid = std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&temp);
        copy_dir(&test_source_root(), &temp.join("source"));
        temp
    }
    #[test]
    fn leash_polygon_is_optional_hash_covered_and_validated() {
        let mut source=load_source(&test_source_root()).unwrap();let before=serde_json::to_vec(&canonicalize(&source)).unwrap();
        let spawn=&mut source.zones[0].monster_spawns[0];let (x,z)=(spawn.x,spawn.z);
        spawn.leash_polygon=vec![[x-2.0,z-2.0],[x+2.0,z-2.0],[x+2.0,z+2.0],[x-2.0,z+2.0]];
        validate(&source).unwrap();assert_ne!(before,serde_json::to_vec(&canonicalize(&source)).unwrap());
        source.zones[0].monster_spawns[0].leash_polygon=vec![[0.0,0.0],[1.0,0.0],[1.0,1.0]];assert!(validate(&source).is_err());
        source.zones[0].monster_spawns[0].leash_polygon.clear();assert_eq!(before,serde_json::to_vec(&canonicalize(&source)).unwrap());
    }

    #[test]
    fn map_owner_four_home_repairs_keep_ids_clear_support_and_spawn_refuge() {
        let content=test_content();assert_eq!(content.spawns.len(),13);
        let hunt:serde_json::Value=serde_json::from_slice(&std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../planning/levels/sunmeadow-v2-monsters.json")).unwrap()).unwrap();
        let polygon=hunt["zones"].as_array().unwrap().iter().find(|zone|zone["id"]=="hunt_meadow_east").unwrap()["spawn_polygon_xz"].as_array().unwrap().iter().map(|p|[p[0].as_f64().unwrap() as f32,p[1].as_f64().unwrap() as f32]).collect::<Vec<_>>();assert!(crate::grounded_city::overlaps_polygon(15.0,-1.5,0.0,&polygon));
        let city=content.zone_city_traversal.as_ref().unwrap();let fixture=crate::coordinate_fixture::CoordinateFixture::embedded();
        let mut world=crate::world::World::new(&content,crate::character::CharacterStore::shared());let snapshot=world.advance();assert_eq!(snapshot.monsters.len(),13);
        let blockers=content.zone_colliders.iter().map(|c|crate::coordinate_fixture::StaticCollider::from_center_dimensions(c.center,c.size)).collect::<Vec<_>>();
        for (index,enemy,x,z) in [(0,"puddlekin",15.0,-1.5),(3,"mossling",-13.0,3.0),(6,"thistle_boar",13.0,6.0),(8,"glade_wisp",-15.0,-2.0)] {
            let spawn=&content.spawns[index];assert_eq!(spawn.enemy,enemy);assert_eq!((spawn.x,spawn.z),(x,z));assert_eq!(snapshot.monsters[index].id,101+index as u32);assert_eq!(snapshot.monsters[index].kind,content.enemy(enemy).unwrap().kind);assert_eq!((snapshot.monsters[index].x,snapshot.monsters[index].z),(x,z));
            assert_eq!(city.height_at(x,z),Some(0.0));assert!(city.position_is_clear(x,0.0,z,fixture.player_radius(),fixture.player_height(),&blockers));
            assert!(crate::coordinate_fixture::capsule_position_is_clear(x,z,fixture.player_radius(),fixture.player_height(),&blockers));
            for slot in 0..48 {let sx=(slot%4) as f32*2.0-3.0;let sz=-3.0-(slot/4) as f32*1.5;let distance=(x-sx).hypot(z-sz);assert!(distance>=11.0);assert!(distance>content.enemy(enemy).unwrap().aggro);}
        }
    }

}
