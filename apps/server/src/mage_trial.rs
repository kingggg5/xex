//! Typed, bounded session Mage trial. It never selects or persists a vocation.
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, VecDeque};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum SkillId {
    #[serde(rename = "h02_basic")]
    Basic,
    #[serde(rename = "h02_star_lance")]
    StarLance,
}
impl SkillId {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Basic => "h02_basic",
            Self::StarLance => "h02_star_lance",
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SpellConfig {
    pub range_m: f32,
    pub windup_ms: u16,
    pub cooldown_ms: u16,
    pub recovery_ms: u16,
    pub sp_cost: u16,
    pub projectile_speed_m_s: f32,
    pub damage_numerator: u16,
    pub damage_denominator: u16,
    pub cancel_on_move: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema: u8,
    pub base_power: u16,
    pub allocated_int_coefficient: u16,
    pub allocated_dex_divisor: u16,
    pub basic: SpellConfig,
    pub star_lance: SpellConfig,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            schema: 1,
            base_power: 25,
            allocated_int_coefficient: 2,
            allocated_dex_divisor: 5,
            basic: SpellConfig {
                range_m: 9.0,
                windup_ms: 100,
                cooldown_ms: 600,
                recovery_ms: 200,
                sp_cost: 0,
                projectile_speed_m_s: 20.0,
                damage_numerator: 1,
                damage_denominator: 1,
                cancel_on_move: false,
            },
            star_lance: SpellConfig {
                range_m: 11.0,
                windup_ms: 500,
                cooldown_ms: 5000,
                recovery_ms: 300,
                sp_cost: 8,
                projectile_speed_m_s: 20.0,
                damage_numerator: 7,
                damage_denominator: 4,
                cancel_on_move: true,
            },
        }
    }
}
impl Config {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.schema != 1
            || self.allocated_dex_divisor == 0
            || self.base_power > 10000
            || self.allocated_int_coefficient > 100
        {
            return Err("invalid mage power configuration");
        }
        for s in [&self.basic, &self.star_lance] {
            if !s.range_m.is_finite()
                || !(0.5..=25.0).contains(&s.range_m)
                || !s.projectile_speed_m_s.is_finite()
                || !(1.0..=100.0).contains(&s.projectile_speed_m_s)
                || s.windup_ms == 0
                || s.windup_ms > 5000
                || s.windup_ms % 50 != 0
                || s.cooldown_ms < s.windup_ms
                || s.cooldown_ms > 60000
                || s.recovery_ms > 5000
                || s.damage_denominator == 0
                || s.damage_numerator == 0
                || s.damage_numerator > 20
                || s.sp_cost > 1000
            {
                return Err("invalid mage spell configuration");
            }
        }
        Ok(())
    }
    pub fn spell(&self, id: SkillId) -> &SpellConfig {
        match id {
            SkillId::Basic => &self.basic,
            SkillId::StarLance => &self.star_lance,
        }
    }
    pub fn power(&self, int: u16, dex: u16) -> u16 {
        (u32::from(self.base_power)
            + u32::from(int) * u32::from(self.allocated_int_coefficient)
            + u32::from(dex) / u32::from(self.allocated_dex_divisor))
        .min(u32::from(u16::MAX)) as u16
    }
    pub fn damage(&self, id: SkillId, power: u16) -> u16 {
        (u32::from(power) * u32::from(self.spell(id).damage_numerator)
            / u32::from(self.spell(id).damage_denominator))
        .min(u32::from(u16::MAX)) as u16
    }
}
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TrialRequest {
    pub t: String,
    pub enabled: bool,
    pub op_id: String,
}
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CastRequest {
    pub t: String,
    pub epoch: u32,
    pub sequence: u32,
    pub skill_id: SkillId,
    pub target_id: u32,
}
#[derive(Debug, Clone, Serialize)]
pub struct AvailableSpell {
    pub skill_id: SkillId,
    pub range_m: f32,
    pub windup_ms: u16,
    pub cooldown_ms: u16,
    pub recovery_ms: u16,
    pub sp_cost: u16,
    pub projectile_speed_m_s: f32,
    pub available: bool,
    pub power: u16,
}
#[derive(Debug, Clone, Serialize)]
pub struct TrialState {
    pub t: String,
    pub capability_enabled: bool,
    pub profile: String,
    pub focus_equipped: bool,
    pub epoch: u32,
    pub skills: Vec<AvailableSpell>,
}
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct CastState {
    pub t: String,
    pub cast_id: String,
    pub source_id: u32,
    pub epoch: u32,
    pub sequence: u32,
    pub skill_id: SkillId,
    pub phase: String,
    pub reason: String,
    pub server_ms: u64,
    pub start_ms: u64,
    pub release_ms: u64,
    pub impact_ms: Option<u64>,
    pub recovery_end_ms: u64,
    pub cooldown_end_ms: u64,
    pub target_id: u32,
    pub origin: [f32; 3],
    pub target: [f32; 3],
    pub damage: u16,
    pub flags: u8,
}
#[derive(Debug, Clone)]
pub(crate) struct PendingCast {
    pub request: CastRequest,
    pub encounter: uuid::Uuid,
    pub start_tick: u64,
    pub release_tick: u64,
    pub impact_tick: Option<u64>,
    pub cooldown_tick: u64,
    pub recovery_tick: u64,
    pub origin: [f32; 3],
    pub target: [f32; 3],
    pub power: u16,
    pub released: bool,
}
#[derive(Debug, Default)]
pub(crate) struct PlayerTrial {
    pub enabled: bool,
    pub epoch: u32,
    pub watermark: u32,
    pub recovery_tick: u64,
    pub ready: BTreeMap<SkillId, u64>,
    pub pending: Option<PendingCast>,
    pub recent: VecDeque<(CastRequest, CastState)>,
}
impl PlayerTrial {
    pub fn remember(&mut self, request: CastRequest, state: CastState) {
        if let Some(row) = self
            .recent
            .iter_mut()
            .find(|(r, _)| r.epoch == request.epoch && r.sequence == request.sequence)
        {
            *row = (request, state);
            return;
        }
        self.recent.push_back((request, state));
        while self.recent.len() > 32 {
            self.recent.pop_front();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn config_is_typed_bounded_and_power_uses_only_approved_allocations() {
        let c = Config::default();
        assert!(c.validate().is_ok());
        assert_eq!(c.power(0, 0), 25);
        assert_eq!(c.power(3, 6), 32);
        assert_eq!(c.damage(SkillId::StarLance, 32), 56);
        let mut bad = c.clone();
        bad.basic.range_m = f32::NAN;
        assert!(bad.validate().is_err());
        bad = c;
        bad.allocated_dex_divisor = 0;
        assert!(bad.validate().is_err());
    }
}
