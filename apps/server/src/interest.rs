//! Bounded, acknowledged AOI snapshots. Entity bytes are prepared once per world
//! update; recipient ACKs and targeting overlays never enter the shared cache.
use crate::{
    wire::{self, DecodeError},
    world::{CombatEvent, Snapshot},
};
use std::{
    collections::{BTreeMap, BTreeSet, HashMap, VecDeque},
    sync::Arc,
    time::{Duration, Instant},
};

pub const BASELINE_LIMIT: usize = 32;
pub const VISIBLE_PLAYER_LIMIT: usize = 64;
pub const VISIBLE_MONSTER_LIMIT: usize = 64;
pub const VISIBLE_PET_LIMIT: usize = 64;
pub const INTEREST_RADIUS: f32 = 32.0;
const ORDINARY_PLAYERS: usize = 16;
const ORDINARY_MONSTERS: usize = 24;
const CELL: f32 = 32.0;

#[derive(Clone, Debug, PartialEq)]
struct Record {
    id: u32,
    groups: Vec<Vec<u8>>,
}
type Records = BTreeMap<u32, Arc<Record>>;
#[derive(Clone, Default, Debug)]
pub struct VisibleState {
    players: Records,
    monsters: Records,
    pets: Records,
    event_max: u64,
}
#[derive(Default)]
pub struct Stream {
    pub target_id: u32,
    acknowledged: Option<(u64, Arc<VisibleState>)>,
    history: VecDeque<(u64, Arc<VisibleState>)>,
    sent: BTreeSet<u64>,
    pub resyncs: u64,
}
impl Stream {
    pub fn acknowledge(&mut self, tick: u64, resync: bool) -> bool {
        if resync {
            self.acknowledged = None;
            self.history.clear();
            self.sent.clear();
            self.resyncs += 1;
            return true;
        }
        if self
            .acknowledged
            .as_ref()
            .is_some_and(|(old, _)| tick <= *old)
        {
            return false;
        }
        if !self.sent.contains(&tick) {
            return false;
        }
        if let Some((_, state)) = self.history.iter().find(|(sent, _)| *sent == tick) {
            self.acknowledged = Some((tick, state.clone()));
            true
        } else {
            false
        }
    }
    pub fn mark_sent(&mut self, tick: u64) {
        if self.history.iter().any(|(t, _)| *t == tick) {
            self.sent.insert(tick);
            while self.sent.len() > BASELINE_LIMIT {
                self.sent.pop_first();
            }
        }
    }
    pub fn oldest_unacked_ticks(&self, tick: u64) -> u64 {
        self.acknowledged
            .as_ref()
            .map(|(t, _)| tick.saturating_sub(*t))
            .unwrap_or_else(|| {
                self.history
                    .front()
                    .map(|(t, _)| tick.saturating_sub(*t))
                    .unwrap_or(0)
            })
    }
    pub fn retained_baselines(&self) -> usize {
        self.history.len()
    }
}

#[derive(Clone, Copy, Default, PartialEq, Eq)]
pub struct InterestContext {
    pub realm: u64,
    pub zone: u16,
    pub epoch: u32,
    pub teleport_revision: u64,
}
#[derive(Default)]
pub struct OrdinaryMembership {
    context: Option<InterestContext>,
    cell: (i32, i32),
    last_position: (f32, f32),
    refreshed: Option<Instant>,
    next_tick: u64,
    players: Vec<u32>,
    monsters: Vec<u32>,
}
#[derive(Default)]
pub struct TickEncoder {
    zone_limit: f32,
    players: Records,
    monsters: Records,
    cells: HashMap<(i32, i32), Vec<u32>>,
    player_xy: HashMap<u32, (f32, f32)>,
    monster_xy: HashMap<u32, (f32, f32)>,
    frame_self: HashMap<u32, crate::world::PlayerSnapshot>,
    monster_cells: HashMap<(i32, i32), Vec<u32>>,
    // A patch is shared whenever an entity and its acknowledged record agree.
    patches: HashMap<(u8, u32, Vec<u8>), Arc<[u8]>>,
    shared: HashMap<Vec<u64>, Arc<[u8]>>,
    states: HashMap<Vec<u64>, Arc<VisibleState>>,
    event_records: HashMap<u64, Arc<[u8]>>,
    frame_events: HashMap<u64, CombatEvent>,
    player_events: HashMap<u32, Vec<u64>>,
    monster_only_events: Vec<u64>,
    pub shared_encodes: u64,
    pub shared_hits: u64,
    pub record_encodes: u64,
    pub essential_event_overflows: u64,
    pub delta_comparisons: u64,
    pub unchanged_record_skips: u64,
    pub record_key_constructions: u64,
    pub key_bytes_copied: u64,
    pub ordinary_cache_hits: u64,
    pub ordinary_cache_refreshes: u64,
}
fn pos(x: f32) -> f32 {
    (x * 128.0).round() / 128.0
}
fn coord(x: f32, z: f32) -> Vec<u8> {
    [pos(x).to_le_bytes(), pos(z).to_le_bytes()].concat()
}
fn cell(x: f32, z: f32) -> (i32, i32) {
    ((x / CELL).floor() as i32, (z / CELL).floor() as i32)
}
fn flatten(record: &Record) -> Vec<u8> {
    record.groups.concat()
}
impl TickEncoder {
    pub fn new(snapshot: &Snapshot, zone_limit: f32) -> Result<Self, DecodeError> {
        let mut out = Self {
            zone_limit,
            ..Self::default()
        };
        for p in &snapshot.players {
            if p.id == 0 || p.hp > p.max_hp || !p.y.is_finite() {
                return Err(DecodeError::InvalidField);
            }
            check_xy(p.x, p.z, zone_limit)?;
            let flags = u8::from(p.connected)
                | u8::from(p.down) << 1
                | u8::from(p.dodging) << 2
                | u8::from(p.guarding) << 3;
            out.players.insert(
                p.id,
                Arc::new(Record {
                    id: p.id,
                    groups: vec![
                        coord(p.x, p.z),
                        wire::quantize_facing(p.facing)?.to_le_bytes().to_vec(),
                        [p.hp.to_le_bytes(), p.max_hp.to_le_bytes()].concat(),
                        vec![flags],
                        vec![p.anim],
                        p.y.to_le_bytes().to_vec(),
                    ],
                }),
            );
            out.cells.entry(cell(p.x, p.z)).or_default().push(p.id);
            out.player_xy.insert(p.id, (p.x, p.z));
            out.frame_self.insert(p.id, p.clone());
        }
        for m in &snapshot.monsters {
            check_xy(m.x, m.z, zone_limit)?;
            check_xy(m.target_x, m.target_z, zone_limit)?;
            if m.id == 0 || m.kind == 0 || m.hp > m.max_hp || m.max_hp == 0 || m.flags & !7 != 0 {
                return Err(DecodeError::InvalidField);
            }
            out.monsters.insert(
                m.id,
                Arc::new(Record {
                    id: m.id,
                    groups: vec![
                        coord(m.x, m.z),
                        wire::quantize_facing(m.facing)?.to_le_bytes().to_vec(),
                        [m.hp.to_le_bytes(), m.max_hp.to_le_bytes()].concat(),
                        vec![(m.flags & 2) | u8::from(m.active)],
                        [
                            vec![m.state, m.ability],
                            (if m.state_ticks == 0 {
                                0
                            } else {
                                snapshot.tick + u64::from(m.state_ticks)
                            })
                            .to_le_bytes()
                            .to_vec(),
                        ]
                        .concat(),
                        coord(m.target_x, m.target_z),
                        vec![m.kind],
                    ],
                }),
            );
            out.monster_cells
                .entry(cell(m.x, m.z))
                .or_default()
                .push(m.id);
            out.monster_xy.insert(m.id, (m.x, m.z));
        }
        // v7 never transported pet records. The v8 collection remains reserved;
        // existing zero-based server pet kinds must not block room snapshots.
        out.refresh_events(snapshot);
        Ok(out)
    }
    pub fn retained_shared_states(&self) -> usize {
        self.states.len()
    }

    fn refresh_events(&mut self, snapshot: &Snapshot) {
        if self.shared.len() > 2048 {
            self.shared.clear();
        }
        if self.states.len() > 2048 {
            self.states.clear();
        }
        if self.patches.len() > 32768 {
            self.patches.clear();
        }
        self.frame_events.clear();
        self.player_events.clear();
        self.monster_only_events.clear();
        for event in &snapshot.events {
            self.frame_events.insert(event.id, event.clone());
            if event.source_kind == 0 {
                self.player_events
                    .entry(event.source_id)
                    .or_default()
                    .push(event.id);
            }
            if event.target_kind == 1
                && !(event.source_kind == 0 && event.source_id == event.target_id)
            {
                self.player_events
                    .entry(event.target_id)
                    .or_default()
                    .push(event.id);
            }
            if event.source_kind == 1 && event.target_kind == 0 {
                self.monster_only_events.push(event.id);
            }
        }
        self.event_records
            .retain(|id, _| self.frame_events.contains_key(id));
    }
    pub fn refresh_private(&mut self, snapshot: &Snapshot) {
        self.refresh_events(snapshot);
        self.frame_self.clear();
        self.frame_self
            .extend(snapshot.players.iter().map(|p| (p.id, p.clone())));
        self.players
            .retain(|id, _| self.frame_self.contains_key(id));
        let live_monsters = snapshot
            .monsters
            .iter()
            .map(|m| m.id)
            .collect::<BTreeSet<_>>();
        self.monsters.retain(|id, _| live_monsters.contains(id));
        let mut public_players_changed = false;
        for p in &snapshot.players {
            // A player can join between the 10Hz pose-bank updates. New party
            // membership must have an immediately available public record.
            if !self.players.contains_key(&p.id)
                && p.id != 0
                && p.hp <= p.max_hp
                && p.y.is_finite()
                && check_xy(p.x, p.z, self.zone_limit).is_ok()
                && let Ok(facing) = wire::quantize_facing(p.facing)
            {
                self.players.insert(
                    p.id,
                    Arc::new(Record {
                        id: p.id,
                        groups: vec![
                            coord(p.x, p.z),
                            facing.to_le_bytes().to_vec(),
                            [p.hp.to_le_bytes(), p.max_hp.to_le_bytes()].concat(),
                            vec![
                                u8::from(p.connected)
                                    | u8::from(p.down) << 1
                                    | u8::from(p.dodging) << 2
                                    | u8::from(p.guarding) << 3,
                            ],
                            vec![p.anim],
                            p.y.to_le_bytes().to_vec(),
                        ],
                    }),
                );
                self.cells.entry(cell(p.x, p.z)).or_default().push(p.id);
                self.player_xy.insert(p.id, (p.x, p.z));
                public_players_changed = true;
            }
            if let Some(record) = self.players.get_mut(&p.id) {
                let health = [p.hp.to_le_bytes(), p.max_hp.to_le_bytes()].concat();
                let flags = vec![
                    u8::from(p.connected)
                        | u8::from(p.down) << 1
                        | u8::from(p.dodging) << 2
                        | u8::from(p.guarding) << 3,
                ];
                let anim = vec![p.anim];
                let y = p.y.to_le_bytes().to_vec();
                if record.groups[2] != health
                    || record.groups[3] != flags
                    || record.groups[4] != anim
                    || record.groups[5] != y
                {
                    let record = Arc::make_mut(record);
                    record.groups[2] = health;
                    record.groups[3] = flags;
                    record.groups[4] = anim;
                    record.groups[5] = y;
                    public_players_changed = true;
                }
            }
        }
        if public_players_changed {
            self.shared.clear();
            self.patches.clear();
            self.states.clear();
        }
        // State deadlines make countdowns tick locally without sending a new
        // record every tick. Changes and telegraph endpoints remain immediate.
        let mut changed = false;
        for m in &snapshot.monsters {
            if let Some(record) = self.monsters.get_mut(&m.id) {
                let flags = vec![(m.flags & 2) | u8::from(m.active)];
                let state = [
                    vec![m.state, m.ability],
                    (if m.state_ticks == 0 {
                        0
                    } else {
                        snapshot.tick + u64::from(m.state_ticks)
                    })
                    .to_le_bytes()
                    .to_vec(),
                ]
                .concat();
                let target = coord(m.target_x, m.target_z);
                let health = [m.hp.to_le_bytes(), m.max_hp.to_le_bytes()].concat();
                if record.groups[2] != health
                    || record.groups[3] != flags
                    || record.groups[4] != state
                    || record.groups[5] != target
                {
                    let record = Arc::make_mut(record);
                    record.groups[2] = health;
                    record.groups[3] = flags;
                    record.groups[4] = state;
                    record.groups[5] = target;
                    changed = true;
                }
            }
        }
        if changed {
            self.shared.clear();
            self.patches.clear();
            self.states.clear();
        }
    }
    fn candidates(&self, cells: &HashMap<(i32, i32), Vec<u32>>, x: f32, z: f32) -> Vec<u32> {
        let (cx, cz) = cell(x, z);
        let mut ids = Vec::new();
        for dx in -1..=1 {
            for dz in -1..=1 {
                if let Some(rows) = cells.get(&(cx + dx, cz + dz)) {
                    ids.extend(rows);
                }
            }
        }
        ids
    }
    fn ordinary_ids(&self, player_id: u32) -> (Vec<u32>, Vec<u32>) {
        let Some(own) = self.frame_self.get(&player_id) else {
            return (vec![], vec![]);
        };
        let mut players = self
            .candidates(&self.cells, own.x, own.z)
            .into_iter()
            .filter(|id| self.frame_self.get(id).is_some_and(|p| p.connected))
            .filter_map(|id| {
                self.player_xy
                    .get(&id)
                    .map(|(x, z)| (id, (*x - own.x).hypot(*z - own.z)))
            })
            .filter(|(_, distance)| *distance <= INTEREST_RADIUS)
            .collect::<Vec<_>>();
        let nearest_players = ORDINARY_PLAYERS.min(players.len());
        if players.len() > nearest_players {
            players.select_nth_unstable_by(nearest_players, |a, b| {
                a.1.total_cmp(&b.1).then(a.0.cmp(&b.0))
            });
            players.truncate(nearest_players);
        }
        players.sort_by(|a, b| a.1.total_cmp(&b.1).then(a.0.cmp(&b.0)));
        let mut monsters = self
            .candidates(&self.monster_cells, own.x, own.z)
            .into_iter()
            .filter_map(|id| {
                self.monster_xy
                    .get(&id)
                    .map(|(x, z)| (id, (*x - own.x).hypot(*z - own.z)))
            })
            .filter(|(_, distance)| *distance <= INTEREST_RADIUS)
            .collect::<Vec<_>>();
        let nearest_monsters = ORDINARY_MONSTERS.min(monsters.len());
        if monsters.len() > nearest_monsters {
            monsters.select_nth_unstable_by(nearest_monsters, |a, b| {
                a.1.total_cmp(&b.1).then(a.0.cmp(&b.0))
            });
            monsters.truncate(nearest_monsters);
        }
        monsters.sort_by(|a, b| a.1.total_cmp(&b.1).then(a.0.cmp(&b.0)));
        (
            players.into_iter().map(|p| p.0).collect(),
            monsters.into_iter().map(|m| m.0).collect(),
        )
    }
    pub fn select(
        &self,
        snapshot: &Snapshot,
        player_id: u32,
        party: &BTreeSet<u32>,
        target: u32,
    ) -> VisibleState {
        let (players, monsters) = self.ordinary_ids(player_id);
        self.materialize(snapshot, player_id, party, target, &players, &monsters)
    }
    pub fn select_cached(
        &mut self,
        snapshot: &Snapshot,
        player_id: u32,
        party: &BTreeSet<u32>,
        target: u32,
        cache: &mut OrdinaryMembership,
        context: InterestContext,
    ) -> VisibleState {
        let Some(own) = self.frame_self.get(&player_id) else {
            return VisibleState::default();
        };
        let now = Instant::now();
        let current_cell = cell(own.x, own.z);
        let removed = cache
            .players
            .iter()
            .any(|id| !self.frame_self.get(id).is_some_and(|p| p.connected))
            || cache
                .monsters
                .iter()
                .any(|id| !self.monsters.contains_key(id));
        let jumped = (own.x - cache.last_position.0).hypot(own.z - cache.last_position.1) > 2.0;
        let refresh = cache.context != Some(context)
            || cache.cell != current_cell
            || jumped
            || removed
            || snapshot.tick >= cache.next_tick
            || cache
                .refreshed
                .is_none_or(|time| now.duration_since(time) >= Duration::from_millis(100));
        if refresh {
            let (players, monsters) = self.ordinary_ids(player_id);
            cache.players = players;
            cache.monsters = monsters;
            cache.context = Some(context);
            cache.cell = current_cell;
            cache.refreshed = Some(now);
            cache.next_tick = snapshot.tick
                + if snapshot.tick % 2 == u64::from(player_id) % 2 {
                    2
                } else {
                    1
                };
            self.ordinary_cache_refreshes += 1;
        } else {
            self.ordinary_cache_hits += 1;
        }
        cache.last_position = (own.x, own.z);
        self.materialize(
            snapshot,
            player_id,
            party,
            target,
            &cache.players,
            &cache.monsters,
        )
    }
    fn materialize(
        &self,
        snapshot: &Snapshot,
        player_id: u32,
        party: &BTreeSet<u32>,
        target: u32,
        ordinary_players: &[u32],
        ordinary_monsters: &[u32],
    ) -> VisibleState {
        let mut player_ids = party.clone();
        player_ids.remove(&player_id);
        player_ids.extend(ordinary_players.iter().copied());
        let mut monster_ids = snapshot
            .monsters
            .iter()
            .filter(|m| {
                m.id == target
                    || m.target_player_id
                        .is_some_and(|id| id == player_id || party.contains(&id))
            })
            .map(|m| m.id)
            .collect::<BTreeSet<_>>();
        for id in ordinary_monsters {
            if monster_ids.len() < VISIBLE_MONSTER_LIMIT {
                monster_ids.insert(*id);
            }
        }
        VisibleState {
            players: player_ids
                .into_iter()
                .filter_map(|id| self.players.get(&id).map(|r| (id, r.clone())))
                .filter(|(id, _)| *id != player_id)
                .take(VISIBLE_PLAYER_LIMIT - 1)
                .collect(),
            monsters: monster_ids
                .into_iter()
                .filter_map(|id| self.monsters.get(&id).map(|r| (id, r.clone())))
                .take(VISIBLE_MONSTER_LIMIT)
                .collect(),
            pets: BTreeMap::new(),
            event_max: 0,
        }
    }
    fn patch(&mut self, kind: u8, current: &Record, old: Option<&Record>) -> Arc<[u8]> {
        self.record_key_constructions += 1;
        let old_key = old.map(flatten).unwrap_or_default();
        self.key_bytes_copied += old_key.len() as u64;
        let key = (kind, current.id, old_key);
        if let Some(bytes) = self.patches.get(&key) {
            return bytes.clone();
        }
        let mut mask = 0u8;
        for (index, group) in current.groups.iter().enumerate() {
            if old.is_none_or(|o| o.groups[index] != *group) {
                mask |= 1 << index;
            }
        }
        if mask == 0 {
            return Arc::from([]);
        }
        let mut compact = None;
        if mask & 1 != 0 {
            if let Some(old) = old {
                let cx = f32::from_le_bytes(current.groups[0][0..4].try_into().unwrap());
                let cz = f32::from_le_bytes(current.groups[0][4..8].try_into().unwrap());
                let ox = f32::from_le_bytes(old.groups[0][0..4].try_into().unwrap());
                let oz = f32::from_le_bytes(old.groups[0][4..8].try_into().unwrap());
                let dx = ((cx - ox) * 128.0).round();
                let dz = ((cz - oz) * 128.0).round();
                if (-128.0..=127.0).contains(&dx) && (-128.0..=127.0).contains(&dz) {
                    mask |= 128;
                    compact = Some([dx as i8 as u8, dz as i8 as u8]);
                }
            }
        }
        let mut bytes = current.id.to_le_bytes().to_vec();
        bytes.push(mask);
        for (index, group) in current.groups.iter().enumerate() {
            if mask & (1 << index) != 0 {
                if index == 0 && compact.is_some() {
                    bytes.extend(compact.unwrap());
                } else {
                    bytes.extend(group);
                }
            }
        }
        let bytes: Arc<[u8]> = bytes.into();
        self.record_encodes += 1;
        self.patches.insert(key, bytes.clone());
        bytes
    }
    fn collection(
        &mut self,
        payload: &mut Vec<u8>,
        kind: u8,
        current: &Records,
        old: Option<&Records>,
    ) -> Result<(), DecodeError> {
        let mut changes = Vec::new();
        for (id, record) in current {
            self.delta_comparisons += 1;
            if old.and_then(|o| o.get(id)).is_some_and(|prior| {
                Arc::ptr_eq(record, prior) || record.as_ref() == prior.as_ref()
            }) {
                self.unchanged_record_skips += 1;
                continue;
            }
            let bytes = self.patch(
                kind,
                record,
                old.and_then(|o| o.get(id)).map(|r| r.as_ref()),
            );
            if !bytes.is_empty() {
                changes.push(bytes);
            }
        }
        let removed = old
            .map(|o| {
                o.keys()
                    .filter(|id| !current.contains_key(id))
                    .copied()
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        if changes.len() > 64 || removed.len() > 64 {
            return Err(DecodeError::TooLarge);
        }
        payload.push(changes.len() as u8);
        payload.push(removed.len() as u8);
        for c in changes {
            payload.extend(c.iter());
        }
        for id in removed {
            payload.extend(id.to_le_bytes());
        }
        Ok(())
    }
    pub fn packet(
        &mut self,
        snapshot: &Snapshot,
        mut current: VisibleState,
        stream: &mut Stream,
        epoch: u32,
        player_id: u32,
        party: &BTreeSet<u32>,
        ack: (u32, f32, f32, u8),
        zone_limit: f32,
    ) -> Result<Vec<u8>, DecodeError> {
        if epoch == 0 {
            return Err(DecodeError::InvalidField);
        }
        check_xy(ack.1, ack.2, zone_limit)?;
        // More than the bounded receipt window without an ACK requires a full;
        // this also makes overwritten watch slots safe for a paused writer.
        let baseline = stream
            .acknowledged
            .clone()
            .filter(|(tick, _)| snapshot.tick.saturating_sub(*tick) <= BASELINE_LIMIT as u64);
        let baseline_tick = baseline.as_ref().map(|(t, _)| *t).unwrap_or(0);
        let old = baseline.as_ref().map(|(_, s)| s.as_ref());
        let event_floor = old.map(|o| o.event_max).unwrap_or(0);
        let mut candidates = BTreeSet::new();
        for id in std::iter::once(&player_id)
            .chain(party.iter())
            .chain(current.players.keys())
        {
            if let Some(events) = self.player_events.get(id) {
                candidates.extend(events.iter().copied());
            }
        }
        candidates.extend(self.monster_only_events.iter().copied());
        let mut events = candidates
            .into_iter()
            .filter_map(|id| self.frame_events.get(&id))
            .filter(|e| {
                e.id > event_floor && (essential(e, player_id, party) || visible_event(e, &current))
            })
            .collect::<Vec<_>>();
        events.sort_by_key(|e| {
            (
                if e.source_kind == 0 && e.source_id == player_id
                    || e.target_kind == 1 && e.target_id == player_id
                {
                    0
                } else if essential(e, player_id, party) {
                    1
                } else {
                    2
                },
                e.id,
            )
        });
        self.essential_event_overflows += events
            .iter()
            .filter(|e| essential(e, player_id, party))
            .count()
            .saturating_sub(64) as u64;
        events.truncate(64);
        let events = events.into_iter().cloned().collect::<Vec<_>>();
        current.event_max = old
            .map(|o| o.event_max)
            .unwrap_or(0)
            .max(events.iter().map(|e| e.id).max().unwrap_or(0));
        let mut key = vec![baseline_tick];
        if let Some(old) = old {
            for records in [&old.players, &old.monsters, &old.pets] {
                key.push(records.len() as u64);
                key.extend(records.keys().map(|id| u64::from(*id)));
            }
        } else {
            key.extend([0, 0, 0]);
        }
        for records in [&current.players, &current.monsters, &current.pets] {
            key.push(records.len() as u64);
            key.extend(records.keys().map(|id| u64::from(*id)));
        }
        key.push(events.len() as u64);
        key.extend(events.iter().map(|e| e.id));
        let shared = if let Some(bytes) = self.shared.get(&key) {
            self.shared_hits += 1;
            bytes.clone()
        } else {
            let mut payload = Vec::new();
            self.collection(&mut payload, 0, &current.players, old.map(|o| &o.players))?;
            self.collection(&mut payload, 1, &current.monsters, old.map(|o| &o.monsters))?;
            self.collection(&mut payload, 2, &current.pets, old.map(|o| &o.pets))?;
            payload.push(events.len() as u8);
            for event in events {
                let bytes = if let Some(bytes) = self.event_records.get(&event.id) {
                    bytes.clone()
                } else {
                    let bytes: Arc<[u8]> = wire::encode_event_record(&event, zone_limit)?.into();
                    self.event_records.insert(event.id, bytes.clone());
                    bytes
                };
                payload.extend(bytes.iter());
            }
            let bytes: Arc<[u8]> = payload.into();
            self.shared_encodes += 1;
            self.shared.insert(key, bytes.clone());
            bytes
        };
        let targeting = snapshot
            .monsters
            .iter()
            .filter(|m| {
                current.monsters.contains_key(&m.id) && m.target_player_id == Some(player_id)
            })
            .map(|m| m.id)
            .collect::<Vec<_>>();
        let mut payload = epoch.to_le_bytes().to_vec();
        payload.extend(snapshot.tick.to_le_bytes());
        payload.extend(baseline_tick.to_le_bytes());
        payload.extend(ack.0.to_le_bytes());
        payload.push(ack.3);
        payload.extend(ack.1.to_le_bytes());
        payload.extend(ack.2.to_le_bytes());
        let own = self
            .frame_self
            .get(&player_id)
            .ok_or(DecodeError::InvalidField)?;
        payload.extend(own.id.to_le_bytes());
        payload.extend(own.x.to_le_bytes());
        payload.extend(own.z.to_le_bytes());
        payload.extend(wire::quantize_facing(own.facing)?.to_le_bytes());
        payload.extend(own.hp.to_le_bytes());
        payload.extend(own.max_hp.to_le_bytes());
        payload.push(
            u8::from(own.connected)
                | u8::from(own.down) << 1
                | u8::from(own.dodging) << 2
                | u8::from(own.guarding) << 3,
        );
        payload.push(own.anim);
        payload.extend(own.y.to_le_bytes());
        payload.push(targeting.len() as u8);
        for id in targeting {
            payload.extend(id.to_le_bytes());
        }
        payload.extend(shared.iter());
        let bytes = wire::packet(0x86, payload)?;
        if stream.history.len() >= BASELINE_LIMIT {
            stream.history.pop_front();
        }
        let mut state_key = vec![current.event_max];
        for rows in [&current.players, &current.monsters, &current.pets] {
            state_key.push(rows.len() as u64);
            state_key.extend(rows.keys().map(|id| u64::from(*id)));
        }
        let state = self
            .states
            .entry(state_key)
            .or_insert_with(|| Arc::new(current))
            .clone();
        stream.history.push_back((snapshot.tick, state));
        Ok(bytes)
    }
}
fn check_xy(x: f32, z: f32, limit: f32) -> Result<(), DecodeError> {
    if !x.is_finite()
        || !z.is_finite()
        || x.abs() > limit.min(4096.0)
        || z.abs() > limit.min(4096.0)
    {
        Err(DecodeError::InvalidField)
    } else {
        Ok(())
    }
}
fn essential(e: &CombatEvent, own: u32, party: &BTreeSet<u32>) -> bool {
    e.source_kind == 0 && (e.source_id == own || party.contains(&e.source_id))
        || e.target_kind == 1 && (e.target_id == own || party.contains(&e.target_id))
}
fn visible_event(e: &CombatEvent, s: &VisibleState) -> bool {
    (if e.source_kind == 0 {
        s.players.contains_key(&e.source_id)
    } else {
        s.monsters.contains_key(&e.source_id)
    }) && (if e.target_kind == 0 {
        s.monsters.contains_key(&e.target_id)
    } else {
        s.players.contains_key(&e.target_id)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn snapshot() -> Snapshot {
        let mut world = crate::world::World::new(
            &crate::content::test_content(),
            crate::character::CharacterStore::shared(),
        );
        world.join([1; 32]).unwrap();
        world.advance()
    }
    #[test]
    fn ack_requires_published_tick_and_history_is_bounded() {
        let snapshot = snapshot();
        let own = snapshot.players[0].id;
        let mut stream = Stream::default();
        assert!(!stream.acknowledge(900, false));
        for i in 1..100 {
            let mut s = snapshot.clone();
            s.tick = i;
            let mut encoder = TickEncoder::new(&s, 308.0).unwrap();
            let state = encoder.select(&s, own, &BTreeSet::new(), 0);
            encoder
                .packet(
                    &s,
                    state,
                    &mut stream,
                    1,
                    own,
                    &BTreeSet::new(),
                    (0, 0.0, 0.0, 0),
                    308.0,
                )
                .unwrap();
        }
        assert_eq!(stream.retained_baselines(), 32);
        assert!(!stream.acknowledge(1, false));
        stream.mark_sent(99);
        assert!(stream.acknowledge(99, false));
        assert!(!stream.acknowledge(98, false));
        assert!(stream.acknowledge(0, true));
        assert_eq!(stream.retained_baselines(), 0);
    }
    #[test]
    fn recipient_private_header_never_changes_shared_payload() {
        let snapshot = snapshot();
        let own = snapshot.players[0].id;
        let mut encoder = TickEncoder::new(&snapshot, 308.0).unwrap();
        let state = encoder.select(&snapshot, own, &BTreeSet::new(), 0);
        let a = encoder
            .packet(
                &snapshot,
                state.clone(),
                &mut Stream::default(),
                1,
                own,
                &BTreeSet::new(),
                (1, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
        let b = encoder
            .packet(
                &snapshot,
                state,
                &mut Stream::default(),
                2,
                own,
                &BTreeSet::new(),
                (2, 1.0, 1.0, 0),
                308.0,
            )
            .unwrap();
        assert_ne!(&a[6..39], &b[6..39]);
        assert_eq!(&a[64..], &b[64..]);
        assert_eq!(encoder.shared_encodes, 1);
        assert_eq!(encoder.shared_hits, 1);
    }
    #[test]
    fn cache_key_includes_acknowledged_membership() {
        let mut snapshot = snapshot();
        snapshot.tick = 42;
        let own = snapshot.players[0].id;
        let mut peer = snapshot.players[0].clone();
        peer.id = 9001;
        snapshot.players.push(peer.clone());
        peer.id = 9002;
        snapshot.players.push(peer);
        let mut encoder = TickEncoder::new(&snapshot, 308.0).unwrap();
        let current = encoder.select(&snapshot, own, &BTreeSet::new(), 0);
        let mut old_a = current.clone();
        old_a.players.remove(&9002);
        let mut old_b = current.clone();
        old_b.players.remove(&9001);
        let mut a = Stream::default();
        a.acknowledged = Some((41, Arc::new(old_a)));
        let mut b = Stream::default();
        b.acknowledged = Some((41, Arc::new(old_b)));
        let pa = encoder
            .packet(
                &snapshot,
                current.clone(),
                &mut a,
                1,
                own,
                &BTreeSet::new(),
                (0, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
        let pb = encoder
            .packet(
                &snapshot,
                current,
                &mut b,
                1,
                own,
                &BTreeSet::new(),
                (0, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
        assert_ne!(&pa[64..], &pb[64..]);
        assert_eq!(encoder.shared_encodes, 2);
    }
    #[test]
    fn targeting_you_overlay_is_private_even_when_public_state_is_shared() {
        let mut snapshot = snapshot();
        snapshot.tick = 42;
        let own = snapshot.players[0].id;
        let mut peer = snapshot.players[0].clone();
        peer.id = 9001;
        snapshot.players.push(peer);
        for monster in &mut snapshot.monsters {
            monster.target_player_id = None;
            monster.flags &= !2;
        }
        snapshot.monsters[0].target_player_id = Some(own);
        snapshot.monsters[0].flags = 3;
        let mut encoder = TickEncoder::new(&snapshot, 308.0).unwrap();
        let mut state = encoder.select(&snapshot, own, &BTreeSet::new(), 0);
        state.players.clear();
        let pa = encoder
            .packet(
                &snapshot,
                state.clone(),
                &mut Stream::default(),
                1,
                own,
                &BTreeSet::new(),
                (0, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
        let pb = encoder
            .packet(
                &snapshot,
                state,
                &mut Stream::default(),
                1,
                9001,
                &BTreeSet::new(),
                (0, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
        assert_eq!(pa[63], 1);
        assert_eq!(pb[63], 0);
        assert_eq!(&pa[68..], &pb[64..]);
        assert_eq!(encoder.shared_encodes, 1);
        assert_eq!(encoder.shared_hits, 1);
    }
    #[test]
    fn reserved_pet_collection_preserves_existing_zero_based_pet_state() {
        let mut snapshot = snapshot();
        let own = snapshot.players[0].id;
        snapshot.pets.push(crate::world::PetSnapshot {
            owner_id: own,
            x: 0.0,
            z: 0.0,
            kind: 0,
            flags: 1,
        });
        let mut encoder = TickEncoder::new(&snapshot, 308.0).unwrap();
        let state = encoder.select(&snapshot, own, &BTreeSet::new(), 0);
        assert!(state.pets.is_empty());
        encoder
            .packet(
                &snapshot,
                state,
                &mut Stream::default(),
                1,
                own,
                &BTreeSet::new(),
                (0, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
    }

    #[test]
    fn essential_events_survive_a_pool_larger_than_the_old_global_wire_cap() {
        let mut snapshot = snapshot();
        let own = snapshot.players[0].id;
        snapshot.events = (1..=100)
            .map(|id| CombatEvent {
                id,
                source_kind: 0,
                source_id: own + 1000,
                target_kind: 0,
                target_id: snapshot.monsters[0].id,
                action: crate::world::ActionKind::Attack,
                damage: 1,
                flags: 0,
                world_x: 0.0,
                world_z: 0.0,
            })
            .collect();
        snapshot.events.push(CombatEvent {
            id: 101,
            source_kind: 0,
            source_id: own,
            target_kind: 0,
            target_id: snapshot.monsters[0].id,
            action: crate::world::ActionKind::Attack,
            damage: 1,
            flags: 0,
            world_x: 0.0,
            world_z: 0.0,
        });
        let mut encoder = TickEncoder::new(&snapshot, 308.0).unwrap();
        let state = encoder.select(&snapshot, own, &BTreeSet::new(), 0);
        let mut stream = Stream::default();
        let packet = encoder
            .packet(
                &snapshot,
                state,
                &mut stream,
                1,
                own,
                &BTreeSet::new(),
                (0, 0.0, 0.0, 0),
                308.0,
            )
            .unwrap();
        assert!(packet.windows(8).any(|bytes| bytes == 101u64.to_le_bytes()));
        assert_eq!(stream.history.back().unwrap().1.event_max, 101);
        assert_eq!(
            encoder.event_records.len(),
            1,
            "off-AOI source hits on a visible monster are not broadcast"
        );
    }
    #[test]
    fn ordinary_cache_staggers_and_never_caches_vitals_or_essential_membership() {
        let mut s = snapshot();
        s.tick = 1;
        let own = s.players[0].id;
        let mut peer = s.players[0].clone();
        peer.id = 9001;
        peer.x = 100.0;
        s.players.push(peer);
        s.monsters[0].x = 100.0;
        s.monsters[0].z = 100.0;
        let mut encoder = TickEncoder::new(&s, 308.0).unwrap();
        let mut cache = OrdinaryMembership::default();
        let ctx = InterestContext {
            realm: 1,
            zone: 1,
            epoch: 1,
            teleport_revision: 0,
        };
        let first = encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        assert!(!first.players.contains_key(&9001));
        assert!(!first.monsters.contains_key(&s.monsters[0].id));
        assert_eq!(cache.next_tick, 3);
        s.tick = 2;
        s.players[1].hp = 0;
        s.players[1].down = true;
        s.monsters[0].target_player_id = Some(own);
        s.monsters[0].flags = 3;
        encoder.refresh_private(&s);
        let next = encoder.select_cached(&s, own, &BTreeSet::from([9001]), 0, &mut cache, ctx);
        assert_eq!(encoder.ordinary_cache_hits, 1);
        assert!(next.monsters.contains_key(&s.monsters[0].id));
        assert_eq!(
            u16::from_le_bytes(next.players[&9001].groups[2][..2].try_into().unwrap()),
            0
        );
        assert_eq!(next.players[&9001].groups[3][0] & 2, 2);
        s.monsters[0].target_player_id = None;
        encoder.refresh_private(&s);
        let changed = encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        assert!(!changed.players.contains_key(&9001));
        assert!(!changed.monsters.contains_key(&s.monsters[0].id));
        let mut joining = s.players[1].clone();
        joining.id = 9003;
        s.players.push(joining);
        encoder.refresh_private(&s);
        let immediate = encoder.select_cached(&s, own, &BTreeSet::from([9003]), 0, &mut cache, ctx);
        assert!(
            immediate.players.contains_key(&9003),
            "a newly joined party peer is essential on this tick"
        );
        cache.next_tick = u64::MAX;
        cache.refreshed = Some(Instant::now() - Duration::from_millis(101));
        let old = encoder.ordinary_cache_refreshes;
        encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        assert_eq!(encoder.ordinary_cache_refreshes, old + 1);
        let mut even_peer = s.players[1].clone();
        even_peer.id = 9002;
        s.players.push(even_peer);
        encoder.refresh_private(&s);
        let mut other = OrdinaryMembership::default();
        encoder.select_cached(&s, 9002, &BTreeSet::new(), 0, &mut other, ctx);
        assert_eq!(other.next_tick, 4);
    }
    #[test]
    fn ordinary_cache_invalidates_removal_cell_epoch_realm_zone_and_teleport() {
        let mut s = snapshot();
        s.tick = 1;
        let own = s.players[0].id;
        let mut peer = s.players[0].clone();
        peer.id = 9001;
        peer.x += 1.0;
        s.players.push(peer);
        let mut encoder = TickEncoder::new(&s, 308.0).unwrap();
        let mut cache = OrdinaryMembership::default();
        let mut ctx = InterestContext {
            realm: 1,
            zone: 1,
            epoch: 1,
            teleport_revision: 0,
        };
        encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        s.tick = 2;
        s.players[1].connected = false;
        encoder.refresh_private(&s);
        let selected = encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        assert!(!selected.players.contains_key(&9001));
        for change in 0..4 {
            let before = encoder.ordinary_cache_refreshes;
            match change {
                0 => ctx.epoch += 1,
                1 => ctx.realm += 1,
                2 => ctx.zone += 1,
                _ => ctx.teleport_revision += 1,
            };
            encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
            assert_eq!(encoder.ordinary_cache_refreshes, before + 1);
        }
        let before = encoder.ordinary_cache_refreshes;
        s.players[0].x = 33.0;
        encoder.refresh_private(&s);
        encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        assert_eq!(encoder.ordinary_cache_refreshes, before + 1);
        let mon = s.monsters[0].id;
        cache.monsters.push(mon);
        s.monsters.retain(|m| m.id != mon);
        encoder.refresh_private(&s);
        let selected = encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, ctx);
        assert!(!selected.monsters.contains_key(&mon));
    }
    #[test]
    fn ordinary_cache_keeps_rank_caps_and_current_private_self() {
        let mut s = snapshot();
        s.tick = 1;
        let own = s.players[0].id;
        for id in 100..200 {
            let mut p = s.players[0].clone();
            p.id = id;
            p.x += 1.0;
            s.players.push(p);
        }
        let mut encoder = TickEncoder::new(&s, 308.0).unwrap();
        let mut cache = OrdinaryMembership::default();
        let context = InterestContext {
            realm: 1,
            zone: 1,
            epoch: 1,
            teleport_revision: 0,
        };
        let first = encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, context);
        assert_eq!(first.players.len(), 15);
        assert!(first.players.contains_key(&100));
        assert!(!first.players.contains_key(&115));
        let ranked = cache.players.clone();
        s.tick = 2;
        s.players[0].x += 0.5;
        s.players[0].hp = 1;
        s.players[0].down = true;
        encoder.refresh_private(&s);
        let state = encoder.select_cached(&s, own, &BTreeSet::new(), 0, &mut cache, context);
        assert_eq!(cache.players, ranked);
        assert_eq!(encoder.ordinary_cache_hits, 1);
        let packet = encoder
            .packet(
                &s,
                state,
                &mut Stream::default(),
                1,
                own,
                &BTreeSet::new(),
                (5, s.players[0].x, s.players[0].z, 2),
                308.0,
            )
            .unwrap();
        assert_eq!(
            f32::from_le_bytes(packet[43..47].try_into().unwrap()),
            s.players[0].x
        );
        assert_eq!(u16::from_le_bytes(packet[53..55].try_into().unwrap()), 1);
        assert_eq!(packet[57] & 2, 2);
        assert!(
            cache.players.len() <= ORDINARY_PLAYERS && cache.monsters.len() <= ORDINARY_MONSTERS
        );
    }
}
