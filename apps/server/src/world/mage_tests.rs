use super::*;
use crate::mage_trial::{CastRequest, SkillId, TrialRequest};
fn arena() -> (World, Welcome, [u8; 32]) {
    let c = crate::content::test_content();
    let mut w = World::new(&c, crate::character::CharacterStore::shared());
    w.mage_capability = true;
    w.static_colliders.clear();
    w.city_traversal = None;
    let session = [211; 32];
    let welcome = w.join(session).unwrap();
    let p = w.players.get_mut(&welcome.player_id).unwrap();
    p.x = 0.0;
    p.z = 0.0;
    p.y = 0.0;
    for m in &mut w.monsters {
        m.hp = 0;
    }
    let m = &mut w.monsters[0];
    m.hp = 100;
    m.max_hp = 100;
    m.x = 0.0;
    m.z = 3.0;
    m.y = 0.0;
    m.home_x = 0.0;
    m.home_z = 3.0;
    m.home_y = 0.0;
    m.speed = 0.0;
    m.aggro = 0.0;
    m.leash = 30.0;
    m.respawn_at = None;
    (w, welcome, session)
}
fn enable(w: &mut World, id: u32) {
    assert_eq!(
        w.mage_trial_activate(
            id,
            TrialRequest {
                t: "mage_trial".into(),
                enabled: true,
                op_id: uuid::Uuid::new_v4().to_string()
            }
        )
        .unwrap()
        .status,
        "accepted"
    );
}
fn cast(w: &World, welcome: &Welcome, seq: u32, skill: SkillId) -> CastRequest {
    CastRequest {
        t: "mage_cast".into(),
        epoch: welcome.epoch,
        sequence: seq,
        skill_id: skill,
        target_id: w.monsters[0].id,
    }
}
#[test]
fn trial_is_explicit_gated_and_focus_is_one_real_piece_without_loadout_loss() {
    let (mut w, wel, _) = arena();
    w.mage_capability = false;
    let r = cast(&w, &wel, 1, SkillId::Basic);
    assert_eq!(w.mage_cast(wel.player_id, r).unwrap().reason, "not_allowed");
    assert_eq!(
        w.mage_trial_activate(
            wel.player_id,
            TrialRequest {
                t: "mage_trial".into(),
                enabled: true,
                op_id: uuid::Uuid::new_v4().to_string()
            }
        )
        .unwrap()
        .reason,
        "mage_trial_disabled"
    );
    w.mage_capability = true;
    let p = w.players.get_mut(&wel.player_id).unwrap();
    p.bag.insert("frontier_blade".into(), 1);
    bump_state_revision(p);
    let blade = p
        .item_instances
        .values()
        .find(|i| i.def == "frontier_blade")
        .unwrap()
        .instance_id
        .clone();
    p.item_instances.get_mut(&blade).unwrap().refine = 4;
    let request = crate::cold::MoveItemInstanceRequest {
        t: "move_item_instance".into(),
        instance_id: blade.clone(),
        op_id: uuid::Uuid::new_v4().to_string(),
        expected_revision: p.state_revision,
        to: "weapon".into(),
    };
    w.move_item_instance(wel.player_id, request).unwrap();
    let before = (
        w.players[&wel.player_id].exp,
        w.players[&wel.player_id].gold,
    );
    enable(&mut w, wel.player_id);
    enable(&mut w, wel.player_id);
    let p = &w.players[&wel.player_id];
    assert_eq!(
        p.item_instances
            .values()
            .filter(|i| i.def == "arcane_focus")
            .count(),
        1
    );
    assert_eq!(p.item_instances[&blade].location, "bag");
    assert_eq!(p.item_instances[&blade].refine, 4);
    assert_eq!(before, (p.exp, p.gold));
    assert_eq!(w.vocation_id, "trailblade");
}
#[test]
fn mage_basic_has_server_release_flight_and_once_only_impact() {
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    let r = cast(&w, &wel, 1, SkillId::Basic);
    let started = w.mage_cast(wel.player_id, r.clone()).unwrap();
    assert_eq!(started.release_ms - started.start_ms, 100);
    assert_eq!(w.monsters[0].hp, 100);
    assert_eq!(w.mage_cast(wel.player_id, r.clone()).unwrap(), started);
    let mut changed = r.clone();
    changed.target_id += 1;
    assert_eq!(
        w.mage_cast(wel.player_id, changed).unwrap().reason,
        "intent_conflict"
    );
    w.advance();
    assert_eq!(w.monsters[0].hp, 100);
    w.advance();
    assert!(
        w.players[&wel.player_id]
            .mage
            .pending
            .as_ref()
            .unwrap()
            .released
    );
    for _ in 0..4 {
        w.advance();
    }
    assert_eq!(w.monsters[0].hp, 75);
    assert!(
        w.recent_events.is_empty(),
        "Mage has no duplicated physical binary HIT"
    );
    let replay = w.mage_cast(wel.player_id, r).unwrap();
    assert_eq!(replay.phase, "impact");
    assert_eq!(w.monsters[0].hp, 75);
}
#[test]
fn rejection_echoes_intent_and_los_range_life_are_authoritative() {
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    let mut r = cast(&w, &wel, 1, SkillId::Basic);
    r.target_id = 999999;
    let rejected = w.mage_cast(wel.player_id, r.clone()).unwrap();
    assert_eq!(rejected.target_id, r.target_id);
    assert_eq!(
        rejected.cast_id,
        format!("{}:{}:1", wel.player_id, wel.epoch)
    );
    assert_eq!(rejected.damage, 0);
    w.static_colliders
        .push(StaticCollider::from_center_dimensions(
            [0.0, 1.0, 1.5],
            [1.0, 2.0, 0.01],
        ));
    assert_eq!(
        w.mage_cast(wel.player_id, cast(&w, &wel, 2, SkillId::Basic))
            .unwrap()
            .reason,
        "blocked"
    );
    w.static_colliders.clear();
    w.monsters[0].z = 10.0;
    assert_eq!(
        w.mage_cast(wel.player_id, cast(&w, &wel, 3, SkillId::Basic))
            .unwrap()
            .reason,
        "out_of_range"
    );
    w.monsters[0].z = 3.0;
    w.mage_cast(wel.player_id, cast(&w, &wel, 4, SkillId::Basic));
    w.monsters[0].encounter_id = uuid::Uuid::new_v4();
    for _ in 0..5 {
        w.advance();
    }
    assert_eq!(w.monsters[0].hp, 100);
    assert!(
        w.players[&wel.player_id]
            .mage
            .recent
            .back()
            .unwrap()
            .1
            .reason
            .contains("life_changed")
    );
}
#[test]
fn lance_move_focus_disconnect_epoch_and_death_cancel_without_refunds_or_rewards() {
    for cause in 0..6 {
        let (mut w, wel, _) = arena();
        enable(&mut w, wel.player_id);
        let before = w.players[&wel.player_id].sp;
        w.mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::StarLance));
        assert_eq!(w.players[&wel.player_id].sp, before - 8);
        let p = w.players.get_mut(&wel.player_id).unwrap();
        match cause {
            0 => p.x += 0.1,
            1 => {
                p.equipment.remove("weapon");
            }
            2 => p.connected = false,
            3 => p.epoch += 1,
            4 => {
                p.hp = 0;
                p.down = true;
            }
            _ => p.y += 0.1,
        }
        for _ in 0..12 {
            w.advance();
        }
        assert_eq!(w.monsters[0].hp, 100);
        assert_eq!(w.players[&wel.player_id].exp, 0);
        assert_eq!(w.players[&wel.player_id].sp, before - 8);
        assert!(w.players[&wel.player_id].mage.pending.is_none());
    }
}
#[test]
fn focus_after_release_does_not_destroy_projectile_and_lance_releases_at500ms() {
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    w.mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::StarLance));
    for _ in 0..9 {
        w.advance();
    }
    assert!(
        !w.players[&wel.player_id]
            .mage
            .pending
            .as_ref()
            .unwrap()
            .released
    );
    w.advance();
    assert!(
        w.players[&wel.player_id]
            .mage
            .pending
            .as_ref()
            .unwrap()
            .released
    );
    w.players
        .get_mut(&wel.player_id)
        .unwrap()
        .equipment
        .remove("weapon");
    for _ in 0..4 {
        w.advance();
    }
    assert_eq!(w.monsters[0].hp, 57);
    assert_eq!(
        w.players[&wel.player_id]
            .mage
            .recent
            .back()
            .unwrap()
            .1
            .release_ms,
        500
    );
}
#[test]
fn mage_defeat_levels_both_tracks_allocates_and_equips_same_character_then_reconnects() {
    let (mut w, wel, session) = arena();
    enable(&mut w, wel.player_id);
    {
        let p = w.players.get_mut(&wel.player_id).unwrap();
        p.exp = 99;
        p.job_exp = 79;
    }
    w.monsters[0].hp = 1;
    w.mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::Basic));
    for _ in 0..6 {
        w.advance();
    }
    let p = &w.players[&wel.player_id];
    assert_eq!((p.level, p.job_level, p.stat_points), (2, 2, 3));
    let before = (p.exp, p.job_exp, p.gold);
    for _ in 0..6 {
        w.advance();
    }
    assert_eq!(
        before,
        (
            w.players[&wel.player_id].exp,
            w.players[&wel.player_id].job_exp,
            w.players[&wel.player_id].gold
        )
    );
    let op = uuid::Uuid::new_v4().to_string();
    w.stat_allocate(
        wel.player_id,
        crate::cold::StatAllocateRequest {
            stat: "int".into(),
            points: 1,
            op_id: op.clone(),
        },
    );
    assert_eq!(w.players[&wel.player_id].stat_points, 2);
    assert_eq!(
        w.stat_allocate(
            wel.player_id,
            crate::cold::StatAllocateRequest {
                stat: "int".into(),
                points: 2,
                op_id: op
            }
        )
        .unwrap()
        .reason,
        "op_id_conflict"
    );
    let p = &w.players[&wel.player_id];
    let focus = p
        .item_instances
        .values()
        .find(|i| i.def == "arcane_focus")
        .unwrap()
        .instance_id
        .clone();
    let req = crate::cold::MoveItemInstanceRequest {
        t: "move_item_instance".into(),
        instance_id: focus,
        expected_revision: p.state_revision,
        op_id: uuid::Uuid::new_v4().to_string(),
        to: "bag".into(),
    };
    assert_eq!(
        w.move_item_instance(wel.player_id, req.clone())
            .unwrap()
            .status,
        "accepted"
    );
    assert_eq!(
        w.move_item_instance(wel.player_id, req).unwrap().status,
        "accepted"
    );
    w.disconnect(wel.player_id, wel.epoch);
    let new = w.join(session).unwrap();
    assert_ne!(new.epoch, wel.epoch);
    assert_eq!(
        (
            w.players[&new.player_id].level,
            w.players[&new.player_id].stat_points
        ),
        (2, 2)
    );
    assert_eq!(
        w.character_state(new.player_id)
            .unwrap()
            .item_instances
            .iter()
            .filter(|i| i.def == "arcane_focus")
            .count(),
        1
    );
}
#[test]
fn recomputing_unrelated_equipment_or_stats_does_not_refill_empty_sp() {
    let (mut w, wel, _) = arena();
    w.players.get_mut(&wel.player_id).unwrap().sp = 0;
    enable(&mut w, wel.player_id);
    assert_eq!(w.players[&wel.player_id].sp, 0);
    w.players.get_mut(&wel.player_id).unwrap().stat_points = 1;
    w.stat_allocate(
        wel.player_id,
        crate::cold::StatAllocateRequest {
            stat: "str".into(),
            points: 1,
            op_id: uuid::Uuid::new_v4().to_string(),
        },
    );
    assert_eq!(w.players[&wel.player_id].sp, 0);
}

#[test]
fn full_bag_activation_is_atomic_and_access_metadata_tracks_focus() {
    let (mut w, wel, _) = arena();
    let p = w.players.get_mut(&wel.player_id).unwrap();
    for n in 0..12 {
        p.bag.insert(format!("fixture-stack-{n}"), 1);
    }
    let before = (
        p.bag.clone(),
        p.equipment.clone(),
        p.item_instances.clone(),
        p.exp,
        p.gold,
    );
    assert_eq!(
        w.mage_trial_activate(
            wel.player_id,
            TrialRequest {
                t: "mage_trial".into(),
                enabled: true,
                op_id: uuid::Uuid::new_v4().to_string()
            }
        )
        .unwrap()
        .reason,
        "inventory_full"
    );
    let p = &w.players[&wel.player_id];
    assert_eq!(
        before,
        (
            p.bag.clone(),
            p.equipment.clone(),
            p.item_instances.clone(),
            p.exp,
            p.gold
        )
    );
    assert!(!p.mage.enabled);
    w.players.get_mut(&wel.player_id).unwrap().bag.clear();
    enable(&mut w, wel.player_id);
    assert!(
        w.mage_trial_state(wel.player_id)
            .unwrap()
            .skills
            .iter()
            .all(|s| s.available)
    );
    w.players.get_mut(&wel.player_id).unwrap().sp = 0;
    assert!(
        w.mage_trial_state(wel.player_id)
            .unwrap()
            .skills
            .iter()
            .all(|s| s.available),
        "availability expresses access, not SP/cooldown"
    );
    w.players
        .get_mut(&wel.player_id)
        .unwrap()
        .equipment
        .remove("weapon");
    assert!(
        w.mage_trial_state(wel.player_id)
            .unwrap()
            .skills
            .iter()
            .all(|s| !s.available)
    );
}

#[test]
fn mage_breakdown_and_full_piece_snapshot_stay_inside_existing_cold_cap() {
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    let mut state = w.character_state(wel.player_id).unwrap();
    state.item_instances = (0..14)
        .map(|n| crate::inventory_instances::ItemInstance {
            instance_id: uuid::Uuid::new_v4().to_string(),
            def: if n == 13 {
                "arcane_focus"
            } else {
                "frontier_blade"
            }
            .into(),
            location: if n == 13 { "weapon" } else { "bag" }.into(),
            refine: 10,
        })
        .collect();
    let json = serde_json::to_string(&state).unwrap();
    assert!(
        crate::cold::encode_server_payload(&json).is_ok(),
        "full piece snapshot was {} bytes",
        json.len()
    );
    assert_eq!(state.magic_power, Some(25));
    assert_eq!(state.combat_profile.as_deref(), Some("mage_trial"));
}

#[test]
fn mage_defeat_reuses_frozen_party_pool_and_boss_mvp_receipts() {
    let (mut w, wel, _) = arena();
    let other = w.join([212; 32]).unwrap();
    {
        let p = w.players.get_mut(&other.player_id).unwrap();
        p.x = 0.0;
        p.y = 0.0;
        p.z = 0.0;
    }
    w.create_party(wel.player_id).unwrap();
    let code = w.parties.values().next().unwrap().code.clone();
    w.join_party(other.player_id, &code).unwrap();
    enable(&mut w, wel.player_id);
    w.enemy_exp.insert(w.monsters[0].kind, 100);
    w.monsters[0].hp = 1;
    w.mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::Basic));
    for _ in 0..7 {
        w.advance();
    }
    let awards = w
        .take_pending_notices()
        .into_iter()
        .filter(|(_, n)| n.key == "exp_gain")
        .collect::<Vec<_>>();
    assert_eq!(awards.len(), 2);
    assert_eq!(
        awards
            .iter()
            .map(|(_, n)| n.params["base"].as_u64().unwrap())
            .sum::<u64>(),
        110
    );
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    w.combat_roll = || 0;
    w.monsters[0].rank = crate::content::MonsterRank::Boss;
    w.monsters[0].max_hp = 25; // One actual HP of contribution exceeds the existing 3% gate.
    w.monsters[0].hp = 1;
    w.mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::Basic));
    for _ in 0..7 {
        w.advance();
    }
    assert_eq!(w.players[&wel.player_id].bag["mvp_chest"], 1);
    assert_eq!(
        w.monsters[0].contributions[&wel.player_id].damage, 1,
        "overkill is never contribution"
    );
    let before = (
        w.players[&wel.player_id].exp,
        w.players[&wel.player_id].gold,
        w.players[&wel.player_id].bag.clone(),
    );
    w.credit_boss(0);
    assert_eq!(
        before,
        (
            w.players[&wel.player_id].exp,
            w.players[&wel.player_id].gold,
            w.players[&wel.player_id].bag.clone()
        )
    );
}
#[test]
fn departed_normal_tag_owner_is_reset_before_mage_can_finish_it() {
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    let other = w.join([214; 32]).unwrap();
    w.monsters[0].tag = Some(KillTag {
        owner: other.player_id,
        members: BTreeSet::from([other.player_id]),
        last_damage_tick: 0,
    });
    w.monsters[0].hp = 1;
    w.players.get_mut(&other.player_id).unwrap().connected = false;
    let old = w.monsters[0].encounter_id;
    let reply = w
        .mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::Basic))
        .unwrap();
    assert_eq!(reply.phase, "started");
    assert_ne!(w.monsters[0].encounter_id, old);
    assert_eq!(w.monsters[0].hp, 100);
    assert!(w.monsters[0].tag.is_none());
}
#[test]
fn recovery_cross_skill_busy_evicted_intent_and_impact_visibility_are_guarded() {
    let (mut w, wel, _) = arena();
    enable(&mut w, wel.player_id);
    w.mage_cast(wel.player_id, cast(&w, &wel, 1, SkillId::StarLance));
    for _ in 0..14 {
        w.advance();
    }
    assert_eq!(
        w.mage_cast(wel.player_id, cast(&w, &wel, 2, SkillId::Basic))
            .unwrap()
            .reason,
        "busy"
    );
    for _ in 0..2 {
        w.advance();
    }
    let request = cast(&w, &wel, 3, SkillId::Basic);
    assert_eq!(
        w.mage_cast(wel.player_id, request.clone()).unwrap().phase,
        "started"
    );
    w.advance();
    w.advance();
    w.static_colliders
        .push(StaticCollider::from_center_dimensions(
            [0.0, 1.0, 1.5],
            [1.0, 2.0, 0.01],
        ));
    let before = w.monsters[0].hp;
    for _ in 0..5 {
        w.advance();
    }
    assert_eq!(w.monsters[0].hp, before);
    assert_eq!(
        w.mage_cast(wel.player_id, request.clone()).unwrap().phase,
        "cancelled"
    );
    for seq in 4..=40 {
        let mut r = cast(&w, &wel, seq, SkillId::Basic);
        r.target_id = 999999;
        w.mage_cast(wel.player_id, r);
    }
    assert_eq!(w.players[&wel.player_id].mage.recent.len(), 32);
    assert_eq!(
        w.mage_cast(wel.player_id, request).unwrap().reason,
        "stale_intent"
    );
    assert_eq!(w.monsters[0].hp, before);
}
