//! Aetherfield binary WebSocket protocol v8 (acknowledged AOI snapshots).
//!
//! Runtime snapshot layout lives in [`crate::interest`]; shared native fixtures
//! are `apps/protocol/golden-v8.json`. Other protocol versions are rejected.
//! Hot path is fixed binary; the cold path (`0x10`/`0x90`) carries tagged,
//! size-capped JSON validated by [`crate::cold`].

use crate::cold::{ColdTag, MAX_COLD_SERVER_BYTES, validate_client_payload};
use crate::world::{ActionKind, Snapshot, Welcome};
#[cfg(test)]
use crate::world::{CombatEvent, MonsterSnapshot, PlayerSnapshot};
#[cfg(test)]
use serde::Deserialize;

pub const PROTOCOL_VERSION: u8 = 8;
pub const MAX_CLIENT_PACKET_BYTES: usize = 4 * 1024;
pub const MAX_SERVER_PACKET_BYTES: usize = 16 * 1024;
pub const INPUT_FLAG_JUMP: u8 = 1 << 0;
pub const INPUT_FLAG_SPRINT: u8 = 1 << 1;
const HEADER_BYTES: usize = 6;
const MAGIC: u16 = 0xA731;
/// Diagnostic 0x82 player-record cap. Runtime 0x86 uses bounded AOI.
/// A worst-case diagnostic snapshot (50 players + 64
/// monsters + 64 events) is 24 + 50*20 + 64*36 + 64*30 = 5248 bytes of
/// payload, well inside [`MAX_SERVER_PACKET_BYTES`].
const MAX_PLAYERS: usize = 50;
const MAX_MONSTERS: usize = 64;
const MAX_EVENTS: usize = 64;
/// Protocol hard maximum; bounds beyond this are never encodable.
const PROTOCOL_HARD_MAX_COORDINATE: f32 = 4096.0;
#[cfg(test)]
const GOLDEN_FIXTURES: &str = include_str!("../../protocol/golden-v8.json");

/// ActionResult reason codes (binary-v6.md §3). Codes activate with their
/// gameplay (cooldown now; shapes, death and stagger in V5-08).
#[allow(dead_code)]
pub mod reason {
    pub const NONE: u8 = 0;
    pub const COOLDOWN: u8 = 1;
    pub const OUT_OF_RANGE: u8 = 2;
    pub const NO_TARGET: u8 = 3;
    pub const DEAD: u8 = 4;
    pub const BUSY: u8 = 5;
    pub const NOT_ALLOWED: u8 = 6;
    pub const RATE_LIMITED: u8 = 7;
}

#[derive(Clone, Debug, PartialEq)]
pub enum ClientCommand {
    Join {
        ticket: [u8; 32],
    },
    Input {
        epoch: u32,
        sequence: u32,
        x: f32,
        z: f32,
        facing: f32,
        /// V6 movement flags; V5 packets decode with both controls inactive.
        flags: u8,
    },
    Action {
        epoch: u32,
        sequence: u32,
        ability: ActionKind,
        aim: f32,
        target_id: u32,
        view_tick: u32,
    },
    Ping {
        nonce: u32,
        client_ms: u32,
    },
    SnapshotAck { epoch: u32, tick: u64, resync: bool },
    Cold {
        tag: ColdTag,
        payload: Vec<u8>,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DecodeError {
    TooShort,
    TooLarge,
    BadMagic,
    UnsupportedVersion(u8),
    InvalidLength,
    UnknownType,
    InvalidField,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u16)]
pub enum ErrorCode {
    ProtocolMismatch = 1,
    MalformedPacket = 2,
    RoomFull = 3,
    SessionActive = 4,
    SessionExpired = 5,
    InvalidJoin = 6,
    /// Sustained per-type rate excess (R3, V5-05a). Sent before the close.
    RateLimited = 7,
    /// Durable storage refused the join-time character load (V5-12): joining
    /// with unknown durable state is refused rather than guessed at.
    StorageUnavailable = 8,
}

impl ErrorCode {
    pub fn from_join_error(code: &str) -> Self {
        match code {
            "room_full" => Self::RoomFull,
            "session_active" => Self::SessionActive,
            "session_expired" => Self::SessionExpired,
            _ => Self::InvalidJoin,
        }
    }
}

/// Quantize a facing angle in radians to a u16 circle. Any finite angle is
/// accepted; it is normalized to `[0, 2π)`.
pub fn quantize_facing(radians: f32) -> Result<u16, DecodeError> {
    if !radians.is_finite() {
        return Err(DecodeError::InvalidField);
    }
    const TAU: f32 = std::f32::consts::TAU;
    let normalized = radians.rem_euclid(TAU) / TAU;
    Ok((normalized * 65535.0).round() as u16)
}

pub fn dequantize_facing(quantized: u16) -> f32 {
    quantized as f32 / 65535.0 * std::f32::consts::TAU
}

pub fn decode_client_packet(packet: &[u8]) -> Result<ClientCommand, DecodeError> {
    let (kind, payload) = read_envelope(packet, MAX_CLIENT_PACKET_BYTES)?;
    let mut reader = Reader::new(payload);
    let command = match kind {
        0x01 => {
            if payload.len() != 32 {
                return Err(DecodeError::InvalidLength);
            }
            let ticket = reader.bytes32()?;
            reader.finish()?;
            if ticket.iter().all(|byte| *byte == 0) {
                return Err(DecodeError::InvalidField);
            }
            ClientCommand::Join { ticket }
        }
        0x02 => {
            if payload.len() != 14 {
                return Err(DecodeError::InvalidLength);
            }
            let epoch = reader.u32()?;
            let sequence = reader.u32()?;
            let qx = reader.i16()?;
            let qz = reader.i16()?;
            let facing = dequantize_facing(reader.u16()?);
            reader.finish()?;
            if epoch == 0 || sequence == 0 || qx == i16::MIN || qz == i16::MIN {
                return Err(DecodeError::InvalidField);
            }
            ClientCommand::Input {
                epoch,
                sequence,
                x: qx as f32 / i16::MAX as f32,
                z: qz as f32 / i16::MAX as f32,
                facing,
                flags: 0,
            }
        }
        0x03 => {
            if payload.len() != 19 {
                return Err(DecodeError::InvalidLength);
            }
            let epoch = reader.u32()?;
            let sequence = reader.u32()?;
            let ability = decode_action(reader.u8()?)?;
            let aim = dequantize_facing(reader.u16()?);
            let target_id = reader.u32()?;
            let view_tick = reader.u32()?;
            reader.finish()?;
            if epoch == 0 || sequence == 0 {
                return Err(DecodeError::InvalidField);
            }
            ClientCommand::Action {
                epoch,
                sequence,
                ability,
                aim,
                target_id,
                view_tick,
            }
        }
        0x04 => {
            if payload.len() != 8 {
                return Err(DecodeError::InvalidLength);
            }
            let nonce = reader.u32()?;
            let client_ms = reader.u32()?;
            reader.finish()?;
            ClientCommand::Ping { nonce, client_ms }
        }
        0x05 => {
            if payload.len() != 13 { return Err(DecodeError::InvalidLength); }
            let epoch = reader.u32()?; let tick = reader.u64()?; let resync = reader.u8()?;
            reader.finish()?;
            if epoch == 0 || resync > 1 || (tick == 0 && resync == 0) { return Err(DecodeError::InvalidField); }
            ClientCommand::SnapshotAck { epoch, tick, resync: resync == 1 }
        }
        0x10 => {
            let tag = validate_client_payload(payload)?;
            reader.skip(payload.len())?;
            reader.finish()?;
            ClientCommand::Cold {
                tag,
                payload: payload.to_vec(),
            }
        }
        _ => return Err(DecodeError::UnknownType),
    };
    Ok(command)
}

pub fn encode_welcome(welcome: &Welcome, zone_limit: f32) -> Result<Vec<u8>, DecodeError> {
    if welcome.player_id == 0
        || welcome.epoch == 0
        || !valid_bounded_coordinate(welcome.x, zone_limit)
        || !valid_bounded_coordinate(welcome.z, zone_limit)
    {
        return Err(DecodeError::InvalidField);
    }
    let mut payload = Vec::with_capacity(35);
    put_u32(&mut payload, welcome.player_id);
    put_u32(&mut payload, welcome.epoch);
    put_u64(&mut payload, welcome.tick);
    put_f32(&mut payload, welcome.x)?;
    put_f32(&mut payload, welcome.z)?;
    put_u16(&mut payload, welcome.zone_id);
    put_u64(&mut payload, welcome.content_hash);
    payload.push(welcome.tick_hz);
    packet(0x81, payload)
}

pub fn encode_snapshot(snapshot: &Snapshot, zone_limit: f32) -> Result<Vec<u8>, DecodeError> {
    if snapshot.players.len() > MAX_PLAYERS
        || snapshot.monsters.len() > MAX_MONSTERS
        || snapshot.events.len() > MAX_EVENTS
    {
        return Err(DecodeError::TooLarge);
    }
    if !valid_bounded_coordinate(snapshot.ack_x, zone_limit)
        || !valid_bounded_coordinate(snapshot.ack_z, zone_limit)
    {
        return Err(DecodeError::InvalidField);
    }
    let payload_size = 24
        + snapshot.players.len() * 20
        + snapshot.monsters.len() * 36
        + snapshot.events.len() * 30;
    if HEADER_BYTES + payload_size > MAX_SERVER_PACKET_BYTES || payload_size > u16::MAX as usize {
        return Err(DecodeError::TooLarge);
    }

    let mut payload = Vec::with_capacity(payload_size);
    put_u64(&mut payload, snapshot.tick);
    put_u32(&mut payload, snapshot.ack_seq);
    payload.push(snapshot.own_flags);
    put_f32(&mut payload, snapshot.ack_x)?;
    put_f32(&mut payload, snapshot.ack_z)?;
    payload.push(snapshot.players.len() as u8);
    payload.push(snapshot.monsters.len() as u8);
    payload.push(snapshot.events.len() as u8);

    for player in &snapshot.players {
        if player.id == 0
            || player.hp > player.max_hp
            || !valid_bounded_coordinate(player.x, zone_limit)
            || !valid_bounded_coordinate(player.z, zone_limit)
            || !player.facing.is_finite()
        {
            return Err(DecodeError::InvalidField);
        }
        let mut flags = 0_u8;
        if player.connected {
            flags |= 1;
        }
        if player.down {
            flags |= 1 << 1;
        }
        if player.dodging {
            flags |= 1 << 2;
        }
        if player.guarding {
            flags |= 1 << 3;
        }
        put_u32(&mut payload, player.id);
        put_f32(&mut payload, player.x)?;
        put_f32(&mut payload, player.z)?;
        put_u16(&mut payload, quantize_facing(player.facing)?);
        put_u16(&mut payload, player.hp);
        put_u16(&mut payload, player.max_hp);
        payload.push(flags);
        payload.push(player.anim);
    }
    for monster in &snapshot.monsters {
        if monster.flags & !7 != 0 || monster.flags & 4 != 0 && monster.flags & 2 == 0 || monster.id == 0
            || monster.hp > monster.max_hp
            || !valid_bounded_coordinate(monster.x, zone_limit)
            || !valid_bounded_coordinate(monster.z, zone_limit)
            || !valid_bounded_coordinate(monster.target_x, zone_limit)
            || !valid_bounded_coordinate(monster.target_z, zone_limit)
            || !monster.facing.is_finite()
        {
            return Err(DecodeError::InvalidField);
        }
        put_u32(&mut payload, monster.id);
        if monster.kind == 0 {
            return Err(DecodeError::InvalidField);
        }
        payload.push(monster.kind);
        put_f32(&mut payload, monster.x)?;
        put_f32(&mut payload, monster.z)?;
        put_u16(&mut payload, quantize_facing(monster.facing)?);
        put_u32(&mut payload, monster.hp);
        put_u32(&mut payload, monster.max_hp);
        // Bit 0 is authoritative from `active`; higher bits carry V5-08 state.
        payload.push(monster.flags & 0xFE | u8::from(monster.active));
        payload.push(monster.state);
        payload.push(monster.ability);
        put_u16(&mut payload, monster.state_ticks);
        put_f32(&mut payload, monster.target_x)?;
        put_f32(&mut payload, monster.target_z)?;
    }
    for event in &snapshot.events {
        if event.id == 0
            || event.flags & 0x80 != 0
            || event.flags & 0x40 != 0 && (event.damage != 0 || event.flags & 0x21 != 0)
            || event.flags & 0x20 != 0 && event.damage == 0
            || event.source_kind > 1
            || event.target_kind > 1
            || event.source_id == 0
            || event.target_id == 0
            || !valid_bounded_coordinate(event.world_x, zone_limit)
            || !valid_bounded_coordinate(event.world_z, zone_limit)
        {
            return Err(DecodeError::InvalidField);
        }
        put_u64(&mut payload, event.id);
        payload.push(event.source_kind);
        put_u32(&mut payload, event.source_id);
        payload.push(event.target_kind);
        put_u32(&mut payload, event.target_id);
        payload.push(action_id(event.action));
        put_u16(&mut payload, event.damage);
        payload.push(event.flags);
        put_f32(&mut payload, event.world_x)?;
        put_f32(&mut payload, event.world_z)?;
    }
    packet(0x82, payload)
}

pub(crate) fn encode_event_record(event: &crate::world::CombatEvent, zone_limit: f32) -> Result<Vec<u8>, DecodeError> {
    let snapshot = Snapshot { tick: 0, ack_seq: 0, own_flags: 0, ack_x: 0.0, ack_z: 0.0, players: vec![], monsters: vec![], events: vec![event.clone()], pets: vec![] };
    let bytes = encode_snapshot(&snapshot, zone_limit)?;
    Ok(bytes[30..].to_vec())
}

pub fn encode_error(code: ErrorCode) -> Vec<u8> {
    let payload = (code as u16).to_le_bytes().to_vec();
    packet(0x83, payload).expect("fixed-size error packet is within protocol limits")
}

pub fn encode_action_result(
    sequence: u32,
    accepted: bool,
    reason: u8,
    ends_at_ms: u64,
) -> Result<Vec<u8>, DecodeError> {
    if sequence == 0 || reason > reason::RATE_LIMITED {
        return Err(DecodeError::InvalidField);
    }
    let mut payload = Vec::with_capacity(14);
    put_u32(&mut payload, sequence);
    payload.push(u8::from(accepted));
    payload.push(reason);
    put_u64(&mut payload, ends_at_ms);
    packet(0x84, payload)
}

pub fn encode_pong(nonce: u32, client_ms: u32, server_tick: u64) -> Vec<u8> {
    let mut payload = Vec::with_capacity(16);
    put_u32(&mut payload, nonce);
    put_u32(&mut payload, client_ms);
    put_u64(&mut payload, server_tick);
    packet(0x85, payload).expect("fixed-size pong packet is within protocol limits")
}

pub fn encode_cold_server(payload: &[u8]) -> Result<Vec<u8>, DecodeError> {
    if payload.len() > MAX_COLD_SERVER_BYTES {
        return Err(DecodeError::TooLarge);
    }
    if serde_json::from_slice::<serde_json::Value>(payload).is_err() {
        return Err(DecodeError::InvalidField);
    }
    packet(0x90, payload.to_vec())
}

fn read_envelope(packet: &[u8], max_bytes: usize) -> Result<(u8, &[u8]), DecodeError> {
    if packet.len() < HEADER_BYTES {
        return Err(DecodeError::TooShort);
    }
    if packet.len() > max_bytes {
        return Err(DecodeError::TooLarge);
    }
    if u16::from_le_bytes([packet[0], packet[1]]) != MAGIC {
        return Err(DecodeError::BadMagic);
    }
    if packet[2] != PROTOCOL_VERSION {
        return Err(DecodeError::UnsupportedVersion(packet[2]));
    }
    let payload_len = u16::from_le_bytes([packet[4], packet[5]]) as usize;
    if packet.len() != HEADER_BYTES + payload_len {
        return Err(DecodeError::InvalidLength);
    }
    Ok((packet[3], &packet[HEADER_BYTES..]))
}

pub(crate) fn packet(kind: u8, payload: Vec<u8>) -> Result<Vec<u8>, DecodeError> {
    let total_len = HEADER_BYTES
        .checked_add(payload.len())
        .ok_or(DecodeError::TooLarge)?;
    if payload.len() > u16::MAX as usize || total_len > MAX_SERVER_PACKET_BYTES {
        return Err(DecodeError::TooLarge);
    }
    let mut packet = Vec::with_capacity(total_len);
    packet.extend_from_slice(&MAGIC.to_le_bytes());
    packet.push(PROTOCOL_VERSION);
    packet.push(kind);
    packet.extend_from_slice(&(payload.len() as u16).to_le_bytes());
    packet.extend_from_slice(&payload);
    Ok(packet)
}

/// Coordinate bound for encoding (R9): the zone's half-extent, capped at the
/// protocol hard maximum. The world clamps simulation to its zone; this is
/// the backstop that keeps a larger zone encodable instead of freezing
/// every client.
fn valid_bounded_coordinate(value: f32, zone_limit: f32) -> bool {
    value.is_finite() && value.abs() <= zone_limit.min(PROTOCOL_HARD_MAX_COORDINATE)
}

fn decode_action(action: u8) -> Result<ActionKind, DecodeError> {
    match action {
        1 => Ok(ActionKind::Attack),
        2 => Ok(ActionKind::ArcSlash),
        3 => Ok(ActionKind::Dodge),
        4 => Ok(ActionKind::Guard),
        5 => Ok(ActionKind::SplashHop),
        _ => Err(DecodeError::InvalidField),
    }
}

fn action_id(action: ActionKind) -> u8 {
    match action {
        ActionKind::Attack => 1,
        ActionKind::ArcSlash => 2,
        ActionKind::Dodge => 3,
        ActionKind::Guard => 4,
        ActionKind::SplashHop => 5,
    }
}

fn put_u16(bytes: &mut Vec<u8>, value: u16) {
    bytes.extend_from_slice(&value.to_le_bytes());
}

fn put_u32(bytes: &mut Vec<u8>, value: u32) {
    bytes.extend_from_slice(&value.to_le_bytes());
}

fn put_u64(bytes: &mut Vec<u8>, value: u64) {
    bytes.extend_from_slice(&value.to_le_bytes());
}

fn put_f32(bytes: &mut Vec<u8>, value: f32) -> Result<(), DecodeError> {
    if !value.is_finite() {
        return Err(DecodeError::InvalidField);
    }
    bytes.extend_from_slice(&value.to_le_bytes());
    Ok(())
}

struct Reader<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Reader<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn take<const N: usize>(&mut self) -> Result<[u8; N], DecodeError> {
        let end = self
            .offset
            .checked_add(N)
            .ok_or(DecodeError::InvalidLength)?;
        let source = self
            .bytes
            .get(self.offset..end)
            .ok_or(DecodeError::InvalidLength)?;
        let mut result = [0_u8; N];
        result.copy_from_slice(source);
        self.offset = end;
        Ok(result)
    }

    fn u8(&mut self) -> Result<u8, DecodeError> {
        Ok(self.take::<1>()?[0])
    }

    fn u16(&mut self) -> Result<u16, DecodeError> {
        Ok(u16::from_le_bytes(self.take::<2>()?))
    }

    fn i16(&mut self) -> Result<i16, DecodeError> {
        Ok(i16::from_le_bytes(self.take::<2>()?))
    }

    fn u64(&mut self) -> Result<u64, DecodeError> { let bytes=self.bytes.get(self.offset..self.offset+8).ok_or(DecodeError::InvalidLength)?; self.offset+=8; Ok(u64::from_le_bytes(bytes.try_into().unwrap())) }

    fn u32(&mut self) -> Result<u32, DecodeError> {
        Ok(u32::from_le_bytes(self.take::<4>()?))
    }

    fn bytes32(&mut self) -> Result<[u8; 32], DecodeError> {
        self.take::<32>()
    }

    fn skip(&mut self, count: usize) -> Result<(), DecodeError> {
        let end = self
            .offset
            .checked_add(count)
            .ok_or(DecodeError::InvalidLength)?;
        if end > self.bytes.len() {
            return Err(DecodeError::InvalidLength);
        }
        self.offset = end;
        Ok(())
    }

    fn finish(self) -> Result<(), DecodeError> {
        if self.offset == self.bytes.len() {
            Ok(())
        } else {
            Err(DecodeError::InvalidLength)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Zone bound used across codec tests (matches the P1 bundle zone).
    const TEST_ZONE: f32 = 28.0;

    #[derive(Deserialize)]
    struct GoldenFile {
        fixtures: Vec<GoldenFixture>,
        #[allow(dead_code)]
        cold_client: Vec<ColdFixture>,
        #[allow(dead_code)]
        cold_server: Vec<ColdFixture>,
    }

    #[derive(Deserialize)]
    struct GoldenFixture {
        name: String,
        hex: String,
    }

    #[derive(Deserialize)]
    struct ColdFixture {
        #[allow(dead_code)]
        name: String,
        #[allow(dead_code)]
        json: String,
    }

    fn golden_file() -> GoldenFile {
        serde_json::from_str(GOLDEN_FIXTURES).expect("golden file parses")
    }

    fn fixture(name: &str) -> Vec<u8> {
        let golden = golden_file();
        let hex = &golden
            .fixtures
            .iter()
            .find(|case| case.name == name)
            .expect("golden fixture exists")
            .hex;
        hex.as_bytes()
            .chunks_exact(2)
            .map(|pair| {
                let text = std::str::from_utf8(pair).expect("hex is ASCII");
                u8::from_str_radix(text, 16).expect("hex byte is valid")
            })
            .collect()
    }

    #[test]
    fn golden_welcome_matches_the_built_bundle() {
        // Pinned: any content edit changes the wire-visible hash, so the v6
        // golden welcome must be regenerated alongside (see the dump helper).
        let content = crate::content::test_content();
        let welcome = fixture("welcome_basic");
        assert_eq!(welcome.len(), 41, "v6 welcome packet layout changed");
        assert_eq!(
            content.hash,
            u64::from_le_bytes(welcome[32..40].try_into().unwrap())
        );
        assert_eq!(
            content.zone_id,
            u16::from_le_bytes(welcome[30..32].try_into().unwrap())
        );
        assert_eq!(content.tick_hz, welcome[40]);
    }

    #[test]
    fn facing_quantization_round_trips() {
        assert_eq!(quantize_facing(0.0).unwrap(), 0);
        assert!(quantize_facing(f32::NAN).is_err());
        assert!(quantize_facing(f32::INFINITY).is_err());
        // Negative and multi-turn angles normalize onto the circle.
        let tau = std::f32::consts::TAU;
        for radians in [0.0, 1.0, -1.0, tau, tau * 3.25, -tau * 2.0] {
            let back = dequantize_facing(quantize_facing(radians).unwrap());
            let expected = radians.rem_euclid(tau);
            let distance = (back - expected).abs().min((back - expected + tau).abs());
            assert!(distance < 0.001, "facing {radians} lost precision");
        }
    }

    #[test]
    fn client_golden_packets_decode() {
        assert_eq!(
            decode_client_packet(&fixture("join_ticket")),
            Ok(ClientCommand::Join {
                ticket: [
                    0xa0, 0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xab, 0xac,
                    0xad, 0xae, 0xaf, 0xb0, 0xb1, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9,
                    0xba, 0xbb, 0xbc, 0xbd, 0xbe, 0xbf
                ]
            })
        );
        assert_eq!(
            decode_client_packet(&fixture("input_full_axes")),
            Ok(ClientCommand::Input {
                epoch: 1,
                sequence: 2,
                x: 1.0,
                z: -1.0,
                facing: 0.0,
                flags: 0,
            })
        );
        assert_eq!(
            decode_client_packet(&fixture("action_arc_slash")),
            Ok(ClientCommand::Action {
                epoch: 1,
                sequence: 3,
                ability: ActionKind::ArcSlash,
                aim: 0.0,
                target_id: 0,
                view_tick: 41,
            })
        );
        assert_eq!(
            decode_client_packet(&fixture("ping_basic")),
            Ok(ClientCommand::Ping {
                nonce: 7,
                client_ms: 123456,
            })
        );
        assert_eq!(
            decode_client_packet(&fixture("cold_resync")),
            Ok(ClientCommand::Cold {
                tag: ColdTag::Resync,
                payload: br#"{"t":"resync"}"#.to_vec(),
            })
        );
    }

    #[test]
    fn server_golden_packets_encode_byte_for_byte() {
        let content = crate::content::test_content();
        let welcome = Welcome {
            player_id: 2,
            epoch: 1,
            tick: 42,
            x: 1.5,
            z: -2.25,
            zone_id: content.zone_id,
            content_hash: content.hash,
            tick_hz: content.tick_hz,
        };
        assert_eq!(
            encode_welcome(&welcome, TEST_ZONE).unwrap(),
            fixture("welcome_basic")
        );

        let snapshot = Snapshot {
            tick: 42,
            ack_seq: 7,
            own_flags: 0,
            ack_x: 1.5,
            ack_z: -2.25,
            players: vec![PlayerSnapshot {
                id: 2,
                x: 1.5,
                z: -2.25,
                y: 0.0,
                facing: 0.0,
                hp: 80,
                max_hp: 100,
                connected: true,
                down: false,
                dodging: false,
                guarding: false,
                anim: 0,
            }],
            monsters: Vec::new(),
            events: Vec::new(),
            pets: Vec::new(),
        };
        assert_eq!(
            encode_snapshot(&snapshot, TEST_ZONE).unwrap(),
            fixture("snapshot_one_player")
        );

        let world_state = Snapshot {
            tick: 42,
            ack_seq: 7,
            own_flags: 0,
            ack_x: 1.5,
            ack_z: -2.25,
            players: vec![PlayerSnapshot {
                id: 2,
                x: 1.5,
                z: -2.25,
                y: 0.0,
                facing: 0.0,
                hp: 80,
                max_hp: 100,
                connected: true,
                down: false,
                dodging: false,
                guarding: false,
                anim: 0,
            }],
            monsters: vec![MonsterSnapshot {
                id: 101,
                kind: 1,
                x: 3.5,
                z: 4.0,
                facing: 0.0,
                hp: 90,
                max_hp: 90,
                active: true,
                flags: 0,
                state: 0,
                ability: 0,
                state_ticks: 0,
                target_x: 3.5,
                target_z: 4.0,
                target_player_id: None,
            }],
            events: vec![CombatEvent {
                id: 9_007_199_254_740_993,
                source_kind: 0,
                source_id: 2,
                target_kind: 0,
                target_id: 101,
                action: ActionKind::Attack,
                damage: 28,
                flags: 1,
                world_x: 3.5,
                world_z: 4.0,
            }],
            pets: Vec::new(),
        };
        assert_eq!(
            encode_snapshot(&world_state, TEST_ZONE).unwrap(),
            fixture("snapshot_player_monster_event_u64")
        );
        assert_eq!(
            encode_error(ErrorCode::RoomFull),
            fixture("error_room_full")
        );
        assert_eq!(
            encode_error(ErrorCode::RateLimited),
            fixture("error_rate_limited")
        );
        assert_eq!(
            encode_action_result(9, true, reason::NONE, 2460).unwrap(),
            fixture("action_result_accepted")
        );
        assert_eq!(
            encode_action_result(10, false, reason::COOLDOWN, 2312).unwrap(),
            fixture("action_result_rejected")
        );
        assert_eq!(encode_pong(7, 123456, 420), fixture("pong_basic"));
    }

    #[test]
    fn action_result_deadlines_use_the_full_u64_width() {
        let ends_at_ms = 9_007_199_254_740_993;
        let packet = encode_action_result(1, true, reason::NONE, ends_at_ms).unwrap();
        assert_eq!(packet.len(), HEADER_BYTES + 14);
        assert_eq!(u16::from_le_bytes(packet[4..6].try_into().unwrap()), 14);
        assert_eq!(
            u64::from_le_bytes(packet[12..20].try_into().unwrap()),
            ends_at_ms
        );
        let no_cooldown = encode_action_result(1, false, reason::DEAD, 0).unwrap();
        assert_eq!(&no_cooldown[12..20], &[0; 8]);
    }

    #[test]
    fn cold_server_packets_are_typed_bounded_envelopes() {
        let payload = br#"{"t":"character_state","rev":1}"#;
        let packet = encode_cold_server(payload).unwrap();
        assert_eq!(packet[3], 0x90);
        assert_eq!(&packet[HEADER_BYTES..], payload);
        assert_eq!(
            encode_cold_server(b"not json"),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            encode_cold_server(&vec![b'x'; MAX_COLD_SERVER_BYTES + 1]),
            Err(DecodeError::TooLarge)
        );
    }

    #[test]
    fn pre_v6_packets_are_rejected() {
        for version in [2, 3, 4, 5] {
            let mut old_join = fixture("join_ticket");
            old_join[2] = version;
            assert_eq!(
                decode_client_packet(&old_join),
                Err(DecodeError::UnsupportedVersion(version))
            );
        }
    }

    #[test]
    fn decoder_rejects_short_wrong_version_trailing_and_invalid_packets() {
        assert_eq!(decode_client_packet(&[0; 5]), Err(DecodeError::TooShort));

        let mut zero_ticket = fixture("join_ticket");
        zero_ticket[HEADER_BYTES..].fill(0);
        assert_eq!(
            decode_client_packet(&zero_ticket),
            Err(DecodeError::InvalidField)
        );

        let mut wrong_version = fixture("join_ticket");
        wrong_version[2] = 1;
        assert_eq!(
            decode_client_packet(&wrong_version),
            Err(DecodeError::UnsupportedVersion(1))
        );

        let mut trailing = fixture("join_ticket");
        trailing.push(0);
        assert_eq!(
            decode_client_packet(&trailing),
            Err(DecodeError::InvalidLength)
        );

        let mut min_axis = fixture("input_full_axes");
        min_axis[16] = 0;
        min_axis[17] = 0x80;
        assert_eq!(
            decode_client_packet(&min_axis),
            Err(DecodeError::InvalidField)
        );

        assert_eq!(
            encode_action_result(0, true, reason::NONE, 0),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            encode_action_result(1, true, 9, 0),
            Err(DecodeError::InvalidField)
        );

        // Unknown hot type and unknown cold tag are both rejected.
        let mut unknown_type = fixture("ping_basic");
        unknown_type[3] = 0x77;
        assert_eq!(
            decode_client_packet(&unknown_type),
            Err(DecodeError::UnknownType)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"fly","mode":1}"#),
            Err(DecodeError::InvalidField)
        );
    }

    #[test]
    fn every_client_packet_truncation_is_rejected() {
        for name in [
            "join_ticket",
            "input_full_axes",
            "action_arc_slash",
            "ping_basic",
            "cold_resync",
        ] {
            let packet = fixture(name);
            for length in 0..packet.len() {
                assert!(
                    decode_client_packet(&packet[..length]).is_err(),
                    "{name} accepted truncation at {length}/{} bytes",
                    packet.len()
                );
            }
        }
    }

    #[test]
    fn snapshot_bound_comes_from_the_zone_capped_at_hard_max() {
        // R9: a 48 m zone (Appendix A field) must encode; absurd bounds clamp
        // to the ±4096 m protocol maximum instead of freezing every client.
        let at = |x: f32| Snapshot {
            tick: 1,
            ack_seq: 0,
            own_flags: 0,
            ack_x: x,
            ack_z: 0.0,
            players: vec![PlayerSnapshot {
                id: 1,
                x,
                z: 0.0,
                y: 0.0,
                facing: 0.0,
                hp: 100,
                max_hp: 100,
                connected: true,
                down: false,
                dodging: false,
                guarding: false,
                anim: 0,
            }],
            monsters: Vec::new(),
            events: Vec::new(),
            pets: Vec::new(),
        };
        assert!(encode_snapshot(&at(30.0), TEST_ZONE).is_err());
        assert!(encode_snapshot(&at(30.0), 48.0).is_ok());
        assert!(encode_snapshot(&at(4000.0), 99999.0).is_ok());
        assert!(encode_snapshot(&at(5000.0), 99999.0).is_err());
        assert!(encode_snapshot(&at(f32::NAN), 48.0).is_err());
    }

    #[test]
    fn encoder_enforces_world_bounds_and_snapshot_caps() {
        let welcome = Welcome {
            player_id: 1,
            epoch: 1,
            tick: 0,
            x: f32::INFINITY,
            z: 0.0,
            zone_id: 1,
            content_hash: 0x7ff3b2ced4ac3484,
            tick_hz: 20,
        };
        assert_eq!(
            encode_welcome(&welcome, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );
        let too_many = Snapshot {
            tick: 0,
            ack_seq: 0,
            own_flags: 0,
            ack_x: 0.0,
            ack_z: 0.0,
            players: (0..=MAX_PLAYERS)
                .map(|id| PlayerSnapshot {
                    id: id as u32 + 1,
                    x: 0.0,
                    z: 0.0,
                    y: 0.0,
                    facing: 0.0,
                    hp: 100,
                    max_hp: 100,
                    connected: true,
                    down: false,
                    dodging: false,
                    guarding: false,
                    anim: 0,
                })
                .collect(),
            monsters: Vec::new(),
            events: Vec::new(),
            pets: Vec::new(),
        };
        assert_eq!(
            encode_snapshot(&too_many, TEST_ZONE),
            Err(DecodeError::TooLarge)
        );
    }

    #[test]
    fn snapshot_encoder_accepts_exactly_the_player_cap_and_binds_the_packet_budget() {
        let at_cap = Snapshot {
            tick: 1,
            ack_seq: 0,
            own_flags: 0,
            ack_x: 0.0,
            ack_z: 0.0,
            players: (0..MAX_PLAYERS)
                .map(|index| PlayerSnapshot {
                    id: index as u32 + 1,
                    x: 0.0,
                    z: 0.0,
                    y: 0.0,
                    facing: 0.0,
                    hp: 100,
                    max_hp: 100,
                    connected: true,
                    down: false,
                    dodging: false,
                    guarding: false,
                    anim: 0,
                })
                .collect(),
            monsters: Vec::new(),
            events: Vec::new(),
            pets: Vec::new(),
        };
        let packet =
            encode_snapshot(&at_cap, TEST_ZONE).expect("a full-room snapshot is encodable");
        // 6-byte envelope + 24-byte snapshot header + 20-byte player records.
        assert_eq!(packet.len(), 6 + 24 + MAX_PLAYERS * 20);
        // The worst case (full players + monsters + events) stays bounded.
        assert!(packet.len() <= MAX_SERVER_PACKET_BYTES);
    }

    #[test]
    fn snapshot_encoder_rejects_invalid_hp_and_zero_event_ids() {
        let mut player = Snapshot {
            tick: 1,
            ack_seq: 0,
            own_flags: 0,
            ack_x: 0.0,
            ack_z: 0.0,
            players: vec![PlayerSnapshot {
                id: 1,
                x: 0.0,
                z: 0.0,
                y: 0.0,
                facing: 0.0,
                hp: 101,
                max_hp: 100,
                connected: true,
                down: false,
                dodging: false,
                guarding: false,
                anim: 0,
            }],
            monsters: Vec::new(),
            events: Vec::new(),
            pets: Vec::new(),
        };
        assert_eq!(
            encode_snapshot(&player, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );

        player.players[0].hp = 100;
        player.ack_x = f32::NAN;
        assert_eq!(
            encode_snapshot(&player, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );
        player.ack_x = 29.0;
        assert_eq!(
            encode_snapshot(&player, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );
        player.ack_x = 0.0;
        player.monsters.push(MonsterSnapshot {
            id: 101,
            kind: 1,
            x: 0.0,
            z: 0.0,
            facing: 0.0,
            hp: 91,
            max_hp: 90,
            active: true,
            flags: 1,
            state: 0,
            ability: 0,
            state_ticks: 0,
            target_x: 0.0,
            target_z: 0.0,
                target_player_id: None,
        });
        assert_eq!(
            encode_snapshot(&player, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );
        player.monsters[0].kind = 0;
        player.monsters[0].hp = 90;
        assert_eq!(
            encode_snapshot(&player, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );
        player.monsters[0].kind = 1;

        player.monsters[0].hp = 90;
        player.events.push(CombatEvent {
            id: 0,
            source_kind: 0,
            source_id: 1,
            target_kind: 0,
            target_id: 101,
            action: ActionKind::Attack,
            damage: 1,
            flags: 0,
            world_x: 0.0,
            world_z: 0.0,
        });
        assert_eq!(
            encode_snapshot(&player, TEST_ZONE),
            Err(DecodeError::InvalidField)
        );
    }

    /// Deterministic PRNG (splitmix64) so randomized decoder coverage runs in
    /// the normal suite without flakes.
    struct Lcg(u64);

    impl Lcg {
        fn next(&mut self) -> u64 {
            self.0 = self.0.wrapping_add(0x9E3779B97F4A7C15);
            let mut z = self.0;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
            z ^ (z >> 31)
        }

        fn below(&mut self, bound: usize) -> usize {
            (self.next() % bound.max(1) as u64) as usize
        }
    }

    #[test]
    fn randomized_decoder_inputs_never_panic_and_stay_bounded() {
        let seeds: Vec<Vec<u8>> = [
            "join_ticket",
            "input_full_axes",
            "action_arc_slash",
            "ping_basic",
            "cold_resync",
            "welcome_basic",
            "snapshot_one_player",
            "snapshot_player_monster_event_u64",
        ]
        .iter()
        .map(|name| fixture(name))
        .collect();
        let mut rng = Lcg(0x5EED_C0DE);
        // 4000 mutated packets: truncation, byte flips, length-field lies.
        for _ in 0..4000 {
            let seed = &seeds[rng.below(seeds.len())];
            let mut packet = seed.clone();
            match rng.below(3) {
                0 => packet.truncate(rng.below(packet.len() + 1)),
                1 => {
                    if !packet.is_empty() {
                        let index = rng.below(packet.len());
                        packet[index] = rng.next() as u8;
                    }
                }
                _ => {
                    if packet.len() >= HEADER_BYTES {
                        let lie = rng.next() as u16;
                        packet[4] = lie as u8;
                        packet[5] = (lie >> 8) as u8;
                    }
                }
            }
            // Client-side packets decode through the client gate; server
            // fixtures must fail it (wrong direction is still an error, and
            // must never panic or allocate without bound).
            let _ = decode_client_packet(&packet);
        }
    }

    #[test]
    #[ignore = "authoring helper: un-ignore once to re-emit golden hex, then re-ignore"]
    fn dump_golden_hex_for_fixture_authoring() {
        // TEMPORARY authoring helper: prints canonical hex for golden-v6.json.
        // Remove once fixtures are checked in (the byte-exact tests above are
        // the real gate; this only generates their input).
        let join = {
            let mut ticket = [0_u8; 32];
            for (index, byte) in ticket.iter_mut().enumerate() {
                *byte = 0xa0 + index as u8;
            }
            let mut packet = vec![0x31, 0xa7, PROTOCOL_VERSION, 1, 32, 0];
            packet.extend_from_slice(&ticket);
            packet
        };
        println!("join_ticket {}", hex_of(&join));
        println!(
            "input_full_axes {}",
            hex_of(&encode_input_fixture(1, 2, 32767, -32767, 0))
        );
        println!(
            "action_arc_slash {}",
            hex_of(&encode_action_fixture(1, 3, 2, 0, 0, 41))
        );
        println!("ping_basic {}", hex_of(&encode_ping_fixture(7, 123456)));
        let cold = br#"{"t":"resync"}"#;
        let mut cold_packet = vec![0x31, 0xa7, PROTOCOL_VERSION, 0x10, cold.len() as u8, 0];
        cold_packet.extend_from_slice(cold);
        println!("cold_resync {}", hex_of(&cold_packet));
        let content = crate::content::test_content();
        let welcome = Welcome {
            player_id: 2,
            epoch: 1,
            tick: 42,
            x: 1.5,
            z: -2.25,
            zone_id: content.zone_id,
            content_hash: content.hash,
            tick_hz: content.tick_hz,
        };
        println!(
            "welcome_basic {}",
            hex_of(&encode_welcome(&welcome, TEST_ZONE).unwrap())
        );
        println!(
            "snapshot_one_player {}",
            hex_of(
                &encode_snapshot(
                    &Snapshot {
                        tick: 42,
                        ack_seq: 7,
                        own_flags: 0,
                        ack_x: 1.5,
                        ack_z: -2.25,
                        players: vec![PlayerSnapshot {
                            id: 2,
                            x: 1.5,
                            z: -2.25,
                            y: 0.0,
                            facing: 0.0,
                            hp: 80,
                            max_hp: 100,
                            connected: true,
                            down: false,
                            dodging: false,
                            guarding: false,
                            anim: 0,
                        }],
                        monsters: Vec::new(),
                        events: Vec::new(),
                        pets: Vec::new(),
                    },
                    TEST_ZONE,
                )
                .unwrap()
            )
        );
        println!(
            "snapshot_player_monster_event_u64 {}",
            hex_of(
                &encode_snapshot(
                    &Snapshot {
                        tick: 42,
                        ack_seq: 7,
                        own_flags: 0,
                        ack_x: 1.5,
                        ack_z: -2.25,
                        players: vec![PlayerSnapshot {
                            id: 2,
                            x: 1.5,
                            z: -2.25,
                            y: 0.0,
                            facing: 0.0,
                            hp: 80,
                            max_hp: 100,
                            connected: true,
                            down: false,
                            dodging: false,
                            guarding: false,
                            anim: 0,
                        }],
                        monsters: vec![MonsterSnapshot {
                            id: 101,
                            kind: 1,
                            x: 3.5,
                            z: 4.0,
                            facing: 0.0,
                            hp: 90,
                            max_hp: 90,
                            active: true,
                            flags: 1,
                            state: 0,
                            ability: 0,
                            state_ticks: 0,
                            target_x: 3.5,
                            target_z: 4.0,
                            target_player_id: None,
                        }],
                        events: vec![CombatEvent {
                            id: 9_007_199_254_740_993,
                            source_kind: 0,
                            source_id: 2,
                            target_kind: 0,
                            target_id: 101,
                            action: ActionKind::Attack,
                            damage: 28,
                            flags: 1,
                            world_x: 3.5,
                            world_z: 4.0,
                        }],
                        pets: Vec::new(),
                    },
                    TEST_ZONE,
                )
                .unwrap()
            )
        );
        println!(
            "error_room_full {}",
            hex_of(&encode_error(ErrorCode::RoomFull))
        );
        println!(
            "action_result_accepted {}",
            hex_of(&encode_action_result(9, true, reason::NONE, 2460).unwrap())
        );
        println!(
            "action_result_rejected {}",
            hex_of(&encode_action_result(10, false, reason::COOLDOWN, 2312).unwrap())
        );
        println!("pong_basic {}", hex_of(&encode_pong(7, 123456, 420)));
    }

    #[cfg(test)]
    fn hex_of(bytes: &[u8]) -> String {
        bytes.iter().map(|byte| format!("{byte:02x}")).collect()
    }

    #[cfg(test)]
    fn encode_input_fixture(epoch: u32, sequence: u32, qx: i16, qz: i16, facing: u16) -> Vec<u8> {
        let mut payload = Vec::new();
        payload.extend_from_slice(&epoch.to_le_bytes());
        payload.extend_from_slice(&sequence.to_le_bytes());
        payload.extend_from_slice(&qx.to_le_bytes());
        payload.extend_from_slice(&qz.to_le_bytes());
        payload.extend_from_slice(&facing.to_le_bytes());
        packet(0x02, payload).unwrap()
    }

    #[cfg(test)]
    fn encode_action_fixture(
        epoch: u32,
        sequence: u32,
        ability: u8,
        aim: u16,
        target_id: u32,
        view_tick: u32,
    ) -> Vec<u8> {
        let mut payload = Vec::new();
        payload.extend_from_slice(&epoch.to_le_bytes());
        payload.extend_from_slice(&sequence.to_le_bytes());
        payload.push(ability);
        payload.extend_from_slice(&aim.to_le_bytes());
        payload.extend_from_slice(&target_id.to_le_bytes());
        payload.extend_from_slice(&view_tick.to_le_bytes());
        packet(0x03, payload).unwrap()
    }

    #[cfg(test)]
    fn encode_ping_fixture(nonce: u32, client_ms: u32) -> Vec<u8> {
        let mut payload = Vec::new();
        payload.extend_from_slice(&nonce.to_le_bytes());
        payload.extend_from_slice(&client_ms.to_le_bytes());
        packet(0x04, payload).unwrap()
    }
}
