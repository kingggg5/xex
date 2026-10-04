// Path import exercises this inactive candidate before root mounts the module.
#[allow(dead_code)]
#[path = "../src/hero_skill_catalog.rs"]
mod hero_skill_catalog;

use hero_skill_catalog::{ActivationState, MAX_DRAFT_BYTES, load_design_draft};
use serde_json::{Value, json};

const DRAFT: &[u8] = include_bytes!("../../../planning/assets/hero-skills.json");
const LEGACY: &[u8] = include_bytes!("../../../content/source/abilities.json");
fn fixture() -> Value {
    serde_json::from_slice(DRAFT).unwrap()
}
fn reject(value: &Value, expected: &str) {
    let error = load_design_draft(&serde_json::to_vec(value).unwrap()).unwrap_err();
    assert!(
        error.to_string().contains(expected),
        "expected {expected:?}, got {error}"
    );
    assert!(error.path.len() <= 180 && error.reason.chars().count() <= 240);
}
fn skill_index(value: &Value, id: &str) -> usize {
    value["skills"]
        .as_array()
        .unwrap()
        .iter()
        .position(|s| s["id"] == id)
        .unwrap()
}

#[test]
fn actual_42_entry_draft_imports_read_only_with_explicit_activation_gaps() {
    let catalog = load_design_draft(DRAFT).unwrap();
    assert_eq!(catalog.activation(), ActivationState::DraftOnly);
    let draft = catalog.draft();
    assert_eq!(
        (
            draft.heroes.len(),
            draft.skills.len(),
            draft.statuses.len(),
            draft.reactions.len()
        ),
        (6, 42, 12, 8)
    );
    assert_eq!(draft.kit.len(), 51);
    assert_eq!(draft.kit.iter().filter(|k| k.kit_version == 1).count(), 21);
    assert_eq!(
        draft
            .kit
            .iter()
            .filter(|k| k.kit_version == 2 && k.kind != "prop")
            .count(),
        28
    );
    assert_eq!(draft.kit.iter().filter(|k| k.kind == "prop").count(), 2);
    assert!(
        catalog
            .activation_gaps()
            .iter()
            .any(|g| g.contains("D1-D8"))
    );
    assert!(
        catalog
            .activation_gaps()
            .iter()
            .any(|g| g.contains("power is prose"))
    );
    assert!(
        catalog
            .activation_gaps()
            .iter()
            .any(|g| g.contains("no live resource"))
    );
}

#[test]
fn fixed_legacy_contract_matches_actual_live_ability_fixture() {
    let catalog = load_design_draft(DRAFT).unwrap();
    let legacy: Value = serde_json::from_slice(LEGACY).unwrap();
    for (draft_id, wire_id) in [("h01_basic", "attack"), ("h01_lodestar_arc", "arc_slash")] {
        let skill = catalog
            .draft()
            .skills
            .iter()
            .find(|s| s.id == draft_id)
            .unwrap();
        let ability = legacy["abilities"]
            .as_array()
            .unwrap()
            .iter()
            .find(|a| a["id"] == wire_id)
            .unwrap();
        assert_eq!(skill.legacy_ability.as_deref(), Some(wire_id));
        assert_eq!(
            u64::from(skill.cooldown_ms),
            ability["cooldown_ms"].as_u64().unwrap()
        );
        assert_eq!(skill.targeting.range_m, ability["range"].as_f64().unwrap());
        assert_eq!(
            u64::from(skill.timing.windup_ms),
            ability["windup_ms"].as_u64().unwrap()
        );
        assert_eq!(
            u64::from(skill.timing.active_ms),
            ability["active_ms"].as_u64().unwrap()
        );
        assert_eq!(
            u64::from(skill.timing.recovery_ms),
            ability["recovery_ms"].as_u64().unwrap()
        );
        assert_eq!(skill.extra["arc_deg"], ability["arc_deg"]);
        if wire_id == "attack" {
            assert_eq!(ability["damage"], 25);
            assert_eq!(skill.power, "25 per link");
        } else {
            assert_eq!(ability["damage"], 45);
            assert_eq!(skill.extra["targets"], ability["targets"]);
        }
    }
    // The proposed arc SP=10 does not retroactively impose a live resource cost.
    assert_eq!(
        catalog
            .draft()
            .skills
            .iter()
            .find(|s| s.id == "h01_lodestar_arc")
            .unwrap()
            .cost
            .sp,
        10
    );
    assert_eq!(catalog.activation(), ActivationState::DraftOnly);
}

#[test]
fn invalid_sp_costs_are_rejected_instead_of_coerced() {
    for cost in [json!(-1), json!(10001), json!(0.25), json!("10")] {
        let mut value = fixture();
        value["skills"][1]["cost"]["sp"] = cost;
        reject(
            &value,
            if value["skills"][1]["cost"]["sp"] == 10001 {
                "SP cost"
            } else {
                "incomplete or unknown"
            },
        );
    }
}
#[test]
fn invalid_cooldowns_fail_and_basics_cannot_cost_sp() {
    for cooldown in [0, 600001] {
        let mut value = fixture();
        value["skills"][1]["cooldown_ms"] = json!(cooldown);
        reject(&value, "duration outside");
    }
    let mut value = fixture();
    value["skills"][0]["cost"]["sp"] = json!(1);
    reject(&value, "basic must remain free");
}
#[test]
fn timing_release_clip_and_event_mutations_fail() {
    for (field, val, error) in [
        ("windup_ms", 0, "duration outside"),
        ("windup_ms", 600001, "duration outside"),
        ("release_ms", 101, "release/clip frame"),
        ("release_frame", 4, "release/clip frame"),
        ("fps", 60, "release/clip frame"),
        ("clip_frames", 99, "release/clip frame"),
        ("active_ms", 10000, "clip shorter"),
    ] {
        let mut value = fixture();
        value["skills"][0]["timing"][field] = json!(val);
        reject(&value, error);
    }
    let mut value = fixture();
    value["skills"][0]["timing"]["events"][1]["t_ms"] = json!(401);
    reject(&value, "out-of-clip event");
    let mut value = fixture();
    value["skills"][0]["timing"]["events"][1]["t_ms"] = json!(101);
    reject(&value, "missing event at release");
}
#[test]
fn half_frame_legacy_release_rounds_up_without_retiming_250ms_event() {
    let catalog = load_design_draft(DRAFT).unwrap();
    let arc = catalog
        .draft()
        .skills
        .iter()
        .find(|s| s.id == "h01_lodestar_arc")
        .unwrap();
    assert_eq!(
        (
            arc.timing.release_ms,
            arc.timing.release_frame,
            arc.timing.release_frame_exact
        ),
        (250, 8, Some(7.5))
    );
    let mut value = fixture();
    let i = skill_index(&value, "h01_lodestar_arc");
    value["skills"][i]["timing"]["release_frame_exact"] = json!(8.0);
    reject(&value, "exact release frame mismatch");
}
#[test]
fn duplicated_hero_skill_slot_and_preset_fail() {
    let mut value = fixture();
    value["skills"][1]["id"] = value["skills"][0]["id"].clone();
    reject(&value, "duplicate identifier");
    let mut value = fixture();
    value["heroes"][1]["id"] = value["heroes"][0]["id"].clone();
    reject(&value, "duplicate identifier");
    let mut value = fixture();
    value["skills"][1]["slot"] = json!(0);
    reject(&value, "duplicate or missing skill slot");
    let mut value = fixture();
    value["skills"][1]["vfx"]["preset"] = value["skills"][0]["vfx"]["preset"].clone();
    reject(&value, "duplicate VFX preset");
}
#[test]
fn missing_or_extra_entry_and_missing_name_fail() {
    let mut value = fixture();
    value["skills"].as_array_mut().unwrap().pop();
    reject(&value, "expected six heroes");
    let mut value = fixture();
    let extra = value["skills"][0].clone();
    value["skills"].as_array_mut().unwrap().push(extra);
    reject(&value, "expected six heroes");
    let mut value = fixture();
    value["skills"][0]["name"]
        .as_object_mut()
        .unwrap()
        .remove("th");
    reject(&value, "incomplete or unknown");
    let mut value = fixture();
    value["skills"][0]["name"]["th"] = json!("   ");
    reject(&value, "empty, oversized");
}
#[test]
fn unknown_nested_fields_or_incomplete_descriptors_fail_loudly() {
    let mut value = fixture();
    value["skills"][0]["cost"]["mana"] = json!(10);
    reject(&value, "unknown field");
    let mut value = fixture();
    value["skills"][0]
        .as_object_mut()
        .unwrap()
        .remove("targeting");
    reject(&value, "missing field");
    let mut value = fixture();
    value["skills"][0]["extra"]["set_admin"] = json!(true);
    reject(&value, "unknown extension field");
    let mut value = fixture();
    value["skills"][0]["targeting"]["radius_m"] = json!("5m");
    reject(&value, "incomplete or unknown");
}
#[test]
fn unresolved_status_reaction_palette_and_kit_mutations_fail() {
    let mut value = fixture();
    value["skills"][1]["status"][0]["id"] = json!("missing");
    reject(&value, "unresolved applied status");
    let mut value = fixture();
    value["skills"][1]["combos"][0] = json!("rx_missing");
    reject(&value, "unresolved reference");
    let mut value = fixture();
    value["skills"][1]["palette"]["body"] = json!("#GG12AB");
    reject(&value, "palette colour");
    let mut value = fixture();
    value["skills"][1]["vfx"]["layers"][0]["kit"][0] = json!("vfx_missing");
    reject(&value, "unresolved reference");
    let mut value = fixture();
    value["skills"][1]["telegraph"]["kind"] = json!("DANGER_RED_ONLY");
    reject(&value, "unknown telegraph kind");
}
#[test]
fn status_duration_stack_and_owner_mismatches_fail() {
    let mut value = fixture();
    value["skills"][1]["status"][0]["duration_ms"] = json!(6001);
    reject(&value, "status owner/duration/stacks");
    let mut value = fixture();
    value["skills"][1]["status"][0]["stacks"] = json!(2);
    reject(&value, "status owner/duration/stacks");
    let mut value = fixture();
    value["heroes"][0]["statuses"][0] = json!("chilled");
    reject(&value, "hero status ownership mismatch");
}
#[test]
fn fifo_consumption_lockout_ancestry_and_pvp_policy_are_checked() {
    for (field, val) in [
        ("pairing", json!("newest_first")),
        ("consume_both", json!(false)),
        ("target_lockout_ms", json!(1499)),
        ("pvp_enabled", json!(true)),
        (
            "can_trigger_reaction_sources",
            json!(["skill_hit", "reaction_damage"]),
        ),
    ] {
        let mut value = fixture();
        value["reaction_rules_numeric"][field] = val;
        reject(&value, "draft reaction policy");
    }
}
#[test]
fn reaction_pair_reference_owner_and_status_backlink_are_checked() {
    let mut value = fixture();
    value["reactions"][0]["pair"][1] = json!("missing");
    reject(&value, "two distinct statuses");
    let mut value = fixture();
    value["reactions"][0]["heroes"][1] = json!("h01");
    reject(&value, "two different hero owners");
    let mut value = fixture();
    value["statuses"][0]["reactions"] = json!([]);
    reject(&value, "references disagree");
}
#[test]
fn layer_tier_scale_role_timing_and_required_kit_are_checked() {
    let mut value = fixture();
    value["skills"][0]["vfx"]["layers"][0]["min_tier"] = json!("ultra_plus");
    reject(&value, "unknown layer tier");
    let mut value = fixture();
    value["skills"][0]["vfx"]["layers"][2]["medium_scale"] = json!(1.1);
    reject(&value, "finite import bounds");
    let mut value = fixture();
    value["skills"][0]["vfx"]["layers"][0]["role"] = json!("core");
    reject(&value, "duplicate VFX layer role");
    let mut value = fixture();
    value["skills"][0]["vfx"]["layers"][0]["t"]["start_ms"] = json!(101);
    reject(&value, "reversed same-anchor");
    let mut value = fixture();
    value["skills"][0]["vfx"]["layers"][0]["kit"] = json!([]);
    reject(&value, "missing its kit");
    let mut value = fixture();
    value["skills"][0]["vfx"]["layers"][0]["t"]["from"] = json!("wall_clock");
    reject(&value, "unknown VFX timing anchor");
}
#[test]
fn byte_collection_text_depth_and_duplicate_json_field_bounds_fail() {
    assert!(
        load_design_draft(&vec![b' '; MAX_DRAFT_BYTES + 1])
            .unwrap_err()
            .reason
            .contains("byte limit")
    );
    assert!(
        load_design_draft(br#"{"schema":"a","schema":"b"}"#)
            .unwrap_err()
            .reason
            .contains("duplicate JSON object field")
    );
    let mut value = fixture();
    value["skills"][0]["summary"] = json!("x".repeat(4097));
    reject(&value, "text byte limit");
    let mut value = fixture();
    value["skills"][0]["effects"] = json!(vec!["x"; 65]);
    reject(&value, "array item limit");
    let mut value = fixture();
    let mut deep = json!(0);
    for _ in 0..17 {
        deep = json!([deep]);
    }
    value["skills"][0]["extra"]["chain"] = deep;
    reject(&value, "nesting or node limit");
    assert!(
        load_design_draft(b"{\"value\":1e400}")
            .unwrap_err()
            .reason
            .contains("invalid JSON")
    );
}
#[test]
fn negative_and_absurd_target_sizes_are_rejected() {
    for range in [json!(-0.1), json!(100.01), json!("12")] {
        let mut value = fixture();
        value["skills"][0]["targeting"]["range_m"] = range;
        assert!(load_design_draft(&serde_json::to_vec(&value).unwrap()).is_err());
    }
    let mut value = fixture();
    value["skills"][0]["targeting"]["radius_m"] = json!(0);
    reject(&value, "finite import bounds");
    let mut value = fixture();
    value["skills"][1]["extra"]["knockback_m"] = json!(1000000);
    reject(&value, "finite import bounds");
}
#[test]
fn proposed_names_and_prose_are_never_parsed_into_runtime_formulas() {
    let mut value = fixture();
    value["skills"][0]["power"] =
        json!("not a damage formula: proposed healing or damage awaits review");
    value["skills"][0]["name"]["en"] = json!("Owner may rename this");
    let catalog = load_design_draft(&serde_json::to_vec(&value).unwrap()).unwrap();
    assert_eq!(catalog.activation(), ActivationState::DraftOnly);
    assert!(
        catalog
            .activation_gaps()
            .iter()
            .any(|g| g.contains("typed damage/healing"))
    );
}
#[test]
fn legacy_mutations_and_foreign_wire_claims_fail() {
    let mut value = fixture();
    let i = skill_index(&value, "h01_lodestar_arc");
    value["skills"][i]["power"] = json!("46");
    reject(&value, "fixed legacy arc_slash");
    let mut value = fixture();
    let i = skill_index(&value, "h01_basic");
    value["skills"][i]["cooldown_ms"] = json!(401);
    reject(&value, "fixed legacy attack");
    let mut value = fixture();
    value["skills"][0]["legacy_ability"] = json!("attack");
    reject(&value, "may not claim a live wire ability");
}

#[test]
fn numeric_quantization_and_idle_padding_do_not_retime_the_skill() {
    let catalog = load_design_draft(DRAFT).unwrap();
    let lance = catalog
        .draft()
        .skills
        .iter()
        .find(|s| s.id == "h02_star_lance")
        .unwrap();
    assert_eq!(
        lance.timing.windup_ms + lance.timing.active_ms + lance.timing.recovery_ms,
        834
    );
    assert_eq!(lance.timing.clip_ms, 833);
    let mut value = fixture();
    let i = skill_index(&value, "h02_star_lance");
    value["skills"][i]["timing"]["recovery_ms"] = json!(302);
    reject(&value, "clip shorter than combat phases");
    let basic = catalog
        .draft()
        .skills
        .iter()
        .find(|s| s.id == "h01_basic")
        .unwrap();
    assert_eq!(basic.timing.clip_ms, 400);
    assert_eq!(
        basic.timing.windup_ms + basic.timing.active_ms + basic.timing.recovery_ms,
        360
    );
}

#[test]
fn distinct_repeated_hits_are_preserved_but_identical_events_fail() {
    let catalog = load_design_draft(DRAFT).unwrap();
    let adder = catalog
        .draft()
        .skills
        .iter()
        .find(|s| s.id == "h05_adders_kiss")
        .unwrap();
    assert_eq!(
        adder.timing.events.iter().filter(|e| e.id == "hit").count(),
        2
    );
    let mut value = fixture();
    let i = skill_index(&value, "h05_adders_kiss");
    let duplicate = value["skills"][i]["timing"]["events"][1].clone();
    value["skills"][i]["timing"]["events"][2] = duplicate;
    reject(&value, "duplicate, unordered or out-of-clip event");
    let mut value = fixture();
    let i = skill_index(&value, "h01_basic");
    value["skills"][i]["extra"]["targets"] = json!(4);
    reject(&value, "fixed legacy attack contract changed");
}
