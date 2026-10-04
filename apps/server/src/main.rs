use aetherfield_server::auth::{
    AuthError, AuthManager, CHANNEL_COUNT, ChannelParseError, SessionId, SessionIdentity,
    decode_session_cookie, decode_token_hex, encode_token_hex, parse_channel, principal_cookie,
    session_cookie,
};
use aetherfield_server::character::{CharacterStore, identity_for_principal, identity_for_session};
use aetherfield_server::cold::SocialMemberMsg;
use aetherfield_server::oauth::{OAuthContext, OAuthSettings};
use aetherfield_server::room::{
    ConnectionOutputs, JoinRoute, RoomCommand, RoomHandle, RoomSummary, TowerEnterError,
    TowerService, parse_tower_floor, room_summaries, route_join_durable,
};
use aetherfield_server::social::{FriendError, GroupError, GroupView, PresenceKind, SocialHub};
use aetherfield_server::storage::{
    JoinCharacter, PRINCIPAL_COOKIE_NAME, PrincipalId, StorageHandle,
};
use aetherfield_server::wire::{self, ClientCommand, DecodeError, ErrorCode, PROTOCOL_VERSION};
use aetherfield_server::world::{ActionKind, MAX_PLAYERS};
use axum::{
    Json, Router,
    body::Bytes,
    extract::{
        DefaultBodyLimit, State, Query, ConnectInfo,
        ws::{Message, WebSocket, WebSocketUpgrade},
    },
    http::{
        HeaderMap, HeaderValue, StatusCode,
        header::{CACHE_CONTROL, COOKIE, ORIGIN, SET_COOKIE},
    },
    response::{IntoResponse, Response},
    routing::{get, post},
};
use futures_util::{SinkExt, StreamExt};
use serde::{Serialize,Deserialize};
use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use tokio::{net::TcpListener, sync::Semaphore, time};

/// One room set: exactly [`CHANNEL_COUNT`] independent worlds, spawned at
/// boot and routed by session channel (0..CHANNEL_COUNT).
const ROOM_COUNT: usize = CHANNEL_COUNT as usize;
/// Global socket cap: every room admits at most [`MAX_PLAYERS`] players, so
/// the process never holds more sockets than the rooms can place. Tower
/// instances add their own cap on top (players vacate a normal socket first,
/// but the extra headroom keeps a full field from blocking tower re-entry).
const MAX_CONNECTIONS: usize = ROOM_COUNT * MAX_PLAYERS;
const ALLOWED_ORIGIN: &str = "http://127.0.0.1:5173";
// Isolated local commerce review: another loopback host keeps browser cookies
// separate from the ongoing main playtest. Never accepts an external origin.
fn allowed_origin() -> String {
    if std::env::var("AETHERFIELD_TEST_COMMERCE").as_deref() == Ok("1") {
        if let Ok(origin) = std::env::var("AETHERFIELD_TEST_ORIGIN") {
            if origin.strip_prefix("http://127.0.0.2:").is_some_and(|port| port.parse::<u16>().is_ok_and(|n| n > 0)) { return origin; }
        }
    }
    ALLOWED_ORIGIN.to_string()
}
const SESSION_COOKIE_NAME: &str = "aetherfield_session";
const JOIN_DEADLINE: Duration = Duration::from_secs(5);
const SOCKET_IDLE_TIMEOUT: Duration = Duration::from_secs(120);
/// Token-bucket budgets per message type (R3, plan §9): sustained rate and
/// the burst each bucket holds. Bursts absorb TCP flushes after short
/// stalls; only sustained excess closes the connection, with an Error first.
const INPUT_RATE_PER_SEC: f64 = 25.0;
const INPUT_BURST: f64 = 40.0;
const ACTION_RATE_PER_SEC: f64 = 10.0;
const ACTION_BURST: f64 = 15.0;
const COLD_RATE_PER_SEC: f64 = 5.0;
const COLD_BURST: f64 = 8.0;
const PING_RATE_PER_SEC: f64 = 2.0;
const PING_BURST: f64 = 4.0;
/// Excess must persist this long before the socket is closed with an error.
const SUSTAINED_EXCESS: Duration = Duration::from_secs(3);
/// Live sockets refresh their session this often so continuous play survives
/// the 1 h idle TTL (R12); the resume grace covers the gaps between refreshes.
const SESSION_REFRESH_INTERVAL: Duration = Duration::from_secs(300);
/// Grace for the rate-limited client to receive the Error before the close.
const RATE_CLOSE_GRACE: Duration = Duration::from_millis(150);

#[derive(Clone)]
struct AppState {
    rooms: Arc<Vec<RoomHandle>>,
    auth: Arc<tokio::sync::Mutex<AuthManager>>,
    oauth: Arc<OAuthContext>,
    connection_slots: Arc<Semaphore>,
    world_alive: Arc<Vec<Arc<AtomicBool>>>,
    /// Private per-session tower instances (registry + entry operations).
    towers: Arc<TowerService>,
    /// Cross-instance character store: the wallet seam, and where friend
    /// lists live for the social endpoints.
    store: Arc<CharacterStore>,
    /// Social layer: presence map, groups, friend ops and cross-instance
    /// chat routing (shared with every room/tower world thread).
    social: Arc<SocialHub>,
    /// Durable storage worker (V5-12). `Disabled` keeps the pre-persistence
    /// session-only behavior so dev tools keep working without PostgreSQL.
    storage: StorageHandle,
    /// The canonical first-join seed, cloned per join so the storage worker
    /// can create the durable row with the economy wallet on first sight.
    seed_template: aetherfield_server::character::CharacterRecord,
}

#[derive(Serialize)]
struct Health {
    status: &'static str,
    protocol: u8,
    tick_hz: u8,
    world_alive: bool,
    rooms: usize,
    players: usize,
}

#[derive(Serialize)]
struct JoinTicketResponse {
    ticket: String,
}

#[tokio::main]
async fn main() {
    // R7: content loads (and fails loudly) before any port opens. Every room
    // is an independent world on its own thread. The boot load also carries
    // the tower table's instance cap and floor ceiling.
    let boot_content = aetherfield_server::content::load_built().unwrap_or_else(|error| {
        eprintln!("refusing to start without content: {error}");
        eprintln!(
            "run `cargo run --manifest-path apps/server/Cargo.toml --bin build_content` first."
        );
        std::process::exit(1);
    });
    let (tower_cap, tower_max_floor) = boot_content
        .tower
        .as_ref()
        .map(|tower| (tower.instances_cap, tower.max_floor))
        .unwrap_or((0, 1));
    let fixture=aetherfield_server::sweep_fixture::from_environment().unwrap_or_else(|reason|{eprintln!("FAIL_CAPACITY: private fixture setup refused ({reason})");std::process::exit(1)});
    let auth_manager=match fixture {
        Some(config)=>{let manager=config.create_auth().unwrap_or_else(|reason|{eprintln!("FAIL_CAPACITY: private fixture setup refused ({reason})");std::process::exit(1)});println!("private sweep fixture: 500 disposable guests, credentials written only to guarded private file");manager},
        None=>AuthManager::default(),
    };
    let auth = Arc::new(tokio::sync::Mutex::new(auth_manager));
    // V5-12: durable storage. `connect_from_env` falls back to a disabled
    // handle (with a loud warning) when no database is configured, so local
    // dev tools keep working; playtest/verify runs always set the URL.
    let storage = StorageHandle::connect_from_env().await;
    // One shared character store: wallet/bag/quest/cosmetics/op-caches
    // survive channel switches and tower entry/exit across every instance.
    // Friend lists live here too; the boot content supplies the same
    // first-join seed the worlds use, so a friend write that arrives before
    // the first join cannot zero the wallet.
    let store = CharacterStore::shared();
    let seed_template = aetherfield_server::world::character_record_seed(&boot_content);
    let social = Arc::new(SocialHub::new(store.clone(), seed_template.clone()));
    let (rooms, alive_flags) = RoomHandle::spawn_all_with_storage(
        ROOM_COUNT, &store, &social, &storage,
    )
    .unwrap_or_else(|error| {
        eprintln!("refusing to start without content: {error}");
        eprintln!(
            "run `cargo run --manifest-path apps/server/Cargo.toml --bin build_content` first."
        );
        std::process::exit(1);
    });
    // Tower floor milestones persist the session's best floor in the auth
    // manager; the pump decouples the world threads from the async auth lock.
    let (floor_events_tx, mut floor_events_rx) =
        tokio::sync::mpsc::unbounded_channel::<(SessionId, u16)>();
    let towers = Arc::new(TowerService::with_storage(
        tower_cap,
        tower_max_floor,
        store.clone(),
        social.clone(),
        storage.clone(),
        floor_events_tx,
    ));
    let pump_auth = auth.clone();
    let pump_storage = storage.clone();
    tokio::spawn(async move {
        while let Some((session, floor)) = floor_events_rx.recv().await {
            let mut auth = pump_auth.lock().await;
            auth.set_best_floor(session, floor, Instant::now());
            // Mirror the milestone into the durable character row (V5-12);
            // monotonic max, so late-arriving events cannot lower it.
            if let Some(principal) = auth.principal_of(session, Instant::now()) {
                pump_storage.record_best_floor(principal, floor);
            }
        }
    });
    let world_alive = Arc::new(alive_flags);
    let state = AppState {
        // The worlds live on their own threads from here on; socket tasks
        // never lock them, they only try_send bounded commands (V5-01).
        rooms: Arc::new(rooms),
        oauth: Arc::new(OAuthContext::new_with_storage(
            OAuthSettings::from_env(),
            auth.clone(),
            storage.clone(),
        )),
        connection_slots: Arc::new(Semaphore::new(MAX_CONNECTIONS + usize::from(tower_cap))),
        world_alive: world_alive.clone(),
        auth,
        towers: towers.clone(),
        store: store.clone(),
        social,
        storage,
        seed_template,
    };

    // R7: a dead world is a useless server; fail fast so the failure is loud.
    // Any one dead room kills the process — the set only works whole.
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(1)).await;
            if world_alive.iter().any(|flag| !flag.load(Ordering::SeqCst)) {
                eprintln!("a world thread died; exiting instead of serving dead rooms.");
                std::process::exit(1);
            }
        }
    });

    // Tower completion (or abandonment) tears the instance down and clears
    // the session's assignment, freeing the cap slot.
    let reaper_towers = towers;
    let reaper_auth = state.auth.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_millis(200)).await;
            for session in reaper_towers.reap_completed().await {
                let _ =
                    reaper_auth
                        .lock()
                        .await
                        .set_tower_assignment(session, None, Instant::now());
            }
        }
    });

    let oauth_context = state.oauth.clone();
    let app = Router::new()
        .route("/healthz", get(health))
        .route("/rooms", get(list_rooms))
        .route("/session", post(create_session))
        .route("/session/whoami", get(whoami))
        .route("/session/channel", post(set_session_channel))
        .route("/session/ticket", post(issue_join_ticket))
        .route("/presence", get(presence))
        .route("/tower", get(tower_status))
        .route("/tower/enter", post(tower_enter))
        .route("/tower/leave", post(tower_leave))
        .route("/friends", get(friends_list))
        .route("/friends/add", post(friends_add))
        .route("/friends/remove", post(friends_remove))
        .route("/group", get(group_status))
        .route("/group/create", post(group_create))
        .route("/group/join", post(group_join))
        .route("/group/leave", post(group_leave))
        .route("/ws", get(websocket))
        .merge(if std::env::var("AETHERFIELD_SWEEP_PROFILE").as_deref()==Ok("1") {Router::new().route("/__sweep/profile",get(sweep_profile))}else{Router::new()})
        .with_state(state)
        // The OAuth routes carry their own shared state and merge after the
        // main router becomes stateless.
        .merge(aetherfield_server::oauth::router(oauth_context))
        .layer(DefaultBodyLimit::max(128));
    // Test-only port override so parallel verification runs (review
    // convention: 3911+) never fight over 3001. Full bind configuration
    // lands in V5-05.
    let port: u16 = std::env::var("AETHERFIELD_PORT")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(3001);
    let listener = TcpListener::bind(("127.0.0.1", port))
        .await
        .expect("bind local game server");
    println!("Aetherfield local Rust room listening at http://127.0.0.1:{port}");
    axum::serve(listener, app.into_make_service_with_connect_info::<std::net::SocketAddr>())
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await
        .expect("serve local game room");
}

async fn health(State(state): State<AppState>) -> Json<Health> {
    // R7: report whether every world thread is alive; a dead world exits the
    // process via the supervisor above, so `degraded` covers only the gap.
    let alive = state
        .world_alive
        .iter()
        .all(|flag| flag.load(Ordering::SeqCst));
    Json(Health {
        status: if alive { "ok" } else { "degraded" },
        protocol: PROTOCOL_VERSION,
        tick_hz: 20,
        world_alive: alive,
        rooms: state.rooms.len(),
        players: state.rooms.iter().map(|room| room.occupancy()).sum(),
    })
}

#[derive(Serialize)]
struct RoomsResponse {
    rooms: Vec<RoomSummary>,
}

/// The room browser's load view: one entry per room, `channel` = room index,
/// `players` = live occupancy, `capacity` = the world's per-room cap.
async fn list_rooms(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed_for_get(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let rooms = room_summaries(state.rooms.iter().map(|room| room.occupancy()));
    let mut response = Json(RoomsResponse { rooms }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

#[derive(Serialize)]
struct ChannelResponse {
    channel: Option<u8>,
}

/// Stores the session's channel choice (`{"channel": <0..19>}`) or clears it
/// back to auto (`{"channel": null}`). The next join routes accordingly.
async fn set_session_channel(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let channel = match parse_channel(&body) {
        Ok(channel) => channel,
        Err(ChannelParseError::Malformed) => {
            return no_store_response(StatusCode::BAD_REQUEST, "malformed_body");
        }
        Err(ChannelParseError::Unknown) => {
            return no_store_response(StatusCode::BAD_REQUEST, "unknown_channel");
        }
    };
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    if let Err(error) = state
        .auth
        .lock()
        .await
        .set_channel(session_id, channel, Instant::now())
    {
        return auth_error_response(error);
    }
    let mut response = Json(ChannelResponse { channel }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

async fn create_session(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    if !body.is_empty() {
        return no_store_response(StatusCode::BAD_REQUEST, "body_not_allowed");
    }
    let existing = session_id_from_headers(&headers);
    let session_id = match state.auth.lock().await.create_or_refresh_session(
        existing,
        SessionIdentity::guest(),
        Instant::now(),
    ) {
        Ok(session_id) => session_id,
        Err(error) => return auth_error_response(error),
    };
    // V5-12: resolve (or create) the durable principal behind the browser's
    // principal cookie and bind the session to it. The 30-day cookie is
    // refreshed on every /session so the sliding lifetime holds.
    let (principal, principal_token) = match ensure_principal(&state, &headers, session_id).await {
        Ok(resolve) => resolve,
        Err(response) => return response,
    };
    // Hydrate the session's best floor from the durable row so tower gating
    // survives restarts even before the first join.
    if let Some(best_floor) = state.storage.peek_best_floor(principal).await {
        state
            .auth
            .lock()
            .await
            .set_best_floor(session_id, best_floor, Instant::now());
    }

    let secure = header_requests_https(&headers);
    let mut response = StatusCode::NO_CONTENT.into_response();
    response.headers_mut().insert(
        SET_COOKIE,
        HeaderValue::from_str(&session_cookie(&session_id, secure))
            .expect("hex session cookie is a valid header"),
    );
    response.headers_mut().append(
        SET_COOKIE,
        HeaderValue::from_str(&principal_cookie(&principal_token, secure))
            .expect("hex principal cookie is a valid header"),
    );
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// Resolve the durable principal for a session (V5-12): reuse the browser's
/// principal-cookie token when present, otherwise mint a fresh one, and
/// persist the principal id on the session record. Returns the principal and
/// the token hex (for the Set-Cookie refresh).
async fn ensure_principal(
    state: &AppState,
    headers: &HeaderMap,
    session_id: SessionId,
) -> Result<(PrincipalId, String), Response> {
    let cookie_header = headers
        .get(COOKIE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("");
    let token = decode_session_cookie(cookie_header, PRINCIPAL_COOKIE_NAME)
        .map(|token| encode_token_hex(&token));
    let token = match token {
        Some(token) => token,
        None => encode_token_hex(&aetherfield_server::auth::random_session_token().map_err(
            |_| no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable"),
        )?),
    };
    let principal = state.storage.ensure_principal(&token).await.map_err(|_| {
        no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable")
    })?;
    state
        .auth
        .lock()
        .await
        .set_principal(session_id, principal, Instant::now())
        .map_err(|_| no_store_response(StatusCode::UNAUTHORIZED, "session_unavailable"))?;
    Ok((principal, token))
}

/// `Secure` on the cookies only when the request arrived over TLS (the
/// playtest tunnel); plain local HTTP keeps cookieless-secure off.
fn header_requests_https(headers: &HeaderMap) -> bool {
    headers
        .get("x-forwarded-proto")
        .and_then(|value| value.to_str().ok())
        .is_some_and(|proto| proto.eq_ignore_ascii_case("https"))
}

#[derive(Serialize)]
struct WhoAmIResponse {
    identity: SessionIdentity,
    /// The session's social display name (`Traveler-XXXX`). Additive on top of
    /// the identity block; derived like the character record's seed-once name.
    name: String,
}

/// The login gate's probe: tells the client which identity a live session
/// carries, or 401 when the browser has no session yet (D-13).
async fn whoami(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed_for_get(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let Some(identity) = state
        .auth
        .lock()
        .await
        .identity_of(session_id, Instant::now())
    else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    // The stored record's name wins (it is seed-once stable); the durable
    // principal's derivation covers a fresh session after a restart (V5-12),
    // and the pure session derivation covers sessions that never joined.
    let durable_name = state
        .auth
        .lock()
        .await
        .principal_of(session_id, Instant::now())
        .map(identity_for_principal)
        .map(|(_, name)| name);
    let name = state
        .store
        .peek(session_id)
        .filter(|record| !record.name.is_empty())
        .map(|record| record.name)
        .or(durable_name)
        .unwrap_or_else(|| identity_for_session(session_id).1);
    let mut response = Json(WhoAmIResponse { identity, name }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

async fn issue_join_ticket(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    if !body.is_empty() {
        return no_store_response(StatusCode::BAD_REQUEST, "body_not_allowed");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let ticket = match state
        .auth
        .lock()
        .await
        .issue_ticket(session_id, Instant::now())
    {
        Ok(ticket) => ticket,
        Err(error) => return auth_error_response(error),
    };
    let mut response = Json(JoinTicketResponse {
        ticket: encode_token_hex(&ticket),
    })
    .into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

#[derive(Serialize)]
struct TowerStatusResponse {
    in_tower: bool,
    floor: u16,
    best_floor: u16,
}

/// `GET /tower`: whether the session is inside a tower instance, its current
/// floor (0 outside), and the session's best floor.
async fn tower_status(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed_for_get(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let (in_tower, floor) = state.towers.status(session_id).await;
    let best_floor = state
        .auth
        .lock()
        .await
        .best_floor_of(session_id, Instant::now());
    let mut response = Json(TowerStatusResponse {
        in_tower,
        floor,
        best_floor,
    })
    .into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

#[derive(Serialize)]
struct TowerEnterResponse {
    floor: u16,
}

/// `POST /tower/enter` with an optional `{"floor": n}` body: marks the
/// session's tower assignment and spawns its private instance. The client
/// then disconnects and reconnects; the join routes into that instance
/// (bypassing channel routing) while the assignment exists.
async fn tower_enter(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let requested = match parse_tower_floor(&body) {
        Ok(floor) => floor,
        Err(_) => return no_store_response(StatusCode::BAD_REQUEST, "bad_floor"),
    };
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let best_floor = state
        .auth
        .lock()
        .await
        .best_floor_of(session_id, Instant::now());
    let floor = match state.towers.enter(session_id, requested, best_floor).await {
        Ok(floor) => floor,
        Err(TowerEnterError::BadFloor) => {
            return no_store_response(StatusCode::BAD_REQUEST, "bad_floor");
        }
        Err(TowerEnterError::Full) => {
            return no_store_response(StatusCode::SERVICE_UNAVAILABLE, "tower_full");
        }
        Err(TowerEnterError::Spawn(_)) => {
            return no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable");
        }
    };
    if state
        .auth
        .lock()
        .await
        .set_tower_assignment(session_id, Some(floor), Instant::now())
        .is_err()
    {
        // The session expired mid-enter: do not leak the fresh instance.
        state.towers.leave(session_id).await;
        return no_store_response(StatusCode::UNAUTHORIZED, "session_unavailable");
    }
    let mut response = Json(TowerEnterResponse { floor }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// `POST /tower/leave`: removes the assignment and schedules the instance's
/// teardown. Idempotent.
async fn tower_leave(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    state.towers.leave(session_id).await;
    let _ = state
        .auth
        .lock()
        .await
        .set_tower_assignment(session_id, None, Instant::now());
    let mut response = StatusCode::NO_CONTENT.into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

// ---------------------------------------------------------------------------
// Social layer (P1): presence, friends, groups. All endpoints follow the
// same-origin rule; friend/group endpoints additionally require a session.
// ---------------------------------------------------------------------------

/// One presence entry: a player in a normal room carries `channel`, a player
/// in a tower instance carries `tower: true` plus their `floor`.
#[derive(Serialize)]
struct PresenceEntryResponse {
    handle: String,
    name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    channel: Option<u8>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    tower: bool,
    floor: u16,
}

#[derive(Serialize)]
struct PresenceResponse {
    players: Vec<PresenceEntryResponse>,
}

/// `GET /presence`: every live socket's social identity and where it is.
async fn presence(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed_for_get(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let mut players = Vec::new();
    for entry in state.social.presence_snapshot() {
        match entry.kind {
            PresenceKind::Normal { channel } => players.push(PresenceEntryResponse {
                handle: entry.handle,
                name: entry.name,
                channel: Some(channel),
                tower: false,
                floor: 0,
            }),
            PresenceKind::Tower => {
                // The floor moves while climbing; read it live from the
                // tower registry (never hold the presence lock across this).
                let (_, floor) = state.towers.status(entry.session).await;
                players.push(PresenceEntryResponse {
                    handle: entry.handle,
                    name: entry.name,
                    channel: None,
                    tower: true,
                    floor,
                });
            }
        }
    }
    let mut response = Json(PresenceResponse { players }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

#[derive(Serialize)]
struct FriendsResponse {
    friends: Vec<SocialMemberMsg>,
}

fn friends_response(entries: Vec<SocialMemberMsg>) -> Response {
    let mut response = Json(FriendsResponse { friends: entries }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// `GET /friends`: the session's contact list; offline friends carry
/// `online: false`. One-directional in P1 (a contact list, not mutual
/// friendship).
async fn friends_list(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed_for_get(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    friends_response(state.social.friends_of(session_id))
}

/// `POST /friends/add` with `{"handle": "abcdef12"}`: adds an online player's
/// handle to the session's contact list. Also pushes the fresh roster to the
/// requester over the socket (cold `friends`).
async fn friends_add(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let handle = match parse_friend_handle(&body) {
        Ok(handle) => handle,
        Err(_) => return no_store_response(StatusCode::BAD_REQUEST, "malformed_body"),
    };
    let entries = match state.social.friend_add(session_id, &handle) {
        Ok(entries) => entries,
        Err(FriendError::UnknownPlayer) => {
            return no_store_response(StatusCode::NOT_FOUND, "unknown_player");
        }
        Err(FriendError::SelfAdd) => return no_store_response(StatusCode::BAD_REQUEST, "self_add"),
        Err(FriendError::Full) => return no_store_response(StatusCode::CONFLICT, "friends_full"),
    };
    persist_social_record(&state, session_id).await;
    friends_response(entries)
}

/// Mirror a social-layer record change (friend list) into durable storage.
/// The world thread owns the `owner_epoch`, so this unfenced write is
/// last-writer-wins by design — friend ops are rare and idempotent.
async fn persist_social_record(state: &AppState, session_id: SessionId) {
    let principal = state
        .auth
        .lock()
        .await
        .principal_of(session_id, Instant::now());
    if let (Some(principal), Some(record)) = (principal, state.store.peek(session_id)) {
        let events = tokio::sync::mpsc::unbounded_channel().0;
        state
            .storage
            .save_character(principal, session_id, record, None, None, events);
    }
}

/// `POST /friends/remove` with `{"handle": ...}`: idempotent removal; answers
/// with the fresh roster.
async fn friends_remove(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let handle = match parse_friend_handle(&body) {
        Ok(handle) => handle,
        Err(_) => return no_store_response(StatusCode::BAD_REQUEST, "malformed_body"),
    };
    let entries = state.social.friend_remove(session_id, &handle);
    persist_social_record(&state, session_id).await;
    friends_response(entries)
}

#[derive(Serialize)]
struct GroupResponse {
    group: Option<GroupView>,
}

fn group_response(view: Option<GroupView>) -> Response {
    let mut response = Json(GroupResponse { group: view }).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// `GET /group`: the session's group (code + member roster) or `null`.
async fn group_status(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !origin_is_allowed_for_get(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    match state.social.group_view(session_id) {
        Ok(view) => group_response(view),
        Err(_) => no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable"),
    }
}

/// `POST /group/create`: creates the session's group (leader = creator) and
/// answers with the invite code.
async fn group_create(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    if !body.is_empty() {
        return no_store_response(StatusCode::BAD_REQUEST, "body_not_allowed");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    match state.social.group_create(session_id) {
        Ok(code) => {
            #[derive(Serialize)]
            struct Created {
                code: String,
            }
            let mut response = Json(Created { code }).into_response();
            response
                .headers_mut()
                .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
            response
        }
        Err(GroupError::AlreadyInGroup) => {
            no_store_response(StatusCode::CONFLICT, "already_in_group")
        }
        Err(GroupError::StoreFull) => {
            no_store_response(StatusCode::SERVICE_UNAVAILABLE, "groups_full")
        }
        Err(GroupError::EntropyUnavailable) => {
            no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable")
        }
        Err(_) => no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable"),
    }
}

/// `POST /group/join` with `{"code": "A1B2C3"}`: joins an existing group.
async fn group_join(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    let code = match parse_group_code(&body) {
        Ok(code) => code,
        Err(_) => return no_store_response(StatusCode::BAD_REQUEST, "malformed_body"),
    };
    match state.social.group_join(session_id, &code) {
        Ok(view) => group_response(Some(view)),
        Err(GroupError::UnknownGroup) => no_store_response(StatusCode::NOT_FOUND, "unknown_group"),
        Err(GroupError::Full) => no_store_response(StatusCode::CONFLICT, "group_full"),
        Err(GroupError::AlreadyInGroup) => {
            no_store_response(StatusCode::CONFLICT, "already_in_group")
        }
        Err(_) => no_store_response(StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable"),
    }
}

/// `POST /group/leave`: idempotent. The leader leaving disbands; every online
/// member is pushed the fresh group state (cold `group`).
async fn group_leave(State(state): State<AppState>, headers: HeaderMap, body: Bytes) -> Response {
    if !origin_is_allowed(&headers) {
        return no_store_response(StatusCode::FORBIDDEN, "origin_denied");
    }
    if !body.is_empty() {
        return no_store_response(StatusCode::BAD_REQUEST, "body_not_allowed");
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return no_store_response(StatusCode::UNAUTHORIZED, "session_required");
    };
    state.social.group_leave(session_id).ok();
    let mut response = StatusCode::NO_CONTENT.into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

/// Browsers omit Origin on same-origin GETs, while cross-site fetches and
/// WebSocket upgrades always send one — so a present Origin must match
/// exactly, and an absent one is allowed.
/// Exact Origin check for state-changing POST endpoints and the WebSocket
/// upgrade: browsers always send Origin there, so a missing one is rejected
/// (V4-03 gate).
fn origin_is_allowed(headers: &HeaderMap) -> bool {
    headers.get(ORIGIN).and_then(|value| value.to_str().ok()) == Some(allowed_origin().as_str())
}

/// Origin check for safe GET endpoints: browsers omit Origin on same-origin
/// GET navigations and fetches, so a missing one is allowed — but a present
/// foreign one is still rejected. The session cookie stays the credential.
fn origin_is_allowed_for_get(headers: &HeaderMap) -> bool {
    match headers.get(ORIGIN).and_then(|value| value.to_str().ok()) {
        None => true,
        Some(origin) => origin == allowed_origin(),
    }
}

/// Parses a friend-op body: `{"handle": "abcdef12"}` — exactly 8 lowercase
/// hex chars (the public handle shape). Anything else is a malformed body.
fn parse_friend_handle(body: &[u8]) -> Result<String, ()> {
    if body.is_empty() {
        return Err(());
    }
    let value: serde_json::Value = serde_json::from_slice(body).map_err(|_| ())?;
    let handle = value
        .get("handle")
        .and_then(serde_json::Value::as_str)
        .ok_or(())?;
    let valid = handle.len() == 8
        && handle
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte));
    if valid {
        Ok(handle.to_string())
    } else {
        Err(())
    }
}

/// Parses a group-join body: `{"code": "A1B2C3"}` — exactly 6 alphanumeric
/// characters, normalized to uppercase (the invite-code shape).
fn parse_group_code(body: &[u8]) -> Result<String, ()> {
    if body.is_empty() {
        return Err(());
    }
    let value: serde_json::Value = serde_json::from_slice(body).map_err(|_| ())?;
    let code = value
        .get("code")
        .and_then(serde_json::Value::as_str)
        .ok_or(())?;
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_alphanumeric()) {
        return Err(());
    }
    Ok(code.to_ascii_uppercase())
}

fn session_id_from_headers(headers: &HeaderMap) -> Option<SessionId> {
    let cookie = headers.get(COOKIE)?.to_str().ok()?;
    let mut found = None;
    let mut seen = false;
    for part in cookie.split(';').map(str::trim) {
        let Some(value) = part.strip_prefix(&format!("{SESSION_COOKIE_NAME}=")) else {
            continue;
        };
        if seen {
            return None;
        }
        seen = true;
        found = decode_token_hex(value);
    }
    found
}

fn auth_error_response(error: AuthError) -> Response {
    let (status, message) = match error {
        AuthError::RateLimited => (StatusCode::TOO_MANY_REQUESTS, "rate_limited"),
        AuthError::CapacityExceeded | AuthError::EntropyUnavailable => {
            (StatusCode::SERVICE_UNAVAILABLE, "temporarily_unavailable")
        }
        AuthError::UnknownChannel => (StatusCode::BAD_REQUEST, "unknown_channel"),
        _ => (StatusCode::UNAUTHORIZED, "session_unavailable"),
    };
    no_store_response(status, message)
}

fn no_store_response(status: StatusCode, message: &'static str) -> Response {
    let mut response = (status, message).into_response();
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

fn idle_deadline_expired(last_activity: Instant, now: Instant) -> bool {
    now.saturating_duration_since(last_activity) >= SOCKET_IDLE_TIMEOUT
}

/// Token bucket: `rate_per_sec` tokens accrue up to `burst`. Short TCP
/// flushes after stalls spend the burst; only sustained excess empties it.
/// Once empty, excess must persist for [`SUSTAINED_EXCESS`] before the
/// socket is closed — with an Error first (R3).
struct TokenBucket {
    rate_per_sec: f64,
    burst: f64,
    tokens: f64,
    last_refill: Instant,
    over_since: Option<Instant>,
    excess_drops: u32,
}

impl TokenBucket {
    fn new(rate_per_sec: f64, burst: f64, now: Instant) -> Self {
        Self {
            rate_per_sec,
            burst,
            tokens: burst,
            last_refill: now,
            over_since: None,
            excess_drops: 0,
        }
    }

    /// Consume one token. Returns `Close` only after sustained excess.
    fn consume(&mut self, now: Instant) -> BudgetVerdict {
        let elapsed = now
            .saturating_duration_since(self.last_refill)
            .as_secs_f64();
        self.last_refill = now;
        self.tokens = (self.tokens + elapsed * self.rate_per_sec).min(self.burst);
        if self.tokens >= self.burst {
            self.over_since = None;
            self.excess_drops = 0;
        }
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            return BudgetVerdict::Allow;
        }
        match self.over_since {
            Some(since) => {
                self.excess_drops = self.excess_drops.saturating_add(1);
                if now.saturating_duration_since(since) >= SUSTAINED_EXCESS
                    && self.excess_drops >= 2
                {
                    BudgetVerdict::Close
                } else {
                    BudgetVerdict::Drop
                }
            }
            None => {
                self.over_since = Some(now);
                self.excess_drops = 1;
                BudgetVerdict::Drop
            }
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum BudgetVerdict {
    Allow,
    /// Over budget but not sustained: drop the message, keep the socket.
    Drop,
    /// Sustained excess: send Error(rate_limited), then close.
    Close,
}

/// Per-message-type rate budgets (plan §9, R3).
struct TypeBudgets {
    input: TokenBucket,
    action: TokenBucket,
    cold: TokenBucket,
    ping: TokenBucket,
    snapshot_ack: TokenBucket,
}

impl TypeBudgets {
    fn new(now: Instant) -> Self {
        Self {
            input: TokenBucket::new(INPUT_RATE_PER_SEC, INPUT_BURST, now),
            action: TokenBucket::new(ACTION_RATE_PER_SEC, ACTION_BURST, now),
            cold: TokenBucket::new(COLD_RATE_PER_SEC, COLD_BURST, now),
            ping: TokenBucket::new(PING_RATE_PER_SEC, PING_BURST, now),
            snapshot_ack: TokenBucket::new(24.0,32.0,now),
        }
    }

    fn allow_input(&mut self, now: Instant) -> BudgetVerdict {
        self.input.consume(now)
    }

    fn allow_action(&mut self, now: Instant) -> BudgetVerdict {
        self.action.consume(now)
    }

    fn allow_cold(&mut self, now: Instant) -> BudgetVerdict {
        self.cold.consume(now)
    }

    fn allow_ping(&mut self, now: Instant) -> BudgetVerdict {
        self.ping.consume(now)
    }
}

async fn websocket(
    State(state): State<AppState>,
    headers: HeaderMap,
    ws: WebSocketUpgrade,
) -> Response {
    if !origin_is_allowed(&headers) {
        return (StatusCode::FORBIDDEN, "origin_denied").into_response();
    }
    let Some(session_id) = session_id_from_headers(&headers) else {
        return (StatusCode::UNAUTHORIZED, "session_required").into_response();
    };
    if !state
        .auth
        .lock()
        .await
        .has_live_session(session_id, Instant::now())
    {
        return (StatusCode::UNAUTHORIZED, "session_required").into_response();
    }
    // V5-12: the durable principal rides the browser's principal cookie.
    // Resolved here so the upgrade path can load the character before the
    // world thread ever sees the join.
    let principal_token = headers
        .get(COOKIE)
        .and_then(|value| value.to_str().ok())
        .and_then(|cookie| decode_session_cookie(cookie, PRINCIPAL_COOKIE_NAME))
        .map(|token| encode_token_hex(&token));
    let Ok(permit) = state.connection_slots.clone().try_acquire_owned() else {
        return (StatusCode::SERVICE_UNAVAILABLE, "room_full").into_response();
    };
    ws.max_message_size(wire::MAX_SERVER_PACKET_BYTES)
        .max_frame_size(wire::MAX_SERVER_PACKET_BYTES)
        .on_upgrade(move |socket| handle_socket(socket, state, permit, session_id, principal_token))
}

async fn handle_socket(
    mut socket: WebSocket,
    state: AppState,
    _permit: tokio::sync::OwnedSemaphorePermit,
    authenticated_session: SessionId,
    principal_token: Option<String>,
) {
    let first_message = match time::timeout(JOIN_DEADLINE, socket.recv()).await {
        Ok(Some(Ok(message))) => message,
        _ => return,
    };
    let first_packet = match first_message {
        Message::Binary(packet) if packet.len() <= wire::MAX_CLIENT_PACKET_BYTES => packet,
        Message::Binary(_) => {
            let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::MalformedPacket)).await;
            return;
        }
        Message::Text(_) => {
            let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::MalformedPacket)).await;
            return;
        }
        Message::Ping(_) | Message::Pong(_) | Message::Close(_) => return,
    };
    let command = match wire::decode_client_packet(first_packet.as_ref()) {
        Ok(command) => command,
        Err(DecodeError::UnsupportedVersion(_)) => {
            let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::ProtocolMismatch)).await;
            return;
        }
        Err(_) => {
            let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::MalformedPacket)).await;
            return;
        }
    };
    let ClientCommand::Join { ticket } = command else {
        let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::InvalidJoin)).await;
        return;
    };
    let session_id = {
        let mut auth = state.auth.lock().await;
        match auth.consume_ticket(ticket, authenticated_session, Instant::now()) {
            Ok(session_id) => session_id,
            Err(_) => {
                let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::InvalidJoin)).await;
                return;
            }
        }
    };
    // V5-12: resolve the durable principal for this join. The browser's
    // principal cookie rides along (or a fresh token is minted); the storage
    // worker loads the character and claims a fresh owner epoch. A storage
    // failure refuses the join rather than guessing at durable state.
    let principal_token = match principal_token {
        Some(token) => token,
        None => match aetherfield_server::auth::random_session_token() {
            Ok(token) => encode_token_hex(&token),
            Err(_) => {
                let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::InvalidJoin)).await;
                return;
            }
        },
    };
    let principal = match state.storage.ensure_principal(&principal_token).await {
        Ok(principal) => principal,
        Err(_) => {
            let _ = send_binary(
                &mut socket,
                wire::encode_error(ErrorCode::StorageUnavailable),
            )
            .await;
            return;
        }
    };
    let _ = state
        .auth
        .lock()
        .await
        .set_principal(session_id, principal, Instant::now());
    let mut character: Option<JoinCharacter> = None;
    if state.storage.is_live() {
        let mut seed = state.seed_template.clone();
        let (handle, name) = identity_for_principal(principal);
        seed.handle = handle;
        seed.name = name;
        match state.storage.load_character(principal, seed).await {
            Ok(loaded) => character = Some(loaded),
            Err(_) => {
                let _ = send_binary(
                    &mut socket,
                    wire::encode_error(ErrorCode::StorageUnavailable),
                )
                .await;
                return;
            }
        }
    }
    // Admission goes through the session's tower instance when one is
    // assigned, otherwise the session's chosen room; no socket task locks
    // any world.
    let tower_assigned = state
        .auth
        .lock()
        .await
        .tower_assignment(session_id, Instant::now())
        .is_some();
    let chosen_channel = state
        .auth
        .lock()
        .await
        .channel_of(session_id, Instant::now());
    let tower_instance = state.towers.instance_of(session_id).await;
    let mut route = route_join_durable(
        &state.rooms,
        tower_instance,
        chosen_channel,
        session_id,
        character.clone(),
    )
    .await;
    match route {
        // The assignment outlived its instance: clear it and route normally.
        Ok(JoinRoute::StaleTower) => {
            state.towers.leave(session_id).await;
            let _ = state
                .auth
                .lock()
                .await
                .set_tower_assignment(session_id, None, Instant::now());
            route =
                route_join_durable(&state.rooms, None, chosen_channel, session_id, character).await;
        }
        // The assignment survived but the instance is already gone: clear it
        // and let this join land in a normal room.
        Ok(JoinRoute::Normal { .. }) if tower_assigned => {
            let _ = state
                .auth
                .lock()
                .await
                .set_tower_assignment(session_id, None, Instant::now());
        }
        _ => {}
    }
    let (room, welcome, outputs, presence_kind) = match route {
        Ok(JoinRoute::Tower {
            handle,
            welcome,
            outputs,
        }) => (handle, welcome, outputs, PresenceKind::Tower),
        Ok(JoinRoute::Normal {
            handle,
            welcome,
            outputs,
            index,
        }) => (
            handle,
            welcome,
            outputs,
            PresenceKind::Normal {
                channel: index as u8,
            },
        ),
        Ok(JoinRoute::StaleTower) => unreachable!("stale tower routes are retried above"),
        Err(code) => {
            let _ = send_binary(
                &mut socket,
                wire::encode_error(ErrorCode::from_join_error(code)),
            )
            .await;
            return;
        }
    };
    // Social presence: this session is live in this instance until its socket
    // task ends. The guard removes it on every exit path; a takeover's fresh
    // guard supersedes the old socket's (token-guarded) removal.
    let (presence_handle, presence_name) = match state.store.peek(session_id) {
        Some(record) if !record.handle.is_empty() => (record.handle, record.name),
        _ => identity_for_session(session_id),
    };
    let _presence = state.social.join_guard_principal(
        session_id,
        presence_kind,
        presence_handle,
        presence_name,
        room.clone(),
        principal,
    );
    let player_id = welcome.player_id;
    let epoch = welcome.epoch;
    let conn = outputs.conn;
    let zone_limit = room.zone_limit();
    // FIFO binding precedes every accepted Cold frame, and survives social-presence teardown.
    if !room.submit(RoomCommand::BindChatPrincipal { conn, epoch, principal }) {
        room.submit(RoomCommand::Disconnect { conn, player_id, epoch });
        let _ = send_binary(&mut socket, wire::encode_error(ErrorCode::RoomFull)).await;
        return;
    }
    let welcome_packet = match wire::encode_welcome(&welcome, zone_limit) {
        Ok(packet) => packet,
        Err(_) => {
            room.submit(RoomCommand::Disconnect {
                conn,
                player_id,
                epoch,
            });
            return;
        }
    };
    let welcome_frame_bytes=websocket_frame_bytes(welcome_packet.len());
    if send_binary(&mut socket, welcome_packet).await.is_err() {
        room.submit(RoomCommand::Disconnect {
            conn,
            player_id,
            epoch,
        });
        return;
    }

    if !room.submit(RoomCommand::FrameSent{conn,epoch,frame_bytes:welcome_frame_bytes,writer_age_us:0}){return;}

    let (mut sender, mut receiver) = socket.split();
    let ConnectionOutputs {
        conn: writer_conn,
        snapshots: _,
        mut wire_packets,
        queue_tracker,
        mut reliable,
        mut closed,
    } = outputs;
    debug_assert_eq!(writer_conn, conn);
    // The writer forwards this connection's own snapshot slot (overwritten
    // each tick, never queued) plus its bounded reliable queue.
    let writer_room=room.clone();
    let writer = tokio::spawn(async move {
        loop {
            tokio::select! {
                changed = wire_packets.changed() => {
                    if changed.is_err() {
                        break;
                    }
                    let packet=wire_packets.borrow_and_update().clone();
                    if let Some(time)=packet.published_at {queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner()).begin_snapshot(packet.tick,time);}
                    if sender.send(Message::Binary(packet.bytes.to_vec().into())).await.is_err() {break;}
                    queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner()).complete();
                    if !writer_room.submit(RoomCommand::SnapshotSent{conn,epoch:packet.epoch,tick:packet.tick,frame_bytes:websocket_frame_bytes(packet.bytes.len()),writer_age_us:packet.published_at.map(|time|time.elapsed().as_micros().min(u128::from(u64::MAX)) as u64).unwrap_or(0)}){break;}

                }
                packet = reliable.recv() => {
                    match packet {
                        Some(bytes) => {
                            let frame_bytes=websocket_frame_bytes(bytes.len());
                            let queued_at=bytes.queued_at;
                            queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner()).begin_reliable(queued_at);
                            if sender.send(Message::Binary(bytes.bytes.into())).await.is_err() {
                                break;
                            }
                            queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner()).complete();
                            if !writer_room.submit(RoomCommand::FrameSent{conn,epoch,frame_bytes,writer_age_us:queued_at.elapsed().as_micros().min(u128::from(u64::MAX)) as u64}){break;}
                        }
                        None => break,
                    }
                }
            }
        }
    });

    let mut budgets = TypeBudgets::new(Instant::now());
    let mut last_activity = Instant::now();
    // R12: the session (and its cookie Max-Age) must survive continuous play
    // past the 1 h idle TTL. Refresh with Guest so a provider identity set
    // by OAuth is never overwritten.
    let mut last_refresh = Instant::now();
    async fn refresh_session(state: &AppState, session_id: SessionId) {
        let _ = state.auth.lock().await.create_or_refresh_session(
            Some(session_id),
            SessionIdentity::guest(),
            Instant::now(),
        );
    }
    // R4: the reader also exits when the world drops this connection, so a
    // dead writer can never leave the socket half-open.
    let mut world_closed = false;
    loop {
        if idle_deadline_expired(last_activity, Instant::now()) {
            break;
        }
        let remaining = SOCKET_IDLE_TIMEOUT
            .saturating_sub(Instant::now().saturating_duration_since(last_activity));
        enum Wake {
            Message(Option<Result<Message, axum::Error>>),
            WorldClosed,
            Idle,
        }
        let wake = tokio::select! {
            biased;
            _ = closed.changed() => Wake::WorldClosed,
            next = receiver.next() => Wake::Message(next),
            _ = time::sleep(remaining) => Wake::Idle,
        };
        let message = match wake {
            Wake::WorldClosed => {
                world_closed = true;
                break;
            }
            Wake::Idle => break,
            Wake::Message(None) => break,
            Wake::Message(Some(Err(_))) => break,
            Wake::Message(Some(Ok(message))) => message,
        };
        last_activity = Instant::now();
        if last_activity.saturating_duration_since(last_refresh) >= SESSION_REFRESH_INTERVAL {
            last_refresh = last_activity;
            refresh_session(&state, session_id).await;
        }
        match message {
            Message::Binary(packet) if packet.len() <= wire::MAX_CLIENT_PACKET_BYTES => {
                let Ok(command) = wire::decode_client_packet(packet.as_ref()) else {
                    break;
                };
                // R3: Drop on transient excess; Error(rate_limited) and close
                // only after sustained excess.
                let budgeted_command = match command {
                    ClientCommand::SnapshotAck {epoch:ack_epoch,tick,resync} => {
                        if ack_epoch!=epoch {break;}
                        match budgets.snapshot_ack.consume(last_activity) {BudgetVerdict::Allow=>RoomCommand::SnapshotAck{conn,epoch,tick,resync},BudgetVerdict::Drop=>continue,BudgetVerdict::Close=>{rate_limited_close(&room,conn).await;break;}}
                    }
                    ClientCommand::Ping { nonce, client_ms } => {
                        match budgets.allow_ping(last_activity) {
                            BudgetVerdict::Allow => RoomCommand::Ping {
                                conn,
                                nonce,
                                client_ms,
                            },
                            BudgetVerdict::Drop => continue,
                            BudgetVerdict::Close => {
                                rate_limited_close(&room, conn).await;
                                break;
                            }
                        }
                    }
                    ClientCommand::Cold { payload, .. } => {
                        match budgets.allow_cold(last_activity) {
                            BudgetVerdict::Allow => RoomCommand::Cold { conn, payload },
                            BudgetVerdict::Drop => continue,
                            BudgetVerdict::Close => {
                                rate_limited_close(&room, conn).await;
                                break;
                            }
                        }
                    }
                    ClientCommand::Input { .. } => {
                        match budgets.allow_input(last_activity) {
                            BudgetVerdict::Allow => (),
                            BudgetVerdict::Drop => continue,
                            BudgetVerdict::Close => {
                                rate_limited_close(&room, conn).await;
                                break;
                            }
                        }
                        match to_room_command(command, conn, player_id, epoch) {
                            Ok(room_command) => room_command,
                            Err(()) => break,
                        }
                    }
                    ClientCommand::Action { .. } => {
                        match budgets.allow_action(last_activity) {
                            BudgetVerdict::Allow => (),
                            BudgetVerdict::Drop => continue,
                            BudgetVerdict::Close => {
                                rate_limited_close(&room, conn).await;
                                break;
                            }
                        }
                        match to_room_command(command, conn, player_id, epoch) {
                            Ok(room_command) => room_command,
                            Err(()) => break,
                        }
                    }
                    ClientCommand::Join { .. } => break,
                };
                if !room.submit(budgeted_command) {
                    break;
                }
            }
            Message::Binary(_) | Message::Text(_) => break,
            Message::Close(_) => break,
            Message::Ping(_) | Message::Pong(_) => {}
        }
    }
    writer.abort();
    // One last refresh so a reconnect within the resume grace finds a live
    // session even if the socket dies right before the next interval.
    refresh_session(&state, session_id).await;
    if !world_closed {
        room.submit(RoomCommand::Disconnect {
            conn,
            player_id,
            epoch,
        });
    }
}

/// R3: queue Error(rate_limited) for the writer to flush, give it a grace
/// window, then let the caller break and close the socket.
async fn rate_limited_close(room: &RoomHandle, conn: u64) {
    room.submit(RoomCommand::Notify {
        conn,
        packet: wire::encode_error(ErrorCode::RateLimited),
    });
    time::sleep(RATE_CLOSE_GRACE).await;
}

/// Cheap per-message validation in the socket task. Authority (epoch,
/// sequence, cooldown, range) stays on the world thread.
fn to_room_command(
    command: ClientCommand,
    conn: u64,
    player_id: u32,
    epoch: u32,
) -> Result<RoomCommand, ()> {
    match command {
        ClientCommand::Input {
            epoch: input_epoch,
            sequence,
            x,
            z,
            facing,
            flags,
        } => {
            if input_epoch != epoch {
                return Err(());
            }
            Ok(RoomCommand::Input {
                conn,
                player_id,
                epoch,
                seq: u64::from(sequence),
                x,
                z,
                facing,
                flags,
            })
        }
        ClientCommand::Action {
            epoch: action_epoch,
            sequence,
            ability,
            aim,
            target_id,
            view_tick,
        } => {
            if action_epoch != epoch
                || !matches!(
                    ability,
                    ActionKind::Attack
                        | ActionKind::ArcSlash
                        | ActionKind::Dodge
                        | ActionKind::Guard
                )
            {
                return Err(());
            }
            Ok(RoomCommand::Action {
                conn,
                player_id,
                epoch,
                seq: u64::from(sequence),
                action: ability,
                aim,
                target_id,
                view_tick,
            })
        }
        ClientCommand::Join { .. } | ClientCommand::Ping { .. } | ClientCommand::Cold { .. } | ClientCommand::SnapshotAck { .. } => {
            Err(())
        }
    }
}

fn websocket_frame_bytes(payload:usize)->u32 {(payload+if payload<=125{2}else if payload<=65535{4}else{10}) as u32}


#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SweepProfileQuery {channel:u16,after:Option<u64>,run_token:Option<String>}
fn sweep_profile_guard(peer:std::net::SocketAddr,headers:&HeaderMap,query:&SweepProfileQuery)->Result<(),StatusCode> {
    if !peer.ip().is_loopback()||!origin_is_allowed(headers){return Err(StatusCode::FORBIDDEN);}
    if usize::from(query.channel)>=ROOM_COUNT{return Err(StatusCode::CONFLICT);}
    if query.run_token.as_ref().is_some_and(|token|token.len()>64||token.bytes().any(|b|!b.is_ascii_alphanumeric()&&!matches!(b,b'-'|b'_'|b'.'))){return Err(StatusCode::BAD_REQUEST);}
    Ok(())
}
async fn sweep_profile(State(state):State<AppState>,ConnectInfo(peer):ConnectInfo<std::net::SocketAddr>,headers:HeaderMap,Query(query):Query<SweepProfileQuery>)->Response {
    if let Err(status)=sweep_profile_guard(peer,&headers,&query){return status.into_response();}
    let Some(room)=state.rooms.get(usize::from(query.channel))else{return StatusCode::CONFLICT.into_response();};
    let Some(window)=room.profile_window(query.after,query.run_token.as_deref().unwrap_or(""))else{return StatusCode::NOT_FOUND.into_response();};
    let status=if window["lost_samples"]==true{StatusCode::CONFLICT}else{StatusCode::OK};let mut response=(status,Json(window)).into_response();response.headers_mut().insert(CACHE_CONTROL,HeaderValue::from_static("no-store"));response
}

async fn send_binary(socket: &mut WebSocket, packet: Vec<u8>) -> Result<(), ()> {
    socket
        .send(Message::Binary(packet.into()))
        .await
        .map_err(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn room_set_constants_agree_with_the_session_channel_range() {
        assert_eq!(ROOM_COUNT, 20);
        assert_eq!(ROOM_COUNT, usize::from(CHANNEL_COUNT));
        assert_eq!(MAX_CONNECTIONS, ROOM_COUNT * MAX_PLAYERS);
        assert_eq!(MAX_PLAYERS, 500);
    }

    #[test]
    fn only_the_exact_local_origin_is_allowed() {
        let mut headers = HeaderMap::new();
        assert!(
            !origin_is_allowed(&headers),
            "absent Origin is rejected on POST/WS"
        );
        assert!(
            origin_is_allowed_for_get(&headers),
            "absent Origin is a same-origin GET"
        );
        headers.insert(ORIGIN, HeaderValue::from_static("null"));
        assert!(!origin_is_allowed(&headers));
        assert!(!origin_is_allowed_for_get(&headers));
        headers.insert(ORIGIN, HeaderValue::from_static("http://localhost:5173"));
        assert!(!origin_is_allowed(&headers));
        assert!(!origin_is_allowed_for_get(&headers));
        headers.insert(ORIGIN, HeaderValue::from_static("https://evil.example"));
        assert!(!origin_is_allowed(&headers));
        assert!(!origin_is_allowed_for_get(&headers));
        headers.insert(ORIGIN, HeaderValue::from_static(ALLOWED_ORIGIN));
        assert!(origin_is_allowed(&headers));
        assert!(origin_is_allowed_for_get(&headers));
    }

    #[test]
    fn session_cookie_parser_requires_one_exact_opaque_token() {
        let session_id = [0xa5; 32];
        let mut headers = HeaderMap::new();
        headers.insert(
            COOKIE,
            HeaderValue::from_str(&format!(
                "theme=dark; {SESSION_COOKIE_NAME}={}",
                encode_token_hex(&session_id)
            ))
            .unwrap(),
        );
        assert_eq!(session_id_from_headers(&headers), Some(session_id));

        headers.insert(
            COOKIE,
            HeaderValue::from_str(&format!(
                "{SESSION_COOKIE_NAME}={}, {SESSION_COOKIE_NAME}={}",
                encode_token_hex(&session_id),
                encode_token_hex(&session_id)
            ))
            .unwrap(),
        );
        assert_eq!(session_id_from_headers(&headers), None);
    }

    #[test]
    fn token_buckets_absorb_bursts_and_close_only_on_sustained_excess() {
        let start = Instant::now();
        let mut budgets = TypeBudgets::new(start);
        // Sustained 100/s against a 25/s budget with burst 40.
        let mut now = start;
        let mut verdicts = Vec::new();
        for _ in 0..500 {
            verdicts.push(budgets.allow_input(now));
            now += Duration::from_millis(10);
        }
        // The burst absorbs the opening flush...
        assert!(
            verdicts
                .iter()
                .take(40)
                .all(|verdict| *verdict == BudgetVerdict::Allow)
        );
        // ...then drops hold the socket open once the 40-message burst and
        // the first two seconds of replenishment have been spent...
        assert_eq!(verdicts[199], BudgetVerdict::Drop);
        // ...and only continuous excess past SUSTAINED_EXCESS closes it.
        assert_eq!(verdicts[499], BudgetVerdict::Close);
        let first_close = verdicts
            .iter()
            .position(|verdict| *verdict == BudgetVerdict::Close)
            .expect("excess closes eventually");
        assert!(
            first_close * 10 >= 3000,
            "close must wait out the excess window"
        );
        // Other budgets are independent.
        assert_eq!(budgets.allow_action(start), BudgetVerdict::Allow);
        assert_eq!(budgets.allow_ping(start), BudgetVerdict::Allow);
        // Refill recovers after the storm passes.
        assert_eq!(
            budgets.allow_input(now + Duration::from_secs(2)),
            BudgetVerdict::Allow
        );
    }

    #[test]
    fn socket_idle_deadline_expires_at_the_configured_limit() {
        let last_activity = Instant::now();
        assert!(!idle_deadline_expired(
            last_activity,
            last_activity + SOCKET_IDLE_TIMEOUT - Duration::from_millis(1)
        ));
        assert!(idle_deadline_expired(
            last_activity,
            last_activity + SOCKET_IDLE_TIMEOUT
        ));
    }

    #[test]
    fn friend_handle_bodies_parse_the_exact_handle_shape() {
        assert_eq!(
            parse_friend_handle(br#"{"handle":"a1b2c3d4"}"#),
            Ok("a1b2c3d4".to_string())
        );
        for malformed in [
            &b""[..],
            b"not json",
            b"{}",
            br#"{"handle":42}"#.as_slice(),
            br#"{"handle":"A1B2C3D4"}"#.as_slice(),
            br#"{"handle":"short"}"#.as_slice(),
            br#"{"handle":"a1b2c3d40"}"#.as_slice(),
            br#"{"handle":"a1b2c3dg"}"#.as_slice(),
            br#"{"handle":"a1b2c3d"}"#.as_slice(),
        ] {
            assert_eq!(
                parse_friend_handle(malformed),
                Err(()),
                "{:?} must be a malformed handle body",
                std::str::from_utf8(malformed).unwrap_or("?")
            );
        }
    }

    #[test]
    fn group_code_bodies_parse_and_normalize_to_uppercase() {
        assert_eq!(
            parse_group_code(br#"{"code":"a1b2c3"}"#),
            Ok("A1B2C3".to_string())
        );
        assert_eq!(
            parse_group_code(br#"{"code":"K7Q2XA"}"#),
            Ok("K7Q2XA".to_string())
        );
        for malformed in [
            &b""[..],
            b"not json",
            b"{}",
            br#"{"code":"SHORT"}"#.as_slice(),
            br#"{"code":"a1b2c"}"#.as_slice(),
            br#"{"code":"a1b2c3!"}"#.as_slice(),
            br#"{"code":123456}"#.as_slice(),
        ] {
            assert_eq!(parse_group_code(malformed), Err(()));
        }
    }
    #[test]
    fn snapshot_ack_and_movement_each_allow_twenty_hz_without_sharing_tokens() {
        let started=Instant::now();let mut budgets=TypeBudgets::new(started);
        for tick in 0..400 {let now=started+Duration::from_millis(tick*50);assert_eq!(budgets.allow_input(now),BudgetVerdict::Allow);assert_eq!(budgets.snapshot_ack.consume(now),BudgetVerdict::Allow);if tick%20==0 {assert_eq!(budgets.allow_ping(now),BudgetVerdict::Allow);}}
    }

    #[test]
    fn sweep_profile_access_requires_real_loopback_origin_and_bounded_scope() {
        let mut headers=HeaderMap::new();headers.insert(ORIGIN,HeaderValue::from_static(ALLOWED_ORIGIN));let mut q=SweepProfileQuery{channel:19,after:None,run_token:Some("s1-probe".into())};
        assert_eq!(sweep_profile_guard("127.0.0.1:1234".parse().unwrap(),&headers,&q),Ok(()));
        assert_eq!(sweep_profile_guard("192.0.2.1:1234".parse().unwrap(),&headers,&q),Err(StatusCode::FORBIDDEN));q.channel=20;assert_eq!(sweep_profile_guard("127.0.0.1:1234".parse().unwrap(),&headers,&q),Err(StatusCode::CONFLICT));q.channel=0;q.run_token=Some("unsafe/token".into());assert_eq!(sweep_profile_guard("127.0.0.1:1234".parse().unwrap(),&headers,&q),Err(StatusCode::BAD_REQUEST));q.run_token=None;headers.clear();assert_eq!(sweep_profile_guard("127.0.0.1:1234".parse().unwrap(),&headers,&q),Err(StatusCode::FORBIDDEN));
    }

}
