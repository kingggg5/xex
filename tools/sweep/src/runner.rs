use crate::{
    config::{Config, Scenario},
    ledger,
    metrics::{BotMetrics, summarize_samples},
    protocol::{self, CodecError, Decoder, ServerMessage, Snapshot, Welcome},
};
use futures_util::{SinkExt, StreamExt};
use reqwest::{
    Client,
    header::{COOKIE, ORIGIN, SET_COOKIE},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::{Arc, Mutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tokio::{
    net::TcpStream,
    sync::{mpsc, oneshot},
    task::JoinHandle,
    time::{MissedTickBehavior, timeout},
};
use tokio_tungstenite::{
    MaybeTlsStream, WebSocketStream, connect_async_with_config,
    tungstenite::{Message, client::IntoClientRequest, protocol::WebSocketConfig},
};
type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;
type Result<T> = std::result::Result<T, String>;
#[derive(Clone)]
struct Session {
    cookie: String,
}
#[derive(Default)]
struct State {
    connected: bool,
    metrics: BotMetrics,
    party_code: Option<String>,
    party_members: usize,
    zone: u16,
    protocol: u8,
    content_hash: u64,
    visible_players: usize,
    visible_monsters: usize,
    combat_targets: u64,
    combat_ready: bool,
    own_hit_ids: BTreeSet<u64>,
    own_hits: u64,
    movement_samples: u64,
    zone_samples: u64,
    measure_started: Option<Instant>,
    measure_duration_s: f64,
    tower_assigned: bool,
}
enum Command {
    Phase(Scenario, bool, oneshot::Sender<()>),
    Cold(Value),
    Transfer(bool, oneshot::Sender<bool>),
    Freeze(oneshot::Sender<()>),
    Stop,
}
struct Bot {
    tx: mpsc::Sender<Command>,
    state: Arc<Mutex<State>>,
    task: JoinHandle<()>,
    session: Session,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SessionFile {
    cookie: String,
}

fn cookie_valid(s: &str) -> bool {
    let mut keys = std::collections::BTreeSet::new();
    s.len() <= 512
        && !s.is_empty()
        && s.bytes().all(|b| (0x20..0x7f).contains(&b))
        && s.split(';').all(|part| {
            let Some((key, value)) = part.trim().split_once('=') else {
                return false;
            };
            keys.insert(key)
                && matches!(key, "aetherfield_session" | "aetherfield_principal")
                && value.len() == 64
                && value.bytes().all(|b| b.is_ascii_hexdigit())
        })
        && s.split(';')
            .any(|p| p.trim().starts_with("aetherfield_session="))
}
async fn body(mut response: reqwest::Response) -> Result<Vec<u8>> {
    let mut b = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "http_body")? {
        if b.len() + chunk.len() > 65536 {
            return Err("http_body_limit".into());
        }
        b.extend(chunk)
    }
    Ok(b)
}
async fn post(
    client: &Client,
    c: &Config,
    path: &str,
    session: Option<&Session>,
    payload: Option<Value>,
) -> Result<reqwest::Response> {
    let mut request = client
        .post(c.server.join(path).map_err(|_| "http_path")?)
        .header(ORIGIN, &c.origin);
    if let Some(s) = session {
        request = request.header(COOKIE, &s.cookie)
    }
    if let Some(p) = payload {
        request = request.json(&p)
    }
    let response = request.send().await.map_err(|_| "http_transport")?;
    if !response.status().is_success() {
        return Err(format!("http_{}", response.status().as_u16()));
    }
    Ok(response)
}
async fn session(client: &Client, c: &Config) -> Result<Session> {
    let response = post(client, c, "/session", None, None).await?;
    let cookie = response
        .headers()
        .get_all(SET_COOKIE)
        .iter()
        .filter_map(|h| h.to_str().ok())
        .filter_map(|s| s.split(';').next())
        .filter(|s| {
            s.starts_with("aetherfield_session=") || s.starts_with("aetherfield_principal=")
        })
        .collect::<Vec<_>>()
        .join("; ");
    if !cookie_valid(&cookie) {
        return Err("invalid_session_cookie".into());
    }
    Ok(Session { cookie })
}
async fn ticket(client: &Client, c: &Config, s: &Session) -> Result<[u8; 32]> {
    let response = post(client, c, "/session/ticket", Some(s), None).await?;
    let v: Value = serde_json::from_slice(&body(response).await?).map_err(|_| "ticket_json")?;
    protocol::ticket_hex(v["ticket"].as_str().ok_or("ticket_missing")?)
}
async fn send(
    socket: &mut Socket,
    packet: Vec<u8>,
    metrics: Option<&Arc<Mutex<State>>>,
) -> Result<()> {
    let bytes = packet.len() as u64;
    timeout(
        Duration::from_millis(1000),
        socket.send(Message::Binary(packet.into())),
    )
    .await
    .map_err(|_| "ws_write_timeout")?
    .map_err(|_| "ws_write")?;
    if let Some(state) = metrics {
        let mut state = state.lock().unwrap();
        state.metrics.counters.tx_messages += 1;
        state.metrics.counters.tx_bytes += bytes;
    }
    Ok(())
}
async fn connect(client: &Client, c: &Config, s: &Session) -> Result<(Socket, Decoder, Welcome)> {
    let mut version = c.protocol;
    for attempt in 0..2 {
        let t = ticket(client, c, s).await?;
        let mut url = c.server.join("/ws").map_err(|_| "ws_url")?;
        url.set_scheme("ws").map_err(|_| "ws_scheme")?;
        let mut request = url
            .as_str()
            .into_client_request()
            .map_err(|_| "ws_request")?;
        request
            .headers_mut()
            .insert(COOKIE, s.cookie.parse().map_err(|_| "ws_cookie")?);
        request
            .headers_mut()
            .insert(ORIGIN, c.origin.parse().map_err(|_| "ws_origin")?);
        let options = WebSocketConfig::default()
            .max_message_size(Some(16384))
            .max_frame_size(Some(16384))
            .write_buffer_size(0)
            .max_write_buffer_size(32768);
        let (mut ws, _) = timeout(
            Duration::from_secs(5),
            connect_async_with_config(request, Some(options), true),
        )
        .await
        .map_err(|_| "ws_connect_timeout")?
        .map_err(|_| "ws_connect")?;
        send(&mut ws, protocol::join(version, &t), None).await?;
        let mut decoder = Decoder::new(version);
        let first = timeout(Duration::from_secs(5), async {
            loop {
                match ws.next().await {
                    Some(Ok(Message::Binary(b))) => {
                        break decoder.decode(&b).map_err(|_| "join_codec".to_string());
                    }
                    Some(Ok(Message::Ping(_) | Message::Pong(_))) => continue,
                    _ => break Err("join_closed".into()),
                }
            }
        })
        .await
        .map_err(|_| "welcome_timeout")??;
        match first {
            ServerMessage::Welcome(w) => return Ok((ws, decoder, w)),
            ServerMessage::Error {
                code: 1,
                version: announced,
            } if attempt == 0 && c.auto_protocol && announced != version => {
                let _ = timeout(Duration::from_millis(200), ws.close(None)).await;
                version = announced;
            }
            ServerMessage::Error { code, .. } => return Err(format!("join_{code}")),
            _ => return Err("expected_welcome".into()),
        }
    }
    Err("protocol_negotiation_failed".into())
}
async fn spawn_bot(index: usize, c: Arc<Config>, client: Client, s: Session) -> Result<Bot> {
    post(
        &client,
        &c,
        "/session/channel",
        Some(&s),
        Some(json!({"channel":c.channel})),
    )
    .await?;
    let (ws, decoder, w) = connect(&client, &c, &s).await?;
    let homes = if c.scenarios.contains(&Scenario::PartyCombat) {
        combat_homes(w.zone)?
    } else {
        Vec::new()
    };
    let state = Arc::new(Mutex::new(State {
        connected: true,
        zone: w.zone,
        protocol: decoder.version,
        content_hash: w.content_hash,
        ..Default::default()
    }));
    let (tx, rx) = mpsc::channel(32);
    let task = tokio::spawn(drive(
        index,
        c,
        client,
        s.clone(),
        ws,
        decoder,
        w,
        state.clone(),
        rx,
        homes,
    ));
    Ok(Bot {
        tx,
        state,
        task,
        session: s,
    })
}
#[allow(clippy::too_many_arguments)]
async fn drive(
    index: usize,
    c: Arc<Config>,
    client: Client,
    s: Session,
    mut ws: Socket,
    mut decoder: Decoder,
    mut welcome: Welcome,
    state: Arc<Mutex<State>>,
    mut commands: mpsc::Receiver<Command>,
    homes: Vec<(f32, f32)>,
) {
    let mut clock = tokio::time::interval_at(
        tokio::time::Instant::now() + Duration::from_millis(index as u64 % 50),
        Duration::from_millis(50),
    );
    clock.set_missed_tick_behavior(MissedTickBehavior::Skip);
    let mut scenario = Scenario::Idle;
    let mut measuring = false;
    let mut seq = 0u32;
    let start = Instant::now();
    let mut last_ping = Instant::now() - Duration::from_secs(2);
    let mut nonce = 0u32;
    let mut pings: BTreeMap<u32, Instant> = BTreeMap::new();
    let mut calibration: Option<(Instant, f64)> = None;
    let mut previous_receive: Option<Instant> = None;
    let mut snapshot: Option<Snapshot> = None;
    let mut last_attack = Instant::now();
    let mut last_resync = Instant::now() - Duration::from_secs(2);
    let mut death_revision = 0u64;
    let normal_zone = welcome.zone;
    loop {
        let output = tokio::select! {
            command=commands.recv()=>{match command{
                Some(Command::Phase(next,measure,done))=>{scenario=next;measuring=measure;previous_receive=None;pings.clear();let mut st=state.lock().unwrap();st.metrics=BotMetrics::default();st.metrics.party_joined=st.party_members>1;st.combat_targets=0;st.own_hit_ids.clear();st.own_hits=0;if !measure{st.combat_ready=false}st.movement_samples=0;st.zone_samples=0;st.visible_players=0;st.visible_monsters=0;st.measure_started=measure.then(Instant::now);st.measure_duration_s=0.0;let _=done.send(());Vec::new()},
                Some(Command::Freeze(done))=>{measuring=false;let mut st=state.lock().unwrap();st.measure_duration_s=st.measure_started.map_or(0.0,|t|t.elapsed().as_secs_f64());let _=done.send(());Vec::new()},
                Some(Command::Cold(value))=>{match protocol::cold(decoder.version,&value){Ok(packet)=>vec![packet],Err(code)=>{state.lock().unwrap().metrics.add_error("cold",&code);Vec::new()}}},
                Some(Command::Transfer(enter,done))=>{
                    let prior=welcome.zone;let route=if enter{"/tower/enter"}else{"/tower/leave"};
                    let result=async{post(&client,&c,route,Some(&s),None).await?;state.lock().unwrap().tower_assigned=enter;let _=timeout(Duration::from_millis(400),ws.close(None)).await;tokio::time::sleep(Duration::from_millis(150)).await;connect(&client,&c,&s).await}.await;
                    match result{Ok((socket,new_decoder,w))=>{ws=socket;decoder=new_decoder;welcome=w;snapshot=None;calibration=None;pings.clear();previous_receive=None;let mut st=state.lock().unwrap();st.connected=true;st.zone=welcome.zone;st.protocol=decoder.version;st.party_code=None;st.party_members=0;if prior!=welcome.zone{st.metrics.zone_transfers+=1}let _=done.send(prior!=welcome.zone);},Err(code)=>{let mut st=state.lock().unwrap();st.connected=false;st.metrics.add_error("zone_transfer",&code);let _=done.send(false);}}
                    Vec::new()
                },Some(Command::Stop)|None=>break,
            }},
            incoming=ws.next(),if state.lock().unwrap().connected=>{
                match incoming{
                    Some(Ok(Message::Binary(bytes)))=>{
                        let now=Instant::now();if measuring{let mut st=state.lock().unwrap();st.metrics.counters.rx_messages+=1;st.metrics.counters.rx_bytes+=bytes.len() as u64;st.metrics.counters.rx_ws_estimated_bytes+=bytes.len() as u64+if bytes.len()<126{2}else{4};}
                        match decoder.decode(&bytes){
                            Ok(ServerMessage::Snapshot(snap))=>{
                                if measuring{let mut st=state.lock().unwrap();st.metrics.counters.snapshots+=1;if snap.baseline_tick==0{st.metrics.counters.full_snapshots+=1}else{st.metrics.counters.delta_snapshots+=1}st.metrics.counters.combat_events+=snap.event_count as u64;st.visible_players=st.visible_players.max(snap.players.len());st.visible_monsters=st.visible_monsters.max(snap.monsters.len());
                                    if let Some(previous)=previous_receive{st.metrics.receive_gap.push(now.duration_since(previous).as_secs_f64()*1000.0)}
                                    if let Some((anchor,server_ms))=calibration{let estimate=server_ms+now.duration_since(anchor).as_secs_f64()*1000.0-snap.tick as f64*50.0;if estimate<0.0{st.metrics.negative_age_estimates+=1}st.metrics.age.push(estimate.max(0.0));}
                                    for id in &snap.own_hit_ids{if st.own_hit_ids.insert(*id){st.own_hits+=1}while st.own_hit_ids.len()>128{st.own_hit_ids.pop_first();}}
                                    if let Some(old)=&snapshot && (old.own.x-snap.own.x).abs()+(old.own.z-snap.own.z).abs()>0.01{st.movement_samples+=1}
                                    if welcome.zone!=normal_zone{st.zone_samples+=1}
                                }previous_receive=Some(now);let ack=decoder.last_ack().map(|(e,t)|protocol::ack(decoder.version,e,t,false));snapshot=Some(snap);ack.into_iter().collect()
                            },
                            Ok(ServerMessage::Pong{nonce:n,tick})=>{if let Some(sent)=pings.remove(&n){let rtt=now.duration_since(sent);calibration=Some((now,tick as f64*50.0+rtt.as_secs_f64()*500.0));if measuring{state.lock().unwrap().metrics.rtt.push(rtt.as_secs_f64()*1000.0)}}Vec::new()},
                            Ok(ServerMessage::Action{accepted,reason})=>{if measuring{let mut st=state.lock().unwrap();if accepted{st.metrics.counters.action_accepted+=1}else{st.metrics.counters.action_rejected+=1;if reason==7{st.metrics.add_error("action","rate_limited")}}}Vec::new()},
                            Ok(ServerMessage::Cold(v))=>{
                                if v["t"]=="party_state"{let mut st=state.lock().unwrap();st.party_code=v["code"].as_str().filter(|s|s.len()==6&&s.bytes().all(|b|b.is_ascii_alphanumeric())).map(str::to_owned);st.party_members=v["members"].as_array().map_or(0,Vec::len);st.metrics.party_joined=st.party_members>1;}
                                if v["t"]=="notice"&&v["key"]=="death_state"&&v["params"]["down"]==true{let revision=v["params"]["revision"].as_u64().unwrap_or(0);if revision!=0&&revision!=death_revision{death_revision=revision;protocol::cold(decoder.version,&json!({"t":"return_to_town","op_id":uuid::Uuid::new_v4().to_string(),"death_revision":revision})).ok().into_iter().collect()}else{Vec::new()}}else{Vec::new()}
                            },
                            Ok(ServerMessage::Error{code,..})=>{state.lock().unwrap().metrics.add_error("server",&format!("error_{code}"));Vec::new()},
                            Ok(ServerMessage::Welcome(_))=>{state.lock().unwrap().metrics.add_error("codec","unexpected_welcome");Vec::new()},
                            Err(CodecError::Resync(code))=>{let mut st=state.lock().unwrap();if measuring{st.metrics.counters.resyncs+=1;st.metrics.add_error("resync",code)}
                                if now.duration_since(last_resync)>Duration::from_secs(1){last_resync=now;vec![protocol::ack(decoder.version,welcome.epoch,0,true)]}else{Vec::new()}},
                            Err(CodecError::Invalid(code))=>{let mut st=state.lock().unwrap();st.metrics.counters.codec_errors+=1;st.metrics.add_error("codec",code);Vec::new()}
                        }
                    },Some(Ok(Message::Ping(_)|Message::Pong(_)))=>Vec::new(),Some(Ok(Message::Close(_)))|None|Some(Err(_))=>{let mut st=state.lock().unwrap();st.connected=false;st.metrics.add_error("socket","closed");Vec::new()},Some(Ok(_))=>{state.lock().unwrap().metrics.add_error("socket","non_binary");Vec::new()}
                }
            },
            expected=clock.tick()=>{
                if measuring{state.lock().unwrap().metrics.control_lag.push(tokio::time::Instant::now().saturating_duration_since(expected).as_secs_f64()*1000.0)}
                if !state.lock().unwrap().connected{continue}let now=Instant::now();seq=seq.wrapping_add(1).max(1);let t=start.elapsed().as_secs_f32();let mut axis=(0.0,0.0);let mut aim=0.0;let mut target=0;
                if let Some(snap)=&snapshot{
                    if scenario==Scenario::PartyCombat{let plan=combat_plan(snap,&homes,measuring);axis=plan.axis;aim=plan.aim;target=plan.target;let mut st=state.lock().unwrap();st.combat_ready=plan.qualified;if measuring&&plan.visible_target{st.combat_targets+=1}}
                    if snap.own.flags&2==0&&scenario==Scenario::Wander{let angle=t*0.45+index as f32*2.39996;axis=(angle.sin(),angle.cos());if snap.own.x.abs()>24.0||snap.own.z.abs()>24.0{let d=(snap.own.x*snap.own.x+snap.own.z*snap.own.z).sqrt().max(1.0);axis=(-snap.own.x/d,-snap.own.z/d)}aim=axis.0.atan2(axis.1);}
                }
                let mut packets=vec![protocol::input(decoder.version,welcome.epoch,seq,axis.0,axis.1,aim)];
                if target!=0&&now.duration_since(last_attack)>=Duration::from_millis(500){last_attack=now;seq=seq.wrapping_add(1).max(1);packets.push(protocol::action(decoder.version,welcome.epoch,seq,aim,target,snapshot.as_ref().map_or(0,|s|s.tick)));}
                if now.duration_since(last_ping)>=Duration::from_secs(2){last_ping=now;nonce=nonce.wrapping_add(1);pings.retain(|_,t|now.duration_since(*t)<Duration::from_secs(10));if pings.len()<8{pings.insert(nonce,now);packets.push(protocol::ping(decoder.version,nonce,start.elapsed().as_millis() as u32));}}packets
            }
        };
        for packet in output {
            if let Err(code) = send(&mut ws, packet, measuring.then_some(&state)).await {
                let mut st = state.lock().unwrap();
                st.metrics.add_error("send", &code);
                st.connected = false;
                break;
            }
        }
    }
    let _ = timeout(Duration::from_millis(300), ws.close(None)).await;
    state.lock().unwrap().connected = false;
}
fn distance(x: f32, z: f32, a: f32, b: f32) -> f32 {
    (x - a) * (x - a) + (z - b) * (z - b)
}
fn combat_homes(zone: u16) -> Result<Vec<(f32, f32)>> {
    // Frozen authored coordinates only. All movement still uses ordinary inputs.
    let source: Value = serde_json::from_str(include_str!("../../../content/source/zones.json"))
        .map_err(|_| "combat_source_json")?;
    let rows = source["zones"]
        .as_array()
        .and_then(|zones| {
            zones
                .iter()
                .find(|z| z["id"].as_u64() == Some(u64::from(zone)))
        })
        .and_then(|z| z["monster_spawns"].as_array())
        .ok_or("combat_source_zone")?;
    if rows.is_empty() || rows.len() > 64 {
        return Err("combat_source_limit".into());
    }
    rows.iter()
        .map(|row| {
            let x = row["x"].as_f64().ok_or("combat_source_coordinate")? as f32;
            let z = row["z"].as_f64().ok_or("combat_source_coordinate")? as f32;
            if !x.is_finite() || !z.is_finite() || x.abs() > 308.0 || z.abs() > 308.0 {
                return Err("combat_source_coordinate".into());
            }
            Ok((x, z))
        })
        .collect()
}
struct CombatPlan {
    axis: (f32, f32),
    aim: f32,
    target: u32,
    qualified: bool,
    visible_target: bool,
}
fn combat_plan(snapshot: &Snapshot, homes: &[(f32, f32)], measured: bool) -> CombatPlan {
    let mut plan = CombatPlan {
        axis: (0.0, 0.0),
        aim: 0.0,
        target: 0,
        qualified: false,
        visible_target: false,
    };
    if snapshot.own.flags & 2 != 0 || snapshot.own.hp == 0 {
        return plan;
    }
    let own = &snapshot.own;
    let nearest = snapshot
        .monsters
        .iter()
        .filter(|m| m.flags & 1 != 0 && m.hp > 0)
        .min_by(|a, b| {
            distance(own.x, own.z, a.x, a.z)
                .total_cmp(&distance(own.x, own.z, b.x, b.z))
                .then(a.id.cmp(&b.id))
        });
    plan.visible_target = nearest.is_some();
    let point = if measured {
        nearest.map(|m| (m.x, m.z))
    } else {
        homes.iter().copied().min_by(|a, b| {
            distance(own.x, own.z, a.0, a.1).total_cmp(&distance(own.x, own.z, b.0, b.1))
        })
    };
    if let Some((x, z)) = point {
        let dx = x - own.x;
        let dz = z - own.z;
        let d = dx.hypot(dz);
        plan.aim = dx.atan2(dz);
        if measured {
            if d > 1.4 {
                plan.axis = (dx / d, dz / d);
            } else {
                plan.target = nearest.unwrap().id;
            }
        } else if d > 12.0 {
            plan.axis = (dx / d, dz / d);
        }
    }
    if let Some(monster) = nearest {
        let dx = monster.x - own.x;
        let dz = monster.z - own.z;
        let d = dx.hypot(dz);
        plan.qualified = d <= 28.0;
        // Setup never attacks; move away from an approaching mob until outside its aggro range.
        if !measured && d < 10.0 && d > 0.001 {
            plan.axis = (-dx / d, -dz / d);
            plan.aim = dx.atan2(dz);
        }
    }
    plan
}
async fn combat_setup(bots: &[Bot]) -> (usize, f64) {
    let start = Instant::now();
    loop {
        let ready = bots
            .iter()
            .filter(|b| {
                let s = b.state.lock().unwrap();
                s.connected && s.party_members > 1 && s.combat_ready
            })
            .count();
        if ready == bots.len() || start.elapsed() >= Duration::from_secs(90) {
            return (ready, start.elapsed().as_secs_f64());
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
}
async fn phase(bots: &[Bot], sc: Scenario, measured: bool) -> Result<()> {
    for b in bots {
        let (tx, rx) = oneshot::channel();
        timeout(
            Duration::from_secs(2),
            b.tx.send(Command::Phase(sc, measured, tx)),
        )
        .await
        .map_err(|_| "phase_send_timeout")?
        .map_err(|_| "bot_stopped")?;
        timeout(Duration::from_secs(2), rx)
            .await
            .map_err(|_| "phase_ack_timeout")?
            .map_err(|_| "phase_ack_closed")?;
    }
    Ok(())
}
async fn parties(bots: &[Bot]) {
    for group in bots.chunks(4) {
        if group.len() < 2 {
            continue;
        }
        if group[0].state.lock().unwrap().party_members < 2 {
            let _ = group[0]
                .tx
                .send(Command::Cold(json!({"t":"party_create"})))
                .await;
        }
    }
    for _ in 0..40 {
        if bots
            .chunks(4)
            .all(|g| g.len() < 2 || g[0].state.lock().unwrap().party_code.is_some())
        {
            break;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    for group in bots.chunks(4) {
        let code = group[0].state.lock().unwrap().party_code.clone();
        if let Some(code) = code {
            for b in &group[1..] {
                if b.state.lock().unwrap().party_members < 2 {
                    let _ =
                        b.tx.send(Command::Cold(json!({"t":"party_join","code":code})))
                            .await;
                }
            }
        }
    }
}
async fn freeze(bots: &[Bot]) -> Result<()> {
    for b in bots {
        let (tx, rx) = oneshot::channel();
        b.tx.send(Command::Freeze(tx))
            .await
            .map_err(|_| "bot_stopped")?;
        timeout(Duration::from_secs(2), rx)
            .await
            .map_err(|_| "freeze_timeout")?
            .map_err(|_| "freeze_ack")?;
    }
    Ok(())
}
async fn transfers(bots: &[Bot], enter: bool) -> usize {
    futures_util::stream::iter(bots)
        .map(|b| async move {
            let (tx, rx) = oneshot::channel();
            if b.tx.send(Command::Transfer(enter, tx)).await.is_err() {
                return 0;
            }
            match timeout(Duration::from_secs(15), rx).await {
                Ok(Ok(true)) => 1,
                _ => 0,
            }
        })
        .buffer_unordered(16)
        .fold(0, |a, b| async move { a + b })
        .await
}
fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
fn timestamp() -> String {
    let sec = now_ms() / 1000;
    let days = (sec / 86400) as i64;
    let z = days + 719468;
    let era = z / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        sec / 3600 % 24,
        sec / 60 % 60,
        sec % 60
    )
}
fn gpu_lock_present() -> bool {
    std::env::var_os("XEX_GPU_LOCK")
        .map(std::path::PathBuf::from)
        .is_some_and(|p| p.exists())
        || std::env::var_os("XEX_SCRATCH")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| std::env::temp_dir().join("xexoria-capture"))
            .join("gpu-measure.lock")
            .exists()
}
fn build() -> Value {
    let git = std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_owned());
    json!({"git":git,"dirty":null,"dirty_files":null,"client_dirty_files":null,"client_hash":null,"source_sha256":null,"dev_hooks":false,"mode":"rust-network-sweep","server_git":null})
}
async fn profile(client: &Client, c: &Config, baseline: Option<&Value>) -> Option<Value> {
    let path = c.profile_path.as_ref()?;
    let before = baseline?;
    let after = before["end_seq"].as_u64()?;
    let response = client
        .get(c.server.join(path).ok()?)
        .query(&[
            ("channel", c.channel.to_string()),
            ("after", after.to_string()),
            ("run_token", c.run_label.clone()),
        ])
        .header(ORIGIN, &c.origin)
        .send()
        .await
        .ok()?;
    if !response.status().is_success() {
        return None;
    }
    let v: Value = serde_json::from_slice(&body(response).await.ok()?).ok()?;
    validate_profile(&v, before, c.channel, &c.run_label)?;
    Some(
        json!({"verified":true,"sample_count":v["sample_count"],"cpu_ms":v["cpu_ms"],"wall_ms":v["wall_ms"],"phases_ms":v["phases_ms"],"transport":v.get("transport").cloned().unwrap_or(Value::Null),"instance_id":v["instance_id"],"after_seq":v["after_seq"],"end_seq":v["end_seq"],"room_index":v["room_index"],"scope":"selected normal room only; excludes private dungeon instances","cpu_method":"elapsed room-owner work excluding timer wait"}),
    )
}
fn validate_profile(v: &Value, before: &Value, channel: u16, token: &str) -> Option<()> {
    if v["schema"] != "xexoria.tick-profile/1"
        || before["schema"] != "xexoria.tick-profile/1"
        || v["run_token"] != token
        || v["room_index"].as_u64()? != channel as u64
        || v["room_index"] != before["room_index"]
        || v["instance_id"].as_str()?.is_empty()
        || v["instance_id"] != before["instance_id"]
        || v["lost_samples"] != false
    {
        return None;
    }
    let start = before["end_seq"].as_u64()?;
    let end = v["end_seq"].as_u64()?;
    if v["after_seq"].as_u64()? != start
        || end <= start
        || v["sample_count"].as_u64()? != end - start
        || end - start > 4096
    {
        return None;
    }
    let summary = |s: &Value| -> Option<()> {
        let a = s["p50"].as_f64()?;
        let b = s["p95"].as_f64()?;
        let c = s["p99"].as_f64()?;
        if a.is_finite()
            && b.is_finite()
            && c.is_finite()
            && a >= 0.0
            && a <= b
            && b <= c
            && c < 120000.0
        {
            Some(())
        } else {
            None
        }
    };
    summary(&v["cpu_ms"])?;
    summary(&v["wall_ms"])?;
    Some(())
}
async fn execute(
    c: Arc<Config>,
    client: Client,
    bots: &mut Vec<Bot>,
    sessions: Vec<Session>,
) -> Result<bool> {
    let mut pass = true;
    let mut blocked: Option<String> = None;
    let build = build();
    for &requested in &c.counts {
        let mut admission_errors = Vec::new();
        while bots.len() < requested && blocked.is_none() {
            let index = bots.len();
            let s = if c.sessions.is_some() {
                sessions
                    .get(index)
                    .cloned()
                    .ok_or_else(|| "sessions_file_exhausted".to_string())
            } else {
                session(&client, &c).await
            };
            let result = match s {
                Ok(s) => spawn_bot(index, c.clone(), client.clone(), s).await,
                Err(e) => Err(e),
            };
            match result {
                Ok(b) => bots.push(b),
                Err(code) => {
                    admission_errors.push(json!({"bot_index":index,"code":code}));
                    blocked = Some(code);
                }
            }
            tokio::time::sleep(Duration::from_millis(c.ramp_ms)).await;
        }
        for &sc in &c.scenarios {
            phase(bots, sc, false).await?;
            let mut setup = Value::Null;
            if sc == Scenario::PartyCombat {
                parties(bots).await;
                let (qualified, seconds) = combat_setup(bots).await;
                setup = json!({"duration_s":seconds,"limit_s":90,"qualified":qualified,"admitted":bots.len(),"qualification":"connected healthy party member with an active visible target within 28m","method":"ordinary 20Hz movement toward frozen authored homes; no setup attacks","excluded_from_measurement":true});
                if qualified != bots.len() || bots.len() < 2 {
                    pass = false;
                    let artifact = c.output.join(format!(
                        "{}-party-combat-setup-{requested}-{}.json",
                        c.run_label,
                        uuid::Uuid::new_v4()
                    ));
                    let report = json!({"schema":"xexoria.combat-setup/1","ts":timestamp(),"requested":requested,"admitted":bots.len(),"preflight_valid":false,"invalid_reasons":["COMBAT_SETUP_INCOMPLETE"],"measured":false,"combat_setup":setup,"artifact":artifact,"bots":bots.iter().enumerate().map(|(i,b)|{let s=b.state.lock().unwrap();json!({"bot_index":i,"qualified":s.combat_ready&&s.connected&&s.party_members>1,"connected":s.connected,"party_members":s.party_members,"content_hash":format!("{:016x}",s.content_hash)})}).collect::<Vec<_>>()});
                    std::fs::create_dir_all(&c.output).map_err(|_| "output_directory")?;
                    std::fs::write(
                        &artifact,
                        serde_json::to_vec_pretty(&report).map_err(|_| "report_json")?,
                    )
                    .map_err(|_| "report_write")?;
                    println!(
                        "party-combat setup: {qualified}/{} qualified; measured case skipped -> {}",
                        bots.len(),
                        artifact.display()
                    );
                    continue;
                }
            }
            tokio::time::sleep(Duration::from_secs(c.warmup_s)).await;
            let before = if let Some(path) = &c.profile_path {
                match client
                    .get(c.server.join(path).map_err(|_| "profile_path")?)
                    .query(&[("channel", c.channel)])
                    .header(ORIGIN, &c.origin)
                    .send()
                    .await
                {
                    Ok(response) => body(response)
                        .await
                        .ok()
                        .and_then(|b| serde_json::from_slice::<Value>(&b).ok()),
                    Err(_) => None,
                }
            } else {
                None
            };
            phase(bots, sc, true).await?;
            let begin = Instant::now();
            let mut enter_ok = 0;
            let mut leave_ok = 0;
            if sc == Scenario::ZoneChange {
                enter_ok = transfers(bots, true).await;
            }
            tokio::time::sleep(Duration::from_secs(c.duration_s)).await;
            if sc == Scenario::ZoneChange {
                leave_ok = transfers(bots, false).await;
            }
            freeze(bots).await?;
            let elapsed = begin.elapsed().as_secs_f64();
            let tick_profile = profile(&client, &c, before.as_ref()).await;
            let states: Vec<_> = bots.iter().map(|b| b.state.lock().unwrap()).collect();
            let admitted = bots.len();
            let connected = states.iter().filter(|s| s.connected).count();
            let capacity = admitted != requested;
            let mut reasons = Vec::new();
            if capacity {
                reasons.push("ADMISSION_LIMIT")
            }
            if connected != admitted {
                reasons.push("DISCONNECTED")
            }
            if states.iter().any(|s| s.metrics.counters.codec_errors > 0) {
                reasons.push("CODEC_ERROR")
            }
            if states.iter().any(|s| !s.metrics.errors.is_empty()) {
                reasons.push("PROTOCOL_OR_TRANSPORT_ERROR")
            }
            if states.iter().any(|s| s.metrics.counters.snapshots == 0) {
                reasons.push("NO_SNAPSHOTS")
            }
            match sc {
                Scenario::Wander => {
                    if states.iter().any(|s| s.movement_samples == 0) {
                        reasons.push("WANDER_NOT_OBSERVED")
                    }
                }
                Scenario::PartyCombat => {
                    if states.iter().any(|s| s.party_members < 2) || admitted < 2 {
                        reasons.push("PARTY_NOT_FORMED")
                    }
                    if states.iter().any(|s| {
                        s.combat_targets == 0
                            || s.metrics.counters.action_accepted == 0
                            || s.own_hits == 0
                    }) {
                        reasons.push("COMBAT_NOT_OBSERVED")
                    }
                }
                Scenario::ZoneChange
                    if enter_ok != admitted
                        || leave_ok != admitted
                        || states.iter().any(|s| s.zone_samples == 0) =>
                {
                    reasons.push("ZONE_CHANGE_NOT_OBSERVED")
                }
                _ => {}
            }
            let mut reports = Vec::new();
            for (i, s) in states.iter().enumerate() {
                let mut r = s.metrics.report(i, true);
                r["measurement_s"] = json!(s.measure_duration_s);
                r["rx_bytes_per_s"] =
                    json!(s.metrics.counters.rx_bytes as f64 / s.measure_duration_s.max(0.001));
                r["snapshot_hz"] =
                    json!(s.metrics.counters.snapshots as f64 / s.measure_duration_s.max(0.001));
                r["content_hash"] = json!(format!("{:016x}", s.content_hash));
                r["connected_at_end"] = json!(s.connected);
                r["protocol"] = json!(s.protocol);
                r["visible_players_peak"] = json!(s.visible_players);
                r["visible_monsters_peak"] = json!(s.visible_monsters);
                r["movement_samples"] = json!(s.movement_samples);
                r["combat_target_samples"] = json!(s.combat_targets);
                r["own_unique_damage_events"] = json!(s.own_hits);
                r["zone_snapshot_samples"] = json!(s.zone_samples);
                reports.push(r)
            }
            let bytes = states
                .iter()
                .map(|s| s.metrics.counters.rx_bytes)
                .sum::<u64>();
            let snaps = states
                .iter()
                .map(|s| s.metrics.counters.snapshots)
                .sum::<u64>();
            let valid = reasons.is_empty();
            pass &= valid;
            let run_id = format!(
                "{}-{}-{}-{}",
                c.run_label,
                sc.name(),
                requested,
                uuid::Uuid::new_v4()
            );
            let artifact = c.output.join(format!("{run_id}.json"));
            let report = json!({"schema":"xexoria.sweep/1","run_id":run_id,"ts":timestamp(),"scenario":format!("{}-{requested}-bots",sc.name()),"scenario_kind":sc.name(),"requested":requested,"admitted":admitted,"connected_at_end":connected,"not_attempted":requested.saturating_sub(admitted+admission_errors.len()),"admission_errors":admission_errors,"admission_stop_reason":blocked,"capacity_limited":capacity,"preflight_valid":valid,"invalid_reasons":reasons,"budgets_pass":null,"budget_results":[],"build":build,"protocol":states.iter().map(|s|s.protocol).collect::<std::collections::BTreeSet<_>>(),"zone":c.channel,"warmup_s":c.warmup_s,"duration_s":elapsed,"requested_hold_s":c.duration_s,"server_profile":tick_profile,"artifact":artifact,
                "combat_setup":setup,"combat_coverage":{"observed_target_participants":states.iter().filter(|s|s.combat_targets>0).count(),"accepted_action_participants":states.iter().filter(|s|s.metrics.counters.action_accepted>0).count(),"own_damage_participants":states.iter().filter(|s|s.own_hits>0).count(),"own_unique_damage_events":states.iter().map(|s|s.own_hits).sum::<u64>()},
                "warnings":["HEADLESS_NETWORK_ONLY","SERVER_FRAME_BUDGET_UNVERIFIED","SNAPSHOT_AGE_IS_ESTIMATE","SERVER_BUILD_ID_UNVERIFIED"],
                "network":{"rx_application_bytes":bytes,"rx_application_mbit_per_s":bytes as f64*8.0/elapsed/1_000_000.0,"snapshots":snaps,"mean_snapshot_hz_per_admitted":if admitted>0{snaps as f64/elapsed/admitted as f64}else{0.0},"rtt_ms":summarize_samples(states.iter().map(|s|&s.metrics.rtt)),"snapshot_receive_gap_ms":summarize_samples(states.iter().map(|s|&s.metrics.receive_gap)),"estimated_snapshot_age_ms":summarize_samples(states.iter().map(|s|&s.metrics.age)),"driver_control_lag_ms":summarize_samples(states.iter().map(|s|&s.metrics.control_lag)),"age_method":"pong tick at receipt plus RTT/2; tick quantum 50ms; negative estimates clamped and counted per bot","wire_bytes_note":"WebSocket estimate assumes one unmasked binary frame; excludes TCP/IP/handshake/control overhead"},"bots":reports,"zone_transfers":{"entered":enter_ok,"returned":leave_ok}});
            drop(states);
            std::fs::create_dir_all(&c.output).map_err(|_| "output_directory")?;
            std::fs::write(
                &artifact,
                serde_json::to_vec_pretty(&report).map_err(|_| "report_json")?,
            )
            .map_err(|_| "report_write")?;
            ledger::append_row(&c.ledger, &ledger::ledger_row(&report)?)
                .map_err(|_| "ledger_append")?;
            println!(
                "{}: {admitted}/{requested} connected={connected} rx={:.3} Mbit/s valid={valid} -> {}",
                sc.name(),
                bytes as f64 * 8.0 / elapsed / 1_000_000.0,
                artifact.display()
            );
        }
    }
    Ok(pass)
}
pub async fn run(c: Config) -> Result<bool> {
    if !c.ignore_gpu_lock && gpu_lock_present() {
        return Err(
            "capture_lock_present: postpone load sweep or explicitly use --allow-gpu-lock".into(),
        );
    }
    let sessions = if let Some(path) = &c.sessions {
        let meta = std::fs::metadata(path).map_err(|_| "sessions_file_read")?;
        if meta.len() > 1024 * 1024 {
            return Err("sessions_file_limit".into());
        }
        let list: Vec<SessionFile> =
            serde_json::from_slice(&std::fs::read(path).map_err(|_| "sessions_file_read")?)
                .map_err(|_| "sessions_file_json")?;
        if list.len() > 500 || list.iter().any(|s| !cookie_valid(&s.cookie)) {
            return Err("sessions_file_invalid".into());
        }
        let mut unique = std::collections::BTreeSet::new();
        if list.iter().any(|s| {
            !unique.insert(
                s.cookie
                    .split(';')
                    .find(|p| p.trim().starts_with("aetherfield_session="))
                    .unwrap()
                    .trim()
                    .to_ascii_lowercase(),
            )
        }) {
            return Err("sessions_file_duplicate".into());
        }
        list.into_iter()
            .map(|s| Session { cookie: s.cookie })
            .collect()
    } else {
        Vec::new()
    };
    let client = Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(5))
        .build()
        .map_err(|_| "http_client")?;
    let c = Arc::new(c);
    let mut bots = Vec::new();
    let outcome = tokio::select! {result=execute(c.clone(),client.clone(),&mut bots,sessions)=>result,_=tokio::signal::ctrl_c()=>Err("cancelled".into())};
    for b in &bots {
        let _ = b.tx.try_send(Command::Stop);
    }
    for b in bots {
        let mut task = b.task;
        if timeout(Duration::from_secs(2), &mut task).await.is_err() {
            task.abort();
            let _ = task.await;
        } // Remove only this tool's dungeon assignments, never server state or other sessions.
        if b.state.lock().unwrap().tower_assigned {
            let _ = post(&client, &c, "/tower/leave", Some(&b.session), None).await;
        }
    }
    outcome
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cookies_never_accept_headers_or_foreign_names() {
        assert!(!cookie_valid("aetherfield_session=abc\r\nX-Secret: q"));
        assert!(!cookie_valid(&format!("unrelated={}", "a".repeat(64))));
        assert!(!cookie_valid(&format!(
            "aetherfield_session={0}; aetherfield_session={0}",
            "a".repeat(64)
        )));
        assert!(cookie_valid(&format!(
            "aetherfield_session={}",
            "a".repeat(64)
        )));
    }
    #[test]
    fn timestamp_shape() {
        let s = timestamp();
        assert_eq!(s.len(), 20);
        assert_eq!(&s[10..11], "T");
        assert!(s.ends_with('Z'));
    }
    #[test]
    fn combat_setup_uses_authored_homes_and_never_attacks() {
        let homes = combat_homes(1).unwrap();
        assert_eq!(homes.len(), 13);
        assert_eq!(homes[0], (15.0, -1.5));
        let mut s = Snapshot {
            tick: 1,
            baseline_tick: 0,
            own: protocol::Player {
                id: 1,
                hp: 100,
                ..Default::default()
            },
            players: vec![],
            monsters: vec![],
            event_count: 0,
            own_hit_ids: vec![],
        };
        let plan = combat_plan(&s, &[(100.0, 0.0)], false);
        assert_eq!(plan.axis, (1.0, 0.0));
        assert_eq!(plan.target, 0);
        assert!(!plan.qualified);
        s.monsters.push(protocol::Monster {
            id: 101,
            x: 12.0,
            hp: 100,
            flags: 1,
            ..Default::default()
        });
        let setup = combat_plan(&s, &[(12.0, 0.0)], false);
        assert_eq!(setup.target, 0);
        assert!(setup.qualified);
        assert_eq!(setup.axis, (0.0, 0.0));
        let fighting = combat_plan(&s, &homes, true);
        assert_eq!(fighting.axis, (1.0, 0.0));
        s.monsters[0].x = 1.0;
        assert_eq!(combat_plan(&s, &homes, true).target, 101);
        assert_eq!(combat_plan(&s, &homes, false).target, 0);
        s.own.flags = 2;
        assert!(!combat_plan(&s, &homes, false).qualified);
        assert_eq!(combat_plan(&s, &homes, true).target, 0);
    }
    #[test]
    fn tick_profile_rejects_stale_cross_process_and_evicted_windows() {
        let before = json!({"schema":"xexoria.tick-profile/1","room_index":0,"instance_id":"one","end_seq":5});
        let mut v = json!({"schema":"xexoria.tick-profile/1","room_index":0,"instance_id":"one","run_token":"t","after_seq":5,"end_seq":7,"sample_count":2,"lost_samples":false,"cpu_ms":{"p50":1,"p95":2,"p99":3},"wall_ms":{"p50":50,"p95":50,"p99":50}});
        assert!(validate_profile(&v, &before, 0, "t").is_some());
        v["lost_samples"] = json!(true);
        assert!(validate_profile(&v, &before, 0, "t").is_none());
        v["lost_samples"] = json!(false);
        v["instance_id"] = json!("two");
        assert!(validate_profile(&v, &before, 0, "t").is_none());
        v["instance_id"] = json!("one");
        v["after_seq"] = json!(6);
        assert!(validate_profile(&v, &before, 0, "t").is_none());
    }
}
