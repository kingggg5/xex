use super::*;
use crate::mage_trial::{
    AvailableSpell, CastRequest, CastState, PendingCast, SkillId, TrialRequest, TrialState,
};

impl World {
    pub(super) fn reset_stale_combat_tags(&mut self) {
        for monster in &mut self.monsters {
            if monster.hp > 0
                && monster.tag.as_ref().is_some_and(|tag| {
                    self.tick.saturating_sub(tag.last_damage_tick)
                        >= crate::combat_rules::TAG_IDLE_TICKS
                        || !tag.members.iter().any(|id| {
                            self.players.get(id).is_some_and(|p| {
                                p.connected
                                    && !p.down
                                    && p.hp > 0
                                    && (p.x - monster.home_x).hypot(p.z - monster.home_z)
                                        <= monster.leash
                            })
                        })
                })
            {
                monster.reset_home();
            }
        }
    }
    pub(super) fn mutate_monster_damage(
        &mut self,
        index: usize,
        player_id: u32,
        damage: u16,
        members: &BTreeSet<u32>,
        now: Instant,
    ) -> (
        bool,
        Option<(usize, u32, u8, f32, f32, u32, Option<BTreeSet<u32>>)>,
    ) {
        let monster = &mut self.monsters[index];
        let actual = u32::from(damage).min(monster.hp);
        if actual > 0 {
            monster.phase = crate::combat_rules::EncounterPhase::Engaged;
            if monster.rank == crate::content::MonsterRank::Boss {
                let c = monster.contributions.entry(player_id).or_default();
                if c.damage == 0 {
                    c.first_hit = self.tick;
                }
                c.damage = c.damage.saturating_add(u64::from(actual));
            } else {
                let tag = monster.tag.get_or_insert_with(|| KillTag {
                    owner: player_id,
                    members: members.clone(),
                    last_damage_tick: self.tick,
                });
                if tag.members.contains(&player_id) {
                    tag.last_damage_tick = self.tick;
                }
            }
        }
        monster.hp = monster.hp.saturating_sub(actual);
        let defeated = monster.hp == 0;
        let kill = if defeated {
            if self.tower.is_none() {
                monster.respawn_at = Some(
                    now + self
                        .enemy_respawn
                        .get(&monster.kind)
                        .copied()
                        .unwrap_or(Duration::from_secs(15)),
                );
            }
            monster.state = monster_state::IDLE;
            monster.state_ticks = 0;
            monster.phase = crate::combat_rules::EncounterPhase::Defeated;
            Some((
                index,
                monster.id,
                monster.kind,
                monster.x,
                monster.z,
                monster.tag.as_ref().map(|t| t.owner).unwrap_or(player_id),
                monster.tag.as_ref().map(|t| t.members.clone()),
            ))
        } else {
            None
        };
        (defeated, kill)
    }
    pub(super) fn credit_defeats(
        &mut self,
        kills: Vec<(usize, u32, u8, f32, f32, u32, Option<BTreeSet<u32>>)>,
    ) {
        for (index, id, kind, tx, tz, owner, members) in kills {
            if self.monsters[index].rank == crate::content::MonsterRank::Boss {
                self.credit_boss(index);
            } else {
                let encounter = self.monsters[index].encounter_id.to_string();
                let already = self
                    .players
                    .get(&owner)
                    .is_some_and(|p| p.reward_receipts.contains(&encounter));
                if !already {
                    self.monsters[index].rewarded = true;
                    self.credit_kill_for(owner, kind, tx, tz, id, members);
                    if let Some(p) = self.players.get_mut(&owner) {
                        p.reward_receipts.push_back(encounter);
                        while p.reward_receipts.len() > 256 {
                            p.reward_receipts.pop_front();
                        }
                    }
                }
            }
        }
        if self.tower.is_some() {
            self.tower_check_clear();
        }
    }
    fn apply_mage_damage(&mut self, id: u32, index: usize, raw: u16) -> (u16, u8) {
        let p = &self.players[&id];
        let members = p
            .party_id
            .and_then(|id| self.parties.get(&id))
            .map(|p| p.members.clone())
            .unwrap_or_else(|| BTreeSet::from([id]));
        let level = p.level;
        let m = &self.monsters[index];
        if m.rank == crate::content::MonsterRank::Boss
            && !m.contributions.contains_key(&id)
            && m.contributions.len() >= crate::combat_rules::CONTRIBUTOR_LIMIT
        {
            return (0, 0);
        }
        let miss = crate::combat_rules::miss_percent(level, u32::from(m.level));
        let missed = miss > 0 && miss > (self.combat_roll)();
        let critical = m.state == monster_state::RECOVERY || m.state == monster_state::STAGGER;
        let damage = if missed {
            0
        } else {
            (f32::from(raw) * if critical { 1.5 } else { 1.0 }).round() as u16
        };
        let (defeated, kill) =
            self.mutate_monster_damage(index, id, damage, &members, Instant::now());
        if let Some(kill) = kill {
            self.credit_defeats(vec![kill]);
        }
        (
            damage,
            if missed {
                crate::combat_rules::MISS
            } else {
                u8::from(defeated)
                    | if critical {
                        crate::combat_rules::CRIT
                    } else {
                        0
                    }
            },
        )
    }
    pub(super) fn equipment_bonus(&self, p: &Player) -> crate::cold::EquipmentBonus {
        let mut b = crate::cold::EquipmentBonus::default();
        for id in p.equipment.values() {
            if let Some(i) = self.items.get(id) {
                b.atk = b.atk.saturating_add(i.atk);
                b.def = b.def.saturating_add(i.def);
                b.max_hp = b.max_hp.saturating_add(i.hp);
            }
        }
        b.atk = b
            .atk
            .saturating_add(u16::from(p.equipment_refine.get("weapon").copied().unwrap_or(0)) * 5);
        let armor = u16::from(p.equipment_refine.get("armor").copied().unwrap_or(0));
        b.def = b.def.saturating_add(armor * 2);
        b.max_hp = b.max_hp.saturating_add(armor * 25);
        b
    }
    pub fn mage_trial_state(&self, id: u32) -> Option<TrialState> {
        let p = self.players.get(&id)?;
        let focus = p
            .equipment
            .get("weapon")
            .is_some_and(|v| v == "arcane_focus");
        let access = self.mage_capability && p.mage.enabled && focus;
        Some(TrialState {
            t: "mage_trial_state".into(),
            capability_enabled: self.mage_capability,
            profile: if p.mage.enabled {
                "mage_trial"
            } else {
                "trailblade"
            }
            .into(),
            focus_equipped: focus,
            epoch: p.epoch,
            skills: [SkillId::Basic, SkillId::StarLance]
                .into_iter()
                .map(|skill_id| {
                    let s = self.mage_config.spell(skill_id);
                    AvailableSpell {
                        skill_id,
                        range_m: s.range_m,
                        windup_ms: s.windup_ms,
                        cooldown_ms: s.cooldown_ms,
                        recovery_ms: s.recovery_ms,
                        sp_cost: s.sp_cost,
                        projectile_speed_m_s: s.projectile_speed_m_s,
                        available: access,
                        power: self.mage_config.damage(
                            skill_id,
                            self.mage_config.power(p.allocated_int, p.allocated_dex),
                        ),
                    }
                })
                .collect(),
        })
    }
    pub fn mage_trial_activate(&mut self, id: u32, r: TrialRequest) -> Option<OpResultMsg> {
        if !self.owns_character(id) {
            return Some(op_result(
                &r.op_id,
                "rejected",
                "player_unavailable",
                vec![],
            ));
        }
        if r.enabled && !self.mage_capability {
            return Some(op_result(
                &r.op_id,
                "rejected",
                "mage_trial_disabled",
                vec![],
            ));
        }
        let p = self.players.get_mut(&id)?;
        let key = format!("mage_trial:{}", r.enabled);
        if let Some(result) = replay_cached_op(&p.recent_equip_operations, &r.op_id, &key) {
            return Some(result);
        }
        if r.enabled {
            if self.storage_degraded || !p.inventory_valid || p.down {
                return Some(op_result(
                    &r.op_id,
                    "rejected",
                    "player_unavailable",
                    vec![],
                ));
            }
            // Work on copies so full bags and malformed gear never partially grant/equip.
            let mut bag = p.bag.clone();
            let mut pieces = p.item_instances.clone();
            let mut equip = p.equipment.clone();
            let mut refine = p.equipment_refine.clone();
            let mut schema = p.inventory_schema;
            let focus = pieces
                .values()
                .find(|i| i.def == "arcane_focus")
                .map(|i| i.instance_id.clone());
            if focus.is_none() {
                *bag.entry("arcane_focus".into()).or_default() += 1;
            }
            if crate::inventory_instances::reconcile(
                &p.inventory_namespace,
                &mut schema,
                &mut pieces,
                &bag,
                &equip,
                &refine,
                &p.gear_slots,
            )
            .is_err()
            {
                return Some(op_result(&r.op_id, "rejected", "bag_full", vec![]));
            }
            let focus = pieces
                .values()
                .find(|i| i.def == "arcane_focus")
                .map(|i| i.instance_id.clone())
                .expect("reconciled focus");
            if let Err(reason) = crate::inventory_instances::move_piece(
                &mut pieces,
                &mut bag,
                &mut equip,
                &mut refine,
                &p.gear_slots,
                &focus,
                "weapon",
            ) {
                return Some(op_result(&r.op_id, "rejected", reason, vec![]));
            }
            p.bag = bag;
            p.item_instances = pieces;
            p.equipment = equip;
            p.equipment_refine = refine;
            p.inventory_schema = schema;
            recompute_player_stats(
                p,
                &self.vocation,
                self.player_hp,
                &self.items,
                self.combat.attack_damage,
            );
        }
        p.mage.enabled = r.enabled;
        bump_state_revision(p);
        self.pending_state_updates.insert(id);
        let result = op_result(
            &r.op_id,
            "accepted",
            if r.enabled {
                "mage_trial_enabled"
            } else {
                "mage_trial_disabled"
            },
            vec![],
        );
        remember_op(
            &mut p.recent_equip_operations,
            r.op_id.clone(),
            key.clone(),
            &result,
        );
        if let Some(principal) = p.principal
            && !p.durable_disabled
        {
            submit_commit_op(
                &self.storage,
                &self.storage_events,
                p,
                principal,
                &self.zone_key,
                self.content_hash,
                "equip",
                &r.op_id,
                &key,
                &result,
                None,
                vec![],
            );
        }
        if !r.enabled {
            self.cancel_mage(id, "profile_disabled");
        }
        Some(result)
    }
    fn mage_origin(p: &Player) -> [f32; 3] {
        [p.x, p.y + 1.0, p.z]
    }
    fn mage_target(m: &Monster) -> [f32; 3] {
        [m.x, m.y + 0.7, m.z]
    }
    fn mage_los(&self, a: [f32; 3], b: [f32; 3]) -> bool {
        let blocked = self.static_colliders.iter().any(|v| {
            let mins = [v.min_x, v.min_y, v.min_z];
            let maxs = [v.max_x, v.max_y, v.max_z];
            let (mut lo, mut hi) = (0.0f32, 1.0f32);
            for axis in 0..3 {
                let d = b[axis] - a[axis];
                if d.abs() < 1e-7 {
                    if a[axis] < mins[axis] || a[axis] > maxs[axis] {
                        return false;
                    }
                } else {
                    let x = (mins[axis] - a[axis]) / d;
                    let y = (maxs[axis] - a[axis]) / d;
                    lo = lo.max(x.min(y));
                    hi = hi.min(x.max(y));
                    if lo > hi {
                        return false;
                    }
                }
            }
            true
        });
        !blocked
            && self
                .city_traversal
                .as_ref()
                .is_none_or(|city| city.line_is_clear(a, b))
    }
    fn mage_event(
        &self,
        id: u32,
        c: &PendingCast,
        phase: &str,
        reason: &str,
        damage: u16,
        flags: u8,
    ) -> CastState {
        CastState {
            t: "mage_cast_state".into(),
            cast_id: format!("{id}:{}:{}", c.request.epoch, c.request.sequence),
            source_id: id,
            epoch: c.request.epoch,
            sequence: c.request.sequence,
            skill_id: c.request.skill_id,
            phase: phase.into(),
            reason: reason.into(),
            server_ms: self.tick * 50,
            start_ms: c.start_tick * 50,
            release_ms: c.release_tick * 50,
            impact_ms: c.impact_tick.map(|t| t * 50),
            recovery_end_ms: c.recovery_tick * 50,
            cooldown_end_ms: c.cooldown_tick * 50,
            target_id: c.request.target_id,
            origin: c.origin,
            target: c.target,
            damage,
            flags,
        }
    }
    fn publish_mage(
        &mut self,
        id: u32,
        c: &PendingCast,
        phase: &str,
        reason: &str,
        damage: u16,
        flags: u8,
    ) {
        let event = self.mage_event(id, c, phase, reason, damage, flags);
        if let Some(p) = self.players.get_mut(&id) {
            p.mage.remember(c.request.clone(), event.clone());
        }
        let audience = self
            .players
            .iter()
            .filter(|(pid, p)| {
                (**pid != id || phase != "started")
                    && p.connected
                    && (p.x - c.origin[0]).hypot(p.z - c.origin[2]) <= 32.0
            })
            .map(|(id, _)| *id)
            .collect();
        if self.pending_mage_events.len() < MAX_PLAYERS * 4 {
            self.pending_mage_events.push((audience, event));
        }
    }
    fn cancel_mage(&mut self, id: u32, reason: &str) {
        if let Some(c) = self
            .players
            .get_mut(&id)
            .and_then(|p| p.mage.pending.take())
        {
            self.publish_mage(id, &c, "cancelled", reason, 0, 0);
        }
    }
    pub fn take_mage_events(&mut self) -> Vec<(Vec<u32>, CastState)> {
        std::mem::take(&mut self.pending_mage_events)
    }
    pub fn mage_cast(&mut self, id: u32, r: CastRequest) -> Option<CastState> {
        self.reset_stale_combat_tags();
        let p = self.players.get(&id)?;
        let origin = Self::mage_origin(p);
        let target = self
            .monsters
            .iter()
            .find(|m| m.id == r.target_id)
            .map(Self::mage_target)
            .unwrap_or(origin);
        let s = self.mage_config.spell(r.skill_id).clone();
        let c = PendingCast {
            request: r.clone(),
            encounter: uuid::Uuid::nil(),
            start_tick: self.tick,
            release_tick: self.tick + u64::from(s.windup_ms) / 50,
            impact_tick: None,
            cooldown_tick: p.mage.ready.get(&r.skill_id).copied().unwrap_or(0),
            recovery_tick: self.tick + u64::from(s.windup_ms + s.recovery_ms).div_ceil(50),
            origin,
            target,
            power: self.mage_config.power(p.allocated_int, p.allocated_dex),
            released: false,
        };
        if !self.owns_character(id) || !p.connected || p.epoch != r.epoch {
            return Some(self.mage_event(id, &c, "rejected", "stale_epoch", 0, 0));
        }
        if let Some((prior, state)) = p
            .mage
            .recent
            .iter()
            .find(|(prior, _)| prior.epoch == r.epoch && prior.sequence == r.sequence)
        {
            return Some(if prior == &r {
                state.clone()
            } else {
                self.mage_event(id, &c, "rejected", "intent_conflict", 0, 0)
            });
        }
        let reject = if !self.owns_character(id) || !p.connected || p.epoch != r.epoch {
            Some("stale_epoch")
        } else if p.hp == 0 || p.down {
            Some("dead")
        } else if !self.mage_capability || !p.mage.enabled {
            Some("not_allowed")
        } else if !p
            .equipment
            .get("weapon")
            .is_some_and(|v| v == "arcane_focus")
        {
            Some("focus_required")
        } else if p.mage.epoch == r.epoch && r.sequence <= p.mage.watermark {
            Some("stale_intent")
        } else if p.mage.pending.is_some() || self.tick < p.mage.recovery_tick {
            Some("busy")
        } else if self.tick < p.mage.ready.get(&r.skill_id).copied().unwrap_or(0) {
            Some("cooldown")
        } else if p.sp < s.sp_cost {
            Some("insufficient_sp")
        } else {
            None
        };
        if reject == Some("stale_intent") {
            return Some(self.mage_event(id, &c, "rejected", "stale_intent", 0, 0));
        }
        let p = self.players.get_mut(&id).unwrap();
        if p.mage.epoch != r.epoch {
            p.mage.epoch = r.epoch;
            p.mage.recent.clear();
        }
        p.mage.watermark = r.sequence;
        if let Some(reason) = reject {
            let event = self.mage_event(id, &c, "rejected", reason, 0, 0);
            self.players
                .get_mut(&id)
                .unwrap()
                .mage
                .remember(r, event.clone());
            return Some(event);
        }
        let index = self
            .monsters
            .iter()
            .position(|m| m.id == r.target_id && m.hp > 0 && m.respawn_at.is_none());
        let invalid = if index.is_none() {
            Some("no_target")
        } else if (origin[0] - target[0]).hypot(origin[2] - target[2]) > s.range_m {
            Some("out_of_range")
        } else if !self.mage_los(origin, target) {
            Some("blocked")
        } else {
            None
        };
        if let Some(reason) = invalid {
            let event = self.mage_event(id, &c, "rejected", reason, 0, 0);
            self.players
                .get_mut(&id)
                .unwrap()
                .mage
                .remember(r, event.clone());
            return Some(event);
        }
        let index = index.unwrap();
        if self.monsters[index].rank == crate::content::MonsterRank::Boss
            && !self.monsters[index].contributions.contains_key(&id)
            && self.monsters[index].contributions.len() >= crate::combat_rules::CONTRIBUTOR_LIMIT
        {
            let event = self.mage_event(id, &c, "rejected", "contributor_limit", 0, 0);
            self.players
                .get_mut(&id)
                .unwrap()
                .mage
                .remember(r, event.clone());
            return Some(event);
        }
        let mut c = c;
        c.encounter = self.monsters[index].encounter_id;
        c.cooldown_tick = self.tick + u64::from(s.cooldown_ms).div_ceil(50);
        let p = self.players.get_mut(&id).unwrap();
        if p.mage.epoch != r.epoch {
            p.mage.epoch = r.epoch;
            p.mage.watermark = 0;
            p.mage.recent.clear();
        }
        p.mage.watermark = r.sequence;
        p.sp -= s.sp_cost;
        p.mage.ready.insert(r.skill_id, c.cooldown_tick);
        p.mage.recovery_tick = c.recovery_tick;
        p.mage.pending = Some(c.clone());
        self.pending_state_updates.insert(id);
        let result = self.mage_event(id, &c, "started", "accepted", 0, 0);
        self.publish_mage(id, &c, "started", "accepted", 0, 0);
        Some(result)
    }
    pub(super) fn advance_mage_casts(&mut self) {
        self.reset_stale_combat_tags();
        let ids = self.players.keys().copied().collect::<Vec<_>>();
        for id in ids {
            let Some(mut c) = self
                .players
                .get_mut(&id)
                .and_then(|p| p.mage.pending.take())
            else {
                continue;
            };
            let p = &self.players[&id];
            let s = self.mage_config.spell(c.request.skill_id).clone();
            let reason = if !self.owns_character(id) || !p.connected || p.epoch != c.request.epoch {
                Some("stale_epoch")
            } else if p.hp == 0 || p.down {
                Some("dead")
            } else if !p.mage.enabled {
                Some("profile_disabled")
            } else if !c.released
                && !p
                    .equipment
                    .get("weapon")
                    .is_some_and(|v| v == "arcane_focus")
            {
                Some("focus_removed")
            } else if !c.released
                && s.cancel_on_move
                && ((p.x - c.origin[0]).hypot(p.z - c.origin[2]) > 0.01
                    || (p.y + 1.0 - c.origin[1]).abs() > 0.01)
            {
                Some("moved")
            } else {
                None
            };
            if let Some(reason) = reason {
                self.publish_mage(id, &c, "cancelled", reason, 0, 0);
                continue;
            }
            let Some(index) = self.monsters.iter().position(|m| {
                m.id == c.request.target_id
                    && m.hp > 0
                    && m.respawn_at.is_none()
                    && m.encounter_id == c.encounter
            }) else {
                self.publish_mage(id, &c, "cancelled", "target_life_changed", 0, 0);
                continue;
            };
            if !c.released && self.tick >= c.release_tick {
                c.origin = Self::mage_origin(p);
                c.target = Self::mage_target(&self.monsters[index]);
                if (c.origin[0] - c.target[0]).hypot(c.origin[2] - c.target[2]) > s.range_m
                    || !self.mage_los(c.origin, c.target)
                {
                    self.publish_mage(id, &c, "cancelled", "target_invalid", 0, 0);
                    continue;
                }
                let distance = (c.origin[0] - c.target[0])
                    .hypot(c.origin[2] - c.target[2])
                    .hypot(c.origin[1] - c.target[1]);
                c.impact_tick = Some(
                    self.tick + (distance / s.projectile_speed_m_s / 0.05).ceil().max(1.0) as u64,
                );
                c.released = true;
                self.publish_mage(id, &c, "released", "released", 0, 0);
            }
            if c.released && self.tick >= c.impact_tick.unwrap() {
                c.target = Self::mage_target(&self.monsters[index]);
                if (c.origin[0] - c.target[0]).hypot(c.origin[2] - c.target[2]) > s.range_m
                    || !self.mage_los(c.origin, c.target)
                {
                    self.publish_mage(id, &c, "cancelled", "target_invalid", 0, 0);
                    continue;
                }
                if self.monsters[index].rank == crate::content::MonsterRank::Boss
                    && !self.monsters[index].contributions.contains_key(&id)
                    && self.monsters[index].contributions.len()
                        >= crate::combat_rules::CONTRIBUTOR_LIMIT
                {
                    self.publish_mage(id, &c, "cancelled", "contributor_limit", 0, 0);
                    continue;
                }
                let damage = self.mage_config.damage(c.request.skill_id, c.power);
                let (damage, flags) = self.apply_mage_damage(id, index, damage);
                self.publish_mage(
                    id,
                    &c,
                    "impact",
                    if flags & crate::combat_rules::MISS != 0 {
                        "miss"
                    } else {
                        "confirmed"
                    },
                    damage,
                    flags,
                );
            } else {
                self.players.get_mut(&id).unwrap().mage.pending = Some(c);
            }
        }
    }
}
