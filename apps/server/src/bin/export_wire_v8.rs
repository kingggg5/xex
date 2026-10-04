//! Native offline v8 fixtures; output is an explicit path, never a deployment.
use aetherfield_server::{
    content,
    interest::{Stream, TickEncoder},
    wire,
    world::{ActionKind, CombatEvent, MonsterSnapshot, PlayerSnapshot, Snapshot, Welcome},
};
use std::{collections::BTreeSet, fs, path::PathBuf};
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let output = std::env::args().nth(1).expect("explicit output path");
    let built = content::build_from_source(&root.join("content/source")).unwrap();
    let mut data: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("apps/protocol/golden-v7.json")).unwrap())
            .unwrap();
    for f in data["fixtures"].as_array_mut().unwrap() {
        let mut b = (0..f["hex"].as_str().unwrap().len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&f["hex"].as_str().unwrap()[i..i + 2], 16).unwrap())
            .collect::<Vec<_>>();
        b[2] = 8;
        if f["name"].as_str() == Some("welcome_basic") {
            b = wire::encode_welcome(
                &Welcome {
                    player_id: 2,
                    epoch: 1,
                    tick: 42,
                    x: 1.5,
                    z: -2.25,
                    zone_id: built.zone_id,
                    content_hash: built.hash,
                    tick_hz: built.tick_hz,
                },
                28.0,
            )
            .unwrap();
        }
        f["hex"] = serde_json::json!(hex(&b));
    }
    let own = PlayerSnapshot {
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
    };
    let mut peer = own.clone();
    peer.id = 3;
    peer.x = 2.0;
    let mut s = Snapshot {
        tick: 42,
        ack_seq: 7,
        own_flags: 0,
        ack_x: 1.5,
        ack_z: -2.25,
        players: vec![own, peer],
        monsters: vec![MonsterSnapshot {
            id: 101,
            kind: 1,
            x: 3.5,
            z: 4.0,
            facing: 0.0,
            hp: 70_000,
            max_hp: 100_000,
            active: true,
            flags: 3,
            state: 1,
            ability: 5,
            state_ticks: 8,
            target_x: 1.5,
            target_z: -2.25,
            target_player_id: Some(2),
        }],
        events: vec![CombatEvent {
            id: 9_007_199_254_740_993,
            source_kind: 0,
            source_id: 2,
            target_kind: 0,
            target_id: 101,
            action: ActionKind::Attack,
            damage: 42,
            flags: 32,
            world_x: 3.5,
            world_z: 4.0,
        }],
        pets: vec![],
    };
    let party = BTreeSet::new();
    let mut stream = Stream::default();
    let mut encoder = TickEncoder::new(&s, 28.0).unwrap();
    let state = encoder.select(&s, 2, &party, 101);
    let full = encoder
        .packet(
            &s,
            state,
            &mut stream,
            1,
            2,
            &party,
            (7, 1.5, -2.25, 0),
            28.0,
        )
        .unwrap();
    stream.mark_sent(42);
    assert!(stream.acknowledge(42, false));
    s.tick = 43;
    s.players[0].x = 1.75;
    s.players[0].hp = 75;
    s.players[1].x += 0.125;
    s.monsters[0].state_ticks = 7;
    let mut encoder = TickEncoder::new(&s, 28.0).unwrap();
    let state = encoder.select(&s, 2, &party, 101);
    let delta = encoder
        .packet(
            &s,
            state,
            &mut stream,
            1,
            2,
            &party,
            (8, 1.75, -2.25, 0),
            28.0,
        )
        .unwrap();
    for (name, bytes) in [("interest_full", full), ("interest_delta", delta)] {
        data["fixtures"].as_array_mut().unwrap().push(
            serde_json::json!({"name":name,"direction":"server_to_client","hex":hex(&bytes)}),
        );
    }
    let welcome = wire::encode_welcome(
        &Welcome {
            player_id: 2,
            epoch: 1,
            tick: 42,
            x: 1.5,
            z: -2.25,
            zone_id: 1,
            content_hash: built.hash,
            tick_hz: 20,
        },
        28.0,
    )
    .unwrap();
    data["fixtures"].as_array_mut().unwrap().push(serde_json::json!({"name":"interest_welcome","direction":"server_to_client","hex":hex(&welcome)}));
    data["protocolVersion"] = serde_json::json!(8);
    data["contentHash"] = serde_json::json!(format!("{:016x}", built.hash));
    fs::write(output, serde_json::to_vec_pretty(&data).unwrap()).unwrap();
}
