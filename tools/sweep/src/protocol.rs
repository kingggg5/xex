//! Bounded protocol v7/v8 client. Delta reconstruction commits transactionally.
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Clone, Debug, Default)]
pub struct Player {
    pub id: u32,
    pub x: f32,
    pub z: f32,
    pub facing: u16,
    pub hp: u16,
    pub max_hp: u16,
    pub flags: u8,
    pub anim: u8,
    pub y: f32,
}
#[derive(Clone, Debug, Default)]
pub struct Monster {
    pub id: u32,
    pub x: f32,
    pub z: f32,
    pub facing: u16,
    pub hp: u32,
    pub max_hp: u32,
    pub flags: u8,
    pub state: u8,
    pub ability: u8,
    pub deadline: u64,
    pub target_x: f32,
    pub target_z: f32,
    pub kind: u8,
}
#[derive(Clone, Debug)]
pub struct Welcome {
    pub id: u32,
    pub epoch: u32,
    pub tick: u64,
    pub x: f32,
    pub z: f32,
    pub zone: u16,
    pub content_hash: u64,
    pub tick_hz: u8,
}
#[derive(Clone, Debug)]
pub struct Snapshot {
    pub tick: u64,
    pub baseline_tick: u64,
    pub own: Player,
    pub players: Vec<Player>,
    pub monsters: Vec<Monster>,
    pub event_count: usize,
    pub own_hit_ids: Vec<u64>,
}
#[derive(Debug)]
pub enum ServerMessage {
    Welcome(Welcome),
    Snapshot(Snapshot),
    Error { code: u16, version: u8 },
    Action { accepted: bool, reason: u8 },
    Pong { nonce: u32, tick: u64 },
    Cold(Value),
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CodecError {
    Invalid(&'static str),
    Resync(&'static str),
}
type Result<T> = std::result::Result<T, CodecError>;
struct Reader<'a> {
    b: &'a [u8],
    p: usize,
}
impl<'a> Reader<'a> {
    fn take<const N: usize>(&mut self) -> Result<[u8; N]> {
        let s = self
            .b
            .get(self.p..self.p + N)
            .ok_or(CodecError::Invalid("truncated"))?;
        self.p += N;
        Ok(s.try_into().unwrap())
    }
    fn u8(&mut self) -> Result<u8> {
        Ok(self.take::<1>()?[0])
    }
    fn i8(&mut self) -> Result<i8> {
        Ok(self.u8()? as i8)
    }
    fn u16(&mut self) -> Result<u16> {
        Ok(u16::from_le_bytes(self.take()?))
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take()?))
    }
    fn u64(&mut self) -> Result<u64> {
        Ok(u64::from_le_bytes(self.take()?))
    }
    fn coord(&mut self) -> Result<f32> {
        let x = f32::from_le_bytes(self.take()?);
        if !x.is_finite() || x.abs() > 4096.0 {
            return Err(CodecError::Invalid("coordinate"));
        }
        Ok(x)
    }
    fn finish(&self) -> Result<()> {
        if self.p == self.b.len() {
            Ok(())
        } else {
            Err(CodecError::Invalid("trailing_bytes"))
        }
    }
}
fn valid_player(p: &Player) -> Result<()> {
    if p.id == 0 || p.max_hp == 0 || p.hp > p.max_hp || p.flags & !15 != 0 {
        Err(CodecError::Invalid("player"))
    } else {
        Ok(())
    }
}
fn read_player(r: &mut Reader, y: bool) -> Result<Player> {
    let mut p = Player {
        id: r.u32()?,
        x: r.coord()?,
        z: r.coord()?,
        facing: r.u16()?,
        hp: r.u16()?,
        max_hp: r.u16()?,
        flags: r.u8()?,
        anim: r.u8()?,
        y: 0.0,
    };
    if y {
        p.y = r.coord()?
    }
    valid_player(&p)?;
    Ok(p)
}
fn events(r: &mut Reader, n: usize, own: u32) -> Result<Vec<u64>> {
    if n > 64 {
        return Err(CodecError::Invalid("events_limit"));
    }
    let mut ids = BTreeSet::new();
    let mut hits = Vec::new();
    for _ in 0..n {
        let id = r.u64()?;
        let sk = r.u8()?;
        let sid = r.u32()?;
        let tk = r.u8()?;
        let tid = r.u32()?;
        let action = r.u8()?;
        let amount = r.u16()?;
        let flags = r.u8()?;
        r.coord()?;
        r.coord()?;
        if id == 0
            || !ids.insert(id)
            || sk > 1
            || tk > 1
            || sid == 0
            || tid == 0
            || !(1..=5).contains(&action)
            || flags & 128 != 0
            || flags & 64 != 0 && (amount != 0 || flags & 33 != 0)
            || flags & 32 != 0 && amount == 0
        {
            return Err(CodecError::Invalid("event"));
        }
        if sk == 0 && sid == own && tk == 0 && amount > 0 {
            hits.push(id);
        }
    }
    Ok(hits)
}
#[derive(Clone, Default)]
struct Baseline {
    players: BTreeMap<u32, Player>,
    monsters: BTreeMap<u32, Monster>,
}
pub struct Decoder {
    pub version: u8,
    pub welcome: Option<Welcome>,
    last_tick: u64,
    baselines: VecDeque<(u64, Baseline)>,
}
impl Decoder {
    pub fn new(version: u8) -> Self {
        Self {
            version,
            welcome: None,
            last_tick: 0,
            baselines: VecDeque::new(),
        }
    }
    pub fn last_ack(&self) -> Option<(u32, u64)> {
        self.welcome
            .as_ref()
            .filter(|_| self.last_tick > 0)
            .map(|w| (w.epoch, self.last_tick))
    }
    pub fn decode(&mut self, b: &[u8]) -> Result<ServerMessage> {
        if b.len() < 6
            || b.len() > 16384
            || b[0..2] != [0x31, 0xa7]
            || u16::from_le_bytes([b[4], b[5]]) as usize + 6 != b.len()
        {
            return Err(CodecError::Invalid("envelope"));
        }
        // Only the explicit mismatch error may announce another protocol version.
        if b[2] != self.version
            && !(b[3] == 0x83 && b.len() == 8 && b[6..8] == [1, 0] && (7..=8).contains(&b[2]))
        {
            return Err(CodecError::Invalid("version"));
        }
        let mut r = Reader { b: &b[6..], p: 0 };
        let m = match b[3] {
            0x81 => {
                let w = Welcome {
                    id: r.u32()?,
                    epoch: r.u32()?,
                    tick: r.u64()?,
                    x: r.coord()?,
                    z: r.coord()?,
                    zone: r.u16()?,
                    content_hash: r.u64()?,
                    tick_hz: r.u8()?,
                };
                if w.id == 0 || w.epoch == 0 || w.tick_hz != 20 {
                    return Err(CodecError::Invalid("welcome"));
                }
                r.finish()?;
                self.welcome = Some(w.clone());
                self.last_tick = 0;
                self.baselines.clear();
                ServerMessage::Welcome(w)
            }
            0x82 => ServerMessage::Snapshot(self.full(&mut r)?),
            0x86 if self.version == 8 => ServerMessage::Snapshot(self.interest(&mut r)?),
            0x83 => {
                let code = r.u16()?;
                if !(1..=8).contains(&code) {
                    return Err(CodecError::Invalid("error_code"));
                }
                ServerMessage::Error {
                    code,
                    version: b[2],
                }
            }
            0x84 => {
                r.u32()?;
                let accepted = r.u8()?;
                let reason = r.u8()?;
                r.u64()?;
                if accepted > 1 || reason > 7 {
                    return Err(CodecError::Invalid("action_result"));
                }
                ServerMessage::Action {
                    accepted: accepted == 1,
                    reason,
                }
            }
            0x85 => {
                let nonce = r.u32()?;
                r.u32()?;
                ServerMessage::Pong {
                    nonce,
                    tick: r.u64()?,
                }
            }
            0x90 => {
                if r.b.len() > 4096 {
                    return Err(CodecError::Invalid("cold_limit"));
                }
                let v: Value =
                    serde_json::from_slice(r.b).map_err(|_| CodecError::Invalid("cold_json"))?;
                if v["t"].as_str().is_none() {
                    return Err(CodecError::Invalid("cold_tag"));
                }
                r.p = r.b.len();
                ServerMessage::Cold(v)
            }
            _ => return Err(CodecError::Invalid("message_type")),
        };
        r.finish()?;
        Ok(m)
    }
    fn full(&self, r: &mut Reader) -> Result<Snapshot> {
        let w = self
            .welcome
            .as_ref()
            .ok_or(CodecError::Invalid("snapshot_before_welcome"))?;
        let tick = r.u64()?;
        r.u32()?;
        let flags = r.u8()?;
        let x = r.coord()?;
        let z = r.coord()?;
        let np = r.u8()? as usize;
        let nm = r.u8()? as usize;
        let ne = r.u8()? as usize;
        if np > 50 || nm > 64 || ne > 64 {
            return Err(CodecError::Invalid("full_count"));
        }
        let mut players = Vec::new();
        let mut ids = BTreeSet::new();
        for _ in 0..np {
            let p = read_player(r, false)?;
            if !ids.insert(p.id) {
                return Err(CodecError::Invalid("duplicate_player"));
            }
            players.push(p)
        }
        let mut monsters = Vec::new();
        ids.clear();
        for _ in 0..nm {
            let id = r.u32()?;
            let kind = r.u8()?;
            let mut m = Monster {
                id,
                kind,
                x: r.coord()?,
                z: r.coord()?,
                facing: r.u16()?,
                hp: r.u32()?,
                max_hp: r.u32()?,
                flags: r.u8()?,
                state: r.u8()?,
                ability: r.u8()?,
                ..Default::default()
            };
            m.deadline = tick + r.u16()? as u64;
            m.target_x = r.coord()?;
            m.target_z = r.coord()?;
            if id == 0
                || kind == 0
                || m.max_hp == 0
                || m.hp > m.max_hp
                || m.flags & !7 != 0
                || !ids.insert(id)
            {
                return Err(CodecError::Invalid("monster"));
            }
            monsters.push(m)
        }
        let own_hit_ids = events(r, ne, w.id)?;
        let own = players
            .iter()
            .find(|p| p.id == w.id)
            .cloned()
            .unwrap_or(Player {
                id: w.id,
                x,
                z,
                flags,
                ..Default::default()
            });
        Ok(Snapshot {
            tick,
            baseline_tick: 0,
            own,
            players,
            monsters,
            event_count: ne,
            own_hit_ids,
        })
    }
    fn interest(&mut self, r: &mut Reader) -> Result<Snapshot> {
        let w = self
            .welcome
            .as_ref()
            .ok_or(CodecError::Resync("missing_welcome"))?;
        let epoch = r.u32()?;
        let tick = r.u64()?;
        let base = r.u64()?;
        r.u32()?;
        let own_flags = r.u8()?;
        r.coord()?;
        r.coord()?;
        if epoch != w.epoch {
            return Err(CodecError::Resync("wrong_epoch"));
        }
        if tick <= self.last_tick {
            return Err(CodecError::Resync("stale_tick"));
        }
        if base >= tick {
            return Err(CodecError::Resync("future_baseline"));
        }
        if own_flags & !15 != 0 {
            return Err(CodecError::Invalid("own_flags"));
        }
        let own = read_player(r, true)?;
        if own.id != w.id {
            return Err(CodecError::Invalid("own_identity"));
        }
        let nt = r.u8()?;
        if nt > 64 {
            return Err(CodecError::Invalid("targets_limit"));
        }
        let mut targets = BTreeSet::new();
        for _ in 0..nt {
            let id = r.u32()?;
            if id == 0 || !targets.insert(id) {
                return Err(CodecError::Invalid("target_identity"));
            }
        }
        let mut next = if base == 0 {
            Baseline::default()
        } else {
            self.baselines
                .iter()
                .find(|(t, _)| *t == base)
                .map(|(_, b)| b.clone())
                .ok_or(CodecError::Resync("missing_baseline"))?
        };
        let changed = r.u8()?;
        let removed = r.u8()?;
        counts(changed, removed, base)?;
        let mut seen = BTreeSet::new();
        for _ in 0..changed {
            let id = r.u32()?;
            let mask = r.u8()?;
            let prior = next.players.get(&id);
            patch_check(id, mask, 63, prior.is_some(), &mut seen)?;
            if id == w.id {
                return Err(CodecError::Invalid("own_in_peers"));
            }
            let mut p = prior.cloned().unwrap_or(Player {
                id,
                ..Default::default()
            });
            coords(r, mask, &mut p.x, &mut p.z)?;
            if mask & 2 != 0 {
                p.facing = r.u16()?
            }
            if mask & 4 != 0 {
                p.hp = r.u16()?;
                p.max_hp = r.u16()?
            }
            if mask & 8 != 0 {
                p.flags = r.u8()?
            }
            if mask & 16 != 0 {
                p.anim = r.u8()?
            }
            if mask & 32 != 0 {
                p.y = r.coord()?
            }
            valid_player(&p)?;
            next.players.insert(id, p);
        }
        remove(r, removed, &mut next.players, &mut seen)?;
        if next.players.len() > 63 {
            return Err(CodecError::Invalid("peer_limit"));
        }
        let changed = r.u8()?;
        let removed = r.u8()?;
        counts(changed, removed, base)?;
        seen.clear();
        for _ in 0..changed {
            let id = r.u32()?;
            let mask = r.u8()?;
            let prior = next.monsters.get(&id);
            patch_check(id, mask, 127, prior.is_some(), &mut seen)?;
            let mut m = prior.cloned().unwrap_or(Monster {
                id,
                ..Default::default()
            });
            coords(r, mask, &mut m.x, &mut m.z)?;
            if mask & 2 != 0 {
                m.facing = r.u16()?
            }
            if mask & 4 != 0 {
                m.hp = r.u32()?;
                m.max_hp = r.u32()?
            }
            if mask & 8 != 0 {
                m.flags = r.u8()?
            }
            if mask & 16 != 0 {
                m.state = r.u8()?;
                m.ability = r.u8()?;
                m.deadline = r.u64()?
            }
            if mask & 32 != 0 {
                m.target_x = r.coord()?;
                m.target_z = r.coord()?
            }
            if mask & 64 != 0 {
                m.kind = r.u8()?
            }
            if m.kind == 0
                || m.hp > m.max_hp
                || m.max_hp == 0
                || m.flags & !3 != 0
                || m.deadline > tick.saturating_add(65535)
            {
                return Err(CodecError::Invalid("shared_monster"));
            }
            next.monsters.insert(id, m);
        }
        remove(r, removed, &mut next.monsters, &mut seen)?;
        if next.monsters.len() > 64 {
            return Err(CodecError::Invalid("monster_limit"));
        }
        // Pets are reserved in the current client contract. Fail loudly on schema drift.
        if r.u8()? != 0 || r.u8()? != 0 {
            return Err(CodecError::Invalid("reserved_pets"));
        }
        for id in &targets {
            if !next.monsters.contains_key(id) {
                return Err(CodecError::Resync("unknown_target"));
            }
        }
        let ne = r.u8()? as usize;
        let own_hit_ids = events(r, ne, w.id)?;
        r.finish()?;
        let mut players = vec![own.clone()];
        players.extend(next.players.values().cloned());
        let monsters = next
            .monsters
            .values()
            .cloned()
            .map(|mut m| {
                if targets.contains(&m.id) {
                    m.flags |= 6
                }
                m
            })
            .collect();
        self.baselines.push_back((tick, next));
        while self.baselines.len() > 32 {
            self.baselines.pop_front();
        }
        self.last_tick = tick;
        Ok(Snapshot {
            tick,
            baseline_tick: base,
            own,
            players,
            monsters,
            event_count: ne,
            own_hit_ids,
        })
    }
}
fn counts(c: u8, r: u8, b: u64) -> Result<()> {
    if c > 64 || r > 64 || b == 0 && r != 0 {
        Err(CodecError::Invalid("collection_count"))
    } else {
        Ok(())
    }
}
fn patch_check(id: u32, mask: u8, full: u8, prior: bool, seen: &mut BTreeSet<u32>) -> Result<()> {
    if id == 0
        || !seen.insert(id)
        || mask & full == 0
        || mask & !(full | 128) != 0
        || mask & 128 != 0 && (mask & 1 == 0 || !prior)
    {
        return Err(CodecError::Invalid("patch"));
    }
    if !prior && mask & full != full {
        return Err(CodecError::Resync("unknown_patch"));
    }
    Ok(())
}
fn coords(r: &mut Reader, mask: u8, x: &mut f32, z: &mut f32) -> Result<()> {
    if mask & 1 != 0 {
        if mask & 128 != 0 {
            *x += r.i8()? as f32 / 128.0;
            *z += r.i8()? as f32 / 128.0;
            if x.abs() > 4096.0 || z.abs() > 4096.0 {
                return Err(CodecError::Invalid("relative_coordinate"));
            }
        } else {
            *x = r.coord()?;
            *z = r.coord()?
        }
    }
    Ok(())
}
fn remove<T>(
    r: &mut Reader,
    n: u8,
    map: &mut BTreeMap<u32, T>,
    seen: &mut BTreeSet<u32>,
) -> Result<()> {
    for _ in 0..n {
        let id = r.u32()?;
        if !seen.insert(id) || map.remove(&id).is_none() {
            return Err(CodecError::Resync("unknown_remove"));
        }
    }
    Ok(())
}
pub fn envelope(version: u8, kind: u8, p: &[u8]) -> Vec<u8> {
    let mut b = vec![0x31, 0xa7, version, kind];
    b.extend((p.len() as u16).to_le_bytes());
    b.extend(p);
    b
}
pub fn ticket_hex(s: &str) -> std::result::Result<[u8; 32], String> {
    if s.len() != 64 || !s.is_ascii() {
        return Err("invalid_ticket".into());
    }
    let mut a = [0; 32];
    for (i, v) in a.iter_mut().enumerate() {
        *v = u8::from_str_radix(&s[i * 2..i * 2 + 2], 16).map_err(|_| "invalid_ticket")?
    }
    if a == [0; 32] {
        return Err("invalid_ticket".into());
    }
    Ok(a)
}
pub fn join(v: u8, t: &[u8; 32]) -> Vec<u8> {
    envelope(v, 1, t)
}
pub fn input(v: u8, epoch: u32, seq: u32, x: f32, z: f32, facing: f32) -> Vec<u8> {
    let mut p = epoch.to_le_bytes().to_vec();
    p.extend(seq.to_le_bytes());
    for f in [x, z] {
        p.extend(((f.clamp(-1.0, 1.0) * 32767.0).round() as i16).to_le_bytes())
    }
    p.extend(angle(facing).to_le_bytes());
    envelope(v, 2, &p)
}
fn angle(a: f32) -> u16 {
    (a.rem_euclid(std::f32::consts::TAU) / std::f32::consts::TAU * 65535.0).round() as u16
}
pub fn action(v: u8, epoch: u32, seq: u32, aim: f32, target: u32, tick: u64) -> Vec<u8> {
    let mut p = epoch.to_le_bytes().to_vec();
    p.extend(seq.to_le_bytes());
    p.push(1);
    p.extend(angle(aim).to_le_bytes());
    p.extend(target.to_le_bytes());
    p.extend((tick as u32).to_le_bytes());
    envelope(v, 3, &p)
}
pub fn ping(v: u8, nonce: u32, ms: u32) -> Vec<u8> {
    let mut p = nonce.to_le_bytes().to_vec();
    p.extend(ms.to_le_bytes());
    envelope(v, 4, &p)
}
pub fn ack(v: u8, epoch: u32, tick: u64, resync: bool) -> Vec<u8> {
    let mut p = epoch.to_le_bytes().to_vec();
    p.extend(tick.to_le_bytes());
    p.push(u8::from(resync));
    envelope(v, 5, &p)
}
pub fn cold(v: u8, value: &Value) -> std::result::Result<Vec<u8>, String> {
    let p = serde_json::to_vec(value).map_err(|_| "cold_encoding")?;
    if p.len() > 512 || value["t"].as_str().is_none() {
        return Err("cold_limit".into());
    }
    Ok(envelope(v, 0x10, &p))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn own_hit_observation_requires_own_positive_monster_damage() {
        let mut bytes = Vec::new();
        for (id, source, target, amount) in [
            (1u64, 42u32, 0u8, 2u16),
            (2, 43, 0, 2),
            (3, 42, 0, 0),
            (4, 42, 1, 2),
        ] {
            bytes.extend(id.to_le_bytes());
            bytes.push(0);
            bytes.extend(source.to_le_bytes());
            bytes.push(target);
            bytes.extend(101u32.to_le_bytes());
            bytes.push(1);
            bytes.extend(amount.to_le_bytes());
            bytes.push(0);
            bytes.extend([0; 8]);
        }
        assert_eq!(
            events(&mut Reader { b: &bytes, p: 0 }, 4, 42).unwrap(),
            vec![1]
        );
    }
    fn bytes(s: &str) -> Vec<u8> {
        (0..s.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
            .collect()
    }
    #[test]
    fn repo_goldens_and_all_truncations() {
        for version in [7, 8] {
            let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join(format!("../../apps/protocol/golden-v{version}.json"));
            let g: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
            let fixtures = g["fixtures"].as_array().unwrap();
            let welcome = bytes(
                fixtures
                    .iter()
                    .find(|f| f["name"] == "welcome_basic")
                    .unwrap()["hex"]
                    .as_str()
                    .unwrap(),
            );
            for f in fixtures
                .iter()
                .filter(|f| f["direction"] == "server_to_client")
            {
                let b = bytes(f["hex"].as_str().unwrap());
                let mut d = Decoder::new(version);
                d.decode(&welcome).unwrap();
                if f["name"] == "interest_delta" {
                    let full = fixtures
                        .iter()
                        .find(|x| x["name"] == "interest_full")
                        .unwrap();
                    d.decode(&bytes(full["hex"].as_str().unwrap())).unwrap();
                }
                assert!(d.decode(&b).is_ok(), "{}", f["name"]);
                for n in 0..b.len() {
                    let mut d = Decoder::new(version);
                    d.decode(&welcome).unwrap();
                    assert!(d.decode(&b[..n]).is_err());
                }
            }
        }
    }
    pub fn welcome_packet(id: u32, zone: u16) -> Vec<u8> {
        let mut p = id.to_le_bytes().to_vec();
        p.extend(1u32.to_le_bytes());
        p.extend(1u64.to_le_bytes());
        p.extend(0f32.to_le_bytes());
        p.extend(0f32.to_le_bytes());
        p.extend(zone.to_le_bytes());
        p.extend(1u64.to_le_bytes());
        p.push(20);
        envelope(8, 0x81, &p)
    }
    fn interest(tick: u64, base: u64) -> Vec<u8> {
        let mut p = 1u32.to_le_bytes().to_vec();
        p.extend(tick.to_le_bytes());
        p.extend(base.to_le_bytes());
        p.extend(0u32.to_le_bytes());
        p.push(1);
        p.extend([0; 8]);
        p.extend(1u32.to_le_bytes());
        p.extend([0; 10]);
        p.extend(100u16.to_le_bytes());
        p.extend(100u16.to_le_bytes());
        p.extend([1, 0]);
        p.extend([0; 4]);
        p.extend([0, 0, 0, 0, 0, 0, 0, 0]);
        envelope(8, 0x86, &p)
    }
    #[test]
    fn baseline_is_transactional() {
        let mut d = Decoder::new(8);
        d.decode(&welcome_packet(1, 1)).unwrap();
        let full = interest(2, 0);
        d.decode(&full).unwrap();
        let mut broken = interest(3, 2);
        broken.push(9);
        let len = (broken.len() - 6) as u16;
        broken[4..6].copy_from_slice(&len.to_le_bytes());
        assert!(d.decode(&broken).is_err());
        assert_eq!(d.last_ack(), Some((1, 2)));
        assert!(d.decode(&interest(3, 2)).is_ok());
        assert!(matches!(
            d.decode(&interest(4, 99)),
            Err(CodecError::Resync(_))
        ));
    }
    #[test]
    fn encode_goldens() {
        assert_eq!(
            input(8, 1, 2, 1.0, -1.0, 0.0),
            bytes("31a708020e000100000002000000ff7f01800000")
        );
        assert_eq!(ping(8, 7, 123456), bytes("31a7080408000700000040e20100"));
        assert!(ticket_hex(&"x".repeat(64)).is_err());
        assert!(ticket_hex(&"é".repeat(32)).is_err());
    }
    #[test]
    fn compact_delta_preserves_private_self_and_monster_baseline() {
        let g: Value =
            serde_json::from_str(include_str!("../../../apps/protocol/golden-v8.json")).unwrap();
        let f = |name: &str| {
            bytes(
                g["fixtures"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .find(|f| f["name"] == name)
                    .unwrap()["hex"]
                    .as_str()
                    .unwrap(),
            )
        };
        let mut d = Decoder::new(8);
        d.decode(&f("interest_welcome")).unwrap();
        d.decode(&f("interest_full")).unwrap();
        let ServerMessage::Snapshot(s) = d.decode(&f("interest_delta")).unwrap() else {
            panic!("snapshot expected")
        };
        assert_eq!(s.own.id, 2);
        assert_eq!(s.own.x, 1.75);
        assert_eq!(s.players.iter().find(|p| p.id == 3).unwrap().x, 2.125);
        assert_eq!(s.monsters[0].hp, 70000);
        assert_eq!(s.monsters[0].flags, 7);
        assert_eq!(d.last_ack(), Some((1, 43)));
    }
}
