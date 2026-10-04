use super::*;
use crate::community::{self, Action, Device, Offer};
use crate::storage::ExchangeCommit;

#[derive(Debug, Clone)]
struct Trade {
    id: String,
    members: [u32; 2],
    revision: u32,
    accepted: bool,
    offers: [Offer; 2],
    confirmed: [bool; 2],
    expires: u64,
    pending: Option<ExchangeCommit>,
    queued: bool,
    retry_tick: u64,
}
#[derive(Default)]
pub(super) struct Runtime {
    trades: BTreeMap<String, Trade>,
    enabled: BTreeSet<u32>,
    pub dirty: BTreeSet<u32>,
}
impl Runtime {
    pub fn busy(&self, player: u32) -> bool {
        self.trades
            .values()
            .any(|t| t.members.contains(&player) && t.pending.is_some())
    }
}

impl World {
    pub fn owns_character(&self, id: u32) -> bool {
        self.players
            .get(&id)
            .is_some_and(|p| !p.durable_disabled && self.store.owns(p.session_id, self.store_owner))
    }
    pub fn community_busy(&self, id: u32) -> bool {
        self.community_runtime.busy(id)
    }
    fn community_notice(&mut self, id: u32, key: &str) {
        self.pending_notices.push((
            id,
            crate::cold::NoticeMsg {
                t: "notice".into(),
                key: "community_result".into(),
                params: serde_json::json!({"reason":key}),
            },
        ));
        self.community_runtime.dirty.insert(id);
    }
    pub fn community_error(&mut self, id: u32, key: &str) {
        self.community_notice(id, key);
    }
    pub fn community_sync(&mut self, id: u32) {
        self.community_runtime.dirty.insert(id);
    }
    pub(super) fn community_forget(&mut self,id:u32) {
        self.community_runtime.enabled.remove(&id);
        self.community_runtime.dirty.remove(&id);
    }
    pub fn player_device(&self, id: u32) -> Device {
        self.players.get(&id).map_or(Device::Unknown, |p| p.device)
    }
    pub fn community_snapshot(&self, id: u32) -> Option<crate::cold::NoticeMsg> {
        let p = self.players.get(&id)?;
        let trade=self.community_runtime.trades.values().find(|t|t.members.contains(&id)).map(|t| {
            let side=usize::from(t.members[1]==id);
            let peer=self.players.get(&t.members[1-side]);
            serde_json::json!({"id":t.id,"revision":t.revision,"accepted":t.accepted,"incoming":side==1,"peer":peer.map(|p|p.name.as_str()).unwrap_or("Traveler"),"peer_device":peer.map(|p|p.device).unwrap_or_default(),"mine":t.offers[side],"theirs":t.offers[1-side],"confirmed":t.confirmed[side],"peer_confirmed":t.confirmed[1-side],"pending":t.pending.is_some()})
        });
        let mut nearby: Vec<_> = self
            .players
            .values()
            .filter(|other| other.connected && other.id != id)
            .map(|other| ((other.x - p.x).powi(2) + (other.z - p.z).powi(2), other))
            .collect();
        nearby.sort_by(|a, b| a.0.total_cmp(&b.0));
        let players:Vec<_>=nearby.into_iter().take(12).map(|(distance,other)|serde_json::json!({"handle":other.handle,"name":other.name,"device":other.device,"nearby":distance<=144.0 && (other.y-p.y).abs()<=3.0})).collect();
        let items: Vec<_> = p
            .bag
            .iter()
            .filter(|(id, n)| {
                **n > 0
                    && self.trade_carry().contains_key(*id)
                    && !p.equipment.values().any(|eq| eq == *id)
            })
            .take(12)
            .map(|(id, n)| serde_json::json!({"id":id,"count":n}))
            .collect();
        let mut message = crate::cold::NoticeMsg {
            t: "notice".into(),
            key: "community_state".into(),
            params: serde_json::json!({
                "season":community::SEASON,"xp":p.community.xp,"tiers":community::TIERS,"xp_per_tier":community::XP_PER_TIER,
                "rewards":(1..=community::TIERS).map(|tier|(tier,community::reward_gold(tier,false),community::reward_gold(tier,true))).collect::<Vec<_>>(),
                "packs":community::TOPUP_PACKS,
                "premium":p.community.premium,"free_claims":p.community.free_claims,"premium_claims":p.community.premium_claims,
                "test_credits":p.community.test_credits,"test_enabled":test_enabled(),"premium_test_cost":community::PREMIUM_TEST_COST,
                "orders":p.community.test_orders.iter().rev().take(5).collect::<Vec<_>>(),"order_count":p.community.test_orders.len(),
                "gold":p.gold,"items":items,"players":players,"trade":trade,"durable":self.storage.is_live()
            }),
        };
        // Full trade terms and inventory take priority over distant roster rows.
        while serde_json::to_vec(&message).ok()?.len() > crate::cold::MAX_COLD_SERVER_BYTES {
            if message
                .params
                .get_mut("players")?
                .as_array_mut()?
                .pop()
                .is_none()
            {
                return None;
            }
        }
        Some(message)
    }
    pub fn community_action(&mut self, id: u32, action: Action) {
        if !self.owns_character(id) {
            self.community_notice(id, "player_unavailable");
            return;
        }
        if !self.players.get(&id).is_some_and(|p| p.connected) {
            return;
        }
        if let Action::Sync { device } = action {
            self.community_runtime.enabled.insert(id);
            let p = self.players.get_mut(&id).unwrap();
            let changed = p.device != device;
            p.device = device;
            if changed {
                self.community_runtime
                    .dirty
                    .extend(self.players.keys().copied());
            } else {
                self.community_runtime.dirty.insert(id);
            }
            return;
        }
        if self.community_busy(id) {
            self.community_notice(id, "trade_committing");
            return;
        }
        if let Some((op, key)) = action.operation() {
            let p = &self.players[&id];
            if p.durable_disabled || self.storage_degraded {
                self.community_notice(id, "storage_pending");
                return;
            }
            if let Some(previous) = p.community.operations.get(&op) {
                self.community_notice(
                    id,
                    if previous == &key {
                        "accepted"
                    } else {
                        "operation_conflict"
                    },
                );
                return;
            }
            if p.community.operations.len() >= 128 {
                self.community_notice(id, "test_order_limit");
                return;
            }
        }
        let result = self.apply_community(id, action);
        match result {
            Ok(()) => self.community_notice(id, "accepted"),
            Err(reason) => self.community_notice(id, reason),
        }
    }
    fn apply_community(&mut self, id: u32, action: Action) -> Result<(), &'static str> {
        let operation = action.operation();
        match action {
            Action::Invite { handle } => {
                let peer = self
                    .players
                    .values()
                    .find(|p| p.handle == handle && p.connected)
                    .ok_or("player_unavailable")?
                    .id;
                if peer == id {
                    return Err("cannot_trade_self");
                }
                if self
                    .community_runtime
                    .trades
                    .values()
                    .any(|t| t.members.contains(&id) || t.members.contains(&peer))
                {
                    return Err("trade_busy");
                }
                if !self.trade_near([id, peer]) {
                    return Err("out_of_range");
                }
                if self.community_runtime.trades.len() >= 25 {
                    return Err("trade_busy");
                }
                let trade = Trade {
                    id: uuid::Uuid::new_v4().to_string(),
                    members: [id, peer],
                    revision: 1,
                    accepted: false,
                    offers: Default::default(),
                    confirmed: [false; 2],
                    expires: self.tick + 2400,
                    pending: None,
                    queued: false,
                    retry_tick: 0,
                };
                self.community_runtime
                    .trades
                    .insert(trade.id.clone(), trade);
                self.community_notice(peer, "trade_invited");
            }
            Action::Cancel { trade } => {
                let t = self
                    .community_runtime
                    .trades
                    .get(&trade)
                    .ok_or("trade_expired")?;
                if !t.members.contains(&id) {
                    return Err("not_your_trade");
                }
                let members = t.members;
                self.community_runtime.trades.remove(&trade);
                for member in members {
                    self.community_notice(member, "trade_cancelled");
                }
            }
            Action::Accept { trade, revision } => {
                let t = self.trade_mut(id, &trade, revision)?;
                if t.members[1] != id || t.accepted {
                    return Err("invalid_trade_step");
                }
                t.accepted = true;
                t.revision += 1;
                t.confirmed = [false; 2];
                let members = t.members;
                self.community_runtime.dirty.extend(members);
            }
            Action::Offer {
                trade,
                revision,
                offer,
            } => {
                let t = self
                    .community_runtime
                    .trades
                    .get(&trade)
                    .ok_or("trade_expired")?;
                if !t.accepted {
                    return Err("accept_trade_first");
                }
                let members = t.members;
                if !self.trade_near(members) {
                    return Err("out_of_range");
                }
                let p = self.players.get(&id).ok_or("player_unavailable")?;
                // Check ownership before publishing the new proposal.
                community::exchange(
                    &character_record_of(p),
                    &CharacterRecord::default(),
                    &offer,
                    &Offer::default(),
                    &self.trade_carry(),
                    &self.players[&id].gear_slots,
                )?;
                let expires = self.tick + 2400;
                let t = self.trade_mut(id, &trade, revision)?;
                let side = usize::from(t.members[1] == id);
                t.offers[side] = offer;
                t.confirmed = [false; 2];
                t.revision += 1;
                t.expires = expires;
                self.community_runtime.dirty.extend(members);
            }
            Action::Confirm { trade, revision } => {
                let members = self
                    .community_runtime
                    .trades
                    .get(&trade)
                    .ok_or("trade_expired")?
                    .members;
                if !self.trade_near(members) {
                    return Err("out_of_range");
                }
                let t = self.trade_mut(id, &trade, revision)?;
                if !t.accepted {
                    return Err("accept_trade_first");
                }
                t.confirmed[usize::from(t.members[1] == id)] = true;
                self.community_runtime.dirty.extend(members);
                if self.community_runtime.trades[&trade].confirmed == [true, true] {
                    if let Err(reason) = self.commit_trade(&trade) {
                        if let Some(t) = self.community_runtime.trades.get_mut(&trade) {
                            t.confirmed = [false; 2];
                            t.revision += 1;
                        }
                        for member in members {
                            self.community_notice(member, reason);
                        }
                        return Err(reason);
                    }
                }
            }
            Action::PassClaim {
                season,
                tier,
                premium,
                op_id,
            } => {
                if season != community::SEASON {
                    return Err("season_expired");
                }
                if self.storage_degraded {
                    return Err("storage_pending");
                }
                let p = self.players.get_mut(&id).unwrap();
                let mut next = p.community.clone();
                let gold = community::claim(&mut next, tier, premium)?;
                p.gold = p
                    .gold
                    .checked_add(gold)
                    .filter(|v| *v <= i32::MAX as u32)
                    .ok_or("wallet_full")?;
                p.community = next;
                p.state_revision = p.state_revision.wrapping_add(1).max(1);
                if let Some((id, key)) = &operation {
                    p.community.operations.insert(id.clone(), key.clone());
                }
                if let Some(principal) = p.principal.filter(|_| !p.durable_disabled) {
                    let result = OpResultMsg {
                        t: "op_result".into(),
                        op_id: op_id.clone(),
                        status: "accepted".into(),
                        reason: "pass_claimed".into(),
                        ends_at_ms: 0,
                        grants: vec![],
                    };
                    submit_commit_op(
                        &self.storage,
                        &self.storage_events,
                        p,
                        principal,
                        &self.zone_key,
                        self.content_hash,
                        "battle_pass",
                        &op_id,
                        &format!("{season}:{tier}:{premium}"),
                        &result,
                        Some((format!("pass_{tier}_{premium}"), season)),
                        vec![],
                    );
                }
                self.pending_state_updates.insert(id);
                self.push_store(id);
            }
            Action::PassPremium { season, .. } => {
                if !test_enabled() {
                    return Err("test_disabled");
                }
                if season != community::SEASON {
                    return Err("season_expired");
                }
                let p = self.players.get_mut(&id).unwrap();
                if p.community.premium {
                    return Ok(());
                }
                if p.community.test_credits < community::PREMIUM_TEST_COST {
                    return Err("not_enough_test_credits");
                }
                p.community.test_credits -= community::PREMIUM_TEST_COST;
                p.community.premium = true;
                if let Some((id, key)) = &operation {
                    p.community.operations.insert(id.clone(), key.clone());
                }
                p.state_revision = p.state_revision.wrapping_add(1).max(1);
                self.push_store(id);
            }
            Action::TestTopup { pack, op_id } => {
                if !test_enabled() {
                    return Err("test_disabled");
                }
                let p = self.players.get_mut(&id).unwrap();
                community::test_topup(&mut p.community, &pack, &op_id)?;
                if let Some((id, key)) = &operation {
                    p.community.operations.insert(id.clone(), key.clone());
                }
                p.state_revision = p.state_revision.wrapping_add(1).max(1);
                self.push_store(id);
            }
            Action::Sync { .. } | Action::Megaphone { .. } => {}
        }
        Ok(())
    }
    fn trade_mut(&mut self, id: u32, key: &str, revision: u32) -> Result<&mut Trade, &'static str> {
        let t = self
            .community_runtime
            .trades
            .get_mut(key)
            .ok_or("trade_expired")?;
        if !t.members.contains(&id) {
            return Err("not_your_trade");
        }
        if t.revision != revision {
            return Err("offer_changed");
        }
        Ok(t)
    }
    fn trade_near(&self, members: [u32; 2]) -> bool {
        let Some(a) = self.players.get(&members[0]) else {
            return false;
        };
        let Some(b) = self.players.get(&members[1]) else {
            return false;
        };
        self.owns_character(a.id)
            && self.owns_character(b.id)
            && a.connected
            && b.connected
            && !a.down
            && !b.down
            && (a.x - b.x).powi(2) + (a.z - b.z).powi(2) <= 144.0
            && (a.y - b.y).abs() <= 3.0
    }
    fn trade_carry(&self) -> BTreeMap<String, u8> {
        let mut carry: BTreeMap<_, _> = self.items.keys().map(|id| (id.clone(), 99)).collect();
        carry.insert("trail_potion".into(), 99);
        for id in self.buffs.keys() {
            carry.insert(id.clone(), 99);
        }
        for b in &self.economy.boxes {
            carry.insert(b.id.clone(), 99);
        }
        carry
    }
    fn commit_trade(&mut self, key: &str) -> Result<(), &'static str> {
        let t = self.community_runtime.trades.get(key).unwrap().clone();
        if self.storage_degraded {
            return Err("storage_pending");
        }
        let a = &self.players[&t.members[0]];
        let b = &self.players[&t.members[1]];
        if a.durable_disabled || b.durable_disabled {
            return Err("storage_pending");
        }
        let before = [character_record_of(a), character_record_of(b)];
        let after = community::exchange(
            &before[0],
            &before[1],
            &t.offers[0],
            &t.offers[1],
            &self.trade_carry(),
            &a.gear_slots,
        )?;
        if self.storage.is_live() {
            let (Some(ap), Some(bp)) = (a.principal, b.principal) else {
                return Err("storage_pending");
            };
            if ap == bp {
                return Err("cannot_trade_self");
            }
            let request = ExchangeCommit {
                id: key.into(),
                principals: [ap, bp],
                epochs: [a.owner_epoch, b.owner_epoch],
                before,
                after,
            };
            // Queue fresh pre-trade checkpoints before locking saves for the pair.
            for id in t.members {
                self.push_store(id);
            }
            let queued = self
                .storage
                .exchange(request.clone(), self.storage_events.clone());
            let t = self.community_runtime.trades.get_mut(key).unwrap();
            t.pending = Some(request);
            t.queued = queued;
            t.retry_tick = self.tick + 120;
        } else {
            for (i, id) in t.members.iter().enumerate() {
                apply_character_record(self.players.get_mut(id).unwrap(), &after[i]);
                self.pending_state_updates.insert(*id);
                self.push_store(*id);
                self.community_notice(*id, "trade_complete");
            }
            self.community_runtime.trades.remove(key);
        }
        Ok(())
    }
    pub(super) fn finish_exchange(&mut self, key: &str, accepted: bool) {
        let Some(t) = self.community_runtime.trades.remove(key) else {
            return;
        };
        if let Some(request) = t.pending {
            for (i, id) in t.members.iter().enumerate() {
                if accepted {
                    if let Some(p) = self.players.get_mut(id) {
                        // Preserve legitimate quest/XP changes while the worker was busy.
                        // Item/currency intents are fenced until this pair is resolved.
                        p.gold = request.after[i].gold;
                        p.bag = request.after[i].bag.clone();
                        p.state_revision = p.state_revision.wrapping_add(1).max(1);
                    }
                    self.pending_state_updates.insert(*id);
                }
                self.push_store(*id);
                self.community_notice(
                    *id,
                    if accepted {
                        "trade_complete"
                    } else {
                        "trade_storage_conflict"
                    },
                );
            }
        }
    }
    pub(super) fn retry_exchange(&mut self, key: &str) {
        if let Some(t) = self.community_runtime.trades.get_mut(key) {
            t.queued = false;
            t.retry_tick = self.tick + 120;
        }
    }
    pub(super) fn advance_community(&mut self) {
        let expired: Vec<_> = self
            .community_runtime
            .trades
            .values()
            .filter(|t| {
                t.pending.is_none() && (t.expires <= self.tick || !self.trade_near(t.members))
            })
            .map(|t| t.id.clone())
            .collect();
        for key in expired {
            if let Some(t) = self.community_runtime.trades.remove(&key) {
                for id in t.members {
                    self.community_notice(id, "trade_cancelled");
                }
            }
        }
        for t in self.community_runtime.trades.values_mut() {
            if !t.queued && t.retry_tick <= self.tick {
                if let Some(request) = &t.pending {
                    t.queued = self
                        .storage
                        .exchange(request.clone(), self.storage_events.clone());
                    t.retry_tick = self.tick + 120;
                }
            }
        }
        if self.tick % 100 == 0 {
            self.community_runtime.dirty.extend(
                self.players
                    .values()
                    .filter(|p| p.connected && self.community_runtime.enabled.contains(&p.id))
                    .map(|p| p.id),
            );
        }
        let dirty = std::mem::take(&mut self.community_runtime.dirty);
        for id in dirty {
            if let Some(state) = self.community_snapshot(id) {
                self.pending_notices.push((id, state));
            }
        }
    }
}
fn test_enabled() -> bool {
    std::env::var("AETHERFIELD_TEST_COMMERCE").is_ok_and(|v| v == "1")
}

#[cfg(test)]
mod tests {
    use super::*;
    fn world() -> (World, u32, u32) {
        let mut w = World::new(
            &crate::content::test_content(),
            crate::character::CharacterStore::shared(),
        );
        let a = w.join([1; 32]).unwrap().player_id;
        let b = w.join([2; 32]).unwrap().player_id;
        for id in [a, b] {
            let p = w.players.get_mut(&id).unwrap();
            p.x = 0.;
            p.z = 0.;
            p.y = 0.;
            p.gold = 100;
            p.bag.insert("trail_potion".into(), 3);
        }
        (w, a, b)
    }
    fn invite(w: &mut World, a: u32, b: u32) -> String {
        w.community_action(
            a,
            Action::Invite {
                handle: w.players[&b].handle.clone(),
            },
        );
        let key = w.community_runtime.trades.keys().next().unwrap().clone();
        w.community_action(
            b,
            Action::Accept {
                trade: key.clone(),
                revision: 1,
            },
        );
        key
    }
    #[test]
    fn edits_clear_confirmations_and_stale_confirmation_never_commits() {
        let (mut w, a, b) = world();
        let key = invite(&mut w, a, b);
        w.community_action(
            a,
            Action::Offer {
                trade: key.clone(),
                revision: 2,
                offer: Offer {
                    gold: 20,
                    items: BTreeMap::from([("trail_potion".into(), 1)]),
                    ..Default::default()
                },
            },
        );
        w.community_action(
            a,
            Action::Confirm {
                trade: key.clone(),
                revision: 3,
            },
        );
        w.community_action(
            b,
            Action::Offer {
                trade: key.clone(),
                revision: 3,
                offer: Offer {
                    gold: 10,
                    ..Default::default()
                },
            },
        );
        assert_eq!(w.community_runtime.trades[&key].confirmed, [false; 2]);
        w.community_action(
            a,
            Action::Confirm {
                trade: key.clone(),
                revision: 3,
            },
        );
        assert_eq!(w.players[&a].gold, 100);
        w.community_action(
            a,
            Action::Confirm {
                trade: key.clone(),
                revision: 4,
            },
        );
        w.community_action(
            b,
            Action::Confirm {
                trade: key.clone(),
                revision: 4,
            },
        );
        assert_eq!((w.players[&a].gold, w.players[&b].gold), (90, 110));
        assert_eq!(
            (
                w.players[&a].bag["trail_potion"],
                w.players[&b].bag["trail_potion"]
            ),
            (2, 4)
        );
        w.community_action(
            b,
            Action::Confirm {
                trade: key,
                revision: 4,
            },
        );
        assert_eq!(w.players[&b].gold, 110);
    }
    #[test]
    fn outsider_range_and_disconnect_cancel_without_mutation() {
        let (mut w, a, b) = world();
        let key = invite(&mut w, a, b);
        let c = w.join([3; 32]).unwrap().player_id;
        w.community_action(
            c,
            Action::Confirm {
                trade: key.clone(),
                revision: 2,
            },
        );
        assert_eq!(w.community_runtime.trades[&key].confirmed, [false; 2]);
        w.players.get_mut(&b).unwrap().x = 20.;
        w.advance_community();
        assert!(w.community_runtime.trades.is_empty());
        w.players.get_mut(&b).unwrap().x = 0.;
        invite(&mut w, a, b);
        w.disconnect(b, w.players[&b].epoch);
        w.advance_community();
        assert!(w.community_runtime.trades.is_empty());
        assert_eq!(w.players[&a].gold, 100);
    }
    #[test]
    fn season_claim_survives_room_changes_and_replay() {
        let (mut w, a, _) = world();
        w.players.get_mut(&a).unwrap().community.xp = 100;
        let request = Action::PassClaim {
            season: community::SEASON.into(),
            tier: 1,
            premium: false,
            op_id: uuid::Uuid::new_v4().to_string(),
        };
        w.community_action(a, request.clone());
        w.community_action(a, request);
        assert_eq!(w.players[&a].gold, 105);
        let mut other = World::new(&crate::content::test_content(), w.store.clone());
        let resumed = other.join([1; 32]).unwrap().player_id;
        assert_eq!(other.players[&resumed].community.free_claims, 1);
        assert_eq!(other.players[&resumed].gold, 105);
    }
    #[test]
    fn state_payload_fits_cold_transport() {
        let (mut w, a, b) = world();
        invite(&mut w, a, b);
        let state = w.community_snapshot(a).unwrap();
        let bytes = serde_json::to_vec(&state).unwrap();
        assert!(bytes.len() <= crate::cold::MAX_COLD_SERVER_BYTES);
        assert!(crate::wire::encode_cold_server(&bytes).is_ok());
    }
    #[test]
    fn pending_receipt_preserves_progress_and_duplicate_outcome_is_harmless() {
        let (mut w, a, b) = world();
        let key = invite(&mut w, a, b);
        let before = [
            character_record_of(&w.players[&a]),
            character_record_of(&w.players[&b]),
        ];
        let mut after = before.clone();
        after[0].gold = 80;
        after[1].gold = 120;
        w.community_runtime.trades.get_mut(&key).unwrap().pending = Some(ExchangeCommit {
            id: key.clone(),
            principals: [uuid::Uuid::new_v4(), uuid::Uuid::new_v4()],
            epochs: [1, 1],
            before,
            after,
        });
        assert!(w.community_busy(a));
        let p = w.players.get_mut(&a).unwrap();
        p.community.xp = 70;
        p.exp = 40;
        p.quest_state = "active".into();
        w.finish_exchange(&key, true);
        assert_eq!(w.players[&a].gold, 80);
        assert_eq!(w.players[&a].community.xp, 70);
        assert_eq!(w.players[&a].exp, 40);
        assert_eq!(w.players[&a].quest_state, "active");
        w.finish_exchange(&key, true);
        assert_eq!(w.players[&a].gold, 80);
        assert!(!w.community_busy(a));
    }
    #[test]
    fn changing_rooms_fences_the_previous_world_writer_and_trade() {
        let (mut old, a, b) = world();
        let session = old.players[&a].session_id;
        let mut newer = World::new(&crate::content::test_content(), old.store.clone());
        let next = newer.join(session).unwrap().player_id;
        newer.players.get_mut(&next).unwrap().gold = 75;
        newer.players.get_mut(&next).unwrap().state_revision += 1;
        newer.push_store(next);
        old.players.get_mut(&a).unwrap().gold = 999;
        old.players.get_mut(&a).unwrap().state_revision += 1;
        old.push_store(a);
        assert_eq!(old.store.peek(session).unwrap().gold, 75);
        assert!(!old.owns_character(a));
        old.community_action(
            a,
            Action::Invite {
                handle: old.players[&b].handle.clone(),
            },
        );
        assert!(old.community_runtime.trades.is_empty());
        let resumed = old.join(session).unwrap().player_id;
        assert_eq!(old.players[&resumed].gold, 75);
        assert!(old.owns_character(resumed));
        assert!(!newer.owns_character(next));
    }
}
