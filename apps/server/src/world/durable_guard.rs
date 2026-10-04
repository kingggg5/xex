//! One bounded pre-mutation lookup per character. Historical snapshots are never restored.
use super::*;
use crate::cold::{self, ColdTag};
use crate::storage::OperationLookup;
#[derive(Debug)]
pub(super) struct PendingOp {
    token: u64,
    epoch: u32,
    owner_epoch: u64,
    op_id: String,
    key: String,
    kind: String,
    payload: Vec<u8>,
    expires: u64,
    applied: bool,
}

fn identity(payload: &[u8]) -> Option<(ColdTag, String, String, String)> {
    let tag = cold::validate_client_payload(payload).ok()?;
    let v: serde_json::Value = serde_json::from_slice(payload).ok()?;
    let id = v.get("op_id")?.as_str()?.to_string();
    let field = |name: &str| v.get(name).and_then(|v| v.as_str()).unwrap_or("");
    let (kind, key) = match tag {
        ColdTag::StatAllocate => {
            let r = cold::decode_stat_allocate_request(payload).ok()?;
            ("stat_allocate", format!("{}:{}", r.stat, r.points))
        }
        ColdTag::MoveItemInstance => (
            "equip",
            serde_json::to_string(&cold::decode_move_item_instance_request(payload).ok()?).ok()?,
        ),
        ColdTag::RefineItem => (
            "refine_item",
            serde_json::to_string(&cold::decode_refine_item_request(payload).ok()?).ok()?,
        ),
        ColdTag::MageTrial => (
            "equip",
            format!("mage_trial:{}", v.get("enabled")?.as_bool()?),
        ),
        ColdTag::EquipItem => ("equip", format!("legacy_equip:{}", field("item"))),
        ColdTag::UseItem => ("item", field("item").into()),
        ColdTag::StoreBuy => ("store", field("item").into()),
        ColdTag::BoxOpen => ("box", field("item").into()),
        ColdTag::Claim => ("quest", field("quest").into()),
        ColdTag::PickupDrop => ("item", field("encounter").into()),
        ColdTag::ClaimReward => ("item", format!("claim_reward:{}", field("receipt_id"))),
        ColdTag::ReturnToTown => (
            "item",
            format!("return_to_town:{}", v.get("death_revision")?.as_u64()?),
        ),
        _ => return None,
    };
    Some((tag, id, key, kind.into()))
}
impl World {
    fn cached_guard_result(p: &Player, kind: &str, id: &str, key: &str) -> Option<OpResultMsg> {
        let cache = match kind {
            "stat_allocate" => &p.recent_stat_operations,
            "equip" => &p.recent_equip_operations,
            "refine_item" => &p.recent_refine_operations,
            "item" => &p.recent_item_operations,
            "store" => &p.recent_store_operations,
            "box" => &p.recent_box_operations,
            "quest" => &p.recent_quest_operations,
            _ => return None,
        };
        replay_cached_op(cache, id, key)
    }
    fn defer_result(&mut self, id: u32, result: OpResultMsg) {
        if self.deferred_op_results.len() < MAX_PLAYERS * 2 {
            self.deferred_op_results.push((id, result));
            self.pending_state_updates.insert(id);
        }
    }
    /// True means dispatch was deferred or answered without allowing mutation.
    pub fn guard_durable_cold(&mut self, id: u32, payload: &[u8]) -> bool {
        let Some((_, op_id, key, kind)) = identity(payload) else {
            return false;
        };
        let Some(p) = self.players.get(&id) else {
            return true;
        };
        if !self.storage.is_live() || p.principal.is_none() {
            return false;
        }
        if p.durable_disabled || self.storage_degraded {
            self.defer_result(id, op_result(&op_id, "rejected", "storage_pending", vec![]));
            return true;
        }
        if let Some(result) = Self::cached_guard_result(p, &kind, &op_id, &key) {
            self.defer_result(id, result);
            return true;
        }
        if let Some(pending) = self.pending_durable_ops.get(&id) {
            let reason = if pending.op_id == op_id && (pending.key != key || pending.kind != kind) {
                "op_id_conflict"
            } else {
                "storage_pending"
            };
            self.defer_result(id, op_result(&op_id, "rejected", reason, vec![]));
            return true;
        }
        self.durable_lookup_token = self.durable_lookup_token.wrapping_add(1).max(1);
        let token = self.durable_lookup_token;
        let pending = PendingOp {
            token,
            epoch: p.epoch,
            owner_epoch: p.owner_epoch,
            op_id: op_id.clone(),
            key: key.clone(),
            kind: kind.clone(),
            payload: payload.to_vec(),
            expires: self.tick + 100,
            applied: false,
        };
        if !self.storage.lookup_operation(
            p.principal.unwrap(),
            p.session_id,
            token,
            kind,
            op_id.clone(),
            key,
            p.owner_epoch,
            self.storage_events.clone(),
        ) {
            self.defer_result(id, op_result(&op_id, "rejected", "storage_pending", vec![]));
            return true;
        }
        self.pending_durable_ops.insert(id, pending);
        true
    }
    pub(super) fn complete_durable_lookup(
        &mut self,
        session: crate::auth::SessionId,
        token: u64,
        result: OperationLookup,
    ) {
        let Some(id) = self.sessions.get(&session).copied() else {
            return;
        };
        if !self
            .pending_durable_ops
            .get(&id)
            .is_some_and(|p| p.token == token && !p.applied)
        {
            return;
        }
        let pending = self.pending_durable_ops.remove(&id).unwrap();
        if !self.owns_character(id)
            || !self.players.get(&id).is_some_and(|p| {
                p.connected && p.epoch == pending.epoch && p.owner_epoch == pending.owner_epoch
            })
        {
            return;
        }
        match result {
            OperationLookup::Replay(result) => self.defer_result(id, result),
            OperationLookup::Conflict => self.defer_result(
                id,
                op_result(&pending.op_id, "rejected", "op_id_conflict", vec![]),
            ),
            OperationLookup::StaleOwner | OperationLookup::Unavailable => self.defer_result(
                id,
                op_result(&pending.op_id, "rejected", "storage_pending", vec![]),
            ),
            OperationLookup::Fresh => {
                let result = self.execute_guarded_cold(id, &pending.payload);
                if let Some(result) = result {
                    if result.status == "accepted" {
                        self.pending_durable_ops.insert(
                            id,
                            PendingOp {
                                applied: true,
                                ..pending
                            },
                        );
                    }
                    self.defer_result(id, result);
                }
            }
        }
        self.pending_state_updates.insert(id);
    }
    fn execute_guarded_cold(&mut self, id: u32, payload: &[u8]) -> Option<OpResultMsg> {
        match cold::validate_client_payload(payload).ok()? {
            ColdTag::StatAllocate => {
                self.stat_allocate(id, cold::decode_stat_allocate_request(payload).ok()?)
            }
            ColdTag::MoveItemInstance => {
                self.move_item_instance(id, cold::decode_move_item_instance_request(payload).ok()?)
            }
            ColdTag::RefineItem => {
                self.refine_item(id, cold::decode_refine_item_request(payload).ok()?)
            }
            ColdTag::MageTrial => {
                self.mage_trial_activate(id, serde_json::from_slice(payload).ok()?)
            }
            ColdTag::EquipItem => {
                self.equip_item(id, cold::decode_equip_item_request(payload).ok()?)
            }
            ColdTag::UseItem => self.use_item(id, cold::decode_use_item_request(payload).ok()?),
            ColdTag::StoreBuy => self.store_buy(id, cold::decode_store_buy_request(payload).ok()?),
            ColdTag::BoxOpen => self.box_open(id, cold::decode_box_open_request(payload).ok()?),
            ColdTag::Claim => self.claim_quest(id, cold::decode_claim_request(payload).ok()?),
            ColdTag::PickupDrop => {
                self.pickup_drop(id, cold::decode_pickup_drop_request(payload).ok()?)
            }
            ColdTag::ClaimReward => {
                self.claim_reward(id, cold::decode_claim_reward_request(payload).ok()?)
            }
            ColdTag::ReturnToTown => {
                self.return_to_town(id, cold::decode_return_to_town_request(payload).ok()?)
            }
            _ => None,
        }
    }
    pub fn take_deferred_op_results(&mut self) -> Vec<(u32, OpResultMsg)> {
        std::mem::take(&mut self.deferred_op_results)
    }
    pub(super) fn finish_durable_guard(&mut self, session: crate::auth::SessionId, op_id: &str) {
        if let Some(id) = self.sessions.get(&session).copied()
            && self
                .pending_durable_ops
                .get(&id)
                .is_some_and(|p| p.op_id == op_id)
        {
            self.pending_durable_ops.remove(&id);
        }
    }
    pub(super) fn fail_durable_guard(&mut self, session: crate::auth::SessionId, op_id: &str) {
        if let Some(id) = self.sessions.get(&session).copied()
            && self
                .pending_durable_ops
                .get(&id)
                .is_some_and(|p| p.op_id == op_id)
        {
            self.pending_durable_ops.remove(&id);
            if let Some(p) = self.players.get_mut(&id) {
                p.durable_disabled = true;
                p.durable_dirty = false;
            }
            self.storage_degraded = true;
            self.defer_result(id, op_result(op_id, "rejected", "rejoin_required", vec![]));
        }
    }
    pub(super) fn expire_durable_lookups(&mut self) {
        let ids = self
            .pending_durable_ops
            .iter()
            .filter(|(_, p)| self.tick >= p.expires)
            .map(|(id, _)| *id)
            .collect::<Vec<_>>();
        for id in ids {
            if let Some(p) = self.pending_durable_ops.remove(&id) {
                if p.applied {
                    self.storage_degraded = true;
                    if let Some(player) = self.players.get_mut(&id) {
                        player.durable_disabled = true;
                        player.durable_dirty = false;
                    }
                }
                self.defer_result(
                    id,
                    op_result(&p.op_id, "rejected", "storage_pending", vec![]),
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn setup() -> (
        World,
        u32,
        crate::auth::SessionId,
        tokio::sync::mpsc::Receiver<crate::storage::StorageCommand>,
    ) {
        let c = crate::content::test_content();
        let mut w = World::new(&c, crate::character::CharacterStore::shared());
        let session = [213; 32];
        let id = w.join(session).unwrap().player_id;
        w.players.get_mut(&id).unwrap().stat_points = 100;
        let (storage, rx) = StorageHandle::lookup_fixture();
        w.storage = storage;
        let p = w.players.get_mut(&id).unwrap();
        p.principal = Some(uuid::Uuid::new_v4());
        p.owner_epoch = 1;
        (w, id, session, rx)
    }
    fn payload(id: &str, points: u32) -> Vec<u8> {
        serde_json::to_vec(
            &serde_json::json!({"t":"stat_allocate","stat":"str","points":points,"op_id":id}),
        )
        .unwrap()
    }
    #[test]
    fn evicted_durable_operation_is_checked_before_live_mutation_and_never_rolls_back_newer_state()
    {
        let (mut w, id, session, mut rx) = setup();
        let first = uuid::Uuid::new_v4().to_string();
        for i in 0..65 {
            let op = if i == 0 {
                first.clone()
            } else {
                uuid::Uuid::new_v4().to_string()
            };
            w.stat_allocate(
                id,
                cold::StatAllocateRequest {
                    stat: "str".into(),
                    points: 1,
                    op_id: op,
                },
            );
            while rx.try_recv().is_ok() {}
        }
        assert_eq!(w.players[&id].stat_points, 35);
        assert_eq!(w.players[&id].recent_stat_operations.len(), 64);
        assert!(w.guard_durable_cold(id, &payload(&first, 1)));
        let token = w.pending_durable_ops[&id].token;
        assert_eq!(w.players[&id].stat_points, 35);
        w.handle_storage_event(StorageEvent::OperationChecked {
            session,
            token,
            result: OperationLookup::Replay(op_result(&first, "accepted", "allocated", vec![])),
        });
        assert_eq!(w.players[&id].stat_points, 35);
        assert_eq!(w.players[&id].allocated_str, 65);
        assert!(w.pending_durable_ops.is_empty());
        assert_eq!(w.take_deferred_op_results()[0].1.status, "accepted");
    }
    #[test]
    fn lookup_conflict_timeout_and_owner_change_do_not_mutate() {
        let (mut w, id, session, _rx) = setup();
        let op = uuid::Uuid::new_v4().to_string();
        w.guard_durable_cold(id, &payload(&op, 1));
        let token = w.pending_durable_ops[&id].token;
        assert!(w.guard_durable_cold(id, &payload(&op, 2)));
        assert_eq!(w.take_deferred_op_results()[0].1.reason, "op_id_conflict");
        w.players.get_mut(&id).unwrap().epoch += 1;
        w.handle_storage_event(StorageEvent::OperationChecked {
            session,
            token,
            result: OperationLookup::Fresh,
        });
        assert_eq!(w.players[&id].stat_points, 100);
        w.guard_durable_cold(id, &payload(&uuid::Uuid::new_v4().to_string(), 1));
        w.tick = 101;
        w.expire_durable_lookups();
        assert!(w.pending_durable_ops.is_empty());
        assert_eq!(w.players[&id].stat_points, 100);
    }
    #[test]
    fn fresh_lookup_uses_latest_state_once_and_blocks_unexpected_late_conflict() {
        let (mut w, id, session, mut rx) = setup();
        let op = uuid::Uuid::new_v4().to_string();
        w.guard_durable_cold(id, &payload(&op, 1));
        let token = w.pending_durable_ops[&id].token;
        rx.try_recv().unwrap();
        w.players.get_mut(&id).unwrap().stat_points = 102;
        w.handle_storage_event(StorageEvent::OperationChecked {
            session,
            token,
            result: OperationLookup::Fresh,
        });
        assert_eq!(w.players[&id].stat_points, 101);
        w.handle_storage_event(StorageEvent::OperationChecked {
            session,
            token,
            result: OperationLookup::Fresh,
        });
        assert_eq!(w.players[&id].stat_points, 101);
        w.handle_storage_event(StorageEvent::OpConflict { session, op_id: op });
        assert!(w.players[&id].durable_disabled);
        assert_eq!(w.players[&id].stat_points, 101);
        assert!(w.storage_degraded);
        assert!(
            !w.owns_character(id),
            "uncertain operation state cannot continue hot combat"
        );
        let stored = w.store.peek(session).unwrap();
        w.push_store(id);
        assert_eq!(
            w.store.peek(session).unwrap().generation,
            stored.generation,
            "fenced state cannot publish into another room"
        );
    }
}
