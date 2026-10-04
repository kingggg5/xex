use super::*;

fn world() -> World {World::new(&crate::content::test_content(),crate::character::CharacterStore::shared())}
fn join(world:&mut World, n:u8) -> Welcome {world.join([n;32]).unwrap()}
fn return_request(revision:u32,n:u8) -> crate::cold::ReturnToTownRequest {
    crate::cold::ReturnToTownRequest {t:"return_to_town".into(),death_revision:revision,op_id:format!("00000000-0000-4000-8000-{n:012x}")}
}

#[test]
fn expired_monsters_respawn_at_home_with_reset_state() {
    let mut w=world();let home=(w.monsters[0].home_x,w.monsters[0].home_z);
    let m=&mut w.monsters[0];m.x=25.0;m.z=-10.0;m.hp=0;m.respawn_at=Some(Instant::now());m.target_player_id=Some(1);
    w.advance();assert_eq!((w.monsters[0].x,w.monsters[0].z),home);
    assert_eq!(w.monsters[0].hp,w.monsters[0].max_hp);assert_eq!(w.monsters[0].target_player_id,None);
}
#[test]
fn party_exp_is_one_pool_and_checks_level_distance_boundaries() {
    let mut w=world();let a=join(&mut w,1);let b=join(&mut w,2);let c=join(&mut w,3);let d=join(&mut w,4);
    w.create_party(a.player_id).unwrap();let code=w.parties.values().next().unwrap().code.clone();
    for id in [b.player_id,c.player_id,d.player_id] {w.join_party(id,&code).unwrap();}
    for p in w.players.values_mut() {p.x=0.0;p.z=0.0;p.exp=0;p.job_exp=0;}
    w.enemy_exp.insert(1,100);w.credit_kill(a.player_id,1,0.0,0.0);
    // Base EXP may carry through a level-up; notices record the actual conserved awards.
    let notices=w.take_pending_notices();assert_eq!(notices.iter().filter(|(_,n)|n.key=="exp_gain").map(|(_,n)|n.params["base"].as_u64().unwrap()).sum::<u64>(),130);
    w.players.get_mut(&b.player_id).unwrap().level=w.players[&a.player_id].level+15;
    w.players.get_mut(&c.player_id).unwrap().level=w.players[&a.player_id].level+16;
    w.players.get_mut(&b.player_id).unwrap().x=30.0;
    w.players.get_mut(&d.player_id).unwrap().x=30.001;
    assert_eq!(w.eligible_party_members(a.player_id,0.0,0.0),vec![a.player_id,b.player_id]);
}
#[test]
fn local_monster_movement_respects_blockers() {
    let mut w=world();let a=join(&mut w,1);
    w.static_colliders=vec![StaticCollider::from_center_dimensions([1.0,1.0,0.0],[0.5,2.0,10.0])];
    let p=w.players.get_mut(&a.player_id).unwrap();p.x=4.0;p.z=0.0;
    let m=&mut w.monsters[0];m.x=0.0;m.z=0.0;m.home_x=0.0;m.home_z=0.0;m.state=monster_state::APPROACH;m.target_player_id=Some(a.player_id);m.ability_cooldown_ticks=1000;
    for _ in 0..50 {w.update_monsters();}
    assert!(w.monsters[0].x<=0.75-w.player_radius+0.001);
}
#[test]
fn outsider_finishing_hit_pays_tag_owner_and_cannot_refresh_tag() {
    let mut w=world();let a=join(&mut w,1);let b=join(&mut w,2);
    for m in &mut w.monsters {m.hp=0;}
    let m=&mut w.monsters[0];m.hp=1;m.x=0.0;m.z=1.0;m.home_x=0.0;m.home_z=1.0;m.tag=Some(KillTag {owner:a.player_id,members:BTreeSet::from([a.player_id]),last_damage_tick:0});
    for p in w.players.values_mut() {p.x=0.0;p.z=0.0;p.exp=0;}
    let outcome=w.apply_action(b.player_id,b.epoch,1,ActionKind::Attack,0.0,0,0);
    assert!(outcome.accepted);assert!(w.players[&a.player_id].exp>0);assert_eq!(w.players[&b.player_id].exp,0);
    assert_eq!(w.monsters[0].tag.as_ref().unwrap().last_damage_tick,0);
}
#[test]
fn owner_inactivity_releases_tag_and_resets_contributions() {
    let mut w=world();let a=join(&mut w,1);let m=&mut w.monsters[0];m.hp=1;m.tag=Some(KillTag {owner:a.player_id,members:BTreeSet::from([a.player_id]),last_damage_tick:0});
    w.tick=200;w.update_monsters();assert!(w.monsters[0].tag.is_none());assert_eq!(w.monsters[0].hp,w.monsters[0].max_hp);
}
#[test]
fn large_level_gap_miss_spends_action_without_damage_or_crit() {
    let mut w=world();let a=join(&mut w,1);for m in &mut w.monsters {m.hp=0;}
    let m=&mut w.monsters[0];m.hp=100000;m.max_hp=100000;m.level=20;m.x=0.0;m.z=1.0;
    let p=w.players.get_mut(&a.player_id).unwrap();p.x=0.0;p.z=0.0;
    w.combat_roll=||0;let result=w.apply_action(a.player_id,a.epoch,1,ActionKind::Attack,0.0,0,0);
    assert!(result.accepted);assert_eq!(w.monsters[0].hp,100000);
    let event=&w.recent_events.back().unwrap().0;assert_eq!(event.flags,crate::combat_rules::MISS);assert_eq!(event.damage,0);
}
#[test]
fn boss_personal_rolls_mvp_bonus_and_receipt_are_once_only() {
    let mut w=world();let a=join(&mut w,1);let b=join(&mut w,2);
    w.combat_roll=||0;let m=&mut w.monsters[0];m.rank=crate::content::MonsterRank::Boss;m.hp=0;m.max_hp=10000;
    m.contributions.insert(a.player_id,crate::combat_rules::Contribution {damage:6000,first_hit:1,..Default::default()});
    m.contributions.insert(b.player_id,crate::combat_rules::Contribution {damage:4000,first_hit:2,..Default::default()});
    let before=w.players[&a.player_id].bag.get("trail_potion").copied().unwrap_or(0);
    w.credit_boss(0);assert_eq!(w.players[&a.player_id].bag["mvp_chest"],1);
    assert_eq!(w.players[&a.player_id].bag["trail_potion"],before+2);
    let exp=w.players[&a.player_id].exp;w.credit_boss(0);assert_eq!(w.players[&a.player_id].exp,exp);assert_eq!(w.players[&a.player_id].bag["mvp_chest"],1);
}
#[test]
fn full_bag_mailbox_claim_is_atomic_and_idempotent() {
    let mut w=world();let a=join(&mut w,1);let receipt=uuid::Uuid::new_v4().to_string();
    let p=w.players.get_mut(&a.player_id).unwrap();p.bag=(0..12).map(|i|(format!("full_{i}"),1)).collect();p.reward_mail.insert(receipt.clone(),BTreeMap::from([("mvp_chest".into(),1)]));
    let req=crate::cold::ClaimRewardRequest {t:"claim_reward".into(),op_id:uuid::Uuid::new_v4().to_string(),receipt_id:receipt.clone()};
    assert_eq!(w.claim_reward(a.player_id,req.clone()).unwrap().reason,"inventory_full");assert!(w.players[&a.player_id].reward_mail.contains_key(&receipt));
    w.players.get_mut(&a.player_id).unwrap().bag.clear();let req=crate::cold::ClaimRewardRequest {op_id:uuid::Uuid::new_v4().to_string(),..req};
    assert_eq!(w.claim_reward(a.player_id,req.clone()).unwrap().status,"accepted");assert_eq!(w.claim_reward(a.player_id,req).unwrap().status,"accepted");assert_eq!(w.players[&a.player_id].bag["mvp_chest"],1);
}
#[test]
fn free_manual_return_replays_and_rejects_stale_death_cycles() {
    let mut w=world();let a=join(&mut w,1);let p=w.players.get_mut(&a.player_id).unwrap();p.down=true;p.hp=0;p.gold=0;p.death_revision=1;
    for _ in 0..110 {w.advance();}assert!(w.players[&a.player_id].down);
    assert_eq!(w.return_to_town(a.player_id,return_request(2,1)).unwrap().reason,"stale_death_state");
    let req=return_request(1,2);assert_eq!(w.return_to_town(a.player_id,req.clone()).unwrap().status,"accepted");
    let position=(w.players[&a.player_id].x,w.players[&a.player_id].z);assert_eq!(w.players[&a.player_id].gold,0);assert!(!w.players[&a.player_id].down);
    assert_eq!(w.return_to_town(a.player_id,req).unwrap().status,"accepted");assert_eq!((w.players[&a.player_id].x,w.players[&a.player_id].z),position);
    let p=w.players.get_mut(&a.player_id).unwrap();p.down=true;p.hp=0;p.death_revision=2;
    assert_eq!(w.return_to_town(a.player_id,return_request(1,3)).unwrap().reason,"stale_death_state");assert!(w.players[&a.player_id].down);
}
#[test]
fn death_and_mail_fields_round_trip_old_record_defaults() {
    let mut w=world();let a=join(&mut w,1);let p=w.players.get_mut(&a.player_id).unwrap();p.down=true;p.death_revision=9;
    let record=character_record_of(p);let bytes=serde_json::to_vec(&record).unwrap();let decoded:CharacterRecord=serde_json::from_slice(&bytes).unwrap();assert!(decoded.down);assert_eq!(decoded.death_revision,9);
}

#[test]
fn mvp_chest_pity_updates_once_and_resets_on_a_rune() {
    let mut w=world();let a=join(&mut w,1);
    w.players.get_mut(&a.player_id).unwrap().bag.insert("mvp_chest".into(),2);
    w.rune_roll=||Some(9999);
    let request=BoxOpenRequest {item:"mvp_chest".into(),op_id:uuid::Uuid::new_v4().to_string()};
    assert_eq!(w.box_open(a.player_id,request.clone()).unwrap().status,"accepted");
    assert_eq!(w.players[&a.player_id].mvp_rune_pity,1);
    w.box_open(a.player_id,request).unwrap();assert_eq!(w.players[&a.player_id].mvp_rune_pity,1);
    w.rune_roll=||Some(0);
    let result=w.box_open(a.player_id,BoxOpenRequest {item:"mvp_chest".into(),op_id:uuid::Uuid::new_v4().to_string()}).unwrap();
    assert!(result.grants.iter().any(|g|g.def=="sunmeadow_rune"));assert_eq!(w.players[&a.player_id].mvp_rune_pity,0);
}

fn move_request(w:&World,id:u32,piece:&str,to:&str)->crate::cold::MoveItemInstanceRequest {
    crate::cold::MoveItemInstanceRequest {t:"move_item_instance".into(),op_id:uuid::Uuid::new_v4().to_string(),instance_id:piece.into(),expected_revision:w.players[&id].state_revision,to:to.into()}
}
#[test]
fn precise_moves_refinement_and_payload_replay_survive_swaps() {
    let mut w=world();let id=join(&mut w,1).player_id;
    let p=w.players.get_mut(&id).unwrap();p.bag.insert("frontier_blade".into(),2);p.gold=1000;bump_state_revision(p);
    let ids=w.players[&id].item_instances.keys().cloned().collect::<Vec<_>>();assert_eq!(ids.len(),2);
    assert_eq!(w.equip_item(id,crate::cold::EquipItemRequest {item:"frontier_blade".into(),op_id:uuid::Uuid::new_v4().to_string()}).unwrap().reason,"instance_required");
    let first=move_request(&w,id,&ids[0],"weapon");assert_eq!(w.move_item_instance(id,first.clone()).unwrap().status,"accepted");
    let refine=crate::cold::RefineItemRequest {slot:"weapon".into(),op_id:uuid::Uuid::new_v4().to_string(),instance_id:Some(ids[0].clone()),expected_revision:Some(w.players[&id].state_revision)};
    let delayed=crate::cold::RefineItemRequest {op_id:uuid::Uuid::new_v4().to_string(),..refine.clone()};
    assert_eq!(w.refine_item(id,refine.clone()).unwrap().status,"accepted");let gold=w.players[&id].gold;
    let second=move_request(&w,id,&ids[1],"weapon");assert_eq!(w.move_item_instance(id,second).unwrap().status,"accepted");
    assert_eq!(w.refine_item(id,delayed).unwrap().reason,"stale_revision");assert_eq!(w.players[&id].gold,gold);
    let wrong=crate::cold::RefineItemRequest {op_id:uuid::Uuid::new_v4().to_string(),expected_revision:Some(w.players[&id].state_revision),..refine.clone()};
    assert_eq!(w.refine_item(id,wrong).unwrap().reason,"wrong_slot");assert_eq!(w.players[&id].gold,gold);
    assert_eq!(w.refine_item(id,refine).unwrap().status,"accepted");assert_eq!(w.players[&id].gold,gold);
    assert_eq!(w.players[&id].item_instances[&ids[0]].refine,1);assert_eq!(w.players[&id].item_instances[&ids[0]].location,"bag");assert_eq!(w.players[&id].equipment_refine["weapon"],0);
    assert_eq!(w.move_item_instance(id,first.clone()).unwrap().status,"accepted");assert_eq!(w.players[&id].item_instances[&ids[1]].location,"weapon");
    let changed=crate::cold::MoveItemInstanceRequest {to:"bag".into(),..first};assert_eq!(w.move_item_instance(id,changed).unwrap().reason,"op_id_conflict");
    let foreign=move_request(&w,id,&uuid::Uuid::new_v4().to_string(),"weapon");let before=character_record_of(&w.players[&id]);assert_eq!(w.move_item_instance(id,foreign).unwrap().reason,"not_owned");assert_eq!(w.players[&id].item_instances,before.item_instances);
}
#[test]
fn migration_overflow_rejects_join_and_preserves_saved_gear() {
    let mut w=world();let session=[8;32];let mut record=w.seed_character_record();record.bag.insert("frontier_blade".into(),15);w.store.save(session,&mut record);
    assert!(matches!(w.join(session),Err("inventory_unavailable")));let after=w.store.load_or_seed(session,||panic!("record already exists"));assert_eq!(after.bag["frontier_blade"],15);assert_eq!(after.inventory_schema,0);assert!(after.item_instances.is_empty());assert!(!w.sessions.contains_key(&session));
}
#[test]
fn character_and_piece_identity_are_stable_across_room_and_record_round_trip() {
    let content=crate::content::test_content();let store=crate::character::CharacterStore::shared();let mut a=World::new(&content,store.clone());let session=[11;32];let id=a.join(session).unwrap().player_id;
    let p=a.players.get_mut(&id).unwrap();p.bag.insert("frontier_blade".into(),2);bump_state_revision(p);let original=a.character_state(id).unwrap();a.push_store(id);
    let stored=store.load_or_seed(session,||panic!("record already exists"));let decoded:CharacterRecord=serde_json::from_slice(&serde_json::to_vec(&stored).unwrap()).unwrap();assert_eq!(decoded.item_instances,stored.item_instances);
    let mut b=World::new(&content,store);let other=b.join(session).unwrap().player_id;let next=b.character_state(other).unwrap();assert_eq!(original.character_id,next.character_id);assert_eq!(original.item_instances,next.item_instances);assert!(uuid::Uuid::parse_str(&next.character_id).is_ok());assert!(!next.character_id.contains(&"0b".repeat(16)));
    let fresh=b.join([12;32]).unwrap().player_id;assert_ne!(next.character_id,b.character_state(fresh).unwrap().character_id);
}
#[test]
fn maximum_inventory_character_state_stays_within_cold_envelope() {
    let mut w=world();let id=join(&mut w,1).player_id;let p=w.players.get_mut(&id).unwrap();
    p.bag.clear();p.bag.insert("frontier_blade".into(),6);p.bag.insert("frontier_vest".into(),6);p.equipment=BTreeMap::from([("weapon".into(),"frontier_blade".into()),("armor".into(),"frontier_vest".into())]);p.inventory_schema=0;
    for n in 0..10 {p.bag.insert(format!("{:0<64}",n),99);}p.pouch=BTreeMap::from([("dew_bead".into(),u32::MAX)]);p.name="ช".repeat(32);p.gold=u32::MAX;p.coin=u32::MAX;p.level=u32::MAX;p.exp=u32::MAX;p.job_level=u32::MAX;p.job_exp=u32::MAX;p.stat_points=u32::MAX;p.owned_cosmetics=BTreeSet::from(["skin_crimson","skin_verdant","skin_sand","skin_gold","skin_rose","pet_sprout"].map(String::from));bump_state_revision(p);
    let state=w.character_state(id).unwrap();assert_eq!(state.item_instances.len(),14);assert_eq!(state.bag.len(),12);let json=serde_json::to_string(&state).unwrap();assert!(json.len()<=crate::cold::MAX_COLD_SERVER_BYTES,"{} bytes",json.len());assert!(crate::cold::encode_server_payload(&json).is_ok());
}
#[test]
fn full_instance_capacity_does_not_consume_mail_or_charge_purchase() {
    let mut w=world();let id=join(&mut w,1).player_id;let p=w.players.get_mut(&id).unwrap();p.bag.insert("frontier_blade".into(),14);p.gold=10000;bump_state_revision(p);assert!(p.inventory_valid);
    let receipt=uuid::Uuid::new_v4().to_string();p.reward_mail.insert(receipt.clone(),BTreeMap::from([("frontier_vest".into(),1)]));let before=character_record_of(p);
    let request=crate::cold::ClaimRewardRequest {t:"claim_reward".into(),op_id:uuid::Uuid::new_v4().to_string(),receipt_id:receipt.clone()};assert_eq!(w.claim_reward(id,request).unwrap().reason,"inventory_full");assert!(w.players[&id].reward_mail.contains_key(&receipt));assert_eq!(w.players[&id].bag,before.bag);assert_eq!(w.players[&id].item_instances,before.item_instances);
}
#[test]
fn boss_mailbox_and_storage_retries_keep_frozen_once_only_rewards() {
    let mut w=world();let a=join(&mut w,1);let b=join(&mut w,2);w.combat_roll=||0;
    let m=&mut w.monsters[0];m.rank=crate::content::MonsterRank::Boss;m.hp=0;m.max_hp=10000;m.contributions=BTreeMap::from([(a.player_id,crate::combat_rules::Contribution {damage:6000,first_hit:1,..Default::default()}),(b.player_id,crate::combat_rules::Contribution {damage:4000,first_hit:2,..Default::default()})]);
    let p=w.players.get_mut(&a.player_id).unwrap();p.bag=(0..12).map(|n|(format!("full_{n}"),1)).collect();p.reward_mail=(0..256).map(|_|(uuid::Uuid::new_v4().to_string(),BTreeMap::from([("trail_potion".into(),1)]))).collect();
    w.storage_degraded=true;w.credit_boss(0);assert!(w.monsters[0].reward_prepared);assert_eq!(w.monsters[0].pending_rewards.len(),2);assert!(w.players[&b.player_id].reward_receipts.is_empty());
    w.storage_degraded=false;w.credit_boss(0);assert_eq!(w.monsters[0].pending_rewards.len(),1);let other_exp=w.players[&b.player_id].exp;assert!(!w.monsters[0].rewarded);
    w.players.get_mut(&a.player_id).unwrap().bag.clear();w.combat_roll=||99;w.credit_boss(0);assert!(w.monsters[0].rewarded);assert_eq!(w.players[&a.player_id].bag["mvp_chest"],1);assert_eq!(w.players[&b.player_id].exp,other_exp);assert_eq!(w.players[&a.player_id].bag["trail_potion"],2);
    w.credit_boss(0);assert_eq!(w.players[&a.player_id].bag["mvp_chest"],1);
}
#[test]
fn first_damage_party_remains_the_credit_anchor_after_party_membership_changes() {
    let mut w=world();let a=join(&mut w,1);let b=join(&mut w,2);let outsider=join(&mut w,3);
    w.create_party(a.player_id).unwrap();let code=w.parties.values().next().unwrap().code.clone();w.join_party(b.player_id,&code).unwrap();
    for p in w.players.values_mut() {p.x=0.0;p.z=0.0;p.exp=0;}
    w.leave_party(a.player_id).unwrap();let members=BTreeSet::from([a.player_id,b.player_id]);w.credit_kill_for(a.player_id,1,0.0,0.0,1,Some(members));
    assert!(w.players[&a.player_id].exp>0);assert!(w.players[&b.player_id].exp>0);assert_eq!(w.players[&outsider.player_id].exp,0);
}
#[test]
fn shared_return_state_cannot_resume_a_stale_zero_hp_ko_player() {
    let mut w=world();let id=join(&mut w,1).player_id;let p=w.players.get_mut(&id).unwrap();p.down=true;p.hp=0;p.death_revision=1;let mut record=character_record_of(p);record.down=false;apply_character_record(p,&record);assert!(!p.down);assert!(p.hp>0);
}
#[test]
fn owner_death_releases_the_tag_before_a_command_finishing_hit() {
    let mut w=world();let a=join(&mut w,1);let b=join(&mut w,2);for m in &mut w.monsters {m.hp=0;}
    let m=&mut w.monsters[0];m.hp=1;m.max_hp=1;m.x=0.0;m.z=1.0;m.home_x=0.0;m.home_z=1.0;m.tag=Some(KillTag {owner:a.player_id,members:BTreeSet::from([a.player_id]),last_damage_tick:0});
    for p in w.players.values_mut() {p.x=0.0;p.z=0.0;p.exp=0;}let p=w.players.get_mut(&a.player_id).unwrap();p.down=true;p.hp=0;
    assert!(w.apply_action(b.player_id,b.epoch,1,ActionKind::Attack,0.0,0,0).accepted);assert_eq!(w.players[&a.player_id].exp,0);assert!(w.players[&b.player_id].exp>0);
}
