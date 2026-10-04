//! V5-01 world owner (T06).
//!
//! The simulation [`World`] lives on one dedicated OS thread and is never
//! locked by a socket task. Socket tasks talk to it only through a bounded
//! command inbox (`try_send`, never await) and read per-connection outputs:
//!
//! * a latest-snapshot slot (`watch`, overwritten every tick, never queued),
//! * a bounded reliable queue (`mpsc`, 64 packets) for per-player messages.
//!
//! A failed `try_send` into a full reliable queue drops that packet and
//! counts it; a persistently full queue gets the connection closed. Slow
//! snapshot readers simply observe the newest tick (resync by construction).

use serde::Serialize;
use std::{
    collections::{HashMap, VecDeque},
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU16, AtomicU64, AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};

use tokio::sync::{mpsc, oneshot, watch};

use crate::auth::SessionId;
use crate::character::SharedCharacterStore;
use crate::storage::{JoinCharacter, StorageEvent, StorageHandle};
use crate::world::{ActionKind, Snapshot, Welcome, World};

/// Bound on the world inbox. Socket tasks `try_send` and never wait.
pub const INBOX_BOUND: usize = 8192;
/// Bound on each connection's reliable queue (plan §8: 64 messages).
pub const RELIABLE_BOUND: usize = 64;
/// Per-connection drain budgets per tick (plan §8: 4 inputs, 2 actions,
/// 2 cold messages).
pub const MAX_INPUTS_PER_TICK_PER_CONN: u8 = 4;
pub const MAX_ACTIONS_PER_TICK_PER_CONN: u8 = 2;
pub const MAX_COLD_PER_TICK_PER_CONN: u8 = 2;
/// Upper bound on commands drained in one tick so one burst cannot stall it.
/// The remainder stays queued, still bounded by [`INBOX_BOUND`].
const MAX_COMMANDS_PER_TICK: usize = 4096;
/// Consecutive dropped reliable packets after which the connection is closed.
const RELIABLE_DROP_CLOSE_THRESHOLD: u32 = 16;
/// Last N tick-work samples kept for percentile metrics.
const METRIC_WINDOW: usize = 200;
/// Development metrics cadence.
const METRICS_EVERY: Duration = Duration::from_secs(10);
/// How long a join waits for the world thread to admit it.
const JOIN_TIMEOUT: Duration = Duration::from_secs(2);

pub type ConnectionId = u64;

#[derive(Clone,Default)]
pub struct PublishedSnapshot {pub tick:u64,pub epoch:u32,pub bytes:Arc<[u8]>,pub published_at:Option<Instant>}
#[derive(Debug)]
pub struct QueuedPacket {pub bytes:Vec<u8>,pub queued_at:Instant}
impl std::ops::Deref for QueuedPacket {type Target=[u8];fn deref(&self)->&[u8]{&self.bytes}}
impl PartialEq<Vec<u8>> for QueuedPacket {fn eq(&self,other:&Vec<u8>)->bool{self.bytes==*other}}
/// Bounded metadata for the actual output queues, separate from game state.
#[derive(Default)]
pub struct OutboundQueueState {reliable:VecDeque<Instant>,in_flight:Option<Instant>,snapshot:Option<(u64,Instant)>}
pub type QueueTracker=Arc<std::sync::Mutex<OutboundQueueState>>;
impl OutboundQueueState {
    pub fn oldest_pending_age_us(&self,now:Instant)->Option<u64>{self.reliable.front().copied().into_iter().chain(self.in_flight).chain(self.snapshot.map(|(_,t)|t)).min().map(|time|now.saturating_duration_since(time).as_micros().min(u128::from(u64::MAX)) as u64)}
    pub fn pending_packets(&self)->usize{self.reliable.len()+usize::from(self.in_flight.is_some())+usize::from(self.snapshot.is_some())}
    pub fn begin_reliable(&mut self,time:Instant){let _=self.reliable.pop_front();self.in_flight=Some(time);}
    pub fn begin_snapshot(&mut self,tick:u64,time:Instant){if self.snapshot.is_some_and(|(t,_)|t==tick){self.snapshot=None;}self.in_flight=Some(time);}
    pub fn complete(&mut self){self.in_flight=None;}
}




/// Join carries watch/mpsc senders, so the enum is large by construction.
/// Commands cross the inbox a few dozen times per second at most; the move
/// cost is negligible next to a 50 ms tick. Revisit with AOI (P3).
#[allow(clippy::large_enum_variant)]
pub enum RoomCommand {
    /// Trusted socket task binds the resolved principal before accepting chat frames.
    BindChatPrincipal { conn: ConnectionId, epoch: u32, principal: uuid::Uuid },
    Join {
        conn: ConnectionId,
        session: [u8; 32],
        /// The durable character resolved by the socket task (V5-12); `None`
        /// keeps the session-only seed path (storage disabled / tests).
        character: Option<JoinCharacter>,
        snapshots: watch::Sender<Snapshot>,
        wire_packets: watch::Sender<PublishedSnapshot>,
        queue_tracker: QueueTracker,
        reliable: mpsc::Sender<QueuedPacket>,
        close_send: watch::Sender<bool>,
        reply: oneshot::Sender<Result<Welcome, &'static str>>,
    },
    Input {
        conn: ConnectionId,
        player_id: u32,
        epoch: u32,
        seq: u64,
        x: f32,
        z: f32,
        facing: f32,
        flags: u8,
    },
    Action {
        conn: ConnectionId,
        player_id: u32,
        epoch: u32,
        seq: u64,
        action: ActionKind,
        aim: f32,
        target_id: u32,
        view_tick: u32,
    },
    SnapshotAck {conn:ConnectionId,epoch:u32,tick:u64,resync:bool},
    SnapshotSent {conn:ConnectionId,epoch:u32,tick:u64,frame_bytes:u32,writer_age_us:u64},
    FrameSent {conn:ConnectionId,epoch:u32,frame_bytes:u32,writer_age_us:u64},
    Ping {
        conn: ConnectionId,
        nonce: u32,
        client_ms: u32,
    },
    Cold {
        conn: ConnectionId,
        payload: Vec<u8>,
    },
    /// One pre-encoded packet for exactly one connection.
    /// First gameplay producer lands with V5-06 (character state pushes).
    #[allow(dead_code)]
    Notify { conn: ConnectionId, packet: Vec<u8> },
    /// One pre-encoded packet for every live connection of one session (the
    /// social layer's cross-instance pushes: chat, friends, group state).
    /// Delivered on the world thread through the session → connection map.
    NotifySession { session: [u8; 32], packet: Vec<u8> },
    Disconnect {
        conn: ConnectionId,
        player_id: u32,
        epoch: u32,
    },
}

/// Outputs handed to exactly one connection. Nothing here is shared.
pub struct ConnectionOutputs {
    pub conn: ConnectionId,
    pub snapshots: watch::Receiver<Snapshot>,
    pub wire_packets: watch::Receiver<PublishedSnapshot>,
    pub queue_tracker: QueueTracker,
    pub reliable: mpsc::Receiver<QueuedPacket>,
    /// Fires when the world drops this connection (reader must exit).
    pub closed: watch::Receiver<bool>,
}

struct LiveConnection {
    chat_identity: crate::chat_moderation::ChatIdentity,
    player_id: u32,
    epoch: u32,
    #[allow(dead_code)] // retained for in-process snapshot tests; production publishes encoded bytes
    snapshots: watch::Sender<Snapshot>,
    wire_packets: watch::Sender<PublishedSnapshot>,
    queue_tracker: QueueTracker,
    stream: crate::interest::Stream,
    ordinary_membership:crate::interest::OrdinaryMembership,
    reliable: mpsc::Sender<QueuedPacket>,
    /// Tells the socket task's reader loop to exit (world-initiated close).
    close_send: watch::Sender<bool>,
    /// Consecutive reliable drops; reset on every successful send.
    reliable_drops: u32,
    frame_bytes_window:u64,
    oldest_snapshot_writer_age_us:u64,
    oldest_reliable_writer_age_us:u64,
}

impl LiveConnection {
    /// Returns `true` when the connection must be closed.
    fn push_reliable(&mut self, packet: Vec<u8>, metrics: &mut RoomMetrics) -> bool {
        let queued_at=Instant::now();
        let mut tracker=self.queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner());
        match self.reliable.try_send(QueuedPacket{bytes:packet,queued_at}) {
            Ok(()) => {
                tracker.reliable.push_back(queued_at);debug_assert!(tracker.reliable.len()<=RELIABLE_BOUND+1);
                self.reliable_drops = 0;
                false
            }
            Err(mpsc::error::TrySendError::Full(_)) => {
                self.reliable_drops += 1;
                metrics.reliable_drops += 1;
                self.reliable_drops >= RELIABLE_DROP_CLOSE_THRESHOLD
            }
            Err(mpsc::error::TrySendError::Closed(_)) => true,
        }
    }
}

/// Small pure budget so per-tick fairness is unit-testable without timing.
/// Per connection: 4 inputs, 2 actions, 2 cold messages (plan §8).
#[derive(Default)]
struct PerTickBudget {
    used: HashMap<ConnectionId, [u8; 3]>,
}

impl PerTickBudget {
    fn allow_input(&mut self, conn: ConnectionId) -> bool {
        let entry = self.used.entry(conn).or_insert([0; 3]);
        if entry[0] >= MAX_INPUTS_PER_TICK_PER_CONN {
            return false;
        }
        entry[0] += 1;
        true
    }

    fn allow_action(&mut self, conn: ConnectionId) -> bool {
        let entry = self.used.entry(conn).or_insert([0; 3]);
        if entry[1] >= MAX_ACTIONS_PER_TICK_PER_CONN {
            return false;
        }
        entry[1] += 1;
        true
    }

    fn allow_cold(&mut self, conn: ConnectionId) -> bool {
        let entry = self.used.entry(conn).or_insert([0; 3]);
        if entry[2] >= MAX_COLD_PER_TICK_PER_CONN {
            return false;
        }
        entry[2] += 1;
        true
    }
}

#[derive(Default)]
struct RoomMetrics {
    work_samples: VecDeque<Duration>,
    missed_ticks: u64,
    inbox_high_water: usize,
    dropped_commands: u64,
    reliable_drops: u64,
    resync_closes: u64,
    unhandled_cold: u64,
    snapshot_bytes: u64,
    confirmed_frame_bytes:u64,
    confirmed_total_frame_bytes:u64,
    published_total_snapshot_bytes:u64,
    snapshot_encode_failures: u64,
    window_started_at: Option<Instant>,
    /// Shared live-connection counter, set once when the loop starts. Every
    /// connection insert/removal on this thread keeps it exact.
    occupancy: Occupancy,
}

impl RoomMetrics {
    fn record_work(&mut self, work: Duration) {
        if self.work_samples.len() >= METRIC_WINDOW {
            self.work_samples.pop_front();
        }
        self.work_samples.push_back(work);
    }

    fn percentile(&self, pct: f64) -> Duration {
        if self.work_samples.is_empty() {
            return Duration::ZERO;
        }
        let mut sorted: Vec<Duration> = self.work_samples.iter().copied().collect();
        sorted.sort_unstable();
        let index = ((pct / 100.0) * (sorted.len() as f64 - 1.0)).round() as usize;
        sorted[index.min(sorted.len() - 1)]
    }

    fn report(&mut self, log: &std::sync::mpsc::SyncSender<String>) {
        let now = Instant::now();
        let window_secs = self
            .window_started_at
            .map(|start| now.saturating_duration_since(start).as_secs_f64())
            .unwrap_or(0.0)
            .max(0.1);
        let bytes_per_s = (self.snapshot_bytes as f64 / window_secs).round() as u64;
        log_line(
            log,
            format!(
                "room tick work p50={:?} p95={:?} p99={:?} missed={} inbox_hw={} dropped_cmds={} reliable_drops={} resync_closes={} cold_unhandled={} snapshot_published_bytes_per_s={} ws_confirmed_frame_bytes_per_s={} snap_encode_fail={}",
                self.percentile(50.0),
                self.percentile(95.0),
                self.percentile(99.0),
                self.missed_ticks,
                self.inbox_high_water,
                self.dropped_commands,
                self.reliable_drops,
                self.resync_closes,
                self.unhandled_cold,
                bytes_per_s,
                (self.confirmed_frame_bytes as f64/window_secs).round() as u64,
                self.snapshot_encode_failures,
            ),
        );
        self.snapshot_bytes = 0;
        self.confirmed_frame_bytes=0;
        self.window_started_at = Some(now);
    }
}

fn empty_snapshot() -> Snapshot {
    Snapshot {
        tick: 0,
        ack_seq: 0,
        own_flags: 0,
        ack_x: 0.0,
        ack_z: 0.0,
        players: Vec::new(),
        monsters: Vec::new(),
        events: Vec::new(),
        pets: Vec::new(),
    }
}

/// Deliver one reliable packet to exactly one connection. Connections that
/// must close are fenced out with the epoch they owned (R4).
fn deliver(
    conns: &mut HashMap<ConnectionId, LiveConnection>,
    conn_sessions: &mut HashMap<ConnectionId, [u8; 32]>,
    session_conns: &mut HashMap<[u8; 32], ConnectionId>,
    metrics: &mut RoomMetrics,
    world: &mut World,
    conn: ConnectionId,
    packet: Vec<u8>,
) {
    let must_close = if let Some(live) = conns.get_mut(&conn) {
        let (player_id, epoch) = (live.player_id, live.epoch);
        live.push_reliable(packet, metrics)
            .then_some((player_id, epoch))
    } else {
        None
    };
    if let Some((player_id, epoch)) = must_close {
        drop_conn(
            conns,
            conn_sessions,
            session_conns,
            metrics,
            world,
            conn,
            player_id,
            epoch,
        );
    }
}

/// World-initiated close: signal the socket reader to exit, fence the player
/// out with the epoch this connection owned, and release all per-connection
/// state. A stale epoch makes the disconnect a no-op, so a connection that
/// was already taken over is never disturbed (R4, R5).
#[allow(clippy::too_many_arguments)]
fn drop_conn(
    conns: &mut HashMap<ConnectionId, LiveConnection>,
    conn_sessions: &mut HashMap<ConnectionId, [u8; 32]>,
    session_conns: &mut HashMap<[u8; 32], ConnectionId>,
    metrics: &mut RoomMetrics,
    world: &mut World,
    conn: ConnectionId,
    player_id: u32,
    epoch: u32,
) {
    if let Some(live) = conns.remove(&conn) {
        let _ = live.close_send.send(true);
        metrics.occupancy.dec();
        if let Some(session) = conn_sessions.remove(&conn)
            && session_conns.get(&session) == Some(&conn)
        {
            session_conns.remove(&session);
        }
        metrics.resync_closes += 1;
        world.disconnect(player_id, epoch);
    }
}

/// Release outputs and session maps without signaling or counting (the
/// socket reader is already exiting on its own).
fn release_conn(
    conns: &mut HashMap<ConnectionId, LiveConnection>,
    conn_sessions: &mut HashMap<ConnectionId, [u8; 32]>,
    session_conns: &mut HashMap<[u8; 32], ConnectionId>,
    metrics: &mut RoomMetrics,
    conn: ConnectionId,
) {
    if conns.remove(&conn).is_some() {
        metrics.occupancy.dec();
    }
    if let Some(session) = conn_sessions.remove(&conn)
        && session_conns.get(&session) == Some(&conn)
    {
        session_conns.remove(&session);
    }
}

#[derive(Clone)]
pub struct RoomHandle {
    inbox: mpsc::Sender<RoomCommand>,
    next_conn: std::sync::Arc<AtomicU64>,
    /// Live connection count. The world thread is the only writer, so the
    /// count is exact; cross-thread reads may lag by one tick at worst.
    occupancy: Occupancy,
    /// Set to tear the instance down (tower leave/complete): the world thread
    /// exits on its next tick and further joins are refused immediately.
    closing: Arc<AtomicBool>,
    /// Zone half-extent for wire encoding (R9), from the loaded content.
    zone_limit: f32,
    profile:Option<crate::tick_profile::TickProfile>,
}

/// Live connection count for one room, shared between the world thread
/// (writer) and routing/`/rooms` readers. Never locked: readers tolerate a
/// slightly stale value, the world thread's own join admission is the
/// authoritative capacity gate.
#[derive(Clone, Default)]
pub struct Occupancy(std::sync::Arc<AtomicUsize>);

impl Occupancy {
    fn inc(&self) {
        self.0.fetch_add(1, Ordering::Relaxed);
    }

    fn dec(&self) {
        self.0.fetch_sub(1, Ordering::Relaxed);
    }

    pub fn get(&self) -> usize {
        self.0.load(Ordering::Relaxed)
    }
}

/// Drops the alive flag when the world thread ends, including on panic.
struct AliveGuard(std::sync::Arc<std::sync::atomic::AtomicBool>);

impl Drop for AliveGuard {
    fn drop(&mut self) {
        self.0.store(false, std::sync::atomic::Ordering::SeqCst);
    }
}

/// One room-list entry: the channel (room index), its live player count and
/// the per-room capacity.
#[derive(Serialize)]
pub struct RoomSummary {
    pub channel: u8,
    pub players: usize,
    pub capacity: usize,
}

/// The room browser's load view, in channel order: entry N is channel N.
pub fn room_summaries(occupancy: impl Iterator<Item = usize>) -> Vec<RoomSummary> {
    occupancy
        .enumerate()
        .map(|(index, players)| RoomSummary {
            channel: index as u8,
            players,
            capacity: crate::world::MAX_PLAYERS,
        })
        .collect()
}

/// Auto-routing preference order given per-room occupancy: rooms with space,
/// least-occupied first, ties broken by the lowest channel index. Rooms at
/// `capacity` are skipped entirely.
pub fn auto_route_order(occupancy: &[usize], capacity: usize) -> Vec<usize> {
    let mut candidates: Vec<usize> = (0..occupancy.len())
        .filter(|&index| occupancy[index] < capacity)
        .collect();
    candidates.sort_by_key(|&index| (occupancy[index], index));
    candidates
}

/// Route one join to its room. A stored channel is followed exactly — the
/// room's own world thread enforces capacity and answers `room_full`.
/// Without one, the least-occupied room with space wins; if that room filled
/// up mid-flight, the next candidate is tried, so a routing race can never
/// strand a player on a full room. Returns the room index joined.
pub async fn join_routed(
    rooms: &[RoomHandle],
    chosen: Option<u8>,
    session: [u8; 32],
) -> Result<(usize, Welcome, ConnectionOutputs), &'static str> {
    join_routed_durable(rooms, chosen, session, None).await
}

/// [`join_routed`] with the durable join payload (V5-12).
pub async fn join_routed_durable(
    rooms: &[RoomHandle],
    chosen: Option<u8>,
    session: [u8; 32],
    character: Option<JoinCharacter>,
) -> Result<(usize, Welcome, ConnectionOutputs), &'static str> {
    if let Some(channel) = chosen.filter(|channel| usize::from(*channel) < rooms.len()) {
        let index = usize::from(channel);
        let (welcome, outputs) = rooms[index].join_durable(session, character).await?;
        return Ok((index, welcome, outputs));
    }
    let occupancy: Vec<usize> = rooms.iter().map(RoomHandle::occupancy).collect();
    for index in auto_route_order(&occupancy, crate::world::MAX_PLAYERS) {
        match rooms[index].join_durable(session, character.clone()).await {
            Ok((welcome, outputs)) => return Ok((index, welcome, outputs)),
            Err("room_full") => continue,
            Err(code) => return Err(code),
        }
    }
    Err("room_full")
}

/// What a tower-mode world thread needs beyond a normal room: the bound
/// session and start floor, the completion flag to publish, and where floor
/// milestones go for best_floor persistence.
struct TowerLaunch {
    session: SessionId,
    start_floor: u16,
    completed_tx: watch::Sender<bool>,
    floor_tx: Option<mpsc::UnboundedSender<(SessionId, u16)>>,
    floor_at: Arc<AtomicU16>,
}

impl RoomHandle {
    /// Spawn `count` independent room worlds (one OS thread each). Used at
    /// boot for the full room set; a missing or invalid bundle fails before
    /// any port opens (R7). Every world shares `store` for cross-instance
    /// character state and `social` for the social layer.
    pub fn spawn_all(
        count: usize,
        store: &SharedCharacterStore,
        social: &std::sync::Arc<crate::social::SocialHub>,
    ) -> Result<
        (
            Vec<Self>,
            Vec<std::sync::Arc<std::sync::atomic::AtomicBool>>,
        ),
        crate::content::ContentError,
    > {
        Self::spawn_all_with_storage(count, store, social, &StorageHandle::disabled())
    }

    /// Spawn the room set with the durable storage seam attached (V5-12).
    pub fn spawn_all_with_storage(
        count: usize,
        store: &SharedCharacterStore,
        social: &std::sync::Arc<crate::social::SocialHub>,
        storage: &StorageHandle,
    ) -> Result<
        (
            Vec<Self>,
            Vec<std::sync::Arc<std::sync::atomic::AtomicBool>>,
        ),
        crate::content::ContentError,
    > {
        let mut handles = Vec::with_capacity(count);
        let mut alive_flags = Vec::with_capacity(count);
        for channel in 0..count {
            let profile=(std::env::var("AETHERFIELD_SWEEP_PROFILE").as_deref()==Ok("1")).then(||crate::tick_profile::TickProfile::new(channel as u16));
            let (handle, alive) = Self::spawn_inner(store.clone(),social.clone(),storage.clone(),None,profile)?;
            handles.push(handle);
            alive_flags.push(alive);
        }
        Ok((handles, alive_flags))
    }

    /// Spawn the dedicated world-owner thread and return its handle plus a
    /// liveness flag. Content loads on the calling thread (R7): a missing or
    /// invalid bundle fails here, before any port opens.
    pub fn spawn(
        store: &SharedCharacterStore,
        social: &std::sync::Arc<crate::social::SocialHub>,
    ) -> Result<(Self, std::sync::Arc<std::sync::atomic::AtomicBool>), crate::content::ContentError>
    {
        Self::spawn_with_storage(store, social, &StorageHandle::disabled())
    }

    /// Spawn with the durable storage seam attached (V5-12): saves flow to
    /// the persistence worker and rejections come back through the events.
    pub fn spawn_with_storage(
        store: &SharedCharacterStore,
        social: &std::sync::Arc<crate::social::SocialHub>,
        storage: &StorageHandle,
    ) -> Result<(Self, std::sync::Arc<std::sync::atomic::AtomicBool>), crate::content::ContentError>
    {
        Self::spawn_inner(store.clone(), social.clone(), storage.clone(), None,None)
    }

    /// Spawn a tower instance: a full world (own thread, same content and
    /// curves) bound to one session at `start_floor`. The returned
    /// [`TowerInstance`] carries the completion flag for the registry watcher
    /// and the live floor for `GET /tower`. Tower instances share `social`
    /// too: group chat and friend ops work while climbing.
    pub fn spawn_tower(
        store: &SharedCharacterStore,
        social: &std::sync::Arc<crate::social::SocialHub>,
        session: SessionId,
        start_floor: u16,
        floor_tx: Option<mpsc::UnboundedSender<(SessionId, u16)>>,
    ) -> Result<TowerInstance, crate::content::ContentError> {
        Self::spawn_tower_with_storage(
            store,
            social,
            &StorageHandle::disabled(),
            session,
            start_floor,
            floor_tx,
        )
    }

    /// Tower spawn with the durable storage seam attached (V5-12).
    pub fn spawn_tower_with_storage(
        store: &SharedCharacterStore,
        social: &std::sync::Arc<crate::social::SocialHub>,
        storage: &StorageHandle,
        session: SessionId,
        start_floor: u16,
        floor_tx: Option<mpsc::UnboundedSender<(SessionId, u16)>>,
    ) -> Result<TowerInstance, crate::content::ContentError> {
        let (completed_tx, completed_rx) = watch::channel(false);
        let floor_at = Arc::new(AtomicU16::new(start_floor));
        let (handle, _alive) = Self::spawn_inner(
            store.clone(),
            social.clone(),
            storage.clone(),
            Some(TowerLaunch {
                session,
                start_floor,
                completed_tx,
                floor_tx,
                floor_at: floor_at.clone(),
            }),
            None,
        )?;
        Ok(TowerInstance {
            handle,
            session,
            completed: completed_rx,
            floor: floor_at,
        })
    }

    fn spawn_inner(
        store: SharedCharacterStore,
        social: std::sync::Arc<crate::social::SocialHub>,
        storage: StorageHandle,
        tower: Option<TowerLaunch>,
        profile:Option<crate::tick_profile::TickProfile>,
    ) -> Result<(Self, std::sync::Arc<std::sync::atomic::AtomicBool>), crate::content::ContentError>
    {
        let content = crate::content::load_built()?;
        let zone_limit = content.zone_half_extent;
        let (inbox_tx, inbox_rx) = mpsc::channel(INBOX_BOUND);
        // Durable-save rejections route back into the world loop through one
        // unbounded event channel, drained every tick like floor events.
        let (storage_events_tx, storage_events_rx) = mpsc::unbounded_channel::<StorageEvent>();
        let alive = Arc::new(AtomicBool::new(true));
        // R8: world-thread logging leaves through a bounded queue so a stuck
        // console (Windows QuickEdit, closed stdout) can never freeze the room.
        let (log_tx, log_rx) = std::sync::mpsc::sync_channel::<String>(128);
        std::thread::Builder::new()
            .name("room-log".to_string())
            .spawn(move || {
                for line in log_rx {
                    println!("{line}");
                }
            })
            .expect("spawn room log thread");
        let alive_thread = alive.clone();
        let occupancy = Occupancy::default();
        let occupancy_thread = occupancy.clone();
        let closing = Arc::new(AtomicBool::new(false));
        let closing_thread = closing.clone();
        let profile_thread=profile.clone();
        let thread_name = if tower.is_some() {
            "tower-owner"
        } else {
            "world-owner"
        };
        std::thread::Builder::new()
            .name(thread_name.to_string())
            .spawn(move || {
                let _guard = AliveGuard(alive_thread);
                let runtime = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .expect("world-owner runtime");
                runtime.block_on(world_loop(
                    inbox_rx,
                    content,
                    WorldServices {
                        log: log_tx,
                        occupancy: occupancy_thread,
                        store: store.clone(),
                        social,
                        closing: closing_thread,
                        storage: storage.clone(),
                        storage_events: storage_events_tx,
                        profile:profile_thread,
                    },
                    tower,
                    storage_events_rx,
                ));
            })
            .expect("spawn world-owner thread");
        Ok((
            Self {
                inbox: inbox_tx,
                next_conn: Arc::new(AtomicU64::new(1)),
                occupancy,
                closing,
                zone_limit,
                profile,
            },
            alive,
        ))
    }

    /// Zone half-extent for wire encoding (R9), from the loaded content.
    pub fn zone_limit(&self) -> f32 {
        self.zone_limit
    }

    pub fn profile_window(&self,after:Option<u64>,token:&str)->Option<serde_json::Value>{self.profile.as_ref().map(|profile|profile.window(after,token))}

    /// Schedule this instance's teardown: the world thread exits on its next
    /// tick and new joins are refused immediately. Tower instances are closed
    /// on leave/completion; normal rooms never close.
    pub fn close_instance(&self) {
        self.closing.store(true, Ordering::SeqCst);
    }

    /// Admit one session through the world thread (session-only: no durable
    /// character). Tests and session-only boots use this path.
    pub async fn join(
        &self,
        session: [u8; 32],
    ) -> Result<(Welcome, ConnectionOutputs), &'static str> {
        self.join_inner(session, None).await
    }

    /// Admit one session with the durable character resolved by the socket
    /// task (V5-12): the world adopts the storage worker's record and epoch.
    pub async fn join_durable(
        &self,
        session: [u8; 32],
        character: Option<JoinCharacter>,
    ) -> Result<(Welcome, ConnectionOutputs), &'static str> {
        self.join_inner(session, character).await
    }

    async fn join_inner(
        &self,
        session: [u8; 32],
        character: Option<JoinCharacter>,
    ) -> Result<(Welcome, ConnectionOutputs), &'static str> {
        if self.closing.load(Ordering::SeqCst) {
            return Err("room_full");
        }
        let conn = self.next_conn.fetch_add(1, Ordering::Relaxed).max(1);
        let (snapshot_tx, snapshots) = watch::channel(empty_snapshot());
        let (wire_tx, wire_packets) = watch::channel(PublishedSnapshot::default());
        let queue_tracker=QueueTracker::default();
        let (reliable_tx, reliable) = mpsc::channel(RELIABLE_BOUND);
        let (close_tx, closed) = watch::channel(false);
        let (reply_tx, reply_rx) = oneshot::channel();
        self.inbox
            .try_send(RoomCommand::Join {
                conn,
                session,
                character,
                snapshots: snapshot_tx,
                wire_packets: wire_tx,
                queue_tracker:queue_tracker.clone(),
                reliable: reliable_tx,
                close_send: close_tx,
                reply: reply_tx,
            })
            .map_err(|_| "room_full")?;
        let welcome = match tokio::time::timeout(JOIN_TIMEOUT, reply_rx).await {
            Ok(Ok(Ok(welcome))) => welcome,
            _ => {
                // R4: the world may admit after we give up; fence that
                // cleanup with whatever this conn owned (usually nothing).
                let _ = self.inbox.try_send(RoomCommand::Disconnect {
                    conn,
                    player_id: 0,
                    epoch: 0,
                });
                return Err("room_full");
            }
        };
        Ok((
            welcome,
            ConnectionOutputs {
                conn,
                snapshots,
                wire_packets,
                queue_tracker,
                reliable,
                closed,
            },
        ))
    }

    /// Fire-and-forget command submit. `false` means the inbox was full or the
    /// world is gone; the caller must close the socket.
    pub fn submit(&self, command: RoomCommand) -> bool {
        self.inbox.try_send(command).is_ok()
    }

    /// The room's live connection count, kept exact by the world thread
    /// (writer) and read lock-free for routing and `GET /rooms`.
    pub fn occupancy(&self) -> usize {
        self.occupancy.get()
    }

    /// Queue one pre-encoded packet for exactly one connection. Acceptance
    /// into the inbox is reported; delivery accounting (drops, closes) lives
    /// on the world thread. The first gameplay producer lands with V5-06.
    #[allow(dead_code)]
    pub fn notify(&self, conn: ConnectionId, packet: Vec<u8>) -> bool {
        self.submit(RoomCommand::Notify { conn, packet })
    }

    #[allow(dead_code)]
    pub fn inbox_pressure(&self) -> f64 {
        let max = self.inbox.max_capacity();
        if max == 0 {
            return 1.0;
        }
        (max - self.inbox.capacity()) as f64 / max as f64
    }
}

fn log_line(log: &std::sync::mpsc::SyncSender<String>, line: String) {
    // Dropped when the logger lags; metrics stay on the world thread.
    let _ = log.try_send(line);
}

/// Shared services a world thread needs; bundling keeps `world_loop` under
/// the arity lint and reads as one context object.
struct WorldServices {
    log: std::sync::mpsc::SyncSender<String>,
    occupancy: Occupancy,
    store: SharedCharacterStore,
    social: std::sync::Arc<crate::social::SocialHub>,
    closing: Arc<AtomicBool>,
    /// Durable storage seam (V5-12): worlds submit coalesced saves here.
    storage: StorageHandle,
    /// Where the world submits from; the paired receiver is drained below.
    storage_events: mpsc::UnboundedSender<StorageEvent>,
    profile:Option<crate::tick_profile::TickProfile>,
}

async fn world_loop(
    mut inbox: mpsc::Receiver<RoomCommand>,
    content: crate::content::Content,
    services: WorldServices,
    tower: Option<TowerLaunch>,
    mut storage_events: mpsc::UnboundedReceiver<StorageEvent>,
) {
    let WorldServices {
        log,
        occupancy,
        store,
        social,
        closing,
        storage,
        storage_events: storage_events_tx,
        profile,
    } = services;
    log_line(
        &log,
        format!(
            "world owner loaded content {} ({} bytes){}{}",
            content.hash_hex(),
            content.bundle_json.len(),
            if tower.is_some() { " (tower mode)" } else { "" },
            if storage.is_live() {
                ""
            } else {
                " (session-only: no durable storage)"
            },
        ),
    );
    let mut world = match &tower {
        Some(launch) => World::new_tower(&content, store, launch.session, launch.start_floor),
        None => World::new(&content, store),
    };
    world.attach_storage(storage, storage_events_tx);
    let mut network_encoder: Option<crate::interest::TickEncoder> = None;
    let mut conns: HashMap<ConnectionId, LiveConnection> = HashMap::new();
    let mut conn_sessions: HashMap<ConnectionId, [u8; 32]> = HashMap::new();
    let mut session_conns: HashMap<[u8; 32], ConnectionId> = HashMap::new();
    let mut metrics = RoomMetrics {
        occupancy,
        ..RoomMetrics::default()
    };
    let mut interval = tokio::time::interval(Duration::from_millis(50));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    // The first tick fires immediately; skip it so the loop starts aligned.
    interval.tick().await;
    metrics.window_started_at = Some(Instant::now());

    loop {
        if closing.load(Ordering::SeqCst) {
            // Tower teardown (leave or completion): stop ticking, drop the
            // per-connection outputs so sockets close, end the thread.
            return;
        }
        let tick_deadline = interval.tick().await;
        let work_started = tokio::time::Instant::now();
        let confirmed_before=metrics.confirmed_total_frame_bytes;let published_before=metrics.published_total_snapshot_bytes;
        let mut budget = PerTickBudget::default();
        let mut drained = 0usize;

        while drained < MAX_COMMANDS_PER_TICK {
            match inbox.try_recv() {
                Ok(RoomCommand::Join {
                    conn,
                    session,
                    character,
                    snapshots,
                    wire_packets,
                    queue_tracker,
                    reliable,
                    close_send,
                    reply,
                }) => {
                    // Stop admitting players while behind: answer overload
                    // with room_full instead of queueing more work.
                    let behind = tick_deadline.saturating_duration_since(work_started)
                        > Duration::from_millis(100)
                        || inbox.max_capacity() - inbox.capacity() > INBOX_BOUND * 8 / 10;
                    if behind {
                        let _ = reply.send(Err("room_full"));
                        continue;
                    }
                    match world.join_with(session, character) {
                        Ok(welcome) => {
                            // Takeover (R5): displace the previous outputs
                            // for this session so the old socket is closed
                            // instead of locking the session out.
                            if let Some(old) = session_conns.get(&session).copied()
                                && old != conn
                            {
                                let old_close = conns.get(&old).map(|live| live.close_send.clone());
                                let err = crate::wire::encode_error(
                                    crate::wire::ErrorCode::SessionActive,
                                );
                                deliver(
                                    &mut conns,
                                    &mut conn_sessions,
                                    &mut session_conns,
                                    &mut metrics,
                                    &mut world,
                                    old,
                                    err,
                                );
                                if conns.remove(&old).is_some() {
                                    metrics.resync_closes += 1;
                                    metrics.occupancy.dec();
                                }
                                if let Some(tx) = old_close {
                                    let _ = tx.send(true);
                                }
                                conn_sessions.remove(&old);
                                if session_conns.get(&session) == Some(&old) {
                                    session_conns.remove(&session);
                                }
                            }
                            let (player_id, epoch) = (welcome.player_id, welcome.epoch);
                            conns.insert(
                                conn,
                                LiveConnection {
                                    chat_identity: crate::chat_moderation::ChatIdentity::Session(session),
                                    player_id,
                                    epoch,
                                    snapshots,
                                    wire_packets,
                                    queue_tracker,
                                    stream: crate::interest::Stream::default(),
                                    ordinary_membership:crate::interest::OrdinaryMembership::default(),
                                    reliable,
                                    close_send,
                                    reliable_drops: 0,
                                    frame_bytes_window:0,oldest_snapshot_writer_age_us:0,oldest_reliable_writer_age_us:0,
                                },
                            );
                            metrics.occupancy.inc();
                            if let Some(state)=world.death_state(player_id) {
                                deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);
                            }
                            conn_sessions.insert(conn, session);
                            session_conns.insert(session, conn);
                            if reply.send(Ok(welcome)).is_err() {
                                // R4 rollback: the client gave up waiting;
                                // fence out the admission we just made.
                                drop_conn(
                                    &mut conns,
                                    &mut conn_sessions,
                                    &mut session_conns,
                                    &mut metrics,
                                    &mut world,
                                    conn,
                                    player_id,
                                    epoch,
                                );
                            }
                        }
                        Err(code) => {
                            let _ = reply.send(Err(code));
                        }
                    }
                }
                Ok(RoomCommand::BindChatPrincipal { conn, epoch, principal }) => {
                    drained += 1;
                    if let Some(live) = conns.get_mut(&conn).filter(|live| live.epoch == epoch) {
                        live.chat_identity = crate::chat_moderation::ChatIdentity::Principal(principal);
                    }
                }
                Ok(RoomCommand::Input {
                    conn,
                    player_id,
                    epoch,
                    seq,
                    x,
                    z,
                    facing,
                    flags,
                }) => {
                    drained += 1;
                    if !budget.allow_input(conn) {
                        metrics.dropped_commands += 1;
                        continue;
                    }
                    world.update_input(player_id, epoch, seq, x, z, facing, flags);
                }
                Ok(RoomCommand::Action {
                    conn,
                    player_id,
                    epoch,
                    seq,
                    action,
                    aim,
                    target_id,
                    view_tick,
                }) => {
                    drained += 1;
                    if !budget.allow_action(conn) {
                        metrics.dropped_commands += 1;
                        continue;
                    }
                    if let Some(live)=conns.get_mut(&conn).filter(|live|live.epoch==epoch&&live.player_id==player_id) {live.stream.target_id=target_id;}
                    let outcome = world
                        .apply_action(player_id, epoch, seq, action, aim, target_id, view_tick);
                    match crate::wire::encode_action_result(
                        seq as u32,
                        outcome.accepted,
                        outcome.reason,
                        outcome.ends_at_ms,
                    ) {
                        Ok(packet) => deliver(
                            &mut conns,
                            &mut conn_sessions,
                            &mut session_conns,
                            &mut metrics,
                            &mut world,
                            conn,
                            packet,
                        ),
                        Err(_) => metrics.dropped_commands += 1,
                    }
                }
                Ok(RoomCommand::SnapshotAck {conn,epoch,tick,resync}) => {
                    drained+=1;
                    let player=conns.get_mut(&conn).filter(|live|live.epoch==epoch).and_then(|live|if live.stream.acknowledge(tick,resync)&&resync{Some(live.player_id)}else{None});
                    if let Some(player_id)=player {
                        if let Some(state)=world.death_state(player_id){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);}
                        if let Some(state)=world.character_state(player_id){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);}
                    }
                }
                Ok(RoomCommand::SnapshotSent {conn,epoch,tick,frame_bytes,writer_age_us}) => {
                    drained+=1;
                    if frame_bytes<=crate::wire::MAX_SERVER_PACKET_BYTES as u32+4 {
                        metrics.confirmed_frame_bytes=metrics.confirmed_frame_bytes.saturating_add(u64::from(frame_bytes));metrics.confirmed_total_frame_bytes=metrics.confirmed_total_frame_bytes.saturating_add(u64::from(frame_bytes));
                        if let Some(live)=conns.get_mut(&conn).filter(|live|live.epoch==epoch){live.stream.mark_sent(tick);live.frame_bytes_window=live.frame_bytes_window.saturating_add(u64::from(frame_bytes));live.oldest_snapshot_writer_age_us=live.oldest_snapshot_writer_age_us.max(writer_age_us);}
                    }
                }
                Ok(RoomCommand::FrameSent {conn,epoch,frame_bytes,writer_age_us}) => {
                    drained+=1;
                    if frame_bytes<=crate::wire::MAX_SERVER_PACKET_BYTES as u32+4 {metrics.confirmed_frame_bytes=metrics.confirmed_frame_bytes.saturating_add(u64::from(frame_bytes));metrics.confirmed_total_frame_bytes=metrics.confirmed_total_frame_bytes.saturating_add(u64::from(frame_bytes));if let Some(live)=conns.get_mut(&conn).filter(|live|live.epoch==epoch){live.frame_bytes_window=live.frame_bytes_window.saturating_add(u64::from(frame_bytes));live.oldest_reliable_writer_age_us=live.oldest_reliable_writer_age_us.max(writer_age_us);}}
                }
                Ok(RoomCommand::Ping {
                    conn,
                    nonce,
                    client_ms,
                }) => {
                    drained += 1;
                    let pong = crate::wire::encode_pong(nonce, client_ms, world.tick());
                    deliver(
                        &mut conns,
                        &mut conn_sessions,
                        &mut session_conns,
                        &mut metrics,
                        &mut world,
                        conn,
                        pong,
                    );
                }
                Ok(RoomCommand::Cold { conn, payload }) => {
                    drained += 1;
                    if !budget.allow_cold(conn) {
                        metrics.dropped_commands += 1;
                        continue;
                    }
                    let tag = crate::cold::validate_client_payload(&payload);
                    if conns.get(&conn).is_some_and(|live|!world.owns_character(live.player_id)||world.community_busy(live.player_id)) && !matches!(tag, Ok(crate::cold::ColdTag::Community | crate::cold::ColdTag::Chat | crate::cold::ColdTag::Resync)) { if let Some(live)=conns.get(&conn) {world.community_error(live.player_id,"trade_committing");} continue; }
                    if let Some(id)=conns.get(&conn).map(|live|live.player_id)&&world.guard_durable_cold(id,&payload){continue;}
                    match tag {
                        Ok(crate::cold::ColdTag::MageTrial) => {
                            if let (Some(live),Ok(request))=(conns.get(&conn),serde_json::from_slice::<crate::mage_trial::TrialRequest>(&payload)) {
                                let id=live.player_id;
                                if let Some(result)=world.mage_trial_activate(id,request){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&result);}
                                if let Some(state)=world.mage_trial_state(id){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);}
                                if let Some(state)=world.character_state(id){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);}
                            }
                        }
                        Ok(crate::cold::ColdTag::MageCast) => {
                            if let (Some(live),Ok(request))=(conns.get(&conn),serde_json::from_slice::<crate::mage_trial::CastRequest>(&payload)) {
                                let id=live.player_id;
                                if let Some(state)=world.mage_cast(id,request){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);}
                            }
                        }
                        Ok(crate::cold::ColdTag::Community) => {
                            if let (Some(live),Some(session),Ok(action)) = (conns.get(&conn),conn_sessions.get(&conn).copied(),crate::community::decode(&payload)) {
                                let player_id = live.player_id;
                                if !world.owns_character(player_id) {world.community_error(player_id,"player_unavailable");continue;}
                                match action {
                                    crate::community::Action::Megaphone { text } => {
                                        if let Err(reason) = social.megaphone(session,&text) {
                                            world.community_error(player_id,reason);
                                        }
                                    }
                                    crate::community::Action::Sync { device } => {
                                        social.set_device(session,device);
                                        world.community_action(player_id,crate::community::Action::Sync { device });
                                    }
                                    other => world.community_action(player_id,other),
                                }
                            }
                        }
                        Ok(crate::cold::ColdTag::PickupDrop) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            let request = crate::cold::decode_pickup_drop_request(&payload);
                            match (player_id, request) {
                                (Some(player_id), Ok(request)) => {
                                    if let Some(result) = world.pickup_drop(player_id, request) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &result,
                                        );
                                        if let Some(state) = world.character_state(player_id) {
                                            deliver_cold(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                conn,
                                                &state,
                                            );
                                        }
                                        if let Some(drops) = world.drops_state(player_id) {
                                            deliver_cold(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                conn,
                                                &drops,
                                            );
                                        }
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::StatAllocate) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            let request = crate::cold::decode_stat_allocate_request(&payload);
                            match (player_id, request) {
                                (Some(player_id), Ok(request)) => {
                                    if let Some(result) = world.stat_allocate(player_id, request) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &result,
                                        );
                                        if let Some(state) = world.character_state(player_id) {
                                            deliver_cold(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                conn,
                                                &state,
                                            );
                                        }
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::RefineItem) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            let request = crate::cold::decode_refine_item_request(&payload);
                            match (player_id, request) {
                                (Some(player_id), Ok(request)) => {
                                    if let Some(result) = world.refine_item(player_id, request) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &result,
                                        );
                                        if let Some(state) = world.character_state(player_id) {
                                            deliver_cold(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                conn,
                                                &state,
                                            );
                                        }
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::EquipItem) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            let request = crate::cold::decode_equip_item_request(&payload);
                            match (player_id, request) {
                                (Some(player_id), Ok(request)) => {
                                    if let Some(result) = world.equip_item(player_id, request) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &result,
                                        );
                                        if let Some(state) = world.character_state(player_id) {
                                            deliver_cold(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                conn,
                                                &state,
                                            );
                                        }
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::Interact) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            match (player_id, crate::cold::decode_interact_request(&payload)) {
                                (Some(player_id), Ok(request)) => {
                                    match world.interact(player_id, &request.npc) {
                                        Ok(dialogue) => deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &dialogue,
                                        ),
                                        Err(reason) => deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("interaction_{reason}"),
                                                params: serde_json::json!({}),
                                            },
                                        ),
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::Activate) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            match (player_id, crate::cold::decode_activate_request(&payload)) {
                                (Some(player_id), Ok(request)) => {
                                    match world.start_windmark(player_id, &request.marker) {
                                        Ok(notice) => deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &notice,
                                        ),
                                        Err(reason) => deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("windmark_{reason}"),
                                                params: serde_json::json!({ "marker": request.marker }),
                                            },
                                        ),
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::Choose) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            match (player_id, crate::cold::decode_choose_request(&payload)) {
                                (Some(player_id), Ok(request)) => {
                                    match world.choose(player_id, request) {
                                        Ok(closed) => deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &closed,
                                        ),
                                        Err(reason) => deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("choice_{reason}"),
                                                params: serde_json::json!({}),
                                            },
                                        ),
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::Claim) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            match (player_id, crate::cold::decode_claim_request(&payload)) {
                                (Some(player_id), Ok(request)) => {
                                    if let Some(result) = world.claim_quest(player_id, request) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &result,
                                        );
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(
                            crate::cold::ColdTag::PartyCreate
                            | crate::cold::ColdTag::PartyJoin
                            | crate::cold::ColdTag::PartyLeave,
                        ) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            match (player_id, crate::cold::decode_party_request(&payload)) {
                                (Some(player_id), Ok(crate::cold::PartyRequest::Create)) => {
                                    if let Err(reason) = world.create_party(player_id) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("party_{reason}"),
                                                params: serde_json::json!({}),
                                            },
                                        );
                                    }
                                }
                                (Some(player_id), Ok(crate::cold::PartyRequest::Join { code })) => {
                                    if let Err(reason) = world.join_party(player_id, &code) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("party_{reason}"),
                                                params: serde_json::json!({}),
                                            },
                                        );
                                    }
                                }
                                (Some(player_id), Ok(crate::cold::PartyRequest::Leave)) => {
                                    if let Err(reason) = world.leave_party(player_id) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("party_{reason}"),
                                                params: serde_json::json!({}),
                                            },
                                        );
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::MoveItemInstance) => {
                            if let (Some(player_id),Ok(request))=(conns.get(&conn).map(|l|l.player_id),crate::cold::decode_move_item_instance_request(&payload)) {
                                if let Some(result)=world.move_item_instance(player_id,request) {
                                    deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&result);
                                }
                            }
                        }
                        Ok(crate::cold::ColdTag::ClaimReward) => {
                            if let (Some(player_id),Ok(request))=(conns.get(&conn).map(|l|l.player_id),crate::cold::decode_claim_reward_request(&payload)) {
                                if let Some(result)=world.claim_reward(player_id,request) {
                                    deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&result);
                                }
                            }
                        }
                        Ok(crate::cold::ColdTag::ReturnToTown) => {
                            if let (Some(player_id),Ok(request))=(conns.get(&conn).map(|l|l.player_id),crate::cold::decode_return_to_town_request(&payload)) {
                                if let Some(result)=world.return_to_town(player_id,request) {
                                    deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&result);
                                }
                            }
                        }
                        Ok(crate::cold::ColdTag::Resync) => {
                            if let Some(live)=conns.get_mut(&conn){live.stream.acknowledge(0,true);}
                            if let Some(player_id) = conns.get(&conn).map(|live| live.player_id) {
                                if let Some(state)=world.mage_trial_state(player_id) {
                                    deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);
                                }
                                if let Some(state)=world.death_state(player_id) {
                                    deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);
                                }
                                if let Some(state) = world.character_state(player_id) {
                                    deliver_cold(
                                        &mut conns,
                                        &mut conn_sessions,
                                        &mut session_conns,
                                        &mut metrics,
                                        &mut world,
                                        conn,
                                        &state,
                                    );
                                }
                                if let Some(state) = world.quest_state(player_id) {
                                    deliver_cold(
                                        &mut conns,
                                        &mut conn_sessions,
                                        &mut session_conns,
                                        &mut metrics,
                                        &mut world,
                                        conn,
                                        &state,
                                    );
                                }
                                if let Some(state) = world.party_state(player_id) {
                                    deliver_cold(
                                        &mut conns,
                                        &mut conn_sessions,
                                        &mut session_conns,
                                        &mut metrics,
                                        &mut world,
                                        conn,
                                        &state,
                                    );
                                }
                            }
                        }
                        Ok(crate::cold::ColdTag::UseItem) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            let request = crate::cold::decode_use_item_request(&payload);
                            match (player_id, request) {
                                (Some(player_id), Ok(request)) => {
                                    if let Some(result) = world.use_item(player_id, request) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &result,
                                        );
                                        if let Some(state) = world.character_state(player_id) {
                                            deliver_cold(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                conn,
                                                &state,
                                            );
                                        }
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(crate::cold::ColdTag::Chat) => {
                            let player_id = conns.get(&conn).map(|live| live.player_id);
                            let session = conn_sessions.get(&conn).copied();
                            match (
                                player_id,
                                session,
                                crate::cold::decode_chat_request(&payload),
                            ) {
                                (Some(player_id), Some(session), Ok(request)) => {
                                    match request.channel {
                                        crate::cold::ChatChannel::Room => {
                                            let identity = conns.get(&conn).expect("authenticated chat connection").chat_identity;
                                            let prepared = match social.prepare_bound_room_chat(identity, &request.text) {
                                                Ok(text) => text,
                                                Err(reason) => {
                                                    deliver_cold(&mut conns, &mut conn_sessions, &mut session_conns, &mut metrics,
                                                        &mut world, conn, &crate::cold::NoticeMsg {
                                                            t: "notice".to_string(), key: reason.key().to_string(), params: serde_json::json!({}),
                                                        });
                                                    continue;
                                                }
                                            };
                                            // Room chat: broadcast on the world
                                            // thread to every live connection in
                                            // this instance. Tower instances are
                                            // solo, so the sender is their only
                                            // listener there.
                                            let device = world.player_device(player_id);
                                            let from = world
                                                .player_name(player_id)
                                                .unwrap_or_else(|| "Traveler".to_string());
                                            broadcast_room_chat(
                                                &mut conns,
                                                &mut conn_sessions,
                                                &mut session_conns,
                                                &mut metrics,
                                                &mut world,
                                                &from,
                                                prepared.text(),
                                                device,
                                            );
                                        }
                                        crate::cold::ChatChannel::Group => {
                                            // Group chat crosses instances: the
                                            // social hub routes it through the
                                            // presence map to each member's
                                            // current instance.
                                            if let Err(error) =
                                                social.group_chat(session, &request.text)
                                            {
                                                deliver_cold(
                                                    &mut conns,
                                                    &mut conn_sessions,
                                                    &mut session_conns,
                                                    &mut metrics,
                                                    &mut world,
                                                    conn,
                                                    &crate::cold::NoticeMsg {
                                                        t: "notice".to_string(),
                                                        key: if matches!(error, crate::social::GroupError::ChatRejected(_)) { error.reason().to_string() }
                                                            else { format!("group_{}", error.reason()) },
                                                        params: serde_json::json!({}),
                                                    },
                                                );
                                            }
                                        }
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(
                            crate::cold::ColdTag::FriendAdd | crate::cold::ColdTag::FriendRemove,
                        ) => {
                            let session = conn_sessions.get(&conn).copied();
                            match (session, crate::cold::decode_friend_request(&payload)) {
                                (Some(session), Ok(op)) => {
                                    // On success the hub pushes the fresh
                                    // roster to the requester's instance; the
                                    // cold path only answers errors locally.
                                    let result = match op {
                                        crate::cold::FriendOp::Add { handle } => {
                                            social.friend_add(session, &handle).map(|_entries| ())
                                        }
                                        crate::cold::FriendOp::Remove { handle } => {
                                            social.friend_remove(session, &handle);
                                            Ok(())
                                        }
                                    };
                                    if let Err(error) = result {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("friends_{}", error.reason()),
                                                params: serde_json::json!({}),
                                            },
                                        );
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(
                            crate::cold::ColdTag::GroupCreate
                            | crate::cold::ColdTag::GroupJoin
                            | crate::cold::ColdTag::GroupLeave,
                        ) => {
                            let session = conn_sessions.get(&conn).copied();
                            match (session, crate::cold::decode_group_request(&payload)) {
                                (Some(session), Ok(op)) => {
                                    // Membership changes push the fresh group
                                    // state to every online member from the
                                    // hub; the cold path answers errors only.
                                    let result = match op {
                                        crate::cold::GroupOp::Create => {
                                            social.group_create(session).map(|_code| ())
                                        }
                                        crate::cold::GroupOp::Join { code } => {
                                            social.group_join(session, &code).map(|_view| ())
                                        }
                                        crate::cold::GroupOp::Leave => social.group_leave(session),
                                    };
                                    if let Err(error) = result {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &crate::cold::NoticeMsg {
                                                t: "notice".to_string(),
                                                key: format!("group_{}", error.reason()),
                                                params: serde_json::json!({}),
                                            },
                                        );
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Ok(
                            crate::cold::ColdTag::StoreBuy
                            | crate::cold::ColdTag::BoxOpen
                            | crate::cold::ColdTag::CosmeticsEquip,
                        ) => {
                            let owner = conns.get(&conn).map(|live| live.player_id);
                            let result = owner.and_then(|player_id| {
                                match crate::cold::validate_client_payload(&payload) {
                                    Ok(crate::cold::ColdTag::StoreBuy) => {
                                        crate::cold::decode_store_buy_request(&payload)
                                            .ok()
                                            .and_then(|request| world.store_buy(player_id, request))
                                    }
                                    Ok(crate::cold::ColdTag::BoxOpen) => {
                                        crate::cold::decode_box_open_request(&payload)
                                            .ok()
                                            .and_then(|request| world.box_open(player_id, request))
                                    }
                                    Ok(crate::cold::ColdTag::EquipItem) => {
                                        crate::cold::decode_equip_item_request(&payload)
                                            .ok()
                                            .and_then(|request| {
                                                world.equip_item(player_id, request)
                                            })
                                    }
                                    Ok(crate::cold::ColdTag::CosmeticsEquip) => {
                                        crate::cold::decode_cosmetics_equip_request(&payload)
                                            .ok()
                                            .and_then(|request| {
                                                world.cosmetics_equip(player_id, request)
                                            })
                                    }
                                    _ => None,
                                }
                            });
                            match (owner, result) {
                                (Some(player_id), Some(result)) => {
                                    deliver_cold(
                                        &mut conns,
                                        &mut conn_sessions,
                                        &mut session_conns,
                                        &mut metrics,
                                        &mut world,
                                        conn,
                                        &result,
                                    );
                                    if let Some(state) = world.character_state(player_id) {
                                        deliver_cold(
                                            &mut conns,
                                            &mut conn_sessions,
                                            &mut session_conns,
                                            &mut metrics,
                                            &mut world,
                                            conn,
                                            &state,
                                        );
                                    }
                                }
                                _ => metrics.dropped_commands += 1,
                            }
                        }
                        Err(_) => metrics.dropped_commands += 1,
                    }
                }
                Ok(RoomCommand::Notify { conn, packet }) => {
                    drained += 1;
                    deliver(
                        &mut conns,
                        &mut conn_sessions,
                        &mut session_conns,
                        &mut metrics,
                        &mut world,
                        conn,
                        packet,
                    );
                }
                Ok(RoomCommand::NotifySession { session, packet }) => {
                    drained += 1;
                    // One packet for every live connection of one session (a
                    // takeover leaves at most one). Unknown sessions are
                    // silently dropped: the target is offline.
                    if let Some(conn) = session_conns.get(&session).copied() {
                        deliver(
                            &mut conns,
                            &mut conn_sessions,
                            &mut session_conns,
                            &mut metrics,
                            &mut world,
                            conn,
                            packet,
                        );
                    }
                }
                Ok(RoomCommand::Disconnect {
                    conn,
                    player_id,
                    epoch,
                }) => {
                    drained += 1;
                    if player_id == 0 && epoch == 0 {
                        // Join-timeout cleanup (R4): fence with whatever
                        // this connection owned, if anything.
                        if let Some(live) = conns.get(&conn) {
                            let (owned_player, owned_epoch) = (live.player_id, live.epoch);
                            drop_conn(
                                &mut conns,
                                &mut conn_sessions,
                                &mut session_conns,
                                &mut metrics,
                                &mut world,
                                conn,
                                owned_player,
                                owned_epoch,
                            );
                        }
                    } else {
                        world.disconnect(player_id, epoch);
                        release_conn(
                            &mut conns,
                            &mut conn_sessions,
                            &mut session_conns,
                            &mut metrics,
                            conn,
                        );
                    }
                }
                Err(mpsc::error::TryRecvError::Empty) => break,
                Err(mpsc::error::TryRecvError::Disconnected) => return,
            }
        }

        // Durable-save rejections (a stale epoch) adopt the authoritative
        // record and resync the affected client (V5-12).
        while let Ok(event) = storage_events.try_recv() {
            world.handle_storage_event(event);
        }

        let commands_done=profile.as_ref().map(|_|tokio::time::Instant::now());
        let base = world.advance();
        let advance_done=profile.as_ref().map(|_|tokio::time::Instant::now());
        if let Some(launch) = &tower {
            // Tower completion flips the watch the registry watcher polls;
            // floor milestones persist the session's best floor.
            if world.take_tower_completed() {
                let _ = launch.completed_tx.send(true);
            }
            launch
                .floor_at
                .store(world.current_floor(), Ordering::SeqCst);
            for floor in world.take_tower_floor_events() {
                if let Some(floor_tx) = &launch.floor_tx {
                    let _ = floor_tx.send((launch.session, floor));
                }
            }
        }
        let mut live_by_player = HashMap::new();
        for (conn, live) in &conns {
            live_by_player.insert(live.player_id, *conn);
        }
        for (id,result) in world.take_deferred_op_results() {
            if let Some(conn)=live_by_player.get(&id).copied(){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&result);if let Some(state)=world.mage_trial_state(id){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);}}
        }
        for (audience,event) in world.take_mage_events() {
            for player_id in audience {
                if let Some(conn)=live_by_player.get(&player_id).copied(){deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&event);}
            }
        }
        for (player_id, notice) in world.take_pending_notices() {
            if let Some(conn) = live_by_player.get(&player_id).copied() {
                deliver_cold(
                    &mut conns,
                    &mut conn_sessions,
                    &mut session_conns,
                    &mut metrics,
                    &mut world,
                    conn,
                    &notice,
                );
            }
        }
        for player_id in world.take_pending_drops() {
            if let Some(conn) = live_by_player.get(&player_id).copied()
                && let Some(drops) = world.drops_state(player_id)
            {
                deliver_cold(
                    &mut conns,
                    &mut conn_sessions,
                    &mut session_conns,
                    &mut metrics,
                    &mut world,
                    conn,
                    &drops,
                );
            }
        }
        for player_id in world.take_pending_state_updates() {
            if let Some(conn) = live_by_player.get(&player_id).copied() {
                if let Some(state)=world.mage_trial_state(player_id) {
                    deliver_cold(&mut conns,&mut conn_sessions,&mut session_conns,&mut metrics,&mut world,conn,&state);
                }
                if let Some(state) = world.character_state(player_id) {
                    deliver_cold(
                        &mut conns,
                        &mut conn_sessions,
                        &mut session_conns,
                        &mut metrics,
                        &mut world,
                        conn,
                        &state,
                    );
                }
                if let Some(state) = world.quest_state(player_id) {
                    deliver_cold(
                        &mut conns,
                        &mut conn_sessions,
                        &mut session_conns,
                        &mut metrics,
                        &mut world,
                        conn,
                        &state,
                    );
                }
            }
        }
        for player_id in world.take_pending_party_updates() {
            if let Some(conn) = live_by_player.get(&player_id).copied()
                && let Some(state) = world.party_state(player_id)
            {
                deliver_cold(
                    &mut conns,
                    &mut conn_sessions,
                    &mut session_conns,
                    &mut metrics,
                    &mut world,
                    conn,
                    &state,
                );
            }
        }
        let zone_limit = world.zone_half_extent();
        let encode_prepare_started=profile.as_ref().map(|_|Instant::now());
        let mut encode_stages=[Duration::ZERO;4];
        if network_encoder.is_none() || base.tick%2==0 {
            match crate::interest::TickEncoder::new(&base,zone_limit){Ok(encoder)=>network_encoder=Some(encoder),Err(_)=>{metrics.snapshot_encode_failures+=1;continue;}}
        }
        let encoder=network_encoder.as_mut().unwrap();
        encoder.refresh_private(&base);
        let encoder_before=(encoder.shared_encodes,encoder.shared_hits,encoder.record_encodes,encoder.essential_event_overflows,encoder.delta_comparisons,encoder.unchanged_record_skips,encoder.record_key_constructions,encoder.key_bytes_copied,encoder.ordinary_cache_hits,encoder.ordinary_cache_refreshes);
        if let Some(started)=encode_prepare_started{encode_stages[0]=started.elapsed();}
        let mut dead = Vec::new();
        for (conn, live) in conns.iter_mut() {
            let party=world.interest_party(live.player_id);
            let selection_started=profile.as_ref().map(|_|Instant::now());
            let state=encoder.select_cached(&base,live.player_id,&party,live.stream.target_id,&mut live.ordinary_membership,world.interest_context(live.player_id));
            if let Some(started)=selection_started{encode_stages[1]+=started.elapsed();}
            let ack=world.last_input_position(live.player_id).unwrap_or((0.0,0.0));
            let packet_started=profile.as_ref().map(|_|Instant::now());
            let packet=encoder.packet(&base,state,&mut live.stream,live.epoch,live.player_id,&party,(world.last_input_seq(live.player_id),ack.0,ack.1,0),zone_limit);
            if let Some(started)=packet_started{encode_stages[2]+=started.elapsed();}
            let publish_started=profile.as_ref().map(|_|Instant::now());
            match packet {
                Ok(bytes)=>{let published_at=Instant::now();live.queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner()).snapshot=Some((base.tick,published_at));metrics.snapshot_bytes+=bytes.len() as u64;metrics.published_total_snapshot_bytes+=bytes.len() as u64; if live.wire_packets.send(PublishedSnapshot{tick:base.tick,epoch:live.epoch,bytes:bytes.into(),published_at:Some(published_at)}).is_err(){dead.push(*conn);}},
                Err(_)=>{metrics.snapshot_encode_failures+=1;dead.push(*conn);}
            }
            if let Some(started)=publish_started{encode_stages[3]+=started.elapsed();}
            #[cfg(test)] {
                let mut view=base.clone();view.ack_seq=world.last_input_seq(live.player_id);(view.ack_x,view.ack_z)=ack;
                for monster in &mut view.monsters {monster.flags=(monster.flags&!4)|if monster.target_player_id==Some(live.player_id){4}else{0};}
                let _=live.snapshots.send(view);
            }
        }
        for conn in dead {
            if let Some(live) = conns.get(&conn) {
                let (player_id, epoch) = (live.player_id, live.epoch);
                drop_conn(
                    &mut conns,
                    &mut conn_sessions,
                    &mut session_conns,
                    &mut metrics,
                    &mut world,
                    conn,
                    player_id,
                    epoch,
                );
            }
        }

        let work=work_started.elapsed();
        if let Some(profile)=&profile {
            let now=Instant::now();let mut max_age=0;let mut pending=0;let mut baselines=0;
            for live in conns.values(){let tracker=live.queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner());max_age=max_age.max(tracker.oldest_pending_age_us(now).unwrap_or(0));pending=pending.max(tracker.pending_packets());baselines=baselines.max(live.stream.retained_baselines());}
            profile.record_with_transport(work_started.into_std(),work,[commands_done.unwrap()-work_started,advance_done.unwrap()-commands_done.unwrap(),work.saturating_sub(advance_done.unwrap()-work_started)],crate::tick_profile::TransportSample{confirmed_frame_bytes:metrics.confirmed_total_frame_bytes-confirmed_before,published_snapshot_bytes:metrics.published_total_snapshot_bytes-published_before,oldest_pending_queue_age_us:max_age,pending_packets:pending,shared_encodes:encoder.shared_encodes-encoder_before.0,shared_hits:encoder.shared_hits-encoder_before.1,record_encodes:encoder.record_encodes-encoder_before.2,essential_event_overflows:encoder.essential_event_overflows-encoder_before.3,retained_baselines:baselines,shared_states:encoder.retained_shared_states(),encode_stages_ms:encode_stages.map(|d|d.as_secs_f64()*1000.0),delta_comparisons:encoder.delta_comparisons-encoder_before.4,unchanged_record_skips:encoder.unchanged_record_skips-encoder_before.5,record_key_constructions:encoder.record_key_constructions-encoder_before.6,key_bytes_copied:encoder.key_bytes_copied-encoder_before.7,ordinary_cache_hits:encoder.ordinary_cache_hits-encoder_before.8,ordinary_cache_refreshes:encoder.ordinary_cache_refreshes-encoder_before.9});
        }
        metrics.record_work(work);
        let pressure = inbox.max_capacity() - inbox.capacity();
        metrics.inbox_high_water = metrics.inbox_high_water.max(pressure);
        if tick_deadline.elapsed() > Duration::from_millis(60) {
            metrics.missed_ticks += 1;
        }
        if metrics
            .window_started_at
            .is_some_and(|start| start.elapsed() >= METRICS_EVERY)
        {
            let connection_metrics=conns.iter().map(|(conn,live)|{let tracker=live.queue_tracker.lock().unwrap_or_else(|poison|poison.into_inner());serde_json::json!({"conn":conn,"epoch":live.epoch,"player_id":live.player_id,"confirmed_websocket_frame_bytes":live.frame_bytes_window,"oldest_snapshot_writer_age_us":live.oldest_snapshot_writer_age_us,"oldest_reliable_writer_age_us":live.oldest_reliable_writer_age_us,"max_completed_outbound_age_us":live.oldest_snapshot_writer_age_us.max(live.oldest_reliable_writer_age_us),"oldest_pending_queue_age_us":tracker.oldest_pending_age_us(Instant::now()),"pending_outbound_packets":tracker.pending_packets(),"oldest_unacked_snapshot_age_ms":live.stream.oldest_unacked_ticks(base.tick)*50,"retained_baselines":live.stream.retained_baselines()})}).collect::<Vec<_>>();
            log_line(&log,serde_json::json!({"schema":"xexoria.server-connection-metrics/1","tick":base.tick,"interval":"last_room_metric_window","connections":connection_metrics,"byte_scope":"writer-confirmed WebSocket frames including reliable messages; TCP/IP headers unmeasured","age_scope":"current bounded queues plus completed write-age window, measured with monotonic Instants"}).to_string());
            for live in conns.values_mut(){live.frame_bytes_window=0;live.oldest_snapshot_writer_age_us=0;live.oldest_reliable_writer_age_us=0;}
            metrics.report(&log);
        }
    }
}

fn deliver_cold<T: Serialize>(
    conns: &mut HashMap<ConnectionId, LiveConnection>,
    conn_sessions: &mut HashMap<ConnectionId, [u8; 32]>,
    session_conns: &mut HashMap<[u8; 32], ConnectionId>,
    metrics: &mut RoomMetrics,
    world: &mut World,
    conn: ConnectionId,
    message: &T,
) {
    let Ok(payload) = serde_json::to_vec(message) else {
        metrics.dropped_commands += 1;
        return;
    };
    match crate::wire::encode_cold_server(&payload) {
        Ok(packet) => deliver(
            conns,
            conn_sessions,
            session_conns,
            metrics,
            world,
            conn,
            packet,
        ),
        Err(_) => metrics.dropped_commands += 1,
    }
}

/// Broadcast one room-chat line to every live connection in this instance.
/// The packet is encoded once; delivery reuses the per-connection path so a
/// stuck reader is closed exactly like any reliable send. Never blocks: each
/// push is a bounded queue `try_send`.
#[allow(clippy::too_many_arguments)]
fn broadcast_room_chat(
    conns: &mut HashMap<ConnectionId, LiveConnection>,
    conn_sessions: &mut HashMap<ConnectionId, [u8; 32]>,
    session_conns: &mut HashMap<[u8; 32], ConnectionId>,
    metrics: &mut RoomMetrics,
    world: &mut World,
    from: &str,
    text: &str,
    device: crate::community::Device,
) {
    let message = crate::cold::ChatBroadcastMsg::new("room", from, text).with_device(device);
    let packet = match serde_json::to_vec(&message) {
        Ok(payload) => match crate::wire::encode_cold_server(&payload) {
            Ok(packet) => packet,
            Err(_) => {
                metrics.dropped_commands += 1;
                return;
            }
        },
        Err(_) => {
            metrics.dropped_commands += 1;
            return;
        }
    };
    let targets: Vec<ConnectionId> = conns.keys().copied().collect();
    for conn in targets {
        deliver(
            conns,
            conn_sessions,
            session_conns,
            metrics,
            world,
            conn,
            packet.clone(),
        );
    }
}

// ---------------------------------------------------------------------------
// Tower instances (private, per-session worlds) and their process-wide
// registry service.
// ---------------------------------------------------------------------------

/// A live tower instance bound to one session: its room handle, the
/// completion flag the registry watcher polls, and the current floor for
/// `GET /tower`.
#[derive(Clone)]
pub struct TowerInstance {
    pub handle: RoomHandle,
    pub session: SessionId,
    pub completed: watch::Receiver<bool>,
    pub floor: Arc<AtomicU16>,
}

/// Where a join landed. A tower-assigned session joins its own instance,
/// bypassing channel routing; `StaleTower` means the assignment outlived its
/// instance and the caller must clear it and re-route normally.
pub enum JoinRoute {
    Tower {
        handle: RoomHandle,
        welcome: Welcome,
        outputs: ConnectionOutputs,
    },
    Normal {
        handle: RoomHandle,
        index: usize,
        welcome: Welcome,
        outputs: ConnectionOutputs,
    },
    StaleTower,
}

/// Route one join given the (optional) tower instance already resolved for
/// the session. A live instance wins over channel routing; a dead one (or one
/// closed for teardown) reports stale.
pub async fn route_join(
    rooms: &[RoomHandle],
    instance: Option<TowerInstance>,
    channel: Option<u8>,
    session: SessionId,
) -> Result<JoinRoute, &'static str> {
    route_join_durable(rooms, instance, channel, session, None).await
}

/// Route one join carrying the durable character (V5-12). The socket task
/// resolves the record once and hands it to whichever instance admits the
/// session — room or private tower.
pub async fn route_join_durable(
    rooms: &[RoomHandle],
    instance: Option<TowerInstance>,
    channel: Option<u8>,
    session: SessionId,
    character: Option<JoinCharacter>,
) -> Result<JoinRoute, &'static str> {
    if let Some(instance) = instance {
        return match instance.handle.join_durable(session, character).await {
            Ok((welcome, outputs)) => Ok(JoinRoute::Tower {
                handle: instance.handle,
                welcome,
                outputs,
            }),
            Err(_) => Ok(JoinRoute::StaleTower),
        };
    }
    let (index, welcome, outputs) = join_routed_durable(rooms, channel, session, character).await?;
    Ok(JoinRoute::Normal {
        handle: rooms[index].clone(),
        index,
        welcome,
        outputs,
    })
}

/// Instances still holding their session: completed-but-not-yet-reaped
/// instances do not count against the cap.
fn active_tower_count(towers: &HashMap<SessionId, TowerInstance>) -> usize {
    towers
        .values()
        .filter(|instance| !*instance.completed.borrow())
        .count()
}

/// Why `POST /tower/enter` was refused.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TowerEnterError {
    /// A body floor outside `1..=min(best_floor + 1, max_floor)`.
    BadFloor,
    /// The instance cap (`content.tower.instances_cap`) is reached.
    Full,
    /// The tower world failed to spawn (content unavailable).
    Spawn(String),
}

/// The tower instance registry: capped at `content.tower.instances_cap`, one
/// instance per session, with the entry operations the HTTP handlers call.
pub struct TowerService {
    towers: tokio::sync::Mutex<HashMap<SessionId, TowerInstance>>,
    cap: u16,
    max_floor: u16,
    store: SharedCharacterStore,
    social: std::sync::Arc<crate::social::SocialHub>,
    storage: StorageHandle,
    floor_events: mpsc::UnboundedSender<(SessionId, u16)>,
}

impl TowerService {
    pub fn new(
        cap: u16,
        max_floor: u16,
        store: SharedCharacterStore,
        social: std::sync::Arc<crate::social::SocialHub>,
        floor_events: mpsc::UnboundedSender<(SessionId, u16)>,
    ) -> Self {
        Self::with_storage(
            cap,
            max_floor,
            store,
            social,
            StorageHandle::disabled(),
            floor_events,
        )
    }

    /// Tower service with the durable storage seam attached (V5-12): spawned
    /// tower instances submit coalesced saves like every other world.
    pub fn with_storage(
        cap: u16,
        max_floor: u16,
        store: SharedCharacterStore,
        social: std::sync::Arc<crate::social::SocialHub>,
        storage: StorageHandle,
        floor_events: mpsc::UnboundedSender<(SessionId, u16)>,
    ) -> Self {
        Self {
            towers: tokio::sync::Mutex::new(HashMap::new()),
            cap,
            max_floor,
            store,
            social,
            storage,
            floor_events,
        }
    }

    /// Enter the tower at `requested` floors (`None` = the default floor 1),
    /// gated by the session's `best_floor` (enter up to `best_floor + 1`).
    /// Re-entering with a live instance keeps its progress and returns its
    /// current floor.
    pub async fn enter(
        &self,
        session: SessionId,
        requested: Option<u16>,
        best_floor: u16,
    ) -> Result<u16, TowerEnterError> {
        // Floor validation comes first: a bad body floor is a bad request
        // even when the session already holds a live instance.
        let limit = self.max_floor.min(best_floor.saturating_add(1));
        let floor = match requested {
            Some(floor) if (1..=limit).contains(&floor) => floor,
            Some(_) => return Err(TowerEnterError::BadFloor),
            None => 1,
        };
        let mut towers = self.towers.lock().await;
        if let Some(existing) = towers.get(&session).cloned() {
            if !*existing.completed.borrow() {
                return Ok(existing.floor.load(Ordering::SeqCst).max(1));
            }
            existing.handle.close_instance();
            towers.remove(&session);
        }
        if active_tower_count(&towers) >= usize::from(self.cap) {
            return Err(TowerEnterError::Full);
        }
        let instance = RoomHandle::spawn_tower_with_storage(
            &self.store,
            &self.social,
            &self.storage,
            session,
            floor,
            Some(self.floor_events.clone()),
        )
        .map_err(|error| TowerEnterError::Spawn(error.to_string()))?;
        towers.insert(session, instance);
        Ok(floor)
    }

    /// Remove the session's instance (if any) and schedule its teardown.
    pub async fn leave(&self, session: SessionId) {
        if let Some(instance) = self.towers.lock().await.remove(&session) {
            instance.handle.close_instance();
        }
    }

    /// `(in_tower, current floor)` for `GET /tower`.
    pub async fn status(&self, session: SessionId) -> (bool, u16) {
        match self.towers.lock().await.get(&session) {
            Some(instance) => (true, instance.floor.load(Ordering::SeqCst)),
            None => (false, 0),
        }
    }

    /// The live tower instance for a session, cloned out so join routing does
    /// not hold the registry lock across the world-thread handshake.
    pub async fn instance_of(&self, session: SessionId) -> Option<TowerInstance> {
        self.towers.lock().await.get(&session).cloned()
    }

    /// Remove and close every completed instance; returns their sessions so
    /// the caller can clear the tower assignments.
    pub async fn reap_completed(&self) -> Vec<SessionId> {
        let mut towers = self.towers.lock().await;
        let done: Vec<SessionId> = towers
            .iter()
            .filter(|(_, instance)| *instance.completed.borrow())
            .map(|(session, _)| *session)
            .collect();
        for session in &done {
            if let Some(instance) = towers.remove(session) {
                instance.handle.close_instance();
            }
        }
        done
    }
}

/// Why a `POST /tower/enter` body was refused: a body that is neither empty
/// nor `{"floor": <u16>}` (mirrors [`crate::auth::ChannelParseError`]).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TowerFloorParseError {
    Malformed,
}

/// Parses the optional `{"floor": n}` body of `POST /tower/enter`. An empty
/// body (and a JSON `null`) means the default start floor. Range validation
/// against the session's best floor happens in [`TowerService::enter`].
pub fn parse_tower_floor(body: &[u8]) -> Result<Option<u16>, TowerFloorParseError> {
    if body.is_empty() {
        return Ok(None);
    }
    let value: serde_json::Value =
        serde_json::from_slice(body).map_err(|_| TowerFloorParseError::Malformed)?;
    // An empty object (or a missing/null `floor` key) means the default floor.
    let Some(floor) = value.get("floor").filter(|value| !value.is_null()) else {
        return Ok(None);
    };
    let number = floor.as_u64().ok_or(TowerFloorParseError::Malformed)?;
    u16::try_from(number)
        .map(Some)
        .map_err(|_| TowerFloorParseError::Malformed)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_store() -> crate::character::SharedCharacterStore {
        crate::character::CharacterStore::shared()
    }

    fn test_social() -> std::sync::Arc<crate::social::SocialHub> {
        std::sync::Arc::new(crate::social::SocialHub::new(
            test_store(),
            crate::world::character_record_seed(&crate::content::test_content()),
        ))
    }

    async fn next_snapshot(outputs: &mut ConnectionOutputs) -> Snapshot {
        tokio::time::timeout(Duration::from_secs(2), outputs.snapshots.changed())
            .await
            .expect("room snapshot arrives before timeout")
            .expect("snapshot watch remains open");
        outputs.snapshots.borrow_and_update().clone()
    }

    #[test]
    fn per_tick_budget_fairs_inputs_actions_and_cold_per_connection() {
        let mut budget = PerTickBudget::default();
        for _ in 0..MAX_INPUTS_PER_TICK_PER_CONN {
            assert!(budget.allow_input(7));
        }
        assert!(!budget.allow_input(7));
        // A second connection has its own budget.
        assert!(budget.allow_input(8));
        for _ in 0..MAX_ACTIONS_PER_TICK_PER_CONN {
            assert!(budget.allow_action(7));
        }
        assert!(!budget.allow_action(7));
        assert!(budget.allow_action(8));
        for _ in 0..MAX_COLD_PER_TICK_PER_CONN {
            assert!(budget.allow_cold(7));
        }
        assert!(!budget.allow_cold(7));
        assert!(budget.allow_cold(8));
    }

    #[test]
    fn reliable_queue_is_bounded_at_64() {
        assert_eq!(RELIABLE_BOUND, 64);
        let (tx, mut rx) = mpsc::channel::<Vec<u8>>(RELIABLE_BOUND);
        for _ in 0..RELIABLE_BOUND {
            assert!(tx.try_send(vec![0x82]).is_ok());
        }
        assert!(
            tx.try_send(vec![0x82]).is_err(),
            "a paused reader cannot push memory past the cap"
        );
        // Draining one slot admits exactly one packet: memory cannot grow.
        assert!(rx.try_recv().is_ok());
        assert!(tx.try_send(vec![0x82]).is_ok());
    }

    #[test]
    fn inbox_is_bounded_and_never_blocks_senders() {
        assert_eq!(INBOX_BOUND, 8192);
        let (tx, mut rx) = mpsc::channel::<RoomCommand>(4);
        for index in 0..4 {
            let mut session = [0x77; 32];
            session[0] = index;
            let (snapshot_tx, _) = watch::channel(empty_snapshot());
            let (reliable_tx, _) = mpsc::channel(1);
            let (close_tx, _) = watch::channel(false);
            let (reply_tx, _) = oneshot::channel();
            assert!(
                tx.try_send(RoomCommand::Join {
                    conn: index as u64,
                    session,
                    character: None,
                    snapshots: snapshot_tx,
                    wire_packets: watch::channel(PublishedSnapshot::default()).0,
                    queue_tracker:QueueTracker::default(),
                    reliable: reliable_tx,
                    close_send: close_tx,
                    reply: reply_tx,
                })
                .is_ok()
            );
        }
        let (snapshot_tx, _) = watch::channel(empty_snapshot());
        let (reliable_tx, _) = mpsc::channel(1);
        let (close_tx, _) = watch::channel(false);
        let (reply_tx, _) = oneshot::channel();
        assert!(
            tx.try_send(RoomCommand::Join {
                conn: 99,
                session: [0x78; 32],
                character: None,
                snapshots: snapshot_tx,
                wire_packets: watch::channel(PublishedSnapshot::default()).0,
                    queue_tracker:QueueTracker::default(),
                reliable: reliable_tx,
                close_send: close_tx,
                reply: reply_tx,
            })
            .is_err(),
            "a full inbox must refuse without blocking"
        );
        let _ = rx.try_recv();
    }

    #[test]
    fn stuck_reliable_reader_is_closed_after_the_threshold() {
        let (snapshots, _) = watch::channel(empty_snapshot());
        let (reliable, _rx) = mpsc::channel::<QueuedPacket>(1);
        let mut metrics = RoomMetrics::default();
        let (close_send, _) = watch::channel(false);
        let mut live = LiveConnection {
            chat_identity: crate::chat_moderation::ChatIdentity::Session([0; 32]),
            player_id: 1,
            epoch: 1,
            snapshots,
            wire_packets: watch::channel(PublishedSnapshot::default()).0,
                    queue_tracker:QueueTracker::default(),
            stream:crate::interest::Stream::default(),
            ordinary_membership:crate::interest::OrdinaryMembership::default(),
            reliable,
            close_send,
            reliable_drops: 0,
            frame_bytes_window:0,oldest_snapshot_writer_age_us:0,oldest_reliable_writer_age_us:0,
        };
        // One slot: first send succeeds, then the queue is full.
        assert!(!live.push_reliable(vec![1], &mut metrics));
        let mut closed = false;
        for _ in 0..RELIABLE_DROP_CLOSE_THRESHOLD {
            closed = live.push_reliable(vec![1], &mut metrics);
        }
        assert!(closed, "a stuck reader must be closed, not buffered");
        assert_eq!(
            metrics.reliable_drops,
            u64::from(RELIABLE_DROP_CLOSE_THRESHOLD)
        );
    }

    #[tokio::test]
    async fn world_thread_admits_joins_and_applies_inputs_without_locking() {
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (welcome_a, mut outputs_a) = room.join([0xA1; 32]).await.expect("join A");
        assert_eq!(welcome_a.player_id, 1);
        assert_eq!(welcome_a.epoch, 1);
        let (welcome_b, _outputs_b) = room.join([0xB2; 32]).await.expect("join B");
        assert_ne!(welcome_a.player_id, welcome_b.player_id);

        // Same session takes over (R5): new epoch, old outputs told to close.
        let (welcome_a2, outputs_a2) = room.join([0xA1; 32]).await.expect("takeover succeeds");
        assert_eq!(welcome_a2.player_id, welcome_a.player_id);
        assert!(welcome_a2.epoch > welcome_a.epoch);
        tokio::time::timeout(Duration::from_secs(2), outputs_a.closed.changed())
            .await
            .expect("displaced conn is told to close")
            .expect("watch open");
        assert!(*outputs_a.closed.borrow());
        // A stale disconnect with the old epoch must not disturb the player.
        assert!(room.submit(RoomCommand::Disconnect {
            conn: outputs_a.conn,
            player_id: welcome_a.player_id,
            epoch: welcome_a.epoch,
        }));
        let still_there = tokio::time::timeout(Duration::from_secs(2), async {
            loop {
                if outputs_a2.snapshots.has_changed().is_ok() {
                    let snapshot = outputs_a2.snapshots.borrow().clone();
                    if snapshot.tick > welcome_a2.tick {
                        return snapshot
                            .players
                            .iter()
                            .find(|player| player.id == welcome_a.player_id)
                            .map(|player| player.connected);
                    }
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("snapshot arrives");
        assert_eq!(
            still_there,
            Some(true),
            "stale-epoch disconnect must be a no-op"
        );

        // Inputs flow through the inbox; snapshots arrive on the private slot.
        // (On the taken-over connection, with its fresh epoch.)
        assert!(room.submit(RoomCommand::Input {
            conn: outputs_a2.conn,
            player_id: welcome_a2.player_id,
            epoch: welcome_a2.epoch,
            seq: 1,
            x: 1.0,
            z: 0.0,
            facing: 0.0,
            flags: 0,
        }));
        let snapshot = tokio::time::timeout(Duration::from_secs(3), async {
            loop {
                if outputs_a2.snapshots.has_changed().is_ok()
                    && outputs_a2.snapshots.borrow().tick > welcome_a2.tick
                {
                    return outputs_a2.snapshots.borrow().clone();
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("snapshot advances");
        assert!(snapshot.tick > welcome_a2.tick);
        assert!(
            snapshot
                .players
                .iter()
                .any(|player| player.id == welcome_a2.player_id)
        );

        assert!(room.submit(RoomCommand::Disconnect {
            conn: outputs_a2.conn,
            player_id: welcome_a2.player_id,
            epoch: welcome_a2.epoch,
        }));
    }

    #[tokio::test]
    async fn splash_combat_event_survives_a_paused_room_snapshot_reader() {
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (welcome, mut outputs) = room.join([0xCA; 32]).await.expect("join combat client");
        let mut sequence = 0_u64;
        let warning = tokio::time::timeout(Duration::from_secs(12), async {
            loop {
                let snapshot = next_snapshot(&mut outputs).await;
                let player = snapshot
                    .players
                    .iter()
                    .find(|player| player.id == welcome.player_id)
                    .expect("player is in the latest snapshot");
                let monster = snapshot
                    .monsters
                    .iter()
                    .filter(|monster| monster.active)
                    .min_by(|left, right| {
                        (left.x - player.x)
                            .hypot(left.z - player.z)
                            .total_cmp(&(right.x - player.x).hypot(right.z - player.z))
                    })
                    .expect("a live monster is in the zone");
                if monster.state == crate::world::monster_state::WINDUP
                    && monster.ability == 5
                    && monster.state_ticks <= 4
                {
                    return snapshot;
                }

                let dx = monster.x - player.x;
                let dz = monster.z - player.z;
                let distance = dx.hypot(dz);
                let (x, z) = if distance > 5.0 {
                    (dx / distance, dz / distance)
                } else {
                    (0.0, 0.0)
                };
                sequence += 1;
                assert!(room.submit(RoomCommand::Input {
                    conn: outputs.conn,
                    player_id: welcome.player_id,
                    epoch: welcome.epoch,
                    seq: sequence,
                    x,
                    z,
                    facing: dx.atan2(dz),
                    flags: 0,
                }));
            }
        })
        .await
        .expect("Puddlekin enters the Splash Hop warning window");

        // The reader deliberately stops consuming its one-slot watch channel
        // through the impact. The owner keeps publishing snapshots and the
        // event repeats, so the resumed writer must see the latest event.
        // Follow the room clock while the receiver remains unconsumed. A busy
        // host may skip wall-clock intervals; six simulation ticks cross the
        // <=four-tick windup and its impact without expiring the event window.
        tokio::time::timeout(Duration::from_secs(3),async {
            loop {if outputs.snapshots.borrow().tick>=warning.tick+6 {break;}tokio::time::sleep(Duration::from_millis(5)).await;}
        }).await.expect("paused reader spans the authoritative impact ticks");
        let resumed = next_snapshot(&mut outputs).await;
        assert!(resumed.tick > warning.tick);
        assert!(
            resumed.events.iter().any(|event| {
                event.action == ActionKind::SplashHop
                    && event.target_kind == 1
                    && event.target_id == welcome.player_id
            }),
            "the paused reader receives the repeated Splash Hop event on resume"
        );
        let packet = crate::wire::encode_snapshot(&resumed, 308.0)
            .expect("the resumed snapshot with the combat event serializes");
        assert!(!packet.is_empty());
    }

    #[tokio::test]
    async fn dropped_outputs_do_not_lock_the_session() {
        // R4 ghost regression test: outputs gone (writer exited) must not
        // leave the session stuck; the player is fenced out by epoch and the
        // session rejoins as the same player.
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let session = [0xE5; 32];
        let (welcome, outputs) = room.join(session).await.expect("join");
        drop(outputs);
        tokio::time::sleep(Duration::from_millis(300)).await;
        let (welcome2, outputs2) = room.join(session).await.expect("rejoin after dead outputs");
        assert_eq!(welcome2.player_id, welcome.player_id);
        assert!(welcome2.epoch > welcome.epoch);
        assert!(room.submit(RoomCommand::Disconnect {
            conn: outputs2.conn,
            player_id: welcome2.player_id,
            epoch: welcome2.epoch,
        }));
    }

    #[tokio::test]
    async fn reliable_message_reaches_only_its_owner() {
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (_welcome_a, mut outputs_a) = room.join([0xC1; 32]).await.expect("join A");
        let (_welcome_b, mut outputs_b) = room.join([0xC2; 32]).await.expect("join B");

        drain_drops(&mut outputs_a.reliable);
        assert!(room.notify(outputs_a.conn, vec![0x90, 0x01]));
        let got = tokio::time::timeout(Duration::from_secs(2), outputs_a.reliable.recv())
            .await
            .expect("owner receives its message")
            .expect("queue open");
        assert_eq!(got, vec![0x90, 0x01]);
        // The other connection's queue stays empty: no cross-delivery.
        drain_drops(&mut outputs_b.reliable);
        assert!(
            outputs_b.reliable.try_recv().is_err(),
            "a per-player message must reach only its owner"
        );
    }

    #[tokio::test]
    async fn resync_delivers_revisioned_character_and_quest_only_to_owner() {
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (_welcome_a, mut outputs_a) = room.join([0xE1; 32]).await.expect("join A");
        let (_welcome_b, mut outputs_b) = room.join([0xE2; 32]).await.expect("join B");
        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"resync"}"#.to_vec(),
        }));

        for expected_tag in ["character_state", "quest_state"] {
            loop {
                let packet =
                    tokio::time::timeout(Duration::from_secs(2), outputs_a.reliable.recv())
                        .await
                        .expect("state response arrives")
                        .expect("queue open");
                assert_eq!(packet[3], 0x90);
                let message: serde_json::Value = serde_json::from_slice(&packet[6..]).unwrap();
                if message["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                if message["t"] == "mage_trial_state" {
                    assert_eq!(message["profile"],"trailblade");
                    let skills=message["skills"].as_array().expect("typed Mage skill metadata");
                    assert_eq!(skills.len(),2);
                    assert!(skills.iter().all(|skill|skill["available"]==false),"resync must not opt a player into Mage");
                    continue;
                }
                assert_eq!(message["t"], expected_tag);
                assert!(message["rev"].as_u64().unwrap() > 0);
                break;
            }
        }
        // B's queue only carries its own P4 drops snapshot, never A's state.
        drain_drops(&mut outputs_b.reliable);
        drain_drops(&mut outputs_b.reliable);
        assert!(outputs_b.reliable.try_recv().is_err());
    }

    #[tokio::test]
    async fn party_commands_return_invite_roster_and_leave_state() {
        async fn next_party_state(rx: &mut mpsc::Receiver<QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(Duration::from_secs(2), rx.recv())
                    .await
                    .expect("party update arrives")
                    .expect("reliable queue stays open");
                assert_eq!(packet[3], 0x90);
                let message: serde_json::Value = serde_json::from_slice(&packet[6..]).unwrap();
                if message["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                assert_eq!(message["t"], "party_state");
                break message;
            }
        }

        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (_welcome_a, mut outputs_a) = room.join([0xF1; 32]).await.expect("join A");
        let (_welcome_b, mut outputs_b) = room.join([0xF2; 32]).await.expect("join B");
        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"party_create"}"#.to_vec(),
        }));
        let created = next_party_state(&mut outputs_a.reliable).await;
        assert_eq!(created["members"].as_array().unwrap().len(), 1);
        let code = created["code"].as_str().unwrap().to_string();
        assert_eq!(code.len(), 6);

        assert!(
            room.submit(RoomCommand::Cold {
                conn: outputs_b.conn,
                payload: serde_json::to_vec(
                    &serde_json::json!({ "t": "party_join", "code": code })
                )
                .unwrap(),
            })
        );
        let joined_a = next_party_state(&mut outputs_a.reliable).await;
        let joined_b = next_party_state(&mut outputs_b.reliable).await;
        assert_eq!(joined_a["members"].as_array().unwrap().len(), 2);
        assert_eq!(joined_b["members"].as_array().unwrap().len(), 2);
        assert_eq!(joined_a["leader"], joined_b["leader"]);

        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_b.conn,
            payload: br#"{"t":"party_leave"}"#.to_vec(),
        }));
        let left_a = next_party_state(&mut outputs_a.reliable).await;
        let left_b = next_party_state(&mut outputs_b.reliable).await;
        assert_eq!(left_a["members"].as_array().unwrap().len(), 1);
        assert!(left_b["members"].as_array().unwrap().is_empty());
    }

    #[tokio::test]
    async fn party_cold_requests_publish_roster_changes_to_members() {
        async fn next_json(rx: &mut mpsc::Receiver<QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(Duration::from_secs(2), rx.recv())
                    .await
                    .expect("party update arrives")
                    .expect("queue open");
                assert_eq!(packet[3], 0x90);
                let json: serde_json::Value =
                    serde_json::from_slice(&packet[6..]).expect("cold state is JSON");
                if json["t"] == "drops" {
                    continue; // P4 join/refresh snapshot, not a party update
                }
                break json;
            }
        }

        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (_welcome_a, mut outputs_a) = room.join([0xF1; 32]).await.expect("join A");
        let (_welcome_b, mut outputs_b) = room.join([0xF2; 32]).await.expect("join B");
        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"party_create"}"#.to_vec(),
        }));
        let created = next_json(&mut outputs_a.reliable).await;
        assert_eq!(created["t"], "party_state");
        assert_eq!(created["members"].as_array().unwrap().len(), 1);
        let code = created["code"].as_str().unwrap().to_string();
        assert_eq!(code.len(), 6);

        assert!(
            room.submit(RoomCommand::Cold {
                conn: outputs_b.conn,
                payload: serde_json::to_vec(
                    &serde_json::json!({ "t": "party_join", "code": code })
                )
                .unwrap(),
            })
        );
        let joined_a = next_json(&mut outputs_a.reliable).await;
        let joined_b = next_json(&mut outputs_b.reliable).await;
        assert_eq!(joined_a["members"].as_array().unwrap().len(), 2);
        assert_eq!(joined_b["members"].as_array().unwrap().len(), 2);
        assert_eq!(joined_a["leader"], joined_b["leader"]);

        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_b.conn,
            payload: br#"{"t":"party_leave"}"#.to_vec(),
        }));
        let left_a = next_json(&mut outputs_a.reliable).await;
        let left_b = next_json(&mut outputs_b.reliable).await;
        assert_eq!(left_a["members"].as_array().unwrap().len(), 1);
        assert!(left_b["members"].as_array().unwrap().is_empty());
    }

    #[tokio::test]
    async fn ping_replies_with_a_pong_carrying_the_server_tick() {
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        let (_welcome, mut outputs) = room.join([0xD4; 32]).await.expect("join");
        assert!(room.submit(RoomCommand::Ping {
            conn: outputs.conn,
            nonce: 0xA11CE,
            client_ms: 999,
        }));
        // P4: the join also queues a drops snapshot; skip cold messages until
        // the pong (0x85) arrives.
        let mut pong = None;
        let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
        while pong.is_none() {
            let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
            let packet = tokio::time::timeout(remaining, outputs.reliable.recv())
                .await
                .expect("pong arrives")
                .expect("queue open");
            if packet.len() > 3 && packet[3] == 0x85 {
                pong = Some(packet);
            }
        }
        let pong = pong.expect("pong collected");
        // Envelope (magic, version 6, type 0x85, length 16) + nonce echo.
        assert_eq!(pong.len(), 6 + 16);
        assert_eq!(pong[3], 0x85);
        assert_eq!(u32::from_le_bytes(pong[6..10].try_into().unwrap()), 0xA11CE);
        assert_eq!(u32::from_le_bytes(pong[10..14].try_into().unwrap()), 999);
        assert!(u64::from_le_bytes(pong[14..22].try_into().unwrap()) > 0);
    }

    async fn wait_for_occupancy(room: &RoomHandle, expected: usize) {
        tokio::time::timeout(Duration::from_secs(2), async {
            while room.occupancy() != expected {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("occupancy reaches the expected value");
    }

    #[tokio::test]
    async fn occupancy_counts_rise_on_join_and_fall_on_disconnect_without_leaking() {
        let (room, _alive) = RoomHandle::spawn(&test_store(), &test_social()).expect("spawn room");
        assert_eq!(room.occupancy(), 0);
        let (welcome, outputs) = room.join([0xB0; 32]).await.expect("join");
        wait_for_occupancy(&room, 1).await;

        // A rejoin takeover replaces the old connection, never double-counts.
        let (welcome2, outputs2) = room.join([0xB0; 32]).await.expect("takeover join");
        assert_eq!(welcome2.player_id, welcome.player_id);
        wait_for_occupancy(&room, 1).await;

        assert!(room.submit(RoomCommand::Disconnect {
            conn: outputs2.conn,
            player_id: welcome2.player_id,
            epoch: welcome2.epoch,
        }));
        wait_for_occupancy(&room, 0).await;
        drop(outputs);
    }

    #[tokio::test]
    async fn spawn_all_creates_independent_rooms_with_their_own_counts() {
        let (rooms, alive_flags) =
            RoomHandle::spawn_all(3, &test_store(), &test_social()).expect("spawn rooms");
        assert_eq!(rooms.len(), 3);
        assert_eq!(alive_flags.len(), 3);
        assert!(alive_flags.iter().all(|alive| alive.load(Ordering::SeqCst)));
        for room in &rooms {
            assert_eq!(room.occupancy(), 0);
        }
        let (welcome, outputs) = rooms[0].join([0x5A; 32]).await.expect("join room 0");
        wait_for_occupancy(&rooms[0], 1).await;
        for room in &rooms[1..] {
            assert_eq!(
                room.occupancy(),
                0,
                "joining one room must not touch the others"
            );
        }
        assert!(rooms[0].submit(RoomCommand::Disconnect {
            conn: outputs.conn,
            player_id: welcome.player_id,
            epoch: welcome.epoch,
        }));
        wait_for_occupancy(&rooms[0], 0).await;
    }

    #[tokio::test]
    async fn spawn_all_builds_the_full_twenty_room_set() {
        let (rooms, alive_flags) = RoomHandle::spawn_all(
            usize::from(crate::auth::CHANNEL_COUNT),
            &test_store(),
            &test_social(),
        )
        .expect("spawn rooms");
        assert_eq!(rooms.len(), 20);
        assert_eq!(alive_flags.len(), 20);
        assert!(alive_flags.iter().all(|alive| alive.load(Ordering::SeqCst)));
        for room in &rooms {
            assert_eq!(room.occupancy(), 0);
        }
    }

    #[test]
    fn auto_route_prefers_the_least_occupied_room_and_skips_full_ones() {
        // Least occupancy wins.
        assert_eq!(auto_route_order(&[3, 1, 2], 50), vec![1, 2, 0]);
        // Ties break toward the lowest channel index.
        assert_eq!(auto_route_order(&[0, 0, 0], 50), vec![0, 1, 2]);
        // Rooms at capacity are skipped entirely.
        assert_eq!(auto_route_order(&[50, 1, 50], 50), vec![1]);
        assert_eq!(auto_route_order(&[2, 2], 2), Vec::<usize>::new());
        // A full set routes nowhere.
        assert_eq!(auto_route_order(&[50; 20], 50), Vec::<usize>::new());
    }

    #[test]
    fn room_summaries_list_one_capacity_entry_per_room_in_channel_order() {
        let summaries = room_summaries([3, 0, crate::world::MAX_PLAYERS].into_iter());
        let json = serde_json::to_value(&summaries).expect("room summaries serialize");
        assert_eq!(json.as_array().expect("summaries array").len(), 3);
        assert_eq!(
            json[0],
            serde_json::json!({
                "channel": 0,
                "players": 3,
                "capacity": crate::world::MAX_PLAYERS
            })
        );
        assert_eq!(
            json[1],
            serde_json::json!({ "channel": 1, "players": 0, "capacity": crate::world::MAX_PLAYERS })
        );
        assert_eq!(
            json[2],
            serde_json::json!({
                "channel": 2,
                "players": crate::world::MAX_PLAYERS,
                "capacity": crate::world::MAX_PLAYERS
            })
        );
    }

    #[tokio::test]
    async fn joins_land_in_the_session_channel_and_auto_picks_the_least_occupied_room() {
        let (rooms, _alive_flags) =
            RoomHandle::spawn_all(3, &test_store(), &test_social()).expect("spawn rooms");

        // A fixed channel lands in exactly that room.
        let session = [0xC7; 32];
        let (index, _welcome, _outputs) = join_routed(&rooms, Some(2), session)
            .await
            .expect("fixed-channel join");
        assert_eq!(index, 2);
        tokio::time::timeout(Duration::from_secs(2), async {
            while rooms[2].occupancy() != 1 {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("channel 2 occupancy rises");

        // Auto-routing skips the occupied room: rooms 0 and 1 tie at zero, so
        // the lowest channel wins.
        let (index, _welcome, outputs) = join_routed(&rooms, None, [0xD8; 32])
            .await
            .expect("auto join");
        assert_eq!(index, 0);
        assert!(rooms[1].occupancy() == 0 && rooms[2].occupancy() == 1);
        let _ = rooms[0].submit(RoomCommand::Disconnect {
            conn: outputs.conn,
            player_id: 0,
            epoch: 0,
        });
    }

    #[tokio::test]
    async fn auto_route_never_lands_on_a_full_room() {
        let (rooms, _alive_flags) =
            RoomHandle::spawn_all(2, &test_store(), &test_social()).expect("spawn rooms");
        // Fill channel 0 to capacity, one join at a time (world-thread ticks).
        // The outputs are held for the whole test: dropping one tells the
        // room its reader is gone, and the connection is cleaned up.
        let mut held = Vec::new();
        for slot in 0..crate::world::MAX_PLAYERS {
            let mut session = [0xE9; 32];
            session[0] = slot as u8;
            session[1] = (slot >> 8) as u8;
            held.push(
                rooms[0]
                    .join(session)
                    .await
                    .expect("every room slot admits until the cap"),
            );
        }
        tokio::time::timeout(Duration::from_secs(5), async {
            while rooms[0].occupancy() != crate::world::MAX_PLAYERS {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("room 0 fills to capacity");

        // The full room refuses directly (existing room_full path).
        assert_eq!(
            rooms[0].join([0xFA; 32]).await.err(),
            Some("room_full"),
            "joining a full room must be refused"
        );
        // Auto-routing skips it and lands in the room with space.
        let (index, _welcome, outputs) = join_routed(&rooms, None, [0xFB; 32])
            .await
            .expect("auto join finds the open room");
        assert_eq!(index, 1);
        let _ = rooms[1].submit(RoomCommand::Disconnect {
            conn: outputs.conn,
            player_id: 0,
            epoch: 0,
        });
    }

    // P4: drain drops snapshots so queue-empty assertions see a quiet queue.
    fn drain_drops(rx: &mut mpsc::Receiver<QueuedPacket>) {
        while let Ok(packet) = rx.try_recv() {
            if packet.len() > 6 && &packet[6..] == br#"{"t":"drops","entries":[]}"# {
                continue;
            }
            // Unknown non-empty leftovers are re-checked by the caller's
            // assertion; stop draining on the first non-drops packet.
            if packet[3] == 0x90 {
                let Ok(json) = serde_json::from_slice::<serde_json::Value>(&packet[6..]) else {
                    return;
                };
                if json["t"] == "drops" {
                    continue;
                }
                // Not a drops frame: push it back is impossible with mpsc;
                // the caller's next assertion will see it.
                return;
            }
        }
    }

    // -- social cold path (chat, friends, groups) -----------------------------

    #[tokio::test]
    async fn friend_cold_add_pushes_the_roster_and_errors_become_notices() {
        async fn next_json(rx: &mut mpsc::Receiver<QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(Duration::from_secs(3), rx.recv())
                    .await
                    .expect("social response arrives")
                    .expect("queue stays open");
                assert_eq!(packet[3], 0x90);
                let json: serde_json::Value =
                    serde_json::from_slice(&packet[6..]).expect("cold payload is JSON");
                if json["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                return json;
            }
        }

        let store = test_store();
        let social = test_social();
        let (room, _alive) = RoomHandle::spawn(&store, &social).expect("spawn room");
        let (_welcome_a, mut outputs_a) = room.join([0xA1; 32]).await.expect("join A");
        let (_welcome_b, mut outputs_b) = room.join([0xB2; 32]).await.expect("join B");
        let (handle_a, name_a) = crate::character::identity_for_session([0xA1; 32]);
        let (handle_b, name_b) = crate::character::identity_for_session([0xB2; 32]);
        // Presence normally comes from the socket task; register it directly.
        let _guard_a = social.join_guard(
            [0xA1; 32],
            crate::social::PresenceKind::Normal { channel: 0 },
            handle_a,
            name_a,
            room.clone(),
        );
        let _guard_b = social.join_guard(
            [0xB2; 32],
            crate::social::PresenceKind::Normal { channel: 0 },
            handle_b.clone(),
            name_b.clone(),
            room.clone(),
        );

        // An unknown handle (no live presence) answers with a notice.
        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"friend_add","handle":"e5e5e5e5"}"#.to_vec(),
        }));
        let notice = next_json(&mut outputs_a.reliable).await;
        assert_eq!(notice["t"], "notice");
        assert_eq!(notice["key"], "friends_unknown_player");

        // Adding the online B pushes the roster to A (the hub routes it back
        // through the session's own instance).
        assert!(
            room.submit(RoomCommand::Cold {
                conn: outputs_a.conn,
                payload: serde_json::to_vec(&serde_json::json!({
                    "t": "friend_add", "handle": handle_b
                }))
                .unwrap(),
            })
        );
        let roster = next_json(&mut outputs_a.reliable).await;
        assert_eq!(roster["t"], "friends");
        let entries = roster["entries"].as_array().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0]["handle"], handle_b.as_str());
        assert_eq!(entries[0]["name"], name_b.as_str());
        assert_eq!(entries[0]["online"], true);
        // The other connection never sees A's roster.
        drain_drops(&mut outputs_b.reliable);
        drain_drops(&mut outputs_b.reliable);
        assert!(outputs_b.reliable.try_recv().is_err());

        // Removing answers with the fresh (empty) roster.
        assert!(
            room.submit(RoomCommand::Cold {
                conn: outputs_a.conn,
                payload: serde_json::to_vec(&serde_json::json!({
                    "t": "friend_remove", "handle": handle_b
                }))
                .unwrap(),
            })
        );
        let emptied = next_json(&mut outputs_a.reliable).await;
        assert_eq!(emptied["t"], "friends");
        assert!(emptied["entries"].as_array().unwrap().is_empty());
    }

    #[tokio::test]
    async fn group_cold_commands_publish_state_and_disband_on_leader_leave() {
        async fn next_json(where_: &str, rx: &mut mpsc::Receiver<QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(Duration::from_secs(3), rx.recv())
                    .await
                    .unwrap_or_else(|_| panic!("group push arrives ({where_})"))
                    .expect("queue stays open");
                assert_eq!(packet[3], 0x90);
                let json: serde_json::Value =
                    serde_json::from_slice(&packet[6..]).expect("cold payload is JSON");
                if json["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                break json;
            }
        }

        let store = test_store();
        let social = test_social();
        let (room, _alive) = RoomHandle::spawn(&store, &social).expect("spawn room");
        let (_welcome_a, mut outputs_a) = room.join([0xA1; 32]).await.expect("join A");
        let (_welcome_b, mut outputs_b) = room.join([0xB2; 32]).await.expect("join B");
        let (handle_a, name_a) = crate::character::identity_for_session([0xA1; 32]);
        let (handle_b, name_b) = crate::character::identity_for_session([0xB2; 32]);
        // Presence normally comes from the socket task; register it directly.
        let _guard_a = social.join_guard(
            [0xA1; 32],
            crate::social::PresenceKind::Normal { channel: 0 },
            handle_a,
            name_a,
            room.clone(),
        );
        let _guard_b = social.join_guard(
            [0xB2; 32],
            crate::social::PresenceKind::Normal { channel: 0 },
            handle_b,
            name_b,
            room.clone(),
        );

        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"group_create"}"#.to_vec(),
        }));
        let created = next_json("created", &mut outputs_a.reliable).await;
        assert_eq!(created["t"], "group");
        let code = created["code"].as_str().unwrap().to_string();
        assert_eq!(code.len(), 6);
        assert_eq!(created["members"].as_array().unwrap().len(), 1);

        assert!(
            room.submit(RoomCommand::Cold {
                conn: outputs_b.conn,
                payload: serde_json::to_vec(&serde_json::json!({
                    "t": "group_join", "code": code
                }))
                .unwrap(),
            })
        );
        let joined_a = next_json("joined_a", &mut outputs_a.reliable).await;
        let joined_b = next_json("joined_b", &mut outputs_b.reliable).await;
        assert_eq!(joined_a["members"].as_array().unwrap().len(), 2);
        assert_eq!(joined_b["members"].as_array().unwrap().len(), 2);

        // A member who is already in a group gets already_in_group before any
        // code lookup (leave first); a malformed code shape is dropped at the
        // envelope validator.
        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_b.conn,
            payload: br#"{"t":"group_join","code":"ZZZZZZ"}"#.to_vec(),
        }));
        let bad_code = next_json("bad_code", &mut outputs_b.reliable).await;
        assert_eq!(bad_code["t"], "notice");
        assert_eq!(bad_code["key"], "group_already_in_group");

        // The leader leaving disbands: both members get `code: null`.
        assert!(room.submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"group_leave"}"#.to_vec(),
        }));
        let disbanded_a = next_json("disbanded_a", &mut outputs_a.reliable).await;
        let disbanded_b = next_json("disbanded_b", &mut outputs_b.reliable).await;
        for push in [&disbanded_a, &disbanded_b] {
            assert_eq!(push["t"], "group");
            assert!(push["code"].is_null());
            assert!(push["members"].as_array().unwrap().is_empty());
        }
    }

    #[tokio::test]
    async fn group_chat_via_the_cold_path_reaches_members_on_both_instances() {
        async fn next_json(rx: &mut mpsc::Receiver<QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(Duration::from_secs(3), rx.recv())
                    .await
                    .expect("message arrives")
                    .expect("queue stays open");
                assert_eq!(packet[3], 0x90);
                let json: serde_json::Value =
                    serde_json::from_slice(&packet[6..]).expect("cold payload is JSON");
                if json["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                break json;
            }
        }

        let store = test_store();
        let social = test_social();
        let (rooms, _alive) = RoomHandle::spawn_all(2, &store, &social).expect("rooms");
        let a = [0xA1; 32];
        let b = [0xB2; 32];
        let (_welcome_a, mut outputs_a) = rooms[0].join(a).await.expect("join A");
        let (_welcome_b, mut outputs_b) = rooms[1].join(b).await.expect("join B");
        let (handle_a, name_a) = crate::character::identity_for_session(a);
        let (handle_b, name_b) = crate::character::identity_for_session(b);
        let _guard_a = social.join_guard(
            a,
            crate::social::PresenceKind::Normal { channel: 0 },
            handle_a,
            name_a.clone(),
            rooms[0].clone(),
        );
        let _guard_b = social.join_guard(
            b,
            crate::social::PresenceKind::Normal { channel: 1 },
            handle_b,
            name_b.clone(),
            rooms[1].clone(),
        );

        // A creates the group through the cold path of instance 0; B joins
        // through instance 1.
        assert!(rooms[0].submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"group_create"}"#.to_vec(),
        }));
        let created = next_json(&mut outputs_a.reliable).await;
        let code = created["code"].as_str().unwrap().to_string();
        assert!(
            rooms[1].submit(RoomCommand::Cold {
                conn: outputs_b.conn,
                payload: serde_json::to_vec(&serde_json::json!({
                    "t": "group_join", "code": code
                }))
                .unwrap(),
            })
        );
        let _join_push_a = next_json(&mut outputs_a.reliable).await;
        let _join_push_b = next_json(&mut outputs_b.reliable).await;

        // Group chat sent from B's instance reaches both members.
        assert!(rooms[1].submit(RoomCommand::Cold {
            conn: outputs_b.conn,
            payload: br#"{"t":"chat","channel":"group","text":"cross-instance hi"}"#.to_vec(),
        }));
        let on_a = next_json(&mut outputs_a.reliable).await;
        assert_eq!(on_a["t"], "chat");
        assert_eq!(on_a["channel"], "group");
        assert_eq!(on_a["text"], "cross-instance hi");
        assert_eq!(on_a["from"], name_b.as_str());
        let on_b = next_json(&mut outputs_b.reliable).await;
        assert_eq!(on_b["text"], "cross-instance hi");

        // Room chat from A stays inside instance 0 (B is on instance 1).
        assert!(rooms[0].submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"chat","channel":"room","text":"room only"}"#.to_vec(),
        }));
        let room_line = next_json(&mut outputs_a.reliable).await;
        assert_eq!(room_line["channel"], "room");
        tokio::time::sleep(Duration::from_millis(300)).await;
        assert!(
            outputs_b.reliable.try_recv().is_err(),
            "room chat must not cross instances"
        );
    }

    // -- tower instances -----------------------------------------------------

    #[test]
    fn tower_enter_body_parses_the_optional_floor() {
        assert_eq!(parse_tower_floor(b""), Ok(None));
        assert_eq!(parse_tower_floor(br#"{"floor":null}"#), Ok(None));
        assert_eq!(parse_tower_floor(br#"{"floor":1}"#), Ok(Some(1)));
        assert_eq!(parse_tower_floor(br#"{"floor":100}"#), Ok(Some(100)));
        assert_eq!(parse_tower_floor(br#"{"floor":3,"other":1}"#), Ok(Some(3)));
        // Malformed shapes are a bad-floor body; range checks need the
        // session's best floor and happen in the service.
        assert_eq!(
            parse_tower_floor(b"not json"),
            Err(TowerFloorParseError::Malformed)
        );
        assert_eq!(
            parse_tower_floor(b"{}"),
            Ok(None),
            "an empty object means the default floor"
        );
        assert_eq!(
            parse_tower_floor(br#"{"floor":"3"}"#),
            Err(TowerFloorParseError::Malformed)
        );
        assert_eq!(
            parse_tower_floor(br#"{"floor":-1}"#),
            Err(TowerFloorParseError::Malformed)
        );
        assert_eq!(
            parse_tower_floor(br#"{"floor":1.5}"#),
            Err(TowerFloorParseError::Malformed)
        );
        assert_eq!(
            parse_tower_floor(br#"{"floor":70000}"#),
            Err(TowerFloorParseError::Malformed)
        );
    }

    #[tokio::test]
    async fn tower_service_enter_leave_round_trip_enforces_floor_and_cap() {
        let store = test_store();
        let (floor_tx, _floor_rx) = mpsc::unbounded_channel();
        let service = TowerService::new(2, 100, store, test_social(), floor_tx);
        let session_a = [0xA1; 32];
        let session_b = [0xB2; 32];
        let session_c = [0xC3; 32];

        // Default entry lands at floor 1; re-entering keeps the live
        // instance instead of respawning.
        assert_eq!(service.enter(session_a, None, 0).await, Ok(1));
        assert_eq!(service.enter(session_a, None, 0).await, Ok(1));
        // A bad body floor is refused even while a live instance exists.
        assert_eq!(
            service.enter(session_a, Some(0), 0).await,
            Err(TowerEnterError::BadFloor)
        );

        // Floor validation: 1..=min(best_floor + 1, max_floor).
        assert_eq!(
            service.enter(session_b, Some(0), 0).await,
            Err(TowerEnterError::BadFloor)
        );
        assert_eq!(
            service.enter(session_b, Some(7), 5).await,
            Err(TowerEnterError::BadFloor),
            "one past the highest unlocked floor is refused"
        );
        assert_eq!(
            service.enter(session_b, Some(101), 100).await,
            Err(TowerEnterError::BadFloor),
            "past max_floor even with a full best_floor"
        );
        assert_eq!(service.enter(session_b, Some(2), 1).await, Ok(2));

        // Cap of two live instances: the third session is refused.
        assert_eq!(
            service.enter(session_c, None, 0).await,
            Err(TowerEnterError::Full)
        );

        // Leaving frees the cap; status follows the registry.
        service.leave(session_a).await;
        assert_eq!(service.status(session_a).await, (false, 0));
        assert_eq!(service.enter(session_c, None, 0).await, Ok(1));
        assert_eq!(service.status(session_c).await, (true, 1));
        service.leave(session_b).await;
        service.leave(session_c).await;
    }

    #[tokio::test]
    async fn tower_service_reports_live_floors_and_reaps_completed_instances() {
        let store = test_store();
        let (floor_tx, mut floor_rx) = mpsc::unbounded_channel();
        let service = TowerService::new(4, 100, store, test_social(), floor_tx);
        let session = [0x71; 32];
        assert_eq!(service.enter(session, Some(7), 6).await, Ok(7));
        // The instance starts on the entered floor (world loop confirms).
        wait_for_floor(&service, session, 7).await;

        // Outside the tower the status is flat.
        assert_eq!(service.status([0x72; 32]).await, (false, 0));

        // A completed instance is reaped and its session returned for
        // assignment cleanup.
        {
            let towers = service.towers.lock().await;
            let instance = towers.get(&session).expect("instance exists");
            instance.handle.close_instance();
        }
        assert!(
            service.status(session).await.0,
            "a closing instance still reports in-tower until reaped"
        );
        service.leave(session).await;
        assert_eq!(service.status(session).await, (false, 0));
        // No milestone has been emitted yet (no floor cleared).
        assert!(floor_rx.try_recv().is_err());
    }

    async fn wait_for_floor(service: &TowerService, session: SessionId, floor: u16) {
        tokio::time::timeout(Duration::from_secs(2), async {
            while service.status(session).await.1 != floor {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("tower instance reports its start floor");
    }

    #[test]
    fn completed_instances_do_not_count_against_the_cap() {
        let store = test_store();
        let mut towers = HashMap::new();
        let (live_handle, _alive) = RoomHandle::spawn(&store, &test_social()).expect("live room");
        let (_completed_tx, live_completed) = watch::channel(false);
        towers.insert(
            [0x81; 32],
            TowerInstance {
                handle: live_handle,
                session: [0x81; 32],
                completed: live_completed,
                floor: Arc::new(AtomicU16::new(3)),
            },
        );
        let (closed_handle, _alive) =
            RoomHandle::spawn(&store, &test_social()).expect("closed room");
        let (_completed_tx, closed_completed) = watch::channel(true);
        towers.insert(
            [0x82; 32],
            TowerInstance {
                handle: closed_handle,
                session: [0x82; 32],
                completed: closed_completed,
                floor: Arc::new(AtomicU16::new(100)),
            },
        );
        assert_eq!(
            active_tower_count(&towers),
            1,
            "completed instances free their cap slot before the reaper runs"
        );
    }

    #[tokio::test]
    async fn tower_assigned_sessions_route_into_their_instance_and_stale_ones_fall_back() {
        let store = test_store();
        let (rooms, _alive) =
            RoomHandle::spawn_all(2, &store, &test_social()).expect("spawn rooms");
        let (floor_tx, _floor_rx) = mpsc::unbounded_channel();
        let service = TowerService::new(4, 100, store, test_social(), floor_tx);
        let session = [0x77; 32];
        assert_eq!(service.enter(session, None, 0).await, Ok(1));

        // The tower-assigned session joins its own instance, bypassing the
        // room set entirely.
        let instance = service.instance_of(session).await.expect("instance");
        match route_join(&rooms, Some(instance), None, session)
            .await
            .expect("tower routing")
        {
            JoinRoute::Tower {
                handle, welcome, ..
            } => {
                assert!(welcome.epoch >= 1);
                wait_for_occupancy(&handle, 1).await;
                assert_eq!(rooms[0].occupancy(), 0);
                assert_eq!(rooms[1].occupancy(), 0);
            }
            _ => panic!("a tower-assigned session must join its tower instance"),
        }

        // A stale instance (closed for teardown) refuses joins and reports
        // stale so the caller clears the assignment.
        let instance = service.instance_of(session).await.expect("instance");
        instance.handle.close_instance();
        match route_join(&rooms, Some(instance), Some(1), session)
            .await
            .expect("stale routing")
        {
            JoinRoute::StaleTower => {}
            _ => panic!("a closed tower instance must report stale"),
        }

        // Without an instance the join routes normally into the room set.
        match route_join(&rooms, None, Some(1), session)
            .await
            .expect("normal routing")
        {
            JoinRoute::Normal { index, .. } => assert_eq!(index, 1),
            _ => panic!("a cleared assignment routes normally"),
        }
    }
    #[tokio::test]
    async fn snapshot_ack_is_fenced_to_live_epoch_and_actually_sent_ticks() {
        let (room,_alive)=RoomHandle::spawn(&test_store(),&test_social()).unwrap();
        let (welcome,mut out)=room.join([0x97;32]).await.unwrap();
        async fn next(out:&mut ConnectionOutputs)->PublishedSnapshot{tokio::time::timeout(Duration::from_secs(2),out.wire_packets.changed()).await.unwrap().unwrap();out.wire_packets.borrow_and_update().clone()}
        fn baseline(packet:&PublishedSnapshot)->u64{u64::from_le_bytes(packet.bytes[18..26].try_into().unwrap())}
        let first=next(&mut out).await;assert_eq!(baseline(&first),0);
        room.submit(RoomCommand::SnapshotSent{conn:out.conn,epoch:welcome.epoch+1,tick:first.tick,frame_bytes:0,writer_age_us:0});
        room.submit(RoomCommand::SnapshotAck{conn:out.conn,epoch:welcome.epoch,tick:first.tick,resync:false});
        assert_eq!(baseline(&next(&mut out).await),0,"unsent tick cannot become a baseline");
        room.submit(RoomCommand::SnapshotSent{conn:out.conn,epoch:welcome.epoch,tick:first.tick,frame_bytes:0,writer_age_us:0});
        room.submit(RoomCommand::SnapshotAck{conn:out.conn,epoch:welcome.epoch,tick:first.tick,resync:false});
        assert_eq!(baseline(&next(&mut out).await),first.tick);
        room.submit(RoomCommand::SnapshotAck{conn:out.conn,epoch:welcome.epoch,tick:u64::MAX,resync:false});
        room.submit(RoomCommand::SnapshotAck{conn:out.conn,epoch:welcome.epoch+1,tick:0,resync:true});
        assert_eq!(baseline(&next(&mut out).await),first.tick,"future or stale-epoch ACK cannot alter state");
        room.submit(RoomCommand::SnapshotAck{conn:out.conn,epoch:welcome.epoch,tick:0,resync:true});
        assert_eq!(baseline(&next(&mut out).await),0,"valid resync forces full truth");
    }

    #[test]
    fn outbound_age_tracks_overwritten_snapshot_and_actual_reliable_backlog() {
        let start=Instant::now();let mut q=OutboundQueueState::default();
        q.snapshot=Some((1,start));q.snapshot=Some((2,start+Duration::from_millis(10)));
        assert_eq!(q.pending_packets(),1);assert_eq!(q.oldest_pending_age_us(start+Duration::from_millis(20)),Some(10_000));
        q.begin_snapshot(2,start+Duration::from_millis(10));q.snapshot=Some((3,start+Duration::from_millis(15)));
        q.reliable.push_back(start+Duration::from_millis(12));assert_eq!(q.pending_packets(),3);assert_eq!(q.oldest_pending_age_us(start+Duration::from_millis(20)),Some(10_000));
        q.complete();assert_eq!(q.oldest_pending_age_us(start+Duration::from_millis(20)),Some(8_000));q.begin_reliable(start+Duration::from_millis(12));q.complete();assert_eq!(q.oldest_pending_age_us(start+Duration::from_millis(20)),Some(5_000));
    }

}
