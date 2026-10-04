//! Server-owned social economy. Preview credits never enter the spendable coin wallet.
use crate::character::CharacterRecord;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const SEASON: &str = "sunmeadow-preview-01";
pub const TIERS: u8 = 20;
pub const XP_PER_TIER: u32 = 100;
pub const PREMIUM_TEST_COST: u32 = 300;
pub const TOPUP_PACKS: [(&str, u32); 3] = [
    ("preview_100", 100),
    ("preview_300", 300),
    ("preview_600", 600),
];

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Device {
    Desktop,
    Mobile,
    #[default]
    Unknown,
}
pub fn unknown_device(value: &Device) -> bool {
    *value == Device::Unknown
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Progress {
    pub season: String,
    pub xp: u32,
    pub premium: bool,
    pub free_claims: u32,
    pub premium_claims: u32,
    pub test_credits: u32,
    // Never evict receipts: replay safety survives reconnect/restart. Test orders cap at 64.
    pub test_orders: Vec<TestOrder>,
    pub operations: BTreeMap<String, String>,
}
impl Default for Progress {
    fn default() -> Self {
        Self {
            season: SEASON.into(),
            xp: 0,
            premium: false,
            free_claims: 0,
            premium_claims: 0,
            test_credits: 0,
            test_orders: Vec::new(),
            operations: BTreeMap::new(),
        }
    }
}
impl Progress {
    pub fn ensure_season(&mut self) {
        if self.season != SEASON {
            self.season = SEASON.into();
            self.xp = 0;
            self.premium = false;
            self.free_claims = 0;
            self.premium_claims = 0;
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestOrder {
    pub id: String,
    pub pack: String,
    pub credits: u32,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Offer {
    pub gold: u32,
    pub items: BTreeMap<String, u8>,
    #[serde(default,skip_serializing_if="Vec::is_empty")]
    pub instance_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Sync {
        device: Device,
    },
    Invite {
        handle: String,
    },
    Accept {
        trade: String,
        revision: u32,
    },
    Offer {
        trade: String,
        revision: u32,
        offer: Offer,
    },
    Confirm {
        trade: String,
        revision: u32,
    },
    Cancel {
        trade: String,
    },
    PassClaim {
        season: String,
        tier: u8,
        premium: bool,
        op_id: String,
    },
    PassPremium {
        season: String,
        op_id: String,
    },
    TestTopup {
        pack: String,
        op_id: String,
    },
    Megaphone {
        text: String,
    },
}
impl Action {
    pub fn operation(&self) -> Option<(String, String)> {
        let id = match self {
            Self::PassClaim { op_id, .. }
            | Self::PassPremium { op_id, .. }
            | Self::TestTopup { op_id, .. } => op_id,
            _ => return None,
        };
        Some((
            id.clone(),
            serde_json::to_string(self).expect("typed action serializes"),
        ))
    }
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub t: String,
    pub action: Action,
}

pub fn decode(bytes: &[u8]) -> Result<Action, crate::wire::DecodeError> {
    let request: Request =
        serde_json::from_slice(bytes).map_err(|_| crate::wire::DecodeError::InvalidField)?;
    if request.t != "community" {
        return Err(crate::wire::DecodeError::InvalidField);
    }
    let uuid = |s: &str| s.len() == 36 && uuid::Uuid::parse_str(s).is_ok();
    let valid = match &request.action {
        Action::Invite { handle } => {
            handle.len() == 8 && handle.bytes().all(|b| b.is_ascii_hexdigit())
        }
        Action::Accept { trade, .. } | Action::Confirm { trade, .. } | Action::Cancel { trade } => {
            uuid(trade)
        }
        Action::Offer { trade, offer, .. } => {
            uuid(trade)
                && offer.items.len() <= 6
                && offer.gold <= 1_000_000
                && offer.instance_ids.len()<=crate::inventory_instances::MAX_INSTANCES
                && offer.instance_ids.iter().all(|id|uuid(id))
                && offer.instance_ids.iter().collect::<std::collections::BTreeSet<_>>().len()==offer.instance_ids.len()
                && offer.items.iter().all(|(id, n)| {
                    !id.is_empty()
                        && id.len() <= 64
                        && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
                        && *n > 0
                })
        }
        Action::PassClaim {
            season,
            tier,
            op_id,
            ..
        } => season == SEASON && (1..=TIERS).contains(tier) && uuid(op_id),
        Action::PassPremium { season, op_id } => season == SEASON && uuid(op_id),
        Action::TestTopup { pack, op_id } => {
            TOPUP_PACKS.iter().any(|(id, _)| id == pack) && uuid(op_id)
        }
        Action::Megaphone { text } => {
            !text.trim().is_empty()
                && text.chars().count() <= 110
                && !text.chars().any(|c| c.is_control())
        }
        Action::Sync { .. } => true,
    };
    if !valid {
        return Err(crate::wire::DecodeError::InvalidField);
    }
    Ok(request.action)
}

/// Checks and builds BOTH records before changing either. Offers exclude equipped gear;
/// cosmetic/quest/currency IDs cannot be smuggled into the item bag.
pub fn exchange(
    a: &CharacterRecord,
    b: &CharacterRecord,
    ao: &Offer,
    bo: &Offer,
    carry: &BTreeMap<String, u8>,
    slots: &BTreeMap<String,String>,
) -> Result<[CharacterRecord; 2], &'static str> {
    let mut records = [a.clone(), b.clone()];
    for record in &mut records {if !slots.is_empty() || !record.item_instances.is_empty() {crate::inventory_instances::reconcile(&record.inventory_namespace,&mut record.inventory_schema,&mut record.item_instances,&record.bag,&record.equipment,&record.equipment_refine,slots)?;}}
    // Transfer precise unequipped pieces with the same atomic two-record transaction.
    // Legacy def/count offers remain valid only for one unambiguous bag piece.
    let mut pieces=[Vec::new(),Vec::new()];
    for (i,offer) in [ao,bo].iter().enumerate() {
        let mut selected=std::collections::BTreeSet::new();
        if offer.instance_ids.len()>crate::inventory_instances::MAX_INSTANCES {return Err("invalid_offer");}
        for id in &offer.instance_ids {
            if !selected.insert(id.clone()) {return Err("invalid_offer");}
            let piece=records[i].item_instances.get(id).ok_or("not_owned")?;
            if piece.location!="bag" || !offer.items.contains_key(&piece.def) {return Err("equipped_item");}
        }
        for (def,count) in &offer.items {
            let all=records[i].item_instances.values().filter(|piece|piece.def==*def&&piece.location=="bag").collect::<Vec<_>>();
            if all.is_empty() {continue;}
            let matching=all.iter().filter(|p|selected.contains(&p.instance_id)).collect::<Vec<_>>();
            if matching.is_empty() {
                if all.len()!=1 || *count!=1 {return Err("instance_required");}
                selected.insert(all[0].instance_id.clone());
            } else if matching.len()!=usize::from(*count) {return Err("invalid_offer");}
        }
        for id in selected {pieces[i].push(records[i].item_instances.remove(&id).ok_or("not_owned")?);}
    }
    for (i, offer) in [ao, bo].iter().enumerate() {
        if records[i].gold < offer.gold {
            return Err("not_enough_gold");
        }
        for (id, n) in &offer.items {
            if !carry.contains_key(id)
                || records[i].equipment.values().any(|equipped| equipped == id) && !pieces[i].iter().any(|p|&p.def==id)
            {
                return Err("item_not_tradeable");
            }
            let old = records[i].bag.get(id).copied().unwrap_or(0);
            if old < *n {
                return Err("not_enough_items");
            }
            if old == *n {
                records[i].bag.remove(id);
            } else {
                records[i].bag.insert(id.clone(), old - *n);
            }
        }
        records[i].gold -= offer.gold;
    }
    for (i, incoming) in [bo, ao].iter().enumerate() {
        records[i].gold = records[i]
            .gold
            .checked_add(incoming.gold)
            .filter(|v| *v <= i32::MAX as u32)
            .ok_or("wallet_full")?;
        for (id, n) in &incoming.items {
            let count = records[i]
                .bag
                .get(id)
                .copied()
                .unwrap_or(0)
                .checked_add(*n)
                .filter(|v| *v <= carry[id])
                .ok_or("inventory_full")?;
            records[i].bag.insert(id.clone(), count);
        }
        if records[i].bag.values().filter(|n| **n > 0).count() > 12 {
            return Err("inventory_full");
        }
        records[i].state_revision = records[i].state_revision.wrapping_add(1).max(1);
    }
    for i in 0..2 {
        for piece in &pieces[1-i] {
            if records[i].item_instances.contains_key(&piece.instance_id) {return Err("invalid_inventory_state");}
            records[i].item_instances.insert(piece.instance_id.clone(),piece.clone());
        }
        if records[i].item_instances.len()>crate::inventory_instances::MAX_INSTANCES {return Err("inventory_full");}
        let r=&mut records[i];if !slots.is_empty() || !r.item_instances.is_empty() {crate::inventory_instances::reconcile(&r.inventory_namespace,&mut r.inventory_schema,&mut r.item_instances,&r.bag,&r.equipment,&r.equipment_refine,slots)?;}
    }
    Ok(records)
}

pub fn test_topup(progress: &mut Progress, pack: &str, id: &str) -> Result<(), &'static str> {
    if let Some(order) = progress.test_orders.iter().find(|o| o.id == id) {
        return if order.pack == pack {
            Ok(())
        } else {
            Err("operation_conflict")
        };
    }
    let credits = TOPUP_PACKS
        .iter()
        .find(|(p, _)| *p == pack)
        .map(|(_, n)| *n)
        .ok_or("unknown_pack")?;
    if progress.test_orders.len() >= 64 {
        return Err("test_order_limit");
    }
    progress.test_credits = progress
        .test_credits
        .checked_add(credits)
        .filter(|v| *v <= 10_000)
        .ok_or("test_wallet_full")?;
    progress.test_orders.push(TestOrder {
        id: id.into(),
        pack: pack.into(),
        credits,
    });
    Ok(())
}
pub fn reward_gold(tier: u8, premium: bool) -> u32 {
    u32::from(tier) * if premium { 15 } else { 5 }
}
pub fn claim(progress: &mut Progress, tier: u8, premium: bool) -> Result<u32, &'static str> {
    if !(1..=TIERS).contains(&tier) {
        return Err("invalid_tier");
    }
    if progress.xp < u32::from(tier) * XP_PER_TIER {
        return Err("tier_locked");
    }
    if premium && !progress.premium {
        return Err("premium_required");
    }
    let bit = 1 << (tier - 1);
    let claims = if premium {
        &mut progress.premium_claims
    } else {
        &mut progress.free_claims
    };
    if *claims & bit != 0 {
        return Err("already_claimed");
    }
    *claims |= bit;
    Ok(reward_gold(tier, premium))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn record(gold: u32, items: &[(&str, u8)]) -> CharacterRecord {
        CharacterRecord {
            gold,
            bag: items.iter().map(|(id, n)| (id.to_string(), *n)).collect(),
            ..Default::default()
        }
    }
    fn caps() -> BTreeMap<String, u8> {
        BTreeMap::from([("potion".into(), 20), ("sword".into(), 1)])
    }
    #[test]
    fn precise_trade_preserves_identity_refinement_and_rolls_back_foreign_selection() {
        let slots=BTreeMap::from([("sword".into(),"weapon".into())]);let mut a=record(100,&[("sword",2)]);a.inventory_namespace="owner-a".into();let mut b=record(0,&[]);b.inventory_namespace="owner-b".into();
        crate::inventory_instances::reconcile(&a.inventory_namespace,&mut a.inventory_schema,&mut a.item_instances,&a.bag,&a.equipment,&a.equipment_refine,&slots).unwrap();let ids=a.item_instances.keys().cloned().collect::<Vec<_>>();a.item_instances.get_mut(&ids[0]).unwrap().refine=7;
        let offer=Offer {gold:10,items:BTreeMap::from([("sword".into(),1)]),instance_ids:vec![ids[0].clone()]};
        let output=exchange(&a,&b,&offer,&Offer::default(),&caps(),&slots).unwrap();assert!(!output[0].item_instances.contains_key(&ids[0]));assert_eq!(output[1].item_instances[&ids[0]].refine,7);assert_eq!(output[0].item_instances[&ids[1]].location,"bag");assert_eq!(a.item_instances.len(),2);
        assert_eq!(exchange(&a,&b,&Offer {instance_ids:vec![],..offer.clone()},&Offer::default(),&caps(),&slots).unwrap_err(),"instance_required");
        assert_eq!(exchange(&a,&b,&Offer {instance_ids:vec![uuid::Uuid::new_v4().to_string()],..offer},&Offer::default(),&caps(),&slots).unwrap_err(),"not_owned");assert_eq!(a.gold,100);assert!(b.item_instances.is_empty());
    }
    #[test]
    fn exchange_conserves_and_never_changes_inputs() {
        let a = record(100, &[("potion", 5)]);
        let b = record(20, &[("sword", 1)]);
        let r = exchange(
            &a,
            &b,
            &Offer {
                gold: 30,
                items: BTreeMap::from([("potion".into(), 2)]),
                ..Default::default()
            },
            &Offer {
                gold: 10,
                items: BTreeMap::from([("sword".into(), 1)]),
                ..Default::default()
            },
            &caps(),
            &BTreeMap::new(),
        )
        .unwrap();
        assert_eq!((r[0].gold, r[1].gold), (80, 40));
        assert_eq!(r[0].bag["potion"], 3);
        assert_eq!(r[1].bag["potion"], 2);
        assert_eq!(a.bag["potion"], 5);
    }
    #[test]
    fn rejects_missing_equipped_and_overflow_without_partial_exchange() {
        let mut a = record(100, &[("sword", 1)]);
        let b = record(0, &[("potion", 20)]);
        a.equipment.insert("weapon".into(), "sword".into());
        let ao = Offer {
            gold: 1,
            items: BTreeMap::from([("sword".into(), 1)]),
            ..Default::default()
        };
        assert_eq!(
            exchange(&a, &b, &ao, &Offer::default(), &caps(), &BTreeMap::new()).unwrap_err(),
            "item_not_tradeable"
        );
        assert_eq!(
            exchange(
                &a,
                &b,
                &Offer {
                    gold: 101,
                    ..Default::default()
                },
                &Offer::default(),
                &caps()
                , &BTreeMap::new()
            )
            .unwrap_err(),
            "not_enough_gold"
        );
        assert_eq!(
            exchange(
                &record(0, &[("potion", 1)]),
                &b,
                &Offer {
                    gold: 0,
                    items: BTreeMap::from([("potion".into(), 1)]),
                    ..Default::default()
                },
                &Offer::default(),
                &caps()
                , &BTreeMap::new()
            )
            .unwrap_err(),
            "inventory_full"
        );
    }
    #[test]
    fn claims_are_server_locked_and_one_per_track() {
        let mut p = Progress::default();
        assert_eq!(claim(&mut p, 1, false), Err("tier_locked"));
        p.xp = 200;
        assert_eq!(claim(&mut p, 1, false), Ok(5));
        assert_eq!(claim(&mut p, 1, false), Err("already_claimed"));
        assert_eq!(claim(&mut p, 1, true), Err("premium_required"));
        p.premium = true;
        assert_eq!(claim(&mut p, 1, true), Ok(15));
    }
    #[test]
    fn test_credits_replay_conflict_and_capacity() {
        let mut p = Progress::default();
        test_topup(&mut p, "preview_300", "a").unwrap();
        test_topup(&mut p, "preview_300", "a").unwrap();
        assert_eq!(p.test_credits, 300);
        assert_eq!(
            test_topup(&mut p, "preview_100", "a"),
            Err("operation_conflict")
        );
        p.test_orders = (0..64)
            .map(|i| TestOrder {
                id: i.to_string(),
                pack: "preview_100".into(),
                credits: 100,
            })
            .collect();
        assert_eq!(
            test_topup(&mut p, "preview_100", "new"),
            Err("test_order_limit")
        );
    }
    #[test]
    fn malicious_shapes_and_counts_are_refused() {
        for bytes in [
            br#"{"t":"community","action":{"kind":"sync","device":"tablet"}}"#.as_slice(),
            br#"{"t":"community","action":{"kind":"sync","device":"mobile","coin":999}}"#
                .as_slice(),
            br#"{"t":"community","action":{"kind":"megaphone","text":"\u0001"}}"#.as_slice(),
        ] {
            assert!(decode(bytes).is_err());
        }
        assert!(
            decode(br#"{"t":"community","action":{"kind":"sync","device":"desktop"}}"#).is_ok()
        );
    }
}
