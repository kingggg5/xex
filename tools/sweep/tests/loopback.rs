//! This is a protocol fixture, NOT the MMO server or a capacity benchmark.
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    task::JoinSet,
};
use tokio_tungstenite::{accept_async, tungstenite::Message};
use xexoria_sweep::{config::Config, protocol, runner};

#[derive(Default)]
struct Fixture {
    next: u32,
    cap: u32,
    zones: BTreeMap<u32, u16>,
    parties: BTreeMap<String, BTreeSet<u32>>,
    acks: u64,
    actions: u64,
    inputs: u64,
    tickets: u64,
}
fn id_from_cookie(text: &str) -> u32 {
    text.lines()
        .find(|l| l.to_ascii_lowercase().starts_with("cookie:"))
        .and_then(|l| l.split("aetherfield_session=").nth(1))
        .and_then(|s| s.split([';', '\r', '\n']).next())
        .and_then(|s| u32::from_str_radix(s.get(56..64)?, 16).ok())
        .unwrap_or(0)
}
fn hex(b: &[u8]) -> String {
    b.iter().map(|b| format!("{b:02x}")).collect()
}
async fn http(mut stream: TcpStream, state: Arc<Mutex<Fixture>>) {
    let mut request = Vec::new();
    let mut chunk = [0u8; 1024];
    loop {
        let n = stream.read(&mut chunk).await.unwrap_or(0);
        if n == 0 {
            return;
        }
        request.extend_from_slice(&chunk[..n]);
        if request.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
        if request.len() > 8192 {
            return;
        }
    }
    let text = String::from_utf8_lossy(&request);
    let route = text
        .lines()
        .next()
        .and_then(|l| l.split(' ').nth(1))
        .unwrap_or("");
    let id = id_from_cookie(&text);
    let (status, headers, body) = {
        let mut st = state.lock().unwrap();
        match route {
            "/session" => {
                if st.next >= st.cap {
                    (429, String::new(), "limited".into())
                } else {
                    st.next += 1;
                    let id = st.next;
                    st.zones.insert(id, 1);
                    (
                        204,
                        format!("Set-Cookie: aetherfield_session={id:064x}; HttpOnly; Path=/\r\n"),
                        String::new(),
                    )
                }
            }
            "/session/channel" => (204, String::new(), String::new()),
            "/session/ticket" => {
                st.tickets += 1;
                let mut t = [1; 32];
                t[..4].copy_from_slice(&id.to_le_bytes());
                (200, String::new(), json!({"ticket":hex(&t)}).to_string())
            }
            "/tower/enter" => {
                st.zones.insert(id, 101);
                (200, String::new(), "{\"floor\":1}".into())
            }
            "/tower/leave" => {
                st.zones.insert(id, 1);
                (204, String::new(), String::new())
            }
            _ => (404, String::new(), "missing".into()),
        }
    };
    let response = format!(
        "HTTP/1.1 {status} Fixture\r\nContent-Length: {}\r\nContent-Type: application/json\r\nConnection: close\r\n{headers}\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes()).await;
}
fn welcome(id: u32, zone: u16) -> Vec<u8> {
    let mut p = id.to_le_bytes().to_vec();
    p.extend(1u32.to_le_bytes());
    p.extend(1u64.to_le_bytes());
    p.extend([0; 8]);
    p.extend(zone.to_le_bytes());
    p.extend(1u64.to_le_bytes());
    p.push(20);
    protocol::envelope(8, 0x81, &p)
}
fn snapshot(id: u32, tick: u64, base: u64, x: f32, z: f32, event: bool) -> Vec<u8> {
    // The fixture exposes the closest authored home so staging exercises the
    // same ordinary steering policy. This remains a synthetic codec server.
    let source: Value =
        serde_json::from_str(include_str!("../../../content/source/zones.json")).unwrap();
    let (mx, mz) = source["zones"][0]["monster_spawns"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            (
                row["x"].as_f64().unwrap() as f32,
                row["z"].as_f64().unwrap() as f32,
            )
        })
        .min_by(|a, b| ((a.0 - x).hypot(a.1 - z)).total_cmp(&(b.0 - x).hypot(b.1 - z)))
        .unwrap();
    let mut p = 1u32.to_le_bytes().to_vec();
    p.extend(tick.to_le_bytes());
    p.extend(base.to_le_bytes());
    p.extend(0u32.to_le_bytes());
    p.push(1);
    p.extend(x.to_le_bytes());
    p.extend(z.to_le_bytes());
    p.extend(id.to_le_bytes());
    p.extend(x.to_le_bytes());
    p.extend(z.to_le_bytes());
    p.extend(0u16.to_le_bytes());
    p.extend(100u16.to_le_bytes());
    p.extend(100u16.to_le_bytes());
    p.extend([1, 0]);
    p.extend(0f32.to_le_bytes());
    p.extend([0, 0, 0]); // targeting, changed peers, removed peers
    p.extend([1, 0]);
    p.extend(101u32.to_le_bytes());
    p.push(127); // changed monster with all groups
    p.extend(mx.to_le_bytes());
    p.extend(mz.to_le_bytes());
    p.extend(0u16.to_le_bytes());
    p.extend(1000u32.to_le_bytes());
    p.extend(1000u32.to_le_bytes());
    p.extend([1, 0, 0]);
    p.extend(tick.to_le_bytes());
    p.extend(x.to_le_bytes());
    p.extend(z.to_le_bytes());
    p.push(1);
    p.extend([0, 0]);
    p.push(u8::from(event));
    if event {
        p.extend(tick.to_le_bytes());
        p.push(0);
        p.extend(id.to_le_bytes());
        p.push(0);
        p.extend(101u32.to_le_bytes());
        p.push(1);
        p.extend(10u16.to_le_bytes());
        p.push(0);
        p.extend(x.to_le_bytes());
        p.extend(z.to_le_bytes());
    }
    protocol::envelope(8, 0x86, &p)
}
async fn websocket(stream: TcpStream, state: Arc<Mutex<Fixture>>) {
    let mut socket = accept_async(stream).await.unwrap();
    let Some(Ok(Message::Binary(join))) = socket.next().await else {
        return;
    };
    assert_eq!(join[3], 1);
    let id = u32::from_le_bytes(join[6..10].try_into().unwrap());
    let zone = *state.lock().unwrap().zones.get(&id).unwrap_or(&1);
    socket
        .send(Message::Binary(welcome(id, zone).into()))
        .await
        .unwrap();
    let mut timer = tokio::time::interval(Duration::from_millis(50));
    timer.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut tick = 1;
    let mut base = 0;
    let (mut x, mut z) = (0f32, 0f32);
    let mut event = false;
    let mut previous_party = String::new();
    loop {
        tokio::select! {
            _=timer.tick()=>{tick+=1;let packet=snapshot(id,tick,base,x,z,event);event=false;if socket.send(Message::Binary(packet.into())).await.is_err(){break}
                let party={let st=state.lock().unwrap();st.parties.iter().find(|(_,m)|m.contains(&id)).map(|(code,m)|json!({"t":"party_state","code":code,"members":m.iter().map(|id|json!({"id":id,"name":"Fixture"})).collect::<Vec<_>>(),"leader":m.iter().next()}))};
                if let Some(party)=party{let text=party.to_string();if text!=previous_party{previous_party=text.clone();if socket.send(Message::Binary(protocol::envelope(8,0x90,text.as_bytes()).into())).await.is_err(){break}}}
            },message=socket.next()=>match message{
                Some(Ok(Message::Binary(b)))=>{match b[3]{
                    // Synthetic fast approach keeps this codec fixture bounded;
                    // it never claims authoritative MMO movement or capacity.
                    2=>{state.lock().unwrap().inputs+=1;let dx=i16::from_le_bytes(b[14..16].try_into().unwrap()) as f32/32767.0;let dz=i16::from_le_bytes(b[16..18].try_into().unwrap()) as f32/32767.0;x+=dx;z+=dz;},
                    3=>{state.lock().unwrap().actions+=1;let mut p=b[10..14].to_vec();p.extend([1,0]);p.extend((tick*50+500).to_le_bytes());if socket.send(Message::Binary(protocol::envelope(8,0x84,&p).into())).await.is_err(){break}event=true;},
                    4=>{let mut p=b[6..14].to_vec();p.extend(tick.to_le_bytes());if socket.send(Message::Binary(protocol::envelope(8,0x85,&p).into())).await.is_err(){break}},
                    5=>{base=u64::from_le_bytes(b[10..18].try_into().unwrap());state.lock().unwrap().acks+=1;},
                0x10=>{let v:Value=serde_json::from_slice(&b[6..]).unwrap();let mut st=state.lock().unwrap();if v["t"]=="party_create"{st.parties.entry(format!("{id:06}")).or_default().insert(id);}else if v["t"]=="party_join"{st.parties.get_mut(v["code"].as_str().unwrap()).unwrap().insert(id);}},_=>panic!("unexpected fixture command"),
                }},Some(Ok(Message::Close(_)))|None|Some(Err(_))=>break,Some(Ok(_))=>{}
            }
        }
    }
}
async fn fixture(state: Arc<Mutex<Fixture>>) -> (u16, tokio::task::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    let task = tokio::spawn(async move {
        let mut tasks = JoinSet::new();
        loop {
            tokio::select! {connection=listener.accept()=>{let(stream,_)=connection.unwrap();let state=state.clone();tasks.spawn(async move{let mut peek=[0;4];let n=stream.peek(&mut peek).await.unwrap();if n>=3&&&peek[..3]==b"GET"{websocket(stream,state).await}else{http(stream,state).await}});},result=tasks.join_next(),if !tasks.is_empty()=>{if let Some(result)=result{result.unwrap();}}}
        }
    });
    (port, task)
}
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn four_scenarios_ack_deltas_and_capacity_failure() {
    let state = Arc::new(Mutex::new(Fixture {
        cap: 4,
        ..Default::default()
    }));
    let (port, task) = fixture(state.clone()).await;
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("evidence/tests")
        .join(uuid::Uuid::new_v4().to_string());
    let ledger = dir.join("ledger.jsonl");
    let args = vec![
        "--server".into(),
        format!("http://127.0.0.1:{port}"),
        "--counts".into(),
        "4,6".into(),
        "--duration".into(),
        "3".into(),
        "--warmup".into(),
        "1".into(),
        "--ramp-ms".into(),
        "50".into(),
        "--out".into(),
        dir.to_string_lossy().to_string(),
        "--ledger".into(),
        ledger.to_string_lossy().to_string(),
        "--label".into(),
        "fixture-only".into(),
        "--allow-gpu-lock".into(),
    ];
    let c = Config::parse(args).unwrap().unwrap();
    let result = runner::run(c).await.unwrap();
    task.abort();
    let _ = task.await;
    assert!(!result, "six requested must not become a four-bot pass");
    let lines = std::fs::read_to_string(&ledger).unwrap();
    let rows = lines
        .lines()
        .map(|l| serde_json::from_str::<Value>(l).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(rows.len(), 8);
    for row in &rows[..4] {
        assert_eq!(row["preflight"]["valid"], true, "{row}");
        assert!(row["frames"]["cpu_ms"].is_null());
        let report: Value = serde_json::from_slice(
            &std::fs::read(row["artifacts"]["shot_json"].as_str().unwrap()).unwrap(),
        )
        .unwrap();
        assert!(report["network"]["snapshots"].as_u64().unwrap() > 0);
        assert!(
            report["bots"]
                .as_array()
                .unwrap()
                .iter()
                .all(|b| b["counters"]["delta_snapshots"].as_u64().unwrap() > 0)
        );
    }
    for row in &rows[4..] {
        assert_eq!(row["verdict"]["capture"], "CAPACITY_LIMIT");
        assert_eq!(row["sweep"]["requested"], 6);
        assert_eq!(row["sweep"]["admitted"], 4);
        assert_eq!(row["verdict"]["pass"], false);
    }
    let state = state.lock().unwrap();
    assert_eq!(state.next, 4, "reuse sessions through counts/scenarios");
    assert!(state.acks > 0 && state.inputs > 0 && state.actions > 0);
    assert!(
        state.zones.values().all(|z| *z == 1),
        "all dungeon assignments cleaned"
    );
    assert_eq!(
        state.tickets, 20,
        "initial joins plus two transfer pairs per bot"
    );
}
