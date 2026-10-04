//! Strict import of the A31 *design draft*, deliberately separate from live content.
//!
//! This module has no casts, resource mutations, status resolver, wire IDs or
//! conversion to runtime abilities. Passing validation means the proposal is
//! internally coherent; D1-D8 and prose-only execution fields still block use.

use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const MAX_DRAFT_BYTES: usize = 512 * 1024;
const MAX_NODES: usize = 20_000;
const MAX_DEPTH: usize = 16;
const MAX_COLLECTION: usize = 64;
const MAX_TEXT_BYTES: usize = 4096;
const MAX_MS: u32 = 600_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CatalogError {
    pub path: String,
    pub reason: String,
}
impl fmt::Display for CatalogError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.path, self.reason)
    }
}
impl std::error::Error for CatalogError {}
fn invalid(path: &str, reason: &str) -> CatalogError {
    CatalogError {
        path: path.chars().take(180).collect(),
        reason: reason.chars().take(240).collect(),
    }
}
fn require(ok: bool, path: &str, reason: &str) -> Result<(), CatalogError> {
    if ok {
        Ok(())
    } else {
        Err(invalid(path, reason))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActivationState {
    DraftOnly,
}

/// Read-only proposal. No API promotes this value into the combat catalog.
#[derive(Debug)]
pub struct DraftCatalog {
    draft: HeroSkillDraft,
}
impl DraftCatalog {
    pub fn draft(&self) -> &HeroSkillDraft {
        &self.draft
    }
    pub const fn activation(&self) -> ActivationState {
        ActivationState::DraftOnly
    }
    pub const fn activation_gaps(&self) -> &'static [&'static str] {
        &[
            "Owner decisions D1-D8 remain open; no proposed names or balance are activated.",
            "Skill power is prose; a typed damage/healing formula is required.",
            "Targeting mode and extras do not specify executable shape/selection policies.",
            "Status effects and derived-state modifiers are prose, not typed operations.",
            "Reaction effects, elite/boss scaling and per-reaction exceptions are prose.",
            "Zone/tick schedules and charge-dependent release are not a complete numeric event model.",
            "Weapon sockets, FX markers, clips and kit filenames require asset/socket validation.",
            "A proposed SP pool is data only; no live resource or reaction handler is installed.",
        ]
    }
}

macro_rules! strict_struct {
    ($name:ident { $($field:ident : $ty:ty),* $(,)? }) => {
        #[derive(Debug, Deserialize)]
        #[serde(deny_unknown_fields)]
        pub struct $name { $(pub $field: $ty),* }
    };
}
strict_struct!(Names {
    en: String,
    th: String
});
strict_struct!(Units {
    time: String,
    distance: String,
    angle: String,
    fps: u32,
    release_frame: String,
    power: String,
    layer_t: String
});
strict_struct!(Resource {
    id: String,
    pool: u32,
    regen_in_combat_per_s: f64,
    regen_out_of_combat_per_s: f64,
    note: String
});
strict_struct!(TelegraphMeaning {
    meaning: String,
    shape: String,
    colours: String
});
strict_struct!(TierBudget {
    id: String,
    draws: u32,
    particles: String,
    cpu_ms: f64,
    rule: String
});
strict_struct!(StatusDefinition { id: String, hero: String, name: Names, duration_ms: u32, max_stacks: u32, effect: String, glyph: String, marker: String, hex: String, reactions: Vec<String> });
strict_struct!(DerivedState {
    id: String,
    en: String,
    th: String,
    effect: String
});
strict_struct!(ReactionDefinition { id: String, code: String, name: Names, pop_word_th: String, pair: [String; 2], heroes: [String; 2], unlock_step: u32, effect: String, scaling: String, vfx: String, kit: Vec<String>, palette: Palette, peak_coverage_pct: f64, sfx: String });
strict_struct!(ReactionRulesText {
    trigger: String,
    cross_hero_by_construction: String,
    consumption: String,
    lockout: String,
    ancestry: String,
    ordering: String,
    credit: String,
    scaling: String,
    pvp: String,
    feedback: String,
    durations: String
});
strict_struct!(ReactionRulesNumeric { target_lockout_ms: u32, max_statuses_per_target: u32, ultimate_refund_ms: u32, ultimate_refund_cooldown_ms: u32, pairing: String, consume_both: bool, pvp_enabled: bool, can_trigger_reaction_sources: Vec<String> });
strict_struct!(Palette {
    core: String, body: String, edge: String, accent: String,
    dark: Option<String>, abyss: Option<String>, rim: Option<String>,
    scorch: Option<String>, steam: Option<String>, brass: Option<String>,
    moon: Option<String>, frost: Option<String>, leaf: Option<String>, deep: Option<String>
});

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeroDefinition {
    pub id: String,
    pub num: String,
    pub name: Names,
    pub role: String,
    pub role_th: String,
    pub party_job: String,
    pub element: String,
    pub palette: Palette,
    pub shape_language: String,
    pub statuses: Vec<String>,
    pub reactions: Vec<String>,
    pub weapon: String,
    pub stance: String,
    pub class_set: String,
    pub sockets: String,
    pub trail: String,
    pub skills: Vec<String>,
    #[serde(rename = "class")]
    pub class_name: String,
}
strict_struct!(Targeting { mode: String, range_m: f64, radius_m: Option<f64> });
strict_struct!(Telegraph { kind: String, width_m: Option<f64>, length_m: Option<f64>, radius_m: Option<f64>, angle_deg: Option<f64>, note: Option<String>, then: Option<Box<TelegraphContinuation>> });
strict_struct!(TelegraphContinuation { kind: String, radius_m: f64, at: String, shown_ms: Option<u32> });
strict_struct!(Timing { windup_ms: u32, active_ms: u32, recovery_ms: u32, release_ms: u32, release_frame: u32, fps: u32, clip: String, clip_ms: u32, clip_frames: u32, events: Vec<ClipEvent>, zone: Option<String>, release_frame_exact: Option<f64> });
strict_struct!(ClipEvent {
    id: String,
    t_ms: u32
});
strict_struct!(Cost { sp: u32 });
strict_struct!(AppliedStatus {
    id: String,
    duration_ms: u32,
    stacks: u32
});
strict_struct!(LayerTime {
    from: String,
    start_ms: u32,
    to: String,
    end_ms: u32
});
strict_struct!(VfxLayer { role: String, t: LayerTime, kit: Vec<String>, min_tier: String, desc: String, medium_scale: Option<f64> });
strict_struct!(Vfx { preset: String, reuses: Option<String>, budget_class: String, peak_coverage_pct: f64, layers: Vec<VfxLayer>, readability: Option<String> });
strict_struct!(Sfx { cue: String, phases: Vec<String> });
strict_struct!(Animation {
    clip: String,
    source: String
});
strict_struct!(Keyframe {
    t_ms: u32,
    beat: String
});

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SkillDefinition {
    pub id: String,
    pub hero: String,
    pub slot: u8,
    #[serde(rename = "type")]
    pub kind: String,
    pub name: Names,
    pub summary: String,
    pub targeting: Targeting,
    pub telegraph: Telegraph,
    pub timing: Timing,
    pub cooldown_ms: u32,
    pub cost: Cost,
    pub power: String,
    pub heavy: bool,
    pub damage_type: String,
    pub element: String,
    pub effects: Vec<String>,
    // Only the enumerated draft extension fields are accepted (see validate_extra).
    // Strings are kept as descriptions, never parsed into combat instructions.
    pub extra: BTreeMap<String, Value>,
    pub status: Vec<AppliedStatus>,
    pub combos: Vec<String>,
    pub palette: Palette,
    pub vfx: Vfx,
    pub sfx: Sfx,
    pub anim: Animation,
    pub keyframes: Vec<Keyframe>,
    pub secondary_type: Option<String>,
    pub notes: Option<String>,
    pub legacy_ability: Option<String>,
    pub consumes_status: Option<String>,
}
strict_struct!(KitDefinition { id: String, file: String, kind: String, kit_version: u32, spec: String, used_by_skills: Vec<String>, used_by_reactions: Vec<String>, first_needed_at_step: Option<u32> });
strict_struct!(WeaponDefinition {
    key: String,
    hero: String,
    weapon: String,
    route: String,
    source: String,
    credits: u32,
    length: String,
    tris: String,
    tex: String,
    emissive: String,
    markers: String,
    socket: String,
    trail: String,
    tripo: String
});
strict_struct!(HeroSkillDraft {
    schema: String, version: String, status: String, source_doc: String,
    consumers: Vec<String>, units: Units, resource: Resource,
    telegraph_kinds: BTreeMap<String, TelegraphMeaning>, tiers: Vec<TierBudget>,
    budget_classes: BTreeMap<String, String>, statuses: Vec<StatusDefinition>,
    derived_states: Vec<DerivedState>, reactions: Vec<ReactionDefinition>,
    reaction_rules: ReactionRulesText, reaction_rules_numeric: ReactionRulesNumeric,
    heroes: Vec<HeroDefinition>, production_order: Vec<String>,
    skills: Vec<SkillDefinition>, kit: Vec<KitDefinition>, weapons: Vec<WeaponDefinition>
});

/// Input-size bound is checked before deserialization. Duplicate JSON keys fail,
/// rather than letting the last occurrence shadow an earlier balance value.
pub fn load_design_draft(bytes: &[u8]) -> Result<DraftCatalog, CatalogError> {
    require(
        !bytes.is_empty() && bytes.len() <= MAX_DRAFT_BYTES,
        "$",
        "draft byte limit exceeded or empty input",
    )?;
    let raw: UniqueValue =
        serde_json::from_slice(bytes).map_err(|e| invalid("$", &format!("invalid JSON: {e}")))?;
    let mut nodes = 0;
    validate_tree(&raw.0, 0, &mut nodes)?;
    let draft: HeroSkillDraft = serde_json::from_value(raw.0)
        .map_err(|e| invalid("$", &format!("incomplete or unknown draft descriptor: {e}")))?;
    validate_draft(&draft)?;
    Ok(DraftCatalog { draft })
}

fn text(value: &str, path: &str) -> Result<(), CatalogError> {
    require(
        !value.trim().is_empty()
            && value.len() <= MAX_TEXT_BYTES
            && !value
                .chars()
                .any(|c| c.is_control() && c != '\n' && c != '\t'),
        path,
        "empty, oversized or invalid text",
    )
}
fn id(value: &str, path: &str) -> Result<(), CatalogError> {
    require(
        !value.is_empty()
            && value.len() <= 80
            && value
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'.' || b == b'-'),
        path,
        "invalid identifier",
    )
}
fn names(value: &Names, path: &str) -> Result<(), CatalogError> {
    text(&value.en, path)?;
    text(&value.th, path)
}
fn bounded(value: f64, min: f64, max: f64, path: &str) -> Result<(), CatalogError> {
    require(
        value.is_finite() && value >= min && value <= max,
        path,
        "number outside finite import bounds",
    )
}
fn duration(value: u32, allow_zero: bool, path: &str) -> Result<(), CatalogError> {
    require(
        value <= MAX_MS && (allow_zero || value > 0),
        path,
        "duration outside import bounds",
    )
}
fn colour(value: &str, path: &str) -> Result<(), CatalogError> {
    require(
        value.len() == 7
            && value.starts_with('#')
            && value.as_bytes()[1..].iter().all(|b| b.is_ascii_hexdigit()),
        path,
        "expected #RRGGBB palette colour",
    )
}
fn palette(value: &Palette, path: &str) -> Result<(), CatalogError> {
    for c in [&value.core, &value.body, &value.edge, &value.accent] {
        colour(c, path)?;
    }
    for c in [
        &value.dark,
        &value.abyss,
        &value.rim,
        &value.scorch,
        &value.steam,
        &value.brass,
        &value.moon,
        &value.frost,
        &value.leaf,
        &value.deep,
    ]
    .into_iter()
    .flatten()
    {
        colour(c, path)?;
    }
    Ok(())
}
fn unique<'a>(
    values: impl Iterator<Item = &'a str>,
    path: &str,
) -> Result<BTreeSet<&'a str>, CatalogError> {
    let mut out = BTreeSet::new();
    for value in values {
        id(value, path)?;
        require(out.insert(value), path, "duplicate identifier/reference")?;
    }
    Ok(out)
}
fn refs(values: &[String], available: &BTreeSet<&str>, path: &str) -> Result<(), CatalogError> {
    let items = unique(values.iter().map(String::as_str), path)?;
    require(
        items.iter().all(|v| available.contains(v)),
        path,
        "unresolved reference",
    )
}
fn expected_set(
    actual: &BTreeSet<&str>,
    expected: &[&str],
    path: &str,
) -> Result<(), CatalogError> {
    require(
        actual
            .iter()
            .copied()
            .eq(expected.iter().copied().collect::<BTreeSet<_>>()),
        path,
        "missing or unknown catalog identifier",
    )
}

fn validate_draft(d: &HeroSkillDraft) -> Result<(), CatalogError> {
    require(
        d.schema == "xexoria.hero-skills/1",
        "schema",
        "unsupported draft schema",
    )?;
    text(&d.version, "version")?;
    require(
        d.status.starts_with("DESIGN DRAFT"),
        "status",
        "catalog must remain explicitly DESIGN DRAFT",
    )?;
    text(&d.source_doc, "source_doc")?;
    require(
        d.units.time == "ms"
            && d.units.distance == "m"
            && d.units.angle == "deg"
            && d.units.fps == 30,
        "units",
        "expected metres, milliseconds, degrees and 30 fps",
    )?;
    require(
        d.resource.id == "sp" && d.resource.pool > 0 && d.resource.pool <= 10_000,
        "resource",
        "unsupported resource or pool bounds",
    )?;
    bounded(
        d.resource.regen_in_combat_per_s,
        0.0,
        100.0,
        "resource.regen_in_combat_per_s",
    )?;
    bounded(
        d.resource.regen_out_of_combat_per_s,
        0.0,
        100.0,
        "resource.regen_out_of_combat_per_s",
    )?;

    require(
        d.heroes.len() == 6
            && d.skills.len() == 42
            && d.statuses.len() == 12
            && d.reactions.len() == 8
            && d.weapons.len() == 6,
        "$",
        "expected six heroes, 42 skills, 12 statuses, eight reactions and six weapons",
    )?;
    let heroes = unique(d.heroes.iter().map(|h| h.id.as_str()), "heroes")?;
    expected_set(
        &heroes,
        &["h01", "h02", "h03", "h04", "h05", "h06"],
        "heroes",
    )?;
    let skills = unique(d.skills.iter().map(|s| s.id.as_str()), "skills")?;
    let statuses = unique(d.statuses.iter().map(|s| s.id.as_str()), "statuses")?;
    let reactions = unique(d.reactions.iter().map(|r| r.id.as_str()), "reactions")?;
    let reaction_codes = unique(
        d.reactions.iter().map(|r| r.code.as_str()),
        "reactions.code",
    )?;
    expected_set(
        &reaction_codes,
        &["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"],
        "reactions.code",
    )?;
    let kits = unique(d.kit.iter().map(|k| k.id.as_str()), "kit")?;
    require(
        !kits.is_empty() && kits.len() <= MAX_COLLECTION,
        "kit",
        "empty or oversized kit",
    )?;
    let weapons = unique(d.weapons.iter().map(|w| w.key.as_str()), "weapons")?;
    let telegraphs = unique(
        d.telegraph_kinds.keys().map(String::as_str),
        "telegraph_kinds",
    )?;
    expected_set(
        &telegraphs,
        &[
            "AREA_CIRCLE",
            "AREA_FAN",
            "AREA_LANE",
            "HEAVY_CIRCLE",
            "HEAVY_LANE",
            "SAFE_CIRCLE",
            "SAFE_CIRCLE_ULT",
            "SAFE_BRACKET",
            "TARGET_BRACKET",
            "CAST_RING",
            "NONE_BASIC",
        ],
        "telegraph_kinds",
    )?;
    let tiers = unique(d.tiers.iter().map(|t| t.id.as_str()), "tiers")?;
    expected_set(&tiers, &["low", "medium", "high", "epic"], "tiers")?;
    let budgets = unique(
        d.budget_classes.keys().map(String::as_str),
        "budget_classes",
    )?;
    expected_set(&budgets, &["basic", "heroic", "ultimate"], "budget_classes")?;
    for tier in &d.tiers {
        require(
            tier.draws > 0 && tier.draws <= 32,
            "tiers.draws",
            "draw budget outside bounds",
        )?;
        bounded(tier.cpu_ms, 0.1, 10.0, "tiers.cpu_ms")?;
        text(&tier.particles, "tiers.particles")?;
    }
    refs(&d.production_order, &heroes, "production_order")?;
    require(
        d.production_order.len() == 6,
        "production_order",
        "must list every hero once",
    )?;

    let rules = &d.reaction_rules_numeric;
    require(
        rules.pairing == "fifo_oldest_first"
            && rules.consume_both
            && !rules.pvp_enabled
            && rules.target_lockout_ms == 1500
            && rules.can_trigger_reaction_sources == ["skill_hit"],
        "reaction_rules_numeric",
        "draft reaction policy must be FIFO, consume both, 1500 ms lockout, skill-hit only and PvP off",
    )?;
    require(
        rules.max_statuses_per_target == 4,
        "reaction_rules_numeric.max_statuses_per_target",
        "draft target status cap must be four",
    )?;
    duration(
        rules.ultimate_refund_ms,
        true,
        "reaction_rules_numeric.ultimate_refund_ms",
    )?;
    duration(
        rules.ultimate_refund_cooldown_ms,
        false,
        "reaction_rules_numeric.ultimate_refund_cooldown_ms",
    )?;

    let states = unique(
        d.derived_states.iter().map(|s| s.id.as_str()),
        "derived_states",
    )?;
    require(
        states.len() == 9,
        "derived_states",
        "expected nine described derived states",
    )?;
    for state in &d.derived_states {
        text(&state.en, "derived_states.en")?;
        text(&state.th, "derived_states.th")?;
        text(&state.effect, "derived_states.effect")?;
    }
    for s in &d.statuses {
        require(
            heroes.contains(s.hero.as_str()),
            &s.id,
            "status hero not found",
        )?;
        names(&s.name, &s.id)?;
        duration(s.duration_ms, false, &s.id)?;
        require(
            s.max_stacks > 0 && s.max_stacks <= 8,
            &s.id,
            "stack count outside bounds",
        )?;
        text(&s.effect, &s.id)?;
        colour(&s.hex, &s.id)?;
        refs(&s.reactions, &reactions, &s.id)?;
    }
    let mut pairs = BTreeSet::new();
    for r in &d.reactions {
        names(&r.name, &r.id)?;
        palette(&r.palette, &r.id)?;
        require(
            r.unlock_step > 0 && r.unlock_step <= 6,
            &r.id,
            "unlock step outside bounds",
        )?;
        bounded(r.peak_coverage_pct, 0.1, 100.0, &r.id)?;
        refs(&r.kit, &kits, &r.id)?;
        let owners: Vec<_> = r
            .pair
            .iter()
            .map(|p| d.statuses.iter().find(|s| s.id == *p))
            .collect();
        require(
            owners.iter().all(|o| o.is_some()) && r.pair[0] != r.pair[1],
            &r.id,
            "reaction pair must reference two distinct statuses",
        )?;
        let a = owners[0].unwrap();
        let b = owners[1].unwrap();
        require(
            a.hero != b.hero && r.heroes[0] == a.hero && r.heroes[1] == b.hero,
            &r.id,
            "reaction must pair two different hero owners in matching order",
        )?;
        require(
            a.reactions.contains(&r.id) && b.reactions.contains(&r.id),
            &r.id,
            "status/reaction references disagree",
        )?;
        let mut pair = r.pair.clone();
        pair.sort();
        require(
            pairs.insert(pair),
            &r.id,
            "duplicate unordered reaction pair",
        )?;
    }
    for s in &d.statuses {
        require(
            s.reactions.iter().all(|r| {
                d.reactions
                    .iter()
                    .any(|v| v.id == *r && v.pair.contains(&s.id))
            }),
            &s.id,
            "status points to unrelated reaction",
        )?;
    }
    for h in &d.heroes {
        names(&h.name, &h.id)?;
        palette(&h.palette, &h.id)?;
        require(
            h.num == h.id[1..] && weapons.contains(h.weapon.as_str()),
            &h.id,
            "hero number or weapon not found",
        )?;
        refs(&h.skills, &skills, &h.id)?;
        refs(&h.statuses, &statuses, &h.id)?;
        refs(&h.reactions, &reactions, &h.id)?;
        require(
            h.skills.len() == 7 && h.statuses.len() == 2,
            &h.id,
            "hero needs basic plus six slots and two statuses",
        )?;
        require(
            h.skills
                .iter()
                .all(|v| d.skills.iter().any(|s| s.id == *v && s.hero == h.id)),
            &h.id,
            "hero skill ownership mismatch",
        )?;
        require(
            d.statuses.iter().filter(|s| s.hero == h.id).count() == 2
                && h.statuses
                    .iter()
                    .all(|v| d.statuses.iter().any(|s| s.id == *v && s.hero == h.id)),
            &h.id,
            "hero status ownership mismatch",
        )?;
        require(
            h.reactions.iter().all(|v| {
                d.reactions
                    .iter()
                    .any(|r| r.id == *v && r.heroes.contains(&h.id))
            }),
            &h.id,
            "hero reaction ownership mismatch",
        )?;
        let slots: BTreeSet<_> = d
            .skills
            .iter()
            .filter(|s| s.hero == h.id)
            .map(|s| s.slot)
            .collect();
        require(
            slots == (0..=6).collect() && d.skills.iter().filter(|s| s.hero == h.id).count() == 7,
            &h.id,
            "duplicate or missing skill slot",
        )?;
    }
    let mut presets = BTreeSet::new();
    for s in &d.skills {
        validate_skill(
            s,
            d,
            &heroes,
            &statuses,
            &reactions,
            &kits,
            &telegraphs,
            &tiers,
            &budgets,
        )?;
        require(presets.insert(&s.vfx.preset), &s.id, "duplicate VFX preset")?;
    }
    let mut kit_reactions = reactions.clone();
    kit_reactions.extend(reaction_codes);
    for k in &d.kit {
        text(&k.file, &k.id)?;
        text(&k.spec, &k.id)?;
        require(
            !k.file.contains(['/', '\\', ':']) && !k.file.contains(".."),
            &k.id,
            "kit file must be a relative asset filename",
        )?;
        require(
            [
                "mesh",
                "decal",
                "scroll",
                "billboard",
                "utility",
                "flipbook",
                "sprites",
                "atlas",
                "prop",
            ]
            .contains(&k.kind.as_str())
                && (1..=2).contains(&k.kit_version)
                && k.first_needed_at_step
                    .is_none_or(|step| (1..=6).contains(&step)),
            &k.id,
            "unknown kit descriptor",
        )?;
        require(
            k.first_needed_at_step.is_some()
                || (["utility", "atlas"].contains(&k.kind.as_str())
                    && k.used_by_skills.is_empty()
                    && k.used_by_reactions.is_empty()),
            &k.id,
            "only shared utility assets may omit a production step",
        )?;
        refs(&k.used_by_skills, &skills, &k.id)?;
        refs(&k.used_by_reactions, &kit_reactions, &k.id)?;
    }
    let mut weapon_heroes = BTreeSet::new();
    for w in &d.weapons {
        require(
            heroes.contains(w.hero.as_str())
                && weapon_heroes.insert(&w.hero)
                && d.heroes.iter().any(|h| h.id == w.hero && h.weapon == w.key),
            &w.key,
            "weapon/hero ownership mismatch",
        )?;
        // Source paths, provider settings and credit estimates are descriptions,
        // never filesystem access or spending authorization.
        for v in [&w.weapon, &w.route, &w.source, &w.markers, &w.socket] {
            text(v, &w.key)?;
        }
        require(
            w.credits <= 100_000,
            &w.key,
            "credit estimate outside import bounds",
        )?;
    }
    validate_legacy(d)
}

#[allow(clippy::too_many_arguments)]
fn validate_skill(
    s: &SkillDefinition,
    d: &HeroSkillDraft,
    heroes: &BTreeSet<&str>,
    statuses: &BTreeSet<&str>,
    reactions: &BTreeSet<&str>,
    kits: &BTreeSet<&str>,
    telegraphs: &BTreeSet<&str>,
    tiers: &BTreeSet<&str>,
    budgets: &BTreeSet<&str>,
) -> Result<(), CatalogError> {
    let p = &s.id;
    require(
        heroes.contains(s.hero.as_str())
            && s.id.starts_with(&format!("{}_", s.hero))
            && s.slot <= 6,
        p,
        "invalid hero or skill slot",
    )?;
    names(&s.name, p)?;
    text(&s.summary, p)?;
    text(&s.power, p)?;
    text(&s.targeting.mode, p)?;
    let kinds = [
        "damage", "control", "buff", "ultimate", "debuff", "mobility", "heal",
    ];
    require(
        kinds.contains(&s.kind.as_str())
            && s.secondary_type
                .as_ref()
                .is_none_or(|v| kinds.contains(&v.as_str())),
        p,
        "unknown skill type",
    )?;
    require(
        ["physical", "magical", "none"].contains(&s.damage_type.as_str()),
        p,
        "unknown damage type",
    )?;
    id(&s.element, p)?;
    bounded(s.targeting.range_m, 0.0, 100.0, p)?;
    if let Some(radius) = s.targeting.radius_m {
        bounded(radius, 0.01, 100.0, p)?;
    }
    validate_telegraph(&s.telegraph, telegraphs, p)?;
    let t = &s.timing;
    for ms in [t.windup_ms, t.active_ms, t.recovery_ms, t.clip_ms] {
        duration(ms, false, p)?;
    }
    require(
        t.fps == 30
            && t.release_ms == t.windup_ms
            && t.release_frame == (f64::from(t.windup_ms) * 0.03).round() as u32
            && t.clip_frames == (f64::from(t.clip_ms) * 0.03).round() as u32,
        p,
        "release/clip frame does not match 30 fps timing",
    )?;
    let phases = u64::from(t.windup_ms) + u64::from(t.active_ms) + u64::from(t.recovery_ms);
    require(
        phases <= u64::from(t.clip_ms) + 2,
        p,
        "clip shorter than combat phases (2 ms quantization allowance)",
    )?;
    if let Some(exact) = t.release_frame_exact {
        bounded(exact, 0.0, 18000.0, p)?;
        require(
            (exact - f64::from(t.release_ms) * 0.03).abs() < 0.000001,
            p,
            "exact release frame mismatch",
        )?;
    }
    text(&t.clip, p)?;
    require(
        s.anim.clip == t.clip,
        p,
        "animation and timing clip descriptions disagree",
    )?;
    require(
        !t.events.is_empty() && t.events.len() <= 16,
        p,
        "clip event count outside bounds",
    )?;
    let mut event_ids = BTreeSet::new();
    let mut previous = 0;
    for e in &t.events {
        id(&e.id, p)?;
        require(
            event_ids.insert((&e.id, e.t_ms)) && e.t_ms >= previous && e.t_ms <= t.clip_ms,
            p,
            "duplicate, unordered or out-of-clip event",
        )?;
        previous = e.t_ms;
    }
    require(
        t.events.iter().any(|e| e.t_ms == t.release_ms),
        p,
        "missing event at release time",
    )?;
    duration(s.cooldown_ms, false, p)?;
    require(
        s.cost.sp <= d.resource.pool,
        p,
        "SP cost exceeds proposed pool",
    )?;
    require(
        s.status.len() <= 2 && s.effects.len() <= 16,
        p,
        "too many status/effect descriptions",
    )?;
    let applied = unique(s.status.iter().map(|a| a.id.as_str()), p)?;
    require(
        applied.iter().all(|v| statuses.contains(v)),
        p,
        "unresolved applied status",
    )?;
    for a in &s.status {
        let definition = d.statuses.iter().find(|v| v.id == a.id).unwrap();
        require(
            definition.hero == s.hero
                && a.duration_ms == definition.duration_ms
                && a.stacks > 0
                && a.stacks <= definition.max_stacks,
            p,
            "status owner/duration/stacks disagree with definition",
        )?;
    }
    refs(&s.combos, reactions, p)?;
    require(
        s.combos.iter().all(|r| {
            d.reactions
                .iter()
                .any(|v| v.id == *r && v.pair.iter().any(|a| applied.contains(a.as_str())))
        }),
        p,
        "combo is not enabled by an applied status",
    )?;
    if let Some(consumed) = &s.consumes_status {
        require(
            statuses.contains(consumed.as_str()),
            p,
            "unresolved consumed status",
        )?;
    }
    if s.slot == 0 {
        require(
            s.cost.sp == 0
                && s.status.is_empty()
                && s.combos.is_empty()
                && s.telegraph.kind == "NONE_BASIC"
                && s.vfx.budget_class == "basic",
            p,
            "basic must remain free with no statuses or reactions",
        )?;
    } else {
        require(
            s.telegraph.kind != "NONE_BASIC"
                && ((s.slot == 6) == (s.kind == "ultimate"))
                && s.vfx.budget_class == if s.slot == 6 { "ultimate" } else { "heroic" },
            p,
            "skill slot/type/budget class disagree",
        )?;
        if s.slot == 6 {
            require(
                s.status.len() == 2,
                p,
                "ultimate must apply both hero statuses",
            )?;
        }
    }
    validate_extra(&s.extra, p)?;
    palette(&s.palette, p)?;
    let preset_parts: Vec<_> = s.vfx.preset.split('@').collect();
    require(preset_parts.len() <= 2, p, "invalid preset variant")?;
    for part in preset_parts {
        id(part, p)?;
    }
    require(
        budgets.contains(s.vfx.budget_class.as_str()),
        p,
        "unknown VFX budget class",
    )?;
    bounded(s.vfx.peak_coverage_pct, 0.1, 100.0, p)?;
    require(
        (5..=7).contains(&s.vfx.layers.len()),
        p,
        "expected five to seven VFX layers",
    )?;
    let mut layer_roles = BTreeSet::new();
    for l in &s.vfx.layers {
        require(
            [
                "anticipation",
                "core",
                "secondary",
                "ground",
                "after",
                "light",
                "distortion",
            ]
            .contains(&l.role.as_str())
                && layer_roles.insert(l.role.as_str()),
            p,
            "unknown or duplicate VFX layer role",
        )?;
        require(tiers.contains(l.min_tier.as_str()), p, "unknown layer tier")?;
        text(&l.desc, p)?;
        refs(&l.kit, kits, p)?;
        require(
            !l.kit.is_empty() || ["light", "distortion"].contains(&l.role.as_str()),
            p,
            "render layer is missing its kit references",
        )?;
        for anchor in [&l.t.from, &l.t.to] {
            require(
                ["cast", "hit", "end"].contains(&anchor.as_str()),
                p,
                "unknown VFX timing anchor",
            )?;
        }
        duration(l.t.start_ms, true, p)?;
        duration(l.t.end_ms, true, p)?;
        require(
            l.t.from != l.t.to || l.t.start_ms <= l.t.end_ms,
            p,
            "reversed same-anchor layer interval",
        )?;
        if let Some(scale) = l.medium_scale {
            bounded(scale, 0.0, 1.0, p)?;
        }
        // Missing medium_scale is the documented default 0.5, not missing data.
    }
    require(
        ["anticipation", "core", "secondary", "ground", "after"]
            .iter()
            .all(|r| layer_roles.contains(r)),
        p,
        "missing mandatory VFX role",
    )?;
    id(&s.sfx.cue, p)?;
    require(
        !s.sfx.phases.is_empty() && s.sfx.phases.len() <= 8,
        p,
        "missing or excessive SFX phases",
    )?;
    require(s.keyframes.len() == 8, p, "expected eight reference beats")?;
    let mut previous = 0;
    for k in &s.keyframes {
        duration(k.t_ms, true, p)?;
        text(&k.beat, p)?;
        require(k.t_ms >= previous, p, "unordered keyframe beats")?;
        previous = k.t_ms;
    }
    Ok(())
}

fn validate_telegraph(t: &Telegraph, kinds: &BTreeSet<&str>, p: &str) -> Result<(), CatalogError> {
    require(kinds.contains(t.kind.as_str()), p, "unknown telegraph kind")?;
    for value in [t.width_m, t.length_m, t.radius_m].into_iter().flatten() {
        bounded(value, 0.01, 100.0, p)?;
    }
    if let Some(angle) = t.angle_deg {
        bounded(angle, 0.1, 360.0, p)?;
    }
    if let Some(next) = &t.then {
        require(
            kinds.contains(next.kind.as_str()),
            p,
            "unknown continuation telegraph",
        )?;
        bounded(next.radius_m, 0.01, 100.0, p)?;
        text(&next.at, p)?;
        if let Some(ms) = next.shown_ms {
            duration(ms, false, p)?;
        }
    }
    Ok(())
}

fn validate_extra(extra: &BTreeMap<String, Value>, p: &str) -> Result<(), CatalogError> {
    const TEXT_FIELDS: &[&str] = &[
        "chain",
        "stagger",
        "waves",
        "strikes",
        "beam_ticks",
        "portal_ms",
        "slag_ms",
    ];
    const NUMERIC_FIELDS: &[&str] = &[
        "projectile_speed_mps",
        "knockback_m",
        "knockup_m",
        "pull_mps",
        "collapse_ms",
        "collapse_radius_m",
        "pierce",
        "shield",
        "shield_ms",
        "nova_ms",
        "arc_deg",
        "targets",
        "taunt_ms",
        "dash_ms",
        "knock_aside_m",
        "damage_reduction_pct",
        "zone_ms",
        "knockdown_ms",
        "hits",
        "knives",
        "max_per_target",
        "execute_threshold_pct",
        "untargetable_ms",
        "bomb_flight_ms",
        "finale_ms",
        "finale_radius_m",
        "flight_ms",
        "slow_pct",
        "sentry_range_m",
        "sentry_ms",
        "shot_ms",
        "shots",
        "sentry_hp",
        "threat_pct",
        "air_ms",
        "pulse_ms",
        "shield_per_pulse",
        "shield_cap",
        "def_pct",
        "beacon_lands_ms",
        "impact_ms",
        "tick_ms",
        "ally_heal",
        "hot_ms",
        "ally_shield",
        "ally_shield_ms",
        "revive_pct",
        "noon_grace_ms",
        "arrows",
        "hold_max_ms",
        "knockback_full_m",
        "root_ms",
        "max_hits_per_target",
        "dive_ms",
    ];
    for (k, v) in extra {
        if TEXT_FIELDS.contains(&k.as_str()) {
            text(
                v.as_str()
                    .ok_or_else(|| invalid(p, "extension description must be text"))?,
                p,
            )?;
        } else if k == "ticks" && v.is_string() {
            text(v.as_str().unwrap(), p)?;
        } else {
            require(
                NUMERIC_FIELDS.contains(&k.as_str()) || k == "ticks",
                p,
                "unknown extension field",
            )?;
            let number = v
                .as_f64()
                .ok_or_else(|| invalid(p, "extension number required"))?;
            let max = if k.ends_with("_pct") {
                100.0
            } else if k == "arc_deg" {
                360.0
            } else if k.ends_with("_m") || k.ends_with("_mps") {
                100.0
            } else {
                f64::from(MAX_MS)
            };
            bounded(number, 0.0, max, p)?;
            if k.ends_with("_ms") {
                require(
                    number.fract() == 0.0,
                    p,
                    "millisecond extension must be integral",
                )?;
            }
        }
    }
    Ok(())
}

fn validate_legacy(d: &HeroSkillDraft) -> Result<(), CatalogError> {
    let basic = d
        .skills
        .iter()
        .find(|s| s.id == "h01_basic")
        .ok_or_else(|| invalid("h01_basic", "missing fixed legacy basic"))?;
    let arc = d
        .skills
        .iter()
        .find(|s| s.id == "h01_lodestar_arc")
        .ok_or_else(|| invalid("h01_lodestar_arc", "missing fixed legacy arc"))?;
    require(
        basic.legacy_ability.as_deref() == Some("attack")
            && basic.hero == "h01"
            && basic.slot == 0
            && basic.power == "25 per link"
            && basic.cooldown_ms == 400
            && basic.targeting.range_m == 3.0
            && basic.timing.windup_ms == 100
            && basic.timing.active_ms == 60
            && basic.timing.recovery_ms == 200
            && basic.extra.get("arc_deg").and_then(Value::as_u64) == Some(90)
            && basic
                .extra
                .get("targets")
                .is_none_or(|v| v.as_u64() == Some(1)),
        "h01_basic",
        "fixed legacy attack contract changed",
    )?;
    require(
        arc.legacy_ability.as_deref() == Some("arc_slash")
            && arc.hero == "h01"
            && arc.slot == 1
            && arc.power == "45"
            && arc.cooldown_ms == 5000
            && arc.targeting.range_m == 4.0
            && arc.extra.get("targets").and_then(Value::as_u64) == Some(3)
            && arc.extra.get("arc_deg").and_then(Value::as_u64) == Some(120)
            && arc.telegraph.radius_m == Some(4.0)
            && arc.telegraph.angle_deg == Some(120.0)
            && arc.timing.windup_ms == 250
            && arc.timing.active_ms == 100
            && arc.timing.recovery_ms == 350,
        "h01_lodestar_arc",
        "fixed legacy arc_slash contract changed",
    )?;
    require(
        d.skills
            .iter()
            .all(|s| s.legacy_ability.is_none() || s.id == basic.id || s.id == arc.id),
        "legacy_ability",
        "draft skill may not claim a live wire ability",
    )
}

fn validate_tree(value: &Value, depth: usize, nodes: &mut usize) -> Result<(), CatalogError> {
    *nodes += 1;
    require(
        depth <= MAX_DEPTH && *nodes <= MAX_NODES,
        "$",
        "draft nesting or node limit exceeded",
    )?;
    match value {
        Value::String(s) => text(s, "$")?,
        Value::Number(n) => require(
            n.as_f64().is_some_and(f64::is_finite),
            "$",
            "non-finite number",
        )?,
        Value::Array(a) => {
            require(a.len() <= MAX_COLLECTION, "$", "array item limit exceeded")?;
            for v in a {
                validate_tree(v, depth + 1, nodes)?;
            }
        }
        Value::Object(o) => {
            require(
                o.len() <= MAX_COLLECTION,
                "$",
                "object field limit exceeded",
            )?;
            for (k, v) in o {
                require(k.len() <= 80, "$", "field name limit exceeded")?;
                validate_tree(v, depth + 1, nodes)?;
            }
        }
        _ => {}
    }
    Ok(())
}

struct UniqueValue(Value);
impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct UniqueVisitor;
        impl<'de> Visitor<'de> for UniqueVisitor {
            type Value = UniqueValue;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON with unique object fields")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Bool(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(v.into())))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Number(v.into())))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(v)
                    .map(|n| UniqueValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("non-finite JSON number"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
                require(v.len() <= MAX_TEXT_BYTES, "$", "text byte limit exceeded")
                    .map_err(E::custom)?;
                Ok(UniqueValue(Value::String(v.to_owned())))
            }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Self::Value, E> {
                require(v.len() <= MAX_TEXT_BYTES, "$", "text byte limit exceeded")
                    .map_err(E::custom)?;
                Ok(UniqueValue(Value::String(v)))
            }
            fn visit_none<E: de::Error>(self) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
                Ok(UniqueValue(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut access: A) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(v) = access.next_element::<UniqueValue>()? {
                    if values.len() == MAX_COLLECTION {
                        return Err(de::Error::custom("array item limit exceeded"));
                    }
                    values.push(v.0);
                }
                Ok(UniqueValue(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(k) = access.next_key::<String>()? {
                    if k.len() > 80 || values.len() == MAX_COLLECTION {
                        return Err(de::Error::custom("object field limit exceeded"));
                    }
                    if values.contains_key(&k) {
                        return Err(de::Error::custom("duplicate JSON object field"));
                    }
                    values.insert(k, access.next_value::<UniqueValue>()?.0);
                }
                Ok(UniqueValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(UniqueVisitor)
    }
}
