//! Offline golden export. Reads source content; writes only the explicit output file.
use aetherfield_server::{content, wire, world::{ActionKind, CombatEvent, MonsterSnapshot, PlayerSnapshot, Snapshot, Welcome}};
use std::{fs, path::PathBuf};

fn hex(bytes: &[u8]) -> String { bytes.iter().map(|b|format!("{b:02x}")).collect() }
fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let output = std::env::args().nth(1).expect("explicit external output path");
    let built = content::build_from_source(&root.join("content/source")).expect("source validates");
    let mut data: serde_json::Value = serde_json::from_slice(&fs::read(root.join("apps/protocol/golden-v6.json")).unwrap()).unwrap();
    let player = PlayerSnapshot {id:2,x:1.5,z:-2.25,y:0.0,facing:0.0,hp:80,max_hp:100,connected:true,down:false,dodging:false,guarding:false,anim:0};
    let mut snapshot = Snapshot {tick:42,ack_seq:7,own_flags:0,ack_x:1.5,ack_z:-2.25,players:vec![player],monsters:vec![],events:vec![],pets:vec![]};
    for f in data["fixtures"].as_array_mut().unwrap() {
        let name = f["name"].as_str().unwrap();
        let bytes = match name {
            "welcome_basic" => wire::encode_welcome(&Welcome {player_id:2,epoch:1,tick:42,x:1.5,z:-2.25,zone_id:1,content_hash:built.hash,tick_hz:built.tick_hz},28.0).unwrap(),
            "snapshot_one_player" => wire::encode_snapshot(&snapshot,28.0).unwrap(),
            "snapshot_player_monster_event_u64" => {
                snapshot.monsters=vec![MonsterSnapshot {id:101,kind:1,x:3.5,z:4.0,facing:0.0,hp:90,max_hp:90,active:true,flags:1,state:0,ability:0,state_ticks:0,target_x:3.5,target_z:4.0,target_player_id:None}];
                snapshot.events=vec![CombatEvent {id:9_007_199_254_740_993,source_kind:0,source_id:2,target_kind:0,target_id:101,action:ActionKind::Attack,damage:28,flags:1,world_x:3.5,world_z:4.0}];
                wire::encode_snapshot(&snapshot,28.0).unwrap()
            },
            _ => {let old=f["hex"].as_str().unwrap();let mut bytes=(0..old.len()).step_by(2).map(|i|u8::from_str_radix(&old[i..i+2],16).unwrap()).collect::<Vec<_>>();bytes[2]=wire::PROTOCOL_VERSION;bytes}
        };
        f["hex"]=serde_json::json!(hex(&bytes));
    }
    for (name,flags,damage,mflags) in [("crit_hit",32,42,3),("crit_defeat",33,42,3),("miss_hit",64,0,7),("monster_u32_hp",0,28,7)] {
        snapshot.monsters[0].hp=70_000;snapshot.monsters[0].max_hp=100_000;snapshot.monsters[0].flags=mflags;
        snapshot.events[0].flags=flags;snapshot.events[0].damage=damage;
        data["fixtures"].as_array_mut().unwrap().push(serde_json::json!({"name":name,"direction":"server_to_client","hex":hex(&wire::encode_snapshot(&snapshot,28.0).unwrap())}));
    }
    data["protocolVersion"]=serde_json::json!(wire::PROTOCOL_VERSION);
    data["contentHash"]=serde_json::json!(format!("{:016x}",built.hash));
    fs::write(output,serde_json::to_vec_pretty(&data).unwrap()).expect("external export");
}
