//! Pure, bounded combat/reward decisions; the world owns mutations and storage.
use std::collections::BTreeMap;

pub const CRIT: u8 = 1 << 5;
pub const MISS: u8 = 1 << 6;
pub const TAG_IDLE_TICKS: u64 = 200;
pub const CONTRIBUTOR_LIMIT: usize = 50;

pub fn rune_threshold(pity: u32) -> u16 {
    500u32.saturating_add(pity.saturating_mul(2)).min(10000) as u16
}

/// Bounded rejection sampling avoids modulo bias in the 5% rune table.
pub fn random_basis_points() -> Option<u16> {
    for _ in 0..8 {
        let mut bytes=[0u8;2];
        getrandom::fill(&mut bytes).ok()?;
        let value=u16::from_le_bytes(bytes);
        if value<60000 {return Some(value%10000);}
    }
    None
}

pub fn miss_percent(attacker: u32, target: u32) -> u8 {
    target.saturating_sub(attacker).saturating_sub(9).saturating_mul(5).min(50) as u8
}

pub fn split_exp(exp: u32, ids: &[u32]) -> Vec<(u32, u32)> {
    let mut ids = ids.to_vec();
    ids.sort_unstable();
    ids.dedup();
    if ids.is_empty() { return Vec::new(); }
    let n = ids.len() as u64;
    let pool = u64::from(exp) * (100 + 10 * n.saturating_sub(1).min(3)) / 100;
    ids.into_iter().enumerate().map(|(i, id)| (id, (pool / n + u64::from((i as u64) < pool % n)).min(u64::from(u32::MAX)) as u32)).collect()
}

#[derive(Debug, Clone)]
pub struct Contribution {
    pub damage: u64,
    pub taken: u64,
    pub healing: u64,
    pub tank_ticks: u64,
    pub healing_ticks: u64,
    pub first_hit: u64,
}
impl Default for Contribution {fn default()->Self {Self {damage:0,taken:0,healing:0,tank_ticks:0,healing_ticks:0,first_hit:u64::MAX}}}
impl Contribution {
    pub fn eligible(&self, hp: u32) -> bool {
        self.damage.saturating_mul(100) >= u64::from(hp).saturating_mul(3)
            || self.tank_ticks >= 200 || self.healing_ticks >= 200
    }
    pub fn doubled_score(&self) -> u64 {
        self.damage.saturating_mul(2).saturating_add(self.taken).saturating_add(self.healing)
    }
}

pub fn mvp(contributors: &BTreeMap<u32, Contribution>, hp: u32) -> Option<u32> {
    contributors.iter().filter(|(_, c)| c.eligible(hp)).max_by(|(ia, a), (ib, b)| {
        a.doubled_score().cmp(&b.doubled_score()).then(a.damage.cmp(&b.damage))
            .then_with(|| b.first_hit.cmp(&a.first_hit)).then_with(|| ib.cmp(ia))
    }).map(|(id, _)| *id)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EncounterPhase { Dormant, Announced, Engaged, PhaseTransition, Defeated, Reset, AdminEnded }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn miss_has_no_normal_rng_and_caps_at_fifty() {
        assert_eq!(miss_percent(1,10),0);
        assert_eq!(miss_percent(1,11),5);
        assert_eq!(miss_percent(1,19),45);
        assert_eq!(miss_percent(1,20),50);
        assert_eq!(miss_percent(99,1),0);
    }
    #[test]
    fn party_pool_is_conserved_and_remainder_is_stable() {
        assert_eq!(split_exp(9,&[4,2]),vec![(2,5),(4,4)]);
        let split=split_exp(100,&[4,3,2,1]);
        assert_eq!(split.iter().map(|(_,e)|e).sum::<u32>(),130);
        assert_eq!(split_exp(100,&[1,1]),vec![(1,100)]);
        assert!(split_exp(100,&[]).is_empty());
    }
    #[test]
    fn contribution_thresholds_and_mvp_ties_use_actual_values() {
        let mut c=Contribution {damage:299, ..Default::default()};
        assert!(!c.eligible(10000));c.damage=300;assert!(c.eligible(10000));
        c.damage=0;c.tank_ticks=199;assert!(!c.eligible(10000));c.tank_ticks=200;assert!(c.eligible(10000));
        let mut map=BTreeMap::new();
        map.insert(1,Contribution {damage:300,taken:600,first_hit:10,..Default::default()});
        map.insert(2,Contribution {damage:600,first_hit:20,..Default::default()});
        assert_eq!(mvp(&map,10000),Some(2));
        map.get_mut(&1).unwrap().damage=600;map.get_mut(&1).unwrap().taken=0;
        assert_eq!(mvp(&map,10000),Some(1));
    }
    #[test]
    fn rune_pity_starts_at_five_percent_and_caps_without_overflow() {
        assert_eq!(rune_threshold(0),500);
        assert_eq!(rune_threshold(1),502);
        assert_eq!(rune_threshold(4750),10000);
        assert_eq!(rune_threshold(u32::MAX),10000);
    }
}
