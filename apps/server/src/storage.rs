//! Durable character storage (V5-12, plan v5 §12.3 + Appendix C).
//!
//! PostgreSQL sits behind one persistence worker task. The world threads
//! never touch the database: they submit bounded, non-blocking commands and
//! drain [`StorageEvent`] results each tick, exactly like every other
//! cross-thread seam in this server. HTTP/socket tasks may await a reply via
//! oneshot — they are the async side and join-time loads are allowed to wait.
//!
//! Identity model (plan §12.3): the browser carries a long-lived
//! `aetherfield_principal` cookie (32 random bytes; only the SHA-256 hash is
//! stored). One `principals` row per cookie and, once linked, one per OAuth
//! subject. One `characters` row per principal in P1, fenced by
//! `owner_epoch`: every join claims `owner_epoch + 1` and every durable save
//! carries the epoch it observed. A stale writer updates zero rows and gets
//! the authoritative record back instead of overwriting the live owner.
//!
//! Saves are coalesced per principal (latest record wins, flushed on a short
//! interval) so a hot tick stream can never translate into unbounded write
//! load. Writes go through `save_character` (`try_send`, world threads) or
//! await directly (HTTP side). When `AETHERFIELD_DATABASE_URL` is absent or
//! unreachable the handle runs in [`StorageMode::Disabled`]: every command is
//! a no-op and the server behaves exactly as the pre-V5-12 session-only
//! prototype, with a loud boot warning (playtests then follow the P1a
//! reset policy instead of the P1b durability gates).

use crate::auth::SessionId;
use crate::character::CharacterRecord;
use crate::cold::OpResultMsg;
use sha2::{Digest, Sha256};
use sqlx::postgres::{PgPool, PgPoolOptions};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};

/// The durable owner key. Sessions stay ephemeral (in-memory, 1h); the
/// principal cookie outlives them, and the character row hangs off the
/// principal — that is the whole V5-12 seam.
pub type PrincipalId = uuid::Uuid;

/// Where the durable identity cookie lives (auth.rs owns the session one).
pub const PRINCIPAL_COOKIE_NAME: &str = "aetherfield_principal";
/// 30-day sliding lifetime (plan v5 §12.3).
pub const PRINCIPAL_TTL_SECS: u64 = 30 * 24 * 60 * 60;

/// A character record resolved at join time and handed to the world through
/// `RoomCommand::Join`. `owner_epoch` is the fence this join claimed; the
/// world stamps every durable save with it until the fence is rejected.
#[derive(Debug, Clone)]
pub struct JoinCharacter {
    pub principal: PrincipalId,
    pub record: CharacterRecord,
    pub owner_epoch: u64,
}

/// §12.1 resume point, written alongside every coalesced save.
#[derive(Debug, Clone)]
pub struct Checkpoint {
    pub zone: String,
    pub x: f32,
    pub z: f32,
    pub hp: i32,
}

/// One append-only ledger movement carried by a [`StorageCommand::CommitOp`].
/// Item deltas reconcile against bag/pouch; exp deltas against
/// characters.base_exp (plan v5 Appendix C).
#[derive(Debug, Clone)]
pub enum LedgerEntry {
    Item { item: String, delta: i64 },
    Exp { delta: i64 },
}

/// Why a durable operation failed. The worker never panics into the world
/// threads: errors come back as values.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StorageError {
    /// The pool was built but the database refused / dropped a query.
    Unavailable,
    /// Data could not round-trip (a poisoned record blob). Never overwrites.
    Corrupt,
}

/// Results the worker pushes back to the owning world thread.
/// Large variants are fine: a few events per tick at P1 rates.
#[allow(clippy::large_enum_variant)]
#[derive(Debug, Clone)]
pub enum StorageEvent {
    OperationChecked {session:SessionId,token:u64,result:OperationLookup},
    ExchangeFinished { id: String, accepted: bool },
    ExchangeRetry { id: String },
    /// A save updated zero rows: the epoch is stale (a newer join claimed the
    /// character). `record` is the authoritative durable state — the world
    /// adopts it and stops submitting saves for the session until it re-joins
    /// and claims a fresh epoch. Never an overwrite: the live owner's state
    /// is exactly what the stale world receives.
    SaveRejected {
        session: SessionId,
        record: CharacterRecord,
        owner_epoch: u64,
    },
    /// A coalesced save committed: the world may clear its degraded flag.
    SaveAccepted { session: SessionId },
    /// A durable write failed because the database is unreachable: the world
    /// enters degraded mode and valuable cold ops answer `storage_pending`
    /// until the next success (plan §12.4 "database down").
    StorageDegraded { session: SessionId },
    /// A CommitOp transaction committed (the op is durably recorded).
    OpPersisted { session: SessionId, op_id: String },
    /// The op was already committed earlier with the same payload: the stored
    /// result is authoritative (crash-after-commit replay, §12.4 case 2).
    OpReplayed {
        session: SessionId,
        op_id: String,
        result: OpResultMsg,
    },
    /// The op_id was committed with a DIFFERENT payload: no grant.
    OpConflict { session: SessionId, op_id: String },
}

#[derive(Debug, Clone)]
pub enum OperationLookup {Fresh,Replay(OpResultMsg),Conflict,StaleOwner,Unavailable}

/// Large variants are fine at P1 command rates; revisit with AOI (P3).
#[allow(clippy::large_enum_variant)]
pub(crate) enum StorageCommand {
    LookupOperation {principal:PrincipalId,session:SessionId,token:u64,op_kind:String,op_id:String,key:String,owner_epoch:u64,events:mpsc::UnboundedSender<StorageEvent>},
    Exchange { request: Box<ExchangeCommit>, events: mpsc::UnboundedSender<StorageEvent> },
    /// Join-time claim: upsert principal + character, bump `owner_epoch`,
    /// return the durable record (the seed is used only when the row is new).
    LoadCharacter {
        principal: PrincipalId,
        seed: CharacterRecord,
        reply: oneshot::Sender<Result<JoinCharacter, StorageError>>,
    },
    /// Read-only summary (best-floor hydration). Slides `last_seen_at` so a
    /// plain page load keeps the principal warm.
    PeekCharacter {
        principal: PrincipalId,
        reply: oneshot::Sender<Option<u16>>,
    },
    /// Stamp the OAuth provider identity onto the principal (D-13/V5-12).
    /// `Adopted` means the subject already belongs to another principal and
    /// the caller must move the session onto it (account linking).
    LinkPrincipal {
        principal: PrincipalId,
        provider: String,
        subject: Option<String>,
        reply: oneshot::Sender<Result<LinkOutcome, StorageError>>,
    },
    /// Resolve (or create) the principal behind a principal-cookie hash.
    EnsurePrincipal {
        token_hash: Vec<u8>,
        reply: oneshot::Sender<Result<PrincipalId, StorageError>>,
    },
    /// Coalesced world/HTTP save. `owner_epoch: None` is the HTTP social
    /// path (friends-only update; it cannot write wallets); worlds always fence with the epoch
    /// they claimed at join. `checkpoint: None` skips the §12.1 resume-point
    /// write (the social layer does not know where the player stands).
    SaveCharacter {
        principal: PrincipalId,
        session: SessionId,
        record: CharacterRecord,
        owner_epoch: Option<u64>,
        checkpoint: Option<Checkpoint>,
        events: mpsc::UnboundedSender<StorageEvent>,
    },
    /// Tower floor milestone (pump path): monotonic max, no epoch fence.
    RecordBestFloor { principal: PrincipalId, floor: u16 },
    /// V5-13 transactional cold-op record: the op result, its request digest,
    /// ledger movements, the entitlement (claims) and the post-op record go
    /// into one transaction alongside the normalized state write.
    CommitOp {
        principal: PrincipalId,
        session: SessionId,
        op_kind: String,
        op_id: String,
        payload_digest: String,
        result: OpResultMsg,
        entitlement: Option<(String, String)>,
        ledger: Vec<LedgerEntry>,
        record: CharacterRecord,
        owner_epoch: Option<u64>,
        checkpoint: Option<Checkpoint>,
        content_revision: String,
        events: mpsc::UnboundedSender<StorageEvent>,
    },
}

/// What happened to a provider link attempt.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LinkOutcome {
    /// The subject was free; the principal now carries it.
    Linked,
    /// The subject already belongs to `PrincipalId`; the caller must adopt
    /// that principal for the session (same human, second device).
    Adopted(PrincipalId),
}

/// Clonable handle to the persistence worker.
#[derive(Clone, Debug)]
pub struct StorageHandle {
    tx: mpsc::Sender<StorageCommand>,
    mode: StorageMode,
}

#[derive(Debug, Clone)]
pub struct ExchangeCommit {
    pub id: String,
    pub principals: [PrincipalId; 2],
    pub epochs: [u64; 2],
    pub before: [CharacterRecord; 2],
    pub after: [CharacterRecord; 2],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StorageMode {
    /// No `AETHERFIELD_DATABASE_URL` (or the pool refused to form): every
    /// command is a no-op and nothing is durable.
    Disabled,
    /// The worker is running against a live pool with migrations applied.
    Live,
}

/// Flush cadence for coalesced saves. Far below the §12.1 15 s checkpoint
/// budget, well above the tick rate, so bursts collapse into one write.
const SAVE_FLUSH_INTERVAL: Duration = Duration::from_millis(1000);
/// Bounded command queue: backpressure is "skip and retry next tick", never
/// unbounded memory.
const COMMAND_BOUND: usize = 1024;
/// Pending coalesced saves cap — one entry per live character, so this only
/// overflows if the character count itself does.
const SAVE_PENDING_CAP: usize = 4096;

#[derive(Clone)]
struct PendingSave {
    session: SessionId,
    record: CharacterRecord,
    owner_epoch: Option<u64>,
    checkpoint: Option<Checkpoint>,
    events: Vec<mpsc::UnboundedSender<StorageEvent>>,
}

impl StorageHandle {
    pub fn lookup_operation(&self,principal:PrincipalId,session:SessionId,token:u64,op_kind:String,op_id:String,key:String,owner_epoch:u64,events:mpsc::UnboundedSender<StorageEvent>)->bool {
        self.is_live()&&self.tx.try_send(StorageCommand::LookupOperation{principal,session,token,op_kind,op_id,key,owner_epoch,events}).is_ok()
    }
    #[cfg(test)]
    pub(crate) fn lookup_fixture()->(Self,mpsc::Receiver<StorageCommand>){let(tx,rx)=mpsc::channel(4);(Self{tx,mode:StorageMode::Live},rx)}
    pub fn exchange(&self, request: ExchangeCommit, events: mpsc::UnboundedSender<StorageEvent>) -> bool {
        self.is_live() && self.tx.try_send(StorageCommand::Exchange { request: Box::new(request), events }).is_ok()
    }
    /// Build the disabled handle (session-only mode).
    pub fn disabled() -> Self {
        Self {
            tx: mpsc::channel(1).0,
            mode: StorageMode::Disabled,
        }
    }

    /// Connect, run embedded migrations and spawn the worker. `Err` means the
    /// URL was missing/unreachable — the caller decides to fall back to
    /// session-only mode with a loud warning (dev/test tools stay usable).
    pub async fn connect(url: &str) -> Result<Self, sqlx::Error> {
        let pool = PgPoolOptions::new()
            .max_connections(8)
            .acquire_timeout(Duration::from_secs(3))
            .connect(url)
            .await?;
        sqlx::migrate!("./migrations").run(&pool).await?;
        let (tx, rx) = mpsc::channel(COMMAND_BOUND);
        tokio::spawn(worker_loop(rx, pool));
        Ok(Self {
            tx,
            mode: StorageMode::Live,
        })
    }

    /// Read `AETHERFIELD_DATABASE_URL` and connect; `Disabled` when unset.
    pub async fn connect_from_env() -> Self {
        match std::env::var("AETHERFIELD_DATABASE_URL") {
            Ok(url) if !url.trim().is_empty() => match Self::connect(url.trim()).await {
                Ok(handle) => handle,
                Err(error) => {
                    eprintln!(
                        "durable storage unavailable ({error}); running SESSION-ONLY: \
                         progress resets on restart until the database is reachable."
                    );
                    Self::disabled()
                }
            },
            _ => Self::disabled(),
        }
    }

    pub fn mode(&self) -> StorageMode {
        self.mode
    }

    pub fn is_live(&self) -> bool {
        self.mode == StorageMode::Live
    }

    async fn send(&self, command: StorageCommand) -> Result<(), StorageError> {
        self.tx
            .send(command)
            .await
            .map_err(|_| StorageError::Unavailable)
    }

    /// Join-time character claim. The seed is stamped only when the durable
    /// row does not exist yet; the returned record is always the durable one.
    pub async fn load_character(
        &self,
        principal: PrincipalId,
        seed: CharacterRecord,
    ) -> Result<JoinCharacter, StorageError> {
        if !self.is_live() {
            return Ok(JoinCharacter {
                principal,
                record: seed,
                owner_epoch: 1,
            });
        }
        let (reply_tx, reply_rx) = oneshot::channel();
        self.send(StorageCommand::LoadCharacter {
            principal,
            seed,
            reply: reply_tx,
        })
        .await?;
        reply_rx.await.map_err(|_| StorageError::Unavailable)?
    }

    /// Best-floor hydration (`/session`): `None` when the character does not
    /// exist yet or storage is disabled.
    pub async fn peek_best_floor(&self, principal: PrincipalId) -> Option<u16> {
        if !self.is_live() {
            return None;
        }
        let (reply_tx, reply_rx) = oneshot::channel();
        self.send(StorageCommand::PeekCharacter {
            principal,
            reply: reply_tx,
        })
        .await
        .ok()?;
        reply_rx.await.ok().flatten()
    }

    /// OAuth subject link (see [`StorageCommand::LinkPrincipal`]).
    pub async fn link_principal(
        &self,
        principal: PrincipalId,
        provider: &str,
        subject: Option<&str>,
    ) -> Result<LinkOutcome, StorageError> {
        if !self.is_live() {
            return Ok(LinkOutcome::Linked);
        }
        let (reply_tx, reply_rx) = oneshot::channel();
        self.send(StorageCommand::LinkPrincipal {
            principal,
            provider: provider.to_string(),
            subject: subject.map(str::to_string),
            reply: reply_tx,
        })
        .await?;
        reply_rx.await.map_err(|_| StorageError::Unavailable)?
    }

    /// Resolve (or create) the principal behind a principal-cookie token.
    /// Only the SHA-256 hash of the 64-hex token is ever stored.
    pub async fn ensure_principal(&self, token_hex: &str) -> Result<PrincipalId, StorageError> {
        if !self.is_live() {
            // Session-only mode still needs a stable in-process key so one
            // browser cannot fork characters mid-run; derive it from the
            // token (never persisted, never durable).
            let hash = Sha256::digest(token_hex.as_bytes());
            return Ok(uuid::Uuid::from_slice(&hash[..16]).unwrap_or_default());
        }
        let hash: [u8; 32] = Sha256::digest(token_hex.as_bytes()).into();
        let (reply_tx, reply_rx) = oneshot::channel();
        self.send(StorageCommand::EnsurePrincipal {
            token_hash: hash.to_vec(),
            reply: reply_tx,
        })
        .await?;
        reply_rx.await.map_err(|_| StorageError::Unavailable)?
    }

    /// World/HTTP save submit. Non-blocking: `false` means the queue was full
    /// or closed — the caller keeps its in-memory state and retries later.
    pub fn save_character(
        &self,
        principal: PrincipalId,
        session: SessionId,
        record: CharacterRecord,
        owner_epoch: Option<u64>,
        checkpoint: Option<Checkpoint>,
        events: mpsc::UnboundedSender<StorageEvent>,
    ) -> bool {
        if !self.is_live() {
            return true; // nothing to do; session-only mode accepts everything
        }
        self.tx
            .try_send(StorageCommand::SaveCharacter {
                principal,
                session,
                record,
                owner_epoch,
                checkpoint,
                events,
            })
            .is_ok()
    }

    /// V5-13: record one cold op durably (fire-and-forget; outcomes come
    /// back as [`StorageEvent`]s on the world's event channel).
    #[allow(clippy::too_many_arguments)]
    pub fn commit_op(
        &self,
        principal: PrincipalId,
        session: SessionId,
        op_kind: String,
        op_id: String,
        payload_digest: String,
        result: OpResultMsg,
        entitlement: Option<(String, String)>,
        ledger: Vec<LedgerEntry>,
        record: CharacterRecord,
        owner_epoch: Option<u64>,
        checkpoint: Option<Checkpoint>,
        content_revision: String,
        events: &mpsc::UnboundedSender<StorageEvent>,
    ) -> bool {
        if !self.is_live() {
            return true;
        }
        self.tx
            .try_send(StorageCommand::CommitOp {
                principal,
                session,
                op_kind,
                op_id,
                payload_digest,
                result,
                entitlement,
                ledger,
                record,
                owner_epoch,
                checkpoint,
                content_revision,
                events: events.clone(),
            })
            .is_ok()
    }

    /// Tower floor milestone (monotonic max). Fire-and-forget.
    pub fn record_best_floor(&self, principal: PrincipalId, floor: u16) {
        if !self.is_live() {
            return;
        }
        let _ = self
            .tx
            .try_send(StorageCommand::RecordBestFloor { principal, floor });
    }
}

/// §12.4 crash failpoints: `AETHERFIELD_FAILPOINT=before_commit` exits the
/// process right before the transaction commits (nothing granted);
/// `after_commit_before_notify` exits right after (the result is committed
/// and must replay). Used by the crash drill; a no-op when unset.
fn failpoint(name: &str) {
    if std::env::var("AETHERFIELD_FAILPOINT").is_ok_and(|value| value == name) {
        eprintln!("[failpoint] crashing at {name}");
        std::process::exit(70);
    }
}

/// The worker: one task, sequential loads/links (they are awaited by the
/// caller) and interval-flushed coalesced saves.
async fn worker_loop(mut rx: mpsc::Receiver<StorageCommand>, pool: PgPool) {
    let mut pending: HashMap<PrincipalId, PendingSave> = HashMap::new();
    let mut flush = tokio::time::interval(SAVE_FLUSH_INTERVAL);
    flush.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    flush.tick().await; // the first tick fires immediately; skip it
    loop {
        tokio::select! {
            command = rx.recv() => {
                let Some(command) = command else { break };
                handle_command(&pool, command, &mut pending).await;
            }
            _ = flush.tick() => {
                flush_pending(&pool, &mut pending).await;
            }
        }
    }
    // Drain whatever is left on shutdown so a graceful stop loses nothing.
    flush_pending(&pool, &mut pending).await;
}

async fn handle_command(
    pool: &PgPool,
    command: StorageCommand,
    pending: &mut HashMap<PrincipalId, PendingSave>,
) {
    match command {
        StorageCommand::Exchange { request, events } => {
            // Clear older coalesced saves before the atomic pair. A world with a pending
            // exchange never submits another save until the outcome is known.
            let mut ready = true;
            for principal in request.principals {
                if let Some(save) = pending.remove(&principal) {
                    if flush_one(pool, principal, save).await.is_err() { ready = false; }
                }
            }
            let result = if ready { commit_exchange(pool, &request).await } else { Err(StorageError::Unavailable) };
            let event = match result {
                Ok(accepted) => StorageEvent::ExchangeFinished { id: request.id.clone(), accepted },
                Err(_) => StorageEvent::ExchangeRetry { id: request.id.clone() },
            };
            let _ = events.send(event);
        }
        StorageCommand::LoadCharacter {
            principal,
            seed,
            reply,
        } => {
            // A join claims a new fence. Read the latest queued checkpoint before
            // claiming it; never resurrect a pre-exchange wallet from the cache.
            if let Some(save)=pending.remove(&principal) {
                if let Err(error)=flush_one(pool,principal,save.clone()).await {
                    pending.insert(principal,save);
                    let _=reply.send(Err(error));return;
                }
            }
            let result = load_character(pool, principal, seed).await;
            let _ = reply.send(result);
        }
        StorageCommand::PeekCharacter { principal, reply } => {
            let best_floor = peek_character(pool, principal).await;
            let _ = reply.send(best_floor);
        }
        StorageCommand::LinkPrincipal {
            principal,
            provider,
            subject,
            reply,
        } => {
            let result = link_principal(pool, principal, &provider, subject).await;
            let _ = reply.send(result);
        }
        StorageCommand::EnsurePrincipal { token_hash, reply } => {
            let result = ensure_principal(pool, token_hash).await;
            let _ = reply.send(result);
        }
        StorageCommand::SaveCharacter {
            principal,
            session,
            record,
            owner_epoch,
            checkpoint,
            events,
        } => {
            if owner_epoch.is_none() {
                // HTTP social writes own only friends, never a stale wallet snapshot.
                if write_friends(pool,principal,&record.friends).await.is_err() {
                    let _=events.send(StorageEvent::StorageDegraded {session});
                }
                return;
            }
            // Coalesce per principal: a newer record replaces the older one
            // (it was built from a later state_revision) and inherits the
            // event senders, so every waiting world learns the outcome.
            match pending.get_mut(&principal) {
                Some(existing) => {
                    existing.record = record;
                    existing.owner_epoch = owner_epoch.or(existing.owner_epoch);
                    existing.checkpoint = checkpoint;
                    existing.events.push(events);
                }
                None => {
                    pending.insert(
                        principal,
                        PendingSave {
                            session,
                            record,
                            owner_epoch,
                            checkpoint,
                            events: vec![events],
                        },
                    );
                }
            }
            if pending.len() > SAVE_PENDING_CAP {
                // A character flood cannot translate into unbounded memory:
                // drop the oldest entries' buffers rather than grow forever.
                let Some(oldest) = pending.keys().next().copied() else {
                    return;
                };
                pending.remove(&oldest);
            }
        }
        StorageCommand::LookupOperation{principal,session,token,op_kind,op_id,key,owner_epoch,events} => {
            let result=tokio::time::timeout(Duration::from_secs(2),async {
                let epoch:Option<(i64,)>=sqlx::query_as("SELECT owner_epoch FROM characters WHERE principal=$1").bind(principal).fetch_optional(pool).await?;
                if epoch.is_none_or(|(e,)|u64::try_from(e).ok()!=Some(owner_epoch)){return Ok::<_,sqlx::Error>(OperationLookup::StaleOwner);}
                let row:Option<(String,serde_json::Value)>=sqlx::query_as("SELECT payload_digest,result FROM operation_results WHERE principal=$1 AND op_kind=$2 AND op_id=$3").bind(principal).bind(op_kind).bind(op_id).fetch_optional(pool).await?;
                Ok(match row{None=>OperationLookup::Fresh,Some((stored,result)) if stored==key=>serde_json::from_value(result).map(OperationLookup::Replay).unwrap_or(OperationLookup::Unavailable),Some(_)=>OperationLookup::Conflict})
            }).await;
            let result=match result{Ok(Ok(result))=>result,_=>OperationLookup::Unavailable};let _=events.send(StorageEvent::OperationChecked{session,token,result});
        }
        StorageCommand::RecordBestFloor { principal, floor } => {
            let _ = sqlx::query(
                "UPDATE characters SET best_floor = GREATEST(best_floor, $2) WHERE principal = $1",
            )
            .bind(principal)
            .bind(i32::from(floor))
            .execute(pool)
            .await;
        }
        StorageCommand::CommitOp {
            principal,
            session,
            op_kind,
            op_id,
            payload_digest,
            result,
            entitlement,
            ledger,
            record,
            owner_epoch,
            checkpoint,
            content_revision,
            events,
        } => {
            if let Err(error) = commit_op(
                pool,
                principal,
                session,
                &op_kind,
                &op_id,
                &payload_digest,
                &result,
                entitlement,
                ledger,
                record,
                owner_epoch,
                checkpoint,
                &content_revision,
                &events,
            )
            .await
            {
                eprintln!("durable commit_op failed for {principal}: {error:?}");
                let _ = events.send(StorageEvent::StorageDegraded { session });
            }
        }
    }
}

async fn flush_pending(pool: &PgPool, pending: &mut HashMap<PrincipalId, PendingSave>) {
    let drained: Vec<(PrincipalId, PendingSave)> = pending.drain().collect();
    for (principal, save) in drained {
        let session = save.session;
        let senders = save.events.clone();
        if let Err(error) = flush_one(pool, principal, save).await {
            eprintln!("durable save failed for {principal}: {error:?}");
            for events in &senders {
                let _ = events.send(StorageEvent::StorageDegraded { session });
            }
        }
    }
}

/// One coalesced save, in one transaction: the fenced character update plus
/// the §12.1 checkpoint — and, when the epoch fence rejects, the
/// authoritative record for the stale world to adopt.
async fn flush_one(
    pool: &PgPool,
    principal: PrincipalId,
    save: PendingSave,
) -> Result<(), StorageError> {
    if save.owner_epoch.is_none() {return write_friends(pool,principal,&save.record.friends).await;}
    let mut tx = pool.begin().await.map_err(|_| StorageError::Unavailable)?;
    let record_json = serde_json::to_value(&save.record).map_err(|_| StorageError::Corrupt)?;
    let updated = match save.owner_epoch {
        Some(epoch) => sqlx::query(
            "UPDATE characters
                 SET record = jsonb_set($2::jsonb,'{friends}',COALESCE(record->'friends','[]'::jsonb),true), level = $3, base_exp = $4, gold = $5, coin = $6,
                     revision = revision + 1, updated_at = now()
                 WHERE principal = $1 AND owner_epoch = $7",
        )
        .bind(principal)
        .bind(record_json)
        .bind(i32::try_from(save.record.level.max(1)).unwrap_or(1))
        .bind(i32::try_from(save.record.exp).unwrap_or(0))
        .bind(i32::try_from(save.record.gold).unwrap_or(0))
        .bind(i32::try_from(save.record.coin).unwrap_or(0))
        .bind(i64::try_from(epoch).unwrap_or(0))
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?
        .rows_affected(),
        None => {
            // HTTP social path: rare, last-writer-wins, no join fence to test.
            sqlx::query(
                "UPDATE characters
                 SET record = jsonb_set($2::jsonb,'{friends}',COALESCE(record->'friends','[]'::jsonb),true), level = $3, base_exp = $4, gold = $5, coin = $6,
                     revision = revision + 1, updated_at = now()
                 WHERE principal = $1",
            )
            .bind(principal)
            .bind(record_json)
            .bind(i32::try_from(save.record.level.max(1)).unwrap_or(1))
            .bind(i32::try_from(save.record.exp).unwrap_or(0))
            .bind(i32::try_from(save.record.gold).unwrap_or(0))
            .bind(i32::try_from(save.record.coin).unwrap_or(0))
            .execute(&mut *tx)
            .await
            .map_err(|_| StorageError::Unavailable)?
            .rows_affected()
        }
    };
    if updated == 0 && save.owner_epoch.is_some() {
        // Stale epoch: pull the authoritative row and tell the world. The
        // checkpoint is left untouched — the live owner owns the resume point.
        let authoritative: Option<(serde_json::Value, i64)> =
            sqlx::query_as("SELECT record, owner_epoch FROM characters WHERE principal = $1")
                .bind(principal)
                .fetch_optional(&mut *tx)
                .await
                .map_err(|_| StorageError::Unavailable)?;
        tx.commit().await.map_err(|_| StorageError::Unavailable)?;
        if let Some((record_json, epoch)) = authoritative {
            let record: CharacterRecord =
                serde_json::from_value(record_json).map_err(|_| StorageError::Corrupt)?;
            for events in &save.events {
                let _ = events.send(StorageEvent::SaveRejected {
                    session: save.session,
                    record: record.clone(),
                    owner_epoch: u64::try_from(epoch).unwrap_or_default(),
                });
            }
        }
        return Ok(());
    }
    write_normalized(&mut tx, principal, &save.record).await?;
    if let Some(checkpoint) = &save.checkpoint {
        sqlx::query(
            "INSERT INTO character_checkpoints (principal, zone, x, z, hp)
             VALUES ($1, $2, $3, $4, $5)
             ON CONFLICT (principal) DO UPDATE
             SET zone = $2, x = $3, z = $4, hp = $5, updated_at = now()",
        )
        .bind(principal)
        .bind(&checkpoint.zone)
        .bind(checkpoint.x)
        .bind(checkpoint.z)
        .bind(checkpoint.hp)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    }
    failpoint("before_commit");
    tx.commit().await.map_err(|_| StorageError::Unavailable)?;
    failpoint("after_commit_before_notify");
    // Recovery + degraded-clear signal for the owning world (S12.4 database
    // down): a successful flush means durable writes work again.
    for events in &save.events {
        let _ = events.send(StorageEvent::SaveAccepted {
            session: save.session,
        });
    }
    Ok(())
}

async fn load_character(
    pool: &PgPool,
    principal: PrincipalId,
    seed: CharacterRecord,
) -> Result<JoinCharacter, StorageError> {
    // The principal row is owned by `ensure_principal` (the cookie path runs
    // before any join); here we only slide its warm-window stamp.
    let mut tx = pool.begin().await.map_err(|_| StorageError::Unavailable)?;
    sqlx::query("UPDATE principals SET last_seen_at = now() WHERE id = $1")
        .bind(principal)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    let seed_json = serde_json::to_value(&seed).map_err(|_| StorageError::Corrupt)?;
    let inserted: Option<(uuid::Uuid,)> = sqlx::query_as(
        "INSERT INTO characters (principal, handle, name, level, base_exp, gold, coin, record, content_revision)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
         ON CONFLICT (principal) DO NOTHING
         RETURNING principal",
    )
    .bind(principal)
    .bind(&seed.handle)
    .bind(&seed.name)
    .bind(i32::try_from(seed.level.max(1)).unwrap_or(1))
    .bind(i32::try_from(seed.exp).unwrap_or(0))
    .bind(i32::try_from(seed.gold).unwrap_or(0))
    .bind(i32::try_from(seed.coin).unwrap_or(0))
    .bind(&seed_json)
    .bind("")
    .fetch_optional(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    let row: (i64, serde_json::Value, i32, i32, i32, i32, i32) = sqlx::query_as(
        "UPDATE characters SET owner_epoch = owner_epoch + 1, updated_at = now()
         WHERE principal = $1
         RETURNING owner_epoch, record, best_floor, gold, coin, job_level, job_exp",
    )
    .bind(principal)
    .fetch_one(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    let fresh_seed = inserted.is_some();
    let mut record = match inserted {
        Some(_) => seed,
        None => serde_json::from_value(row.1).map_err(|_| StorageError::Corrupt)?,
    };
    // The normalized tables (Appendix C) are authoritative over the blob —
    // but only for an existing character; a fresh seed has no history yet.
    if !fresh_seed {
        record.gold = u32::try_from(row.3).unwrap_or(record.gold);
        record.coin = u32::try_from(row.4).unwrap_or(record.coin);
        record.job_level = u32::try_from(row.5).unwrap_or(record.job_level).max(1);
        record.job_exp = u32::try_from(row.6).unwrap_or(record.job_exp);
        let equipment: Vec<(String, String)> =
            sqlx::query_as("SELECT slot, item FROM character_equipment WHERE principal = $1")
                .bind(principal)
                .fetch_all(&mut *tx)
                .await
                .map_err(|_| StorageError::Unavailable)?;
        if !equipment.is_empty() {
            record.equipment = equipment.into_iter().collect();
        }
    }
    let bag: Vec<(i32, String, i32)> = sqlx::query_as(
        "SELECT slot_index, item, count FROM bag_slots WHERE principal = $1 ORDER BY slot_index",
    )
    .bind(principal)
    .fetch_all(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    if !bag.is_empty() {
        record.bag = bag
            .into_iter()
            .map(|(_, item, count)| (item, u8::try_from(count).unwrap_or(1)))
            .collect();
    }
    let pouch: Vec<(String, i32)> =
        sqlx::query_as("SELECT item, count FROM material_pouch WHERE principal = $1")
            .bind(principal)
            .fetch_all(&mut *tx)
            .await
            .map_err(|_| StorageError::Unavailable)?;
    if !pouch.is_empty() {
        record.pouch = pouch
            .into_iter()
            .map(|(item, count)| (item, u32::try_from(count).unwrap_or(0)))
            .collect();
    }
    let quest: Option<(
        String,
        String,
        serde_json::Value,
        serde_json::Value,
        serde_json::Value,
    )> = sqlx::query_as(
        "SELECT quest_id, state, objectives, step_ticks, activated
             FROM quest_progress WHERE principal = $1",
    )
    .bind(principal)
    .fetch_optional(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    if let Some((quest_id, state, objectives, step_ticks, activated)) = quest {
        record.quest_id = quest_id;
        record.quest_state = state;
        if let Ok(map) = serde_json::from_value::<BTreeMap<String, u32>>(objectives) {
            record.quest_objectives = map;
        }
        if let Ok(map) = serde_json::from_value::<BTreeMap<String, u64>>(step_ticks) {
            record.quest_step_ticks = map;
        }
        if let Ok(set) = serde_json::from_value::<BTreeSet<String>>(activated) {
            record.activated_windmarks = set;
        }
    }
    // Durable op cache hydration (S12.4 case 2): a committed result replays
    // after a restart instead of granting twice.
    let ops: Vec<(String, String, String, serde_json::Value)> = sqlx::query_as(
        "SELECT op_kind, op_id, payload_digest, result FROM operation_results
         WHERE principal = $1 ORDER BY created_at DESC LIMIT 320",
    )
    .bind(principal)
    .fetch_all(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    if !ops.is_empty() {
        let mut item: VecDeque<(String, String, OpResultMsg)> = VecDeque::new();
        let mut quest: VecDeque<(String, String, OpResultMsg)> = VecDeque::new();
        let mut store: VecDeque<(String, String, OpResultMsg)> = VecDeque::new();
        let mut box_ops: VecDeque<(String, String, OpResultMsg)> = VecDeque::new();
        let mut equip: VecDeque<(String, String, OpResultMsg)> = VecDeque::new();
        for (kind, op_id, digest, result_json) in ops.into_iter().rev() {
            let Ok(result) = serde_json::from_value::<OpResultMsg>(result_json) else {
                continue;
            };
            let entry = (op_id, digest, result);
            match kind.as_str() {
                "item" => push_capped(&mut item, entry),
                "quest" => push_capped(&mut quest, entry),
                "store" => push_capped(&mut store, entry),
                "box" => push_capped(&mut box_ops, entry),
                "equip" => push_capped(&mut equip, entry),
                _ => {}
            }
        }
        record.item_operations = item;
        record.quest_operations = quest;
        record.store_operations = store;
        record.box_operations = box_ops;
        record.equip_operations = equip;
    }
    tx.commit().await.map_err(|_| StorageError::Unavailable)?;
    Ok(JoinCharacter {
        principal,
        record,
        owner_epoch: u64::try_from(row.0).unwrap_or(1),
    })
}

fn push_capped(
    cache: &mut std::collections::VecDeque<(String, String, OpResultMsg)>,
    entry: (String, String, OpResultMsg),
) {
    cache.push_back(entry);
    while cache.len() > 64 {
        cache.pop_front();
    }
}

/// Write the normalized durable state (Appendix C) for a record inside an
/// open transaction: wallet columns, bag slots, material pouch and the
/// quest-progress row. The record JSONB blob stays as the load-time fallback.
async fn write_normalized(
    tx: &mut sqlx::PgConnection,
    principal: PrincipalId,
    record: &CharacterRecord,
) -> Result<(), StorageError> {
    sqlx::query(
        "UPDATE characters SET gold = $2, coin = $3, job_level = $4, job_exp = $5 WHERE principal = $1",
    )
    .bind(principal)
    .bind(i32::try_from(record.gold).unwrap_or(0))
    .bind(i32::try_from(record.coin).unwrap_or(0))
    .bind(i32::try_from(record.job_level.max(1)).unwrap_or(1))
    .bind(i32::try_from(record.job_exp).unwrap_or(0))
    .execute(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    sqlx::query("DELETE FROM character_equipment WHERE principal = $1")
        .bind(principal)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    for (slot, item) in &record.equipment {
        sqlx::query("INSERT INTO character_equipment (principal, slot, item) VALUES ($1, $2, $3)")
            .bind(principal)
            .bind(slot)
            .bind(item)
            .execute(&mut *tx)
            .await
            .map_err(|_| StorageError::Unavailable)?;
    }
    sqlx::query("DELETE FROM bag_slots WHERE principal = $1")
        .bind(principal)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    for (slot_index, (item, count)) in record.bag.iter().enumerate() {
        sqlx::query(
            "INSERT INTO bag_slots (principal, slot_index, item, count) VALUES ($1, $2, $3, $4)",
        )
        .bind(principal)
        .bind(slot_index as i32)
        .bind(item)
        .bind(i32::from(*count))
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    }
    sqlx::query("DELETE FROM material_pouch WHERE principal = $1")
        .bind(principal)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    for (item, count) in &record.pouch {
        sqlx::query("INSERT INTO material_pouch (principal, item, count) VALUES ($1, $2, $3)")
            .bind(principal)
            .bind(item)
            .bind(i32::try_from(*count).unwrap_or(0))
            .execute(&mut *tx)
            .await
            .map_err(|_| StorageError::Unavailable)?;
    }
    if !record.quest_id.is_empty() {
        sqlx::query(
            "INSERT INTO quest_progress (principal, quest_id, state, objectives, step_ticks, activated, revision)
             VALUES ($1, $2, $3, $4, $5, $6, $7)
             ON CONFLICT (principal, quest_id) DO UPDATE
             SET state = $3, objectives = $4, step_ticks = $5, activated = $6,
                 revision = $7, updated_at = now()",
        )
        .bind(principal)
        .bind(&record.quest_id)
        .bind(&record.quest_state)
        .bind(serde_json::to_value(&record.quest_objectives).unwrap_or_default())
        .bind(serde_json::to_value(&record.quest_step_ticks).unwrap_or_default())
        .bind(serde_json::to_value(&record.activated_windmarks).unwrap_or_default())
        .bind(i32::try_from(record.quest_revision).unwrap_or(1))
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    }
    Ok(())
}

/// V5-13: one transactional cold-op record — dedupe, ledger, entitlement,
/// normalized state, fenced character row and the outbox entry (§12.4).
#[allow(clippy::too_many_arguments)]
async fn write_friends(pool:&PgPool,principal:PrincipalId,friends:&[String])->Result<(),StorageError> {
    sqlx::query("UPDATE characters SET record=jsonb_set(record,'{friends}',$2::jsonb,true),updated_at=now() WHERE principal=$1")
        .bind(principal).bind(serde_json::to_value(friends).map_err(|_|StorageError::Corrupt)?)
        .execute(pool).await.map_err(|_|StorageError::Unavailable)?;
    Ok(())
}

async fn commit_exchange(pool: &PgPool, request: &ExchangeCommit) -> Result<bool, StorageError> {
    if request.principals[0] == request.principals[1] { return Ok(false); }
    let mut tx = pool.begin().await.map_err(|_| StorageError::Unavailable)?;
    sqlx::query("SET LOCAL statement_timeout = '3000ms'").execute(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
    // Stable ordering prevents opposite-direction trades from deadlocking.
    let mut order = [0,1]; order.sort_by_key(|i| request.principals[*i]);
    for i in order {
        let epoch: Option<(i64,)> = sqlx::query_as("SELECT owner_epoch FROM characters WHERE principal = $1 FOR UPDATE")
            .bind(request.principals[i]).fetch_optional(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
        if epoch.is_none() { return Ok(false); }
    }
    let payload = serde_json::to_value((&request.before,&request.after,&request.epochs)).map_err(|_| StorageError::Corrupt)?;
    let existing: Option<(serde_json::Value,serde_json::Value)> = sqlx::query_as("SELECT principals,payload FROM player_exchanges WHERE id = $1")
        .bind(&request.id).fetch_optional(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
    let principals = serde_json::json!(request.principals);
    if let Some((p,stored)) = existing { return Ok(p == principals && stored == payload); }
    for i in order {
        let row: (i64,serde_json::Value) = sqlx::query_as("SELECT owner_epoch,record FROM characters WHERE principal = $1")
            .bind(request.principals[i]).fetch_one(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
        let current: CharacterRecord = serde_json::from_value(row.1).map_err(|_| StorageError::Corrupt)?;
        if row.0 != request.epochs[i] as i64 || current.gold != request.before[i].gold || current.bag != request.before[i].bag || current.equipment != request.before[i].equipment { return Ok(false); }
    }
    for i in order {
        let record = &request.after[i];
        write_normalized(&mut tx,request.principals[i],record).await?;
        sqlx::query("UPDATE characters SET record = jsonb_set($2::jsonb,'{friends}',COALESCE(record->'friends','[]'::jsonb),true), level = $3, base_exp = $4, revision = revision + 1, updated_at = now() WHERE principal = $1")
            .bind(request.principals[i]).bind(serde_json::to_value(record).map_err(|_| StorageError::Corrupt)?)
            .bind(i32::try_from(record.level.max(1)).map_err(|_|StorageError::Corrupt)?).bind(i32::try_from(record.exp).map_err(|_|StorageError::Corrupt)?).execute(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
        let ids: BTreeSet<_> = request.before[i].bag.keys().chain(record.bag.keys()).collect();
        for item in ids {
            let delta = i32::from(record.bag.get(item).copied().unwrap_or(0)) - i32::from(request.before[i].bag.get(item).copied().unwrap_or(0));
            if delta != 0 {
                sqlx::query("INSERT INTO item_ledger (principal,op_id,item,delta,reason) VALUES ($1,$2,$3,$4,'player_trade')")
                    .bind(request.principals[i]).bind(&request.id).bind(item).bind(delta).execute(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
            }
        }
        sqlx::query("INSERT INTO outbox (principal,op_id,kind,payload) VALUES ($1,$2,'player_trade',$3)")
            .bind(request.principals[i]).bind(&request.id).bind(serde_json::json!({"peer":request.principals[1-i],"gold_delta":i64::from(record.gold)-i64::from(request.before[i].gold)}))
            .execute(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
    }
    sqlx::query("INSERT INTO player_exchanges (id,principals,payload) VALUES ($1,$2,$3)")
        .bind(&request.id).bind(principals).bind(payload).execute(&mut *tx).await.map_err(|_| StorageError::Unavailable)?;
    tx.commit().await.map_err(|_| StorageError::Unavailable)?;
    Ok(true)
}

async fn commit_op(
    pool: &PgPool,
    principal: PrincipalId,
    session: SessionId,
    op_kind: &str,
    op_id: &str,
    payload_digest: &str,
    result: &OpResultMsg,
    entitlement: Option<(String, String)>,
    ledger: Vec<LedgerEntry>,
    record: CharacterRecord,
    owner_epoch: Option<u64>,
    checkpoint: Option<Checkpoint>,
    content_revision: &str,
    events: &mpsc::UnboundedSender<StorageEvent>,
) -> Result<(), StorageError> {
    let mut tx = pool.begin().await.map_err(|_| StorageError::Unavailable)?;
    let existing: Option<(String, serde_json::Value)> = sqlx::query_as(
        "SELECT payload_digest, result FROM operation_results
         WHERE principal = $1 AND op_kind = $2 AND op_id = $3
         FOR UPDATE",
    )
    .bind(principal)
    .bind(op_kind)
    .bind(op_id)
    .fetch_optional(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    if let Some((stored_digest, stored_result)) = existing {
        tx.commit().await.map_err(|_| StorageError::Unavailable)?;
        if stored_digest == payload_digest {
            let replayed: OpResultMsg =
                serde_json::from_value(stored_result).map_err(|_| StorageError::Corrupt)?;
            let _ = events.send(StorageEvent::OpReplayed {
                session,
                op_id: op_id.to_string(),
                result: replayed,
            });
        } else {
            let _ = events.send(StorageEvent::OpConflict {
                session,
                op_id: op_id.to_string(),
            });
        }
        return Ok(());
    }
    let result_json = serde_json::to_value(result).map_err(|_| StorageError::Corrupt)?;
    sqlx::query(
        "INSERT INTO operation_results (principal, op_kind, op_id, payload_digest, result, content_revision)
         VALUES ($1, $2, $3, $4, $5, $6)",
    )
    .bind(principal)
    .bind(op_kind)
    .bind(op_id)
    .bind(payload_digest)
    .bind(result_json)
    .bind(content_revision)
    .execute(&mut *tx)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    for entry in &ledger {
        match entry {
            LedgerEntry::Item { item, delta } => {
                sqlx::query(
                    "INSERT INTO item_ledger (principal, op_id, item, delta, reason, content_revision)
                     VALUES ($1, $2, $3, $4, $5, $6)",
                )
                .bind(principal)
                .bind(op_id)
                .bind(item)
                .bind(i32::try_from(*delta).unwrap_or(0))
                .bind(op_kind)
                .bind(content_revision)
                .execute(&mut *tx)
                .await
                .map_err(|_| StorageError::Unavailable)?;
            }
            LedgerEntry::Exp { delta } => {
                sqlx::query(
                    "INSERT INTO exp_ledger (principal, op_id, delta, reason, content_revision)
                     VALUES ($1, $2, $3, $4, $5)",
                )
                .bind(principal)
                .bind(op_id)
                .bind(i32::try_from(*delta).unwrap_or(0))
                .bind(op_kind)
                .bind(content_revision)
                .execute(&mut *tx)
                .await
                .map_err(|_| StorageError::Unavailable)?;
            }
        }
    }
    if let Some((entitlement_id, cycle_id)) = &entitlement {
        sqlx::query(
            "INSERT INTO reward_claims (principal, entitlement_id, cycle_id, op_id, content_revision)
             VALUES ($1, $2, $3, $4, $5)
             ON CONFLICT (principal, entitlement_id, cycle_id) DO NOTHING",
        )
        .bind(principal)
        .bind(entitlement_id)
        .bind(cycle_id)
        .bind(op_id)
        .bind(content_revision)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    }
    sqlx::query("INSERT INTO content_versions (content_hash) VALUES ($1) ON CONFLICT DO NOTHING")
        .bind(content_revision)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    write_normalized(&mut tx, principal, &record).await?;
    let record_json = serde_json::to_value(&record).map_err(|_| StorageError::Corrupt)?;
    let updated = match owner_epoch {
        Some(epoch) => sqlx::query(
            "UPDATE characters
                 SET record = jsonb_set($2::jsonb,'{friends}',COALESCE(record->'friends','[]'::jsonb),true), level = $3, base_exp = $4, revision = revision + 1,
                     updated_at = now()
                 WHERE principal = $1 AND owner_epoch = $5",
        )
        .bind(principal)
        .bind(record_json)
        .bind(i32::try_from(record.level.max(1)).unwrap_or(1))
        .bind(i32::try_from(record.exp).unwrap_or(0))
        .bind(i64::try_from(epoch).unwrap_or(0))
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?
        .rows_affected(),
        None => sqlx::query(
            "UPDATE characters
                 SET record = jsonb_set($2::jsonb,'{friends}',COALESCE(record->'friends','[]'::jsonb),true), level = $3, base_exp = $4, revision = revision + 1,
                     updated_at = now()
                 WHERE principal = $1",
        )
        .bind(principal)
        .bind(record_json)
        .bind(i32::try_from(record.level.max(1)).unwrap_or(1))
        .bind(i32::try_from(record.exp).unwrap_or(0))
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?
        .rows_affected(),
    };
    if updated == 0 && owner_epoch.is_some() {
        // Stale fence: the commit must NOT land. The world adopts the
        // authoritative record (via SaveRejected) and the op re-runs there.
        tx.rollback().await.map_err(|_| StorageError::Unavailable)?;
        let _ = events.send(StorageEvent::SaveRejected {
            session,
            record: record.clone(),
            owner_epoch: 0,
        });
        return Ok(());
    }
    sqlx::query("INSERT INTO outbox (principal, op_id, kind, payload) VALUES ($1, $2, $3, $4)")
        .bind(principal)
        .bind(op_id)
        .bind(op_kind)
        .bind(serde_json::json!({ "status": result.status, "reason": result.reason }))
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    if let Some(checkpoint) = &checkpoint {
        sqlx::query(
            "INSERT INTO character_checkpoints (principal, zone, x, z, hp)
             VALUES ($1, $2, $3, $4, $5)
             ON CONFLICT (principal) DO UPDATE
             SET zone = $2, x = $3, z = $4, hp = $5, updated_at = now()",
        )
        .bind(principal)
        .bind(&checkpoint.zone)
        .bind(checkpoint.x)
        .bind(checkpoint.z)
        .bind(checkpoint.hp)
        .execute(&mut *tx)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    }
    failpoint("before_commit");
    tx.commit().await.map_err(|_| StorageError::Unavailable)?;
    failpoint("after_commit_before_notify");
    let _ = events.send(StorageEvent::OpPersisted {
        session,
        op_id: op_id.to_string(),
    });
    let _ = events.send(StorageEvent::SaveAccepted { session });
    Ok(())
}

async fn peek_character(pool: &PgPool, principal: PrincipalId) -> Option<u16> {
    // Slide the principal warm-window; a page load counts as presence.
    let _ = sqlx::query("UPDATE principals SET last_seen_at = now() WHERE id = $1")
        .bind(principal)
        .execute(pool)
        .await;
    let row: Option<(i32,)> =
        sqlx::query_as("SELECT best_floor FROM characters WHERE principal = $1")
            .bind(principal)
            .fetch_optional(pool)
            .await
            .ok()?;
    row.map(|(floor,)| u16::try_from(floor).unwrap_or(0))
}

async fn link_principal(
    pool: &PgPool,
    principal: PrincipalId,
    provider: &str,
    subject: Option<String>,
) -> Result<LinkOutcome, StorageError> {
    let Some(subject) = subject.filter(|subject| !subject.is_empty()) else {
        // Nothing to link (guest refresh): keep the principal as-is.
        return Ok(LinkOutcome::Linked);
    };
    let owned_by: Option<(uuid::Uuid,)> = sqlx::query_as(
        "SELECT id FROM principals WHERE provider = $1 AND subject = $2 AND id <> $3 LIMIT 1",
    )
    .bind(provider)
    .bind(&subject)
    .bind(principal)
    .fetch_optional(pool)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    if let Some((other,)) = owned_by {
        return Ok(LinkOutcome::Adopted(other));
    }
    sqlx::query("UPDATE principals SET provider = $2, subject = $3 WHERE id = $1")
        .bind(principal)
        .bind(provider)
        .bind(&subject)
        .execute(pool)
        .await
        .map_err(|_| StorageError::Unavailable)?;
    Ok(LinkOutcome::Linked)
}

async fn ensure_principal(pool: &PgPool, token_hash: Vec<u8>) -> Result<PrincipalId, StorageError> {
    if let Some((id,)) =
        sqlx::query_as::<_, (uuid::Uuid,)>("SELECT id FROM principals WHERE token_hash = $1")
            .bind(&token_hash)
            .fetch_optional(pool)
            .await
            .map_err(|_| StorageError::Unavailable)?
    {
        let _ = sqlx::query("UPDATE principals SET last_seen_at = now() WHERE id = $1")
            .bind(id)
            .execute(pool)
            .await;
        return Ok(id);
    }
    let id = uuid::Uuid::new_v4();
    let inserted = sqlx::query(
        "INSERT INTO principals (id, token_hash) VALUES ($1, $2)
         ON CONFLICT (token_hash) DO NOTHING",
    )
    .bind(id)
    .bind(&token_hash)
    .execute(pool)
    .await
    .map_err(|_| StorageError::Unavailable)?;
    if inserted.rows_affected() == 0 {
        // A concurrent creator won the unique hash; adopt theirs.
        let (id,): (uuid::Uuid,) =
            sqlx::query_as("SELECT id FROM principals WHERE token_hash = $1")
                .bind(&token_hash)
                .fetch_one(pool)
                .await
                .map_err(|_| StorageError::Unavailable)?;
        return Ok(id);
    }
    Ok(id)
}

/// Database-backed tests. They run only when a test database is provided so
/// the default `cargo test` stays green on machines without PostgreSQL:
/// `AETHERFIELD_TEST_DATABASE_URL=postgres://... cargo test -- --ignored`
#[cfg(test)]
mod tests {
    use super::*;
    use crate::character::identity_for_principal;

    async fn pool() -> Option<PgPool> {
        let url = std::env::var("AETHERFIELD_TEST_DATABASE_URL").ok()?;
        let pool = PgPoolOptions::new()
            .max_connections(2)
            .connect(&url)
            .await
            .expect("test database connects");
        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("migrate");
        Some(pool)
    }

    /// The principal row is normally created by the cookie path
    /// (`ensure_principal`); tests insert it directly.
    async fn seed_principal(pool: &PgPool, principal: PrincipalId) {
        sqlx::query("INSERT INTO principals (id, token_hash) VALUES ($1, $2)")
            .bind(principal)
            .bind(principal.as_bytes())
            .execute(pool)
            .await
            .expect("principal row created");
    }

    #[tokio::test]
    #[ignore = "needs AETHERFIELD_TEST_DATABASE_URL"]
    async fn exchange_is_atomic_replayed_fenced_and_rolls_back_both_on_failure() {
        let Some(pool)=pool().await else{return;};
        let principals=[uuid::Uuid::new_v4(),uuid::Uuid::new_v4()];
        let mut records=Vec::new();let mut epochs=Vec::new();
        for (i,principal) in principals.iter().enumerate() {
            seed_principal(&pool,*principal).await;
            let mut seed=seed_for(*principal);seed.bag.insert("trail_potion".into(),3);
            let loaded=load_character(&pool,*principal,seed).await.unwrap();
            flush_one(&pool,*principal,PendingSave{session:[i as u8;32],record:loaded.record.clone(),owner_epoch:Some(loaded.owner_epoch),checkpoint:None,events:Vec::new()}).await.unwrap();
            epochs.push(loaded.owner_epoch);records.push(loaded.record);
        }
        let before=[records[0].clone(),records[1].clone()];let mut after=before.clone();
        after[0].gold-=20;after[1].gold+=20;after[0].bag.insert("trail_potion".into(),2);after[1].bag.insert("trail_potion".into(),4);
        let request=ExchangeCommit{id:uuid::Uuid::new_v4().to_string(),principals,epochs:[epochs[0],epochs[1]],before,after};
        assert!(commit_exchange(&pool,&request).await.unwrap());
        assert!(commit_exchange(&pool,&request).await.unwrap(),"retry returns the receipt without applying twice");
        for (i,p) in principals.iter().enumerate() {let row:(i32,)=sqlx::query_as("SELECT gold FROM characters WHERE principal=$1").bind(p).fetch_one(&pool).await.unwrap();assert_eq!(row.0,if i==0{230}else{270});}
        let (count,):(i64,)=sqlx::query_as("SELECT count(*) FROM item_ledger WHERE op_id=$1").bind(&request.id).fetch_one(&pool).await.unwrap();assert_eq!(count,2);
        let mut stale_social=request.before[0].clone();stale_social.friends=vec!["aabbccdd".into()];
        flush_one(&pool,principals[0],PendingSave{session:[1;32],record:stale_social,owner_epoch:None,checkpoint:None,events:Vec::new()}).await.unwrap();
        let (gold,record):(i32,serde_json::Value)=sqlx::query_as("SELECT gold,record FROM characters WHERE principal=$1").bind(principals[0]).fetch_one(&pool).await.unwrap();
        assert_eq!(gold,230);assert_eq!(record["bag"]["trail_potion"],2);assert_eq!(record["friends"][0],"aabbccdd");

        let mut conflict=request.clone();conflict.after[0].gold=1;assert!(!commit_exchange(&pool,&conflict).await.unwrap());
        // Constraint failure on either participant rolls back BOTH wallets and the receipt.
        let mut bad=request.clone();bad.id=uuid::Uuid::new_v4().to_string();bad.before=request.after.clone();bad.after=bad.before.clone();bad.after[0].gold-=10;bad.after[1].gold+=10;
        bad.after[1].bag=(0..13).map(|i|(format!("invalid_{i}"),1)).collect();
        assert!(commit_exchange(&pool,&bad).await.is_err());
        let (gold,):(i32,)=sqlx::query_as("SELECT gold FROM characters WHERE principal=$1").bind(principals[0]).fetch_one(&pool).await.unwrap();assert_eq!(gold,230);
        let mut stale=request.clone();stale.id=uuid::Uuid::new_v4().to_string();stale.before=request.after.clone();
        load_character(&pool,principals[0],seed_for(principals[0])).await.unwrap();
        assert!(!commit_exchange(&pool,&stale).await.unwrap(),"new owner fence rejects the exchange");
    }

    #[tokio::test]
    #[ignore = "needs AETHERFIELD_TEST_DATABASE_URL"]
    async fn worker_join_flushes_queued_wallet_and_social_never_replaces_it() {
        let url=std::env::var("AETHERFIELD_TEST_DATABASE_URL").expect("explicit test database");
        let handle=StorageHandle::connect(&url).await.unwrap();
        let principal=handle.ensure_principal(&format!("{}{}",uuid::Uuid::new_v4().simple(),uuid::Uuid::new_v4().simple())).await.unwrap();
        let first=handle.load_character(principal,seed_for(principal)).await.unwrap();
        let (events,_rx)=mpsc::unbounded_channel();
        let mut updated=first.record.clone();updated.gold=600;
        assert!(handle.save_character(principal,[5;32],updated,Some(first.owner_epoch),None,events.clone()));
        let mut old_social=first.record;old_social.gold=1;old_social.friends=vec!["11223344".into()];
        assert!(handle.save_character(principal,[5;32],old_social,None,None,events));
        let joined=handle.load_character(principal,seed_for(principal)).await.unwrap();
        assert_eq!(joined.record.gold,600);assert_eq!(joined.record.friends,vec!["11223344"]);
    }

    fn seed_for(principal: PrincipalId) -> CharacterRecord {
        let (handle, name) = identity_for_principal(principal);
        CharacterRecord {
            gold: 250,
            state_revision: 1,
            handle,
            name,
            ..CharacterRecord::default()
        }
    }

    #[tokio::test]
    #[ignore = "needs AETHERFIELD_TEST_DATABASE_URL"]
    async fn load_claims_a_monotonic_epoch_and_round_trips_the_record() {
        let Some(pool) = pool().await else { return };
        let principal = uuid::Uuid::new_v4();
        seed_principal(&pool, principal).await;
        let mut first = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("first load");
        assert_eq!(first.owner_epoch, 1);
        assert_eq!(first.record.gold, 250, "fresh seed is the record");

        first.record.gold = 500;
        let save = PendingSave {
            session: [1; 32],
            record: first.record.clone(),
            owner_epoch: Some(first.owner_epoch),
            checkpoint: Some(Checkpoint {
                zone: "zone-1".into(),
                x: 1.0,
                z: 2.0,
                hp: 80,
            }),
            events: Vec::new(),
        };
        flush_one(&pool, principal, save)
            .await
            .expect("save commits");

        let second = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("second load");
        assert_eq!(second.owner_epoch, 2, "epoch increments per join");
        assert_eq!(second.record.gold, 500, "durable record restored");
    }

    #[tokio::test]
    #[ignore = "needs AETHERFIELD_TEST_DATABASE_URL"]
    async fn a_stale_epoch_is_rejected_with_the_authoritative_record() {
        let Some(pool) = pool().await else { return };
        let principal = uuid::Uuid::new_v4();
        seed_principal(&pool, principal).await;
        let first = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("load");
        let _second = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("second join claims epoch 2");

        let (events_tx, mut events_rx) = mpsc::unbounded_channel();
        let stale = PendingSave {
            session: [2; 32],
            record: {
                let mut record = first.record.clone();
                record.gold = 999;
                record
            },
            owner_epoch: Some(first.owner_epoch),
            checkpoint: Some(Checkpoint {
                zone: "zone-1".into(),
                x: 0.0,
                z: 0.0,
                hp: 100,
            }),
            events: vec![events_tx],
        };
        flush_one(&pool, principal, stale)
            .await
            .expect("save handled");

        match events_rx.recv().await {
            Some(StorageEvent::SaveRejected {
                record,
                owner_epoch,
                ..
            }) => {
                assert_eq!(owner_epoch, 2);
                assert_ne!(record.gold, 999, "the stale write must not land");
            }
            other => panic!("expected SaveRejected, got {other:?}"),
        }
    }

    fn store_result(op_id: &str) -> crate::cold::OpResultMsg {
        crate::cold::OpResultMsg {
            t: "op_result".to_string(),
            op_id: op_id.to_string(),
            status: "accepted".to_string(),
            reason: "none".to_string(),
            ends_at_ms: 0,
            grants: vec![crate::cold::GrantEntry {
                def: "trail_potion".to_string(),
                count: 1,
            }],
        }
    }

    #[tokio::test]
    #[ignore = "needs AETHERFIELD_TEST_DATABASE_URL"]
    async fn commit_op_records_the_ledger_and_replays_the_same_payload() {
        let Some(pool) = pool().await else { return };
        let principal = uuid::Uuid::new_v4();
        seed_principal(&pool, principal).await;
        let loaded = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("load");
        let mut record = loaded.record.clone();
        record.gold = 225;
        record.bag.insert("trail_potion".to_string(), 4);

        let (events_tx, mut events_rx) = mpsc::unbounded_channel();
        commit_op(
            &pool,
            principal,
            [1; 32],
            "store",
            "op-1",
            "digest-1",
            &store_result("op-1"),
            None,
            vec![LedgerEntry::Item {
                item: "trail_potion".to_string(),
                delta: 1,
            }],
            record.clone(),
            Some(loaded.owner_epoch),
            None,
            "016b7b857bbf490b",
            &events_tx,
        )
        .await
        .expect("first commit");
        match events_rx.recv().await {
            Some(StorageEvent::OpPersisted { op_id, .. }) => assert_eq!(op_id, "op-1"),
            other => panic!("expected OpPersisted, got {other:?}"),
        }
        // Drain the trailing SaveAccepted from the same commit.
        match events_rx.recv().await {
            Some(StorageEvent::SaveAccepted { .. }) => {}
            other => panic!("expected SaveAccepted, got {other:?}"),
        }

        // Same op_id + same payload: the stored result replays verbatim and
        // no second grant lands (§12.4 case 2/3).
        let mut replay_record = record.clone();
        replay_record.gold = 200;
        commit_op(
            &pool,
            principal,
            [1; 32],
            "store",
            "op-1",
            "digest-1",
            &store_result("op-1"),
            None,
            vec![LedgerEntry::Item {
                item: "trail_potion".to_string(),
                delta: 1,
            }],
            replay_record,
            Some(loaded.owner_epoch),
            None,
            "016b7b857bbf490b",
            &events_tx,
        )
        .await
        .expect("replay commit");
        match events_rx.recv().await {
            Some(StorageEvent::OpReplayed { result, .. }) => {
                assert_eq!(result.op_id, "op-1");
                assert_eq!(result.status, "accepted");
            }
            other => panic!("expected OpReplayed, got {other:?}"),
        }

        // Same op_id with a CHANGED payload conflicts: no grant (§12.4 case 4).
        commit_op(
            &pool,
            principal,
            [1; 32],
            "store",
            "op-1",
            "digest-2",
            &store_result("op-1"),
            None,
            Vec::new(),
            record.clone(),
            Some(loaded.owner_epoch),
            None,
            "016b7b857bbf490b",
            &events_tx,
        )
        .await
        .expect("conflict commit");
        match events_rx.recv().await {
            Some(StorageEvent::OpConflict { op_id, .. }) => assert_eq!(op_id, "op-1"),
            other => panic!("expected OpConflict, got {other:?}"),
        }

        // Ledger movements: exactly one +1 for trail_potion (the replay and
        // the conflict wrote nothing).
        let (delta,): (i64,) = sqlx::query_as(
            "SELECT COALESCE(SUM(delta), 0) FROM item_ledger
             WHERE principal = $1 AND item = 'trail_potion'",
        )
        .bind(principal)
        .fetch_one(&pool)
        .await
        .expect("ledger sum");
        assert_eq!(delta, 1, "ledger must count the grant exactly once");

        // Outbox carried exactly one event for the op.
        let (outbox_rows,): (i64,) =
            sqlx::query_as("SELECT count(*) FROM outbox WHERE principal = $1 AND op_id = 'op-1'")
                .bind(principal)
                .fetch_one(&pool)
                .await
                .expect("outbox count");
        assert_eq!(outbox_rows, 1);

        // Durable wallet state matches the record (normalized columns).
        let (gold,): (i32,) = sqlx::query_as("SELECT gold FROM characters WHERE principal = $1")
            .bind(principal)
            .fetch_one(&pool)
            .await
            .expect("wallet column");
        assert_eq!(gold, 225, "replay/conflict must not touch the wallet");
    }

    #[tokio::test]
    #[ignore = "needs AETHERFIELD_TEST_DATABASE_URL"]
    async fn commit_op_never_lands_on_a_stale_epoch() {
        let Some(pool) = pool().await else { return };
        let principal = uuid::Uuid::new_v4();
        seed_principal(&pool, principal).await;
        let first = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("first load");
        let _second = load_character(&pool, principal, seed_for(principal))
            .await
            .expect("second load claims a newer epoch");

        let (events_tx, mut events_rx) = mpsc::unbounded_channel();
        commit_op(
            &pool,
            principal,
            [2; 32],
            "store",
            "stale-op",
            "digest",
            &store_result("stale-op"),
            None,
            Vec::new(),
            first.record.clone(),
            Some(first.owner_epoch), // stale: the second join claimed newer
            None,
            "016b7b857bbf490b",
            &events_tx,
        )
        .await
        .expect("handled");
        match events_rx.recv().await {
            Some(StorageEvent::SaveRejected { .. }) => {}
            other => panic!("expected SaveRejected for the stale fence, got {other:?}"),
        }
        // The op was NOT recorded: a retry under the rightful owner succeeds.
        let (rows,): (i64,) = sqlx::query_as(
            "SELECT count(*) FROM operation_results WHERE principal = $1 AND op_id = 'stale-op'",
        )
        .bind(principal)
        .fetch_one(&pool)
        .await
        .expect("op results count");
        assert_eq!(rows, 0, "a stale-epoch op must not be recorded");
    }
}
