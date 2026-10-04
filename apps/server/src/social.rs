//! Cross-instance social layer (P1): presence, friends and groups.
//!
//! [`SocialHub`] is one process-wide `Arc` shared by `main.rs` (HTTP endpoints
//! and the WebSocket presence lifecycle) and every room/tower world thread
//! (the `chat`/`friend_*`/`group_*` cold dispatch). All state is
//! session-scoped and in-memory; friend lists persist across instance
//! switches through the shared [`CharacterStore`] (the same seam as the
//! wallet), while presence and groups die with the process.
//!
//! Locking discipline: the hub's `std::sync::Mutex` is held only for the
//! duration of one bounded operation and never across an `.await`; pushes to
//! rooms go through `RoomCommand::NotifySession` via `try_send`, so a world
//! thread calling into the hub (group chat, friend ops) can never block on
//! another room's inbox.

use crate::auth::SessionId;
use crate::chat_moderation::{ChatIdentity, ChatLane, ChatModeration, ChatRejection, PreparedChat};
use crate::character::{CharacterRecord, MAX_FRIENDS, SharedCharacterStore, identity_for_session};
use crate::cold::{ChatBroadcastMsg, FriendsMsg, GroupStateMsg, SocialMemberMsg};
use crate::room::{RoomCommand, RoomHandle};
use crate::wire;
use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};

/// Group size cap (party-like, P1).
pub const MAX_GROUP_MEMBERS: usize = 4;
/// Live group cap: keeps the group store bounded no matter how many codes are
/// created and abandoned within the process lifetime.
pub const MAX_GROUPS: usize = 64;
/// Presence hard cap. Sessions are already capped at `auth::MAX_SESSIONS`
/// (256) and presence is keyed by session, so this is pure defense.
pub const MAX_PRESENCE: usize = 512;
/// Handle → name directory cap (FIFO eviction). Every handle in a friend list
/// or group was seen online at least once, so entries are only lost after
/// thousands of distinct sessions.
pub const MAX_NAME_DIRECTORY: usize = 4096;

/// Where a session is connected right now (from the join routing result).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PresenceKind {
    Normal { channel: u8 },
    Tower,
}

/// One live presence record. `room` is the handle of the instance the
/// session's socket joined, so hub pushes can reach the player without a
/// routing lookup.
struct PresenceEntry {
    chat_identity: ChatIdentity,
    device: crate::community::Device,
    kind: PresenceKind,
    handle: String,
    name: String,
    room: RoomHandle,
    /// Socket-lifetime token: a takeover inserts a fresh entry, and the old
    /// socket's teardown must not remove the new one.
    token: u64,
}

/// One presence read for `GET /presence` (owned snapshot; no locks held).
#[derive(Debug, Clone)]
pub struct PresenceSnapshot {
    pub session: SessionId,
    pub kind: PresenceKind,
    pub handle: String,
    pub name: String,
}

/// A group code view for `GET /group` and join responses.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct GroupView {
    pub code: String,
    pub members: Vec<SocialMemberMsg>,
}

struct Group {
    leader: SessionId,
    /// Insertion order (leader first), capped at [`MAX_GROUP_MEMBERS`].
    members: Vec<SessionId>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FriendError {
    /// No live presence record matches the handle (offline targets cannot be
    /// added in P1).
    UnknownPlayer,
    /// The handle is the requester's own.
    SelfAdd,
    /// The requester's list is at [`MAX_FRIENDS`].
    Full,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GroupError {
    ChatRejected(ChatRejection),
    AlreadyInGroup,
    UnknownGroup,
    /// The group already holds [`MAX_GROUP_MEMBERS`].
    Full,
    /// The process is at [`MAX_GROUPS`].
    StoreFull,
    NotInGroup,
    EntropyUnavailable,
}

impl FriendError {
    /// Notice key suffix for the cold path (`friends_<reason>`).
    pub fn reason(self) -> &'static str {
        match self {
            Self::UnknownPlayer => "unknown_player",
            Self::SelfAdd => "self_add",
            Self::Full => "friends_full",
        }
    }
}

impl GroupError {
    /// Notice key suffix for the cold path (`group_<reason>`).
    pub fn reason(self) -> &'static str {
        match self {
            Self::ChatRejected(reason) => reason.key(),
            Self::AlreadyInGroup => "already_in_group",
            Self::UnknownGroup => "unknown_group",
            Self::Full => "group_full",
            Self::StoreFull => "groups_full",
            Self::NotInGroup => "not_in_group",
            Self::EntropyUnavailable => "entropy_unavailable",
        }
    }
}

#[derive(Default)]
struct SocialInner {
    presence: HashMap<SessionId, PresenceEntry>,
    megaphone_limits: HashMap<SessionId,std::time::Instant>,
    groups: HashMap<String, Group>,
    session_group: HashMap<SessionId, String>,
    /// Handle → display name directory for offline roster entries.
    names: HashMap<String, String>,
    names_order: VecDeque<String>,
}

/// The shared social state. Cheap to clone (an `Arc`); every method takes a
/// bounded critical section on one mutex.
pub struct SocialHub {
    chat_moderation: ChatModeration,
    inner: Mutex<SocialInner>,
    store: SharedCharacterStore,
    /// First-join character seed used when a friend write arrives before the
    /// session's first world join (so the wallet is not silently zeroed).
    seed_template: CharacterRecord,
    tokens: AtomicU64,
}

/// Removes the session's presence when the socket task ends — but only if the
/// session was not taken over meanwhile (token guard).
pub struct PresenceGuard {
    hub: Arc<SocialHub>,
    session: SessionId,
    token: u64,
}

impl std::fmt::Debug for PresenceGuard {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("PresenceGuard")
            .field("session", &self.session)
            .field("token", &self.token)
            .finish()
    }
}

impl Drop for PresenceGuard {
    fn drop(&mut self) {
        self.hub.leave(self.session, self.token);
    }
}

impl SocialHub {
    pub fn set_device(&self, session: SessionId, device: crate::community::Device) {
        let (handle,group,online) = {
            let mut inner=self.lock();
            let Some(entry)=inner.presence.get_mut(&session) else{return;};
            if entry.device==device {return;}
            entry.device=device;let handle=entry.handle.clone();
            (handle,inner.session_group.get(&session).cloned(),inner.presence.keys().copied().collect::<Vec<_>>())
        };
        if let Some(code)=group {self.push_group_state(&code);}
        for owner in online {if self.store.friends_of(owner).contains(&handle) {let entries=self.friends_of(owner);self.push_friends(owner,&entries);}}
    }
    /// Server-wide announcement, bounded by presence and one per sender per 30 seconds.
    pub fn megaphone(&self, session: SessionId, text: &str) -> Result<usize, &'static str> {
        let text = self.prepare_chat(session, ChatLane::Megaphone, text).map_err(ChatRejection::key)?;
        let (message, recipients) = {
            let mut inner = self.lock();
            let now = std::time::Instant::now();
            inner.megaphone_limits.retain(|_,until| *until>now);
            if inner.megaphone_limits.contains_key(&session) {return Err("megaphone_cooldown");}
            if !inner.presence.contains_key(&session)||inner.megaphone_limits.len()>=MAX_PRESENCE{return Err("player_unavailable");}
            inner.megaphone_limits.insert(session,now+std::time::Duration::from_secs(30));
            let sender = inner.presence.get(&session).unwrap();
            let message = ChatBroadcastMsg::new("megaphone", &sender.name, text.text()).with_device(sender.device);
            let recipients: Vec<_> = inner.presence.iter().map(|(id,entry)| (*id,entry.room.clone())).collect();
            (message,recipients)
        };
        let payload = serde_json::to_vec(&message).map_err(|_|"broadcast_failed")?;
        let packet = wire::encode_cold_server(&payload).map_err(|_|"broadcast_failed")?;
        Ok(recipients.into_iter().filter(|(session,room)|room.submit(RoomCommand::NotifySession { session:*session, packet:packet.clone() })).count())
    }
    pub fn new(store: SharedCharacterStore, seed_template: CharacterRecord) -> Self {
        Self {
            chat_moderation: ChatModeration::new(),
            inner: Mutex::new(SocialInner::default()),
            store,
            seed_template,
            tokens: AtomicU64::new(1),
        }
    }

    fn lock(&self) -> MutexGuard<'_, SocialInner> {
        // A panicked holder must not poison the social layer for the process.
        self.inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    // -- presence -----------------------------------------------------------

    /// Record a live socket join and return a drop guard for it. A takeover
    /// (same session, new socket) overwrites the entry; the old socket's
    /// guard becomes a no-op through its token.
    pub fn join_guard(
        self: &Arc<Self>,
        session: SessionId,
        kind: PresenceKind,
        handle: String,
        name: String,
        room: RoomHandle,
    ) -> PresenceGuard {
        self.join_guard_with_identity(session,kind,handle,name,room,ChatIdentity::Session(session))
    }

    /// Full server-resolved principal keeps chat quotas stable through session/room changes.
    pub fn join_guard_principal(
        self: &Arc<Self>, session: SessionId, kind: PresenceKind, handle: String,
        name: String, room: RoomHandle, principal: uuid::Uuid,
    ) -> PresenceGuard {
        self.join_guard_with_identity(session,kind,handle,name,room,ChatIdentity::Principal(principal))
    }

    fn join_guard_with_identity(
        self: &Arc<Self>, session: SessionId, kind: PresenceKind, handle: String,
        name: String, room: RoomHandle, chat_identity: ChatIdentity,
    ) -> PresenceGuard {
        let token = self.tokens.fetch_add(1, Ordering::Relaxed);
        {
            let mut inner = self.lock();
            if inner.presence.len() >= MAX_PRESENCE && !inner.presence.contains_key(&session) {
                // Structurally unreachable (sessions are capped below this),
                // but a full map must never grow: the player simply stays
                // invisible to the social layer.
            } else {
                inner.record_name(&handle, &name);
                inner.presence.insert(
                    session,
                    PresenceEntry {
                        chat_identity,
                        device: crate::community::Device::Unknown,
                        kind,
                        handle,
                        name,
                        room,
                        token,
                    },
                );
            }
        }
        PresenceGuard {
            hub: self.clone(),
            session,
            token,
        }
    }

    #[cfg(test)]
    pub(crate) fn prepare_room_chat(&self, session: SessionId, text: &str) -> Result<PreparedChat, ChatRejection> {
        // Room dispatch already resolved this session from its authenticated connection map.
        // Standalone RoomHandle users may not register social presence; retain their session quota.
        let identity = self.lock().presence.get(&session).map(|entry|entry.chat_identity)
            .unwrap_or(ChatIdentity::Session(session));
        self.chat_moderation.prepare(identity,ChatLane::Room,text)
    }

    fn prepare_chat(&self, session: SessionId, lane: ChatLane, text: &str) -> Result<PreparedChat, ChatRejection> {
        let identity = self.lock().presence.get(&session).map(|entry|entry.chat_identity)
            .ok_or(ChatRejection::Unavailable)?;
        self.chat_moderation.prepare(identity,lane,text)
    }

    pub(crate) fn prepare_bound_room_chat(&self, identity: ChatIdentity, text: &str) -> Result<PreparedChat, ChatRejection> {
        self.chat_moderation.prepare(identity,ChatLane::Room,text)
    }

    /// Remove a session's presence if `token` still owns the entry.
    pub fn leave(&self, session: SessionId, token: u64) {
        let mut inner = self.lock();
        if inner
            .presence
            .get(&session)
            .is_some_and(|entry| entry.token == token)
        {
            inner.presence.remove(&session);
        }
    }

    /// Owned presence snapshot in handle order (deterministic output).
    pub fn presence_snapshot(&self) -> Vec<PresenceSnapshot> {
        let inner = self.lock();
        let mut entries: Vec<PresenceSnapshot> = inner
            .presence
            .iter()
            .map(|(session, entry)| PresenceSnapshot {
                session: *session,
                kind: entry.kind,
                handle: entry.handle.clone(),
                name: entry.name.clone(),
            })
            .collect();
        entries.sort_by(|left, right| left.handle.cmp(&right.handle));
        entries
    }

    /// The live presence entry for a handle, if the player is connected.
    fn presence_by_handle<'a>(inner: &'a SocialInner, handle: &str) -> Option<&'a PresenceEntry> {
        inner.presence.values().find(|entry| entry.handle == handle)
    }

    // -- friends ------------------------------------------------------------

    /// The session's roster as social entries (offline friends included,
    /// `online: false`).
    pub fn friends_of(&self, session: SessionId) -> Vec<SocialMemberMsg> {
        let inner = self.lock();
        let handles = self.store.friends_of(session);
        Self::member_entries_for_handles(&inner, &handles)
    }

    /// Add `handle` to the session's contact list. One-directional in P1: a
    /// contact list entry, not mutual friendship. The target must be online
    /// (presence). Pushes the fresh roster to the requester.
    pub fn friend_add(
        &self,
        session: SessionId,
        handle: &str,
    ) -> Result<Vec<SocialMemberMsg>, FriendError> {
        let (own_handle, _) = self.identity_of(session);
        if own_handle == handle {
            return Err(FriendError::SelfAdd);
        }
        let entries = {
            let inner = self.lock();
            let Some(target) = Self::presence_by_handle(&inner, handle) else {
                return Err(FriendError::UnknownPlayer);
            };
            let target_handle = target.handle.clone();
            let mut friends = self.store.friends_of(session);
            if !friends.contains(&target_handle) {
                if friends.len() >= MAX_FRIENDS {
                    return Err(FriendError::Full);
                }
                friends.push(target_handle.clone());
                self.store
                    .set_friends(session, || self.seed_template.clone(), friends);
            }
            let handles = self.store.friends_of(session);
            Self::member_entries_for_handles(&inner, &handles)
        };
        self.push_friends(session, &entries);
        Ok(entries)
    }

    /// Remove `handle` from the session's contact list (idempotent). Pushes
    /// the fresh roster to the requester so panels stay live.
    pub fn friend_remove(&self, session: SessionId, handle: &str) -> Vec<SocialMemberMsg> {
        let mut friends = self.store.friends_of(session);
        let before = friends.len();
        friends.retain(|existing| existing != handle);
        if friends.len() != before {
            self.store
                .set_friends(session, || self.seed_template.clone(), friends);
        }
        let entries = self.friends_of(session);
        self.push_friends(session, &entries);
        entries
    }

    /// Push the cold `friends` roster to the session's current instance.
    fn push_friends(&self, session: SessionId, entries: &[SocialMemberMsg]) {
        let Ok(mut payload)=serde_json::to_vec(&FriendsMsg::new(entries.to_vec())) else{return;};
        if payload.len()>crate::cold::MAX_COLD_SERVER_BYTES {
            payload=serde_json::to_vec(&crate::cold::NoticeMsg {t:"notice".into(),key:"friends_refresh".into(),params:serde_json::json!({})}).expect("static notice serializes");
        }
        let Ok(packet)=wire::encode_cold_server(&payload) else{return;};
        let room = self
            .lock()
            .presence
            .get(&session)
            .map(|entry| entry.room.clone());
        if let Some(room) = room {
            room.submit(RoomCommand::NotifySession { session, packet });
        }
    }

    // -- groups -------------------------------------------------------------

    /// Create a group with the session as leader and first member.
    /// Returns the invite code.
    pub fn group_create(&self, session: SessionId) -> Result<String, GroupError> {
        let code = {
            let mut inner = self.lock();
            if inner.session_group.contains_key(&session) {
                return Err(GroupError::AlreadyInGroup);
            }
            if inner.groups.len() >= MAX_GROUPS {
                return Err(GroupError::StoreFull);
            }
            let code = self.generate_code(&inner)?;
            inner.groups.insert(
                code.clone(),
                Group {
                    leader: session,
                    members: vec![session],
                },
            );
            inner.session_group.insert(session, code.clone());
            code
        };
        self.push_group_state(&code);
        Ok(code)
    }

    /// Join the group with `code`. Membership changes push the fresh group
    /// state to every online member.
    pub fn group_join(&self, session: SessionId, code: &str) -> Result<GroupView, GroupError> {
        {
            let mut inner = self.lock();
            if inner.session_group.contains_key(&session) {
                return Err(GroupError::AlreadyInGroup);
            }
            let Some(group) = inner.groups.get_mut(code) else {
                return Err(GroupError::UnknownGroup);
            };
            if group.members.len() >= MAX_GROUP_MEMBERS {
                return Err(GroupError::Full);
            }
            group.members.push(session);
            inner.session_group.insert(session, code.to_string());
        }
        self.push_group_state(code);
        Ok(self
            .group_view(session)?
            .expect("the joiner is a member of the group"))
    }

    /// Leave the current group. Idempotent: leaving with no group is `Ok`.
    /// The leader leaving disbands; every affected online member is pushed
    /// the fresh state (`code: null` after a disband).
    pub fn group_leave(&self, session: SessionId) -> Result<(), GroupError> {
        enum Outcome {
            /// The group is gone: every former member (leaver included) is
            /// told with a `code: null` push.
            Disbanded(Vec<SessionId>),
            /// The group continues on without the leaver.
            Remaining(String),
        }
        let outcome = {
            let mut inner = self.lock();
            let Some(code) = inner.session_group.remove(&session) else {
                // Idempotent: no group to leave.
                return Ok(());
            };
            let Some(group) = inner.groups.get_mut(&code) else {
                // Dangling index: the group is already gone.
                return Ok(());
            };
            group.members.retain(|member| *member != session);
            if group.members.is_empty() || group.leader == session {
                let former = inner.groups.remove(&code);
                inner.session_group.retain(|_, grouped| grouped != &code);
                let mut affected = former.map(|group| group.members).unwrap_or_default();
                affected.push(session);
                Outcome::Disbanded(affected)
            } else {
                Outcome::Remaining(code)
            }
        };
        match outcome {
            Outcome::Disbanded(affected) => self.push_group_null(&affected),
            Outcome::Remaining(code) => {
                // Remaining members get the fresh roster; the leaver's panel
                // resets with `code: null`.
                self.push_group_state(&code);
                self.push_group_null(&[session]);
            }
        }
        Ok(())
    }

    /// The session's group view, or `None` when not in a group.
    pub fn group_view(&self, session: SessionId) -> Result<Option<GroupView>, GroupError> {
        let inner = self.lock();
        let Some(code) = inner.session_group.get(&session) else {
            return Ok(None);
        };
        let Some(group) = inner.groups.get(code) else {
            return Err(GroupError::UnknownGroup);
        };
        let members = Self::member_entries_for_sessions(&inner, &group.members);
        Ok(Some(GroupView {
            code: code.clone(),
            members,
        }))
    }

    /// Route one group chat line to every online member's current instance
    /// (normal rooms and tower instances alike). Returns the number of member
    /// instances the packet was queued for; `NotInGroup` when the sender has
    /// no group (the cold path answers with a notice).
    pub fn group_chat(&self, sender: SessionId, text: &str) -> Result<usize, GroupError> {
        if !self.lock().session_group.contains_key(&sender) { return Err(GroupError::NotInGroup); }
        let text = self.prepare_chat(sender,ChatLane::Group,text).map_err(GroupError::ChatRejected)?;
        let packet = {
            let inner = self.lock();
            let Some(code) = inner.session_group.get(&sender) else {
                return Err(GroupError::NotInGroup);
            };
            if !inner.groups.contains_key(code) {
                return Err(GroupError::NotInGroup);
            }
            let from = inner
                .presence
                .get(&sender)
                .map(|entry| entry.name.clone())
                .unwrap_or_else(|| identity_for_session(sender).1);
            let message = ChatBroadcastMsg::new("group", &from, text.text()).with_device(inner.presence.get(&sender).map(|e|e.device).unwrap_or_default());
            match serde_json::to_vec(&message)
                .ok()
                .and_then(|payload| wire::encode_cold_server(&payload).ok())
            {
                Some(packet) => packet,
                // Fixed-shape message: encoding cannot fail in practice.
                None => return Ok(0),
            }
        };
        Ok(self.deliver_to_group(sender, &packet))
    }

    /// Queue a pre-encoded packet for every online group member's instance.
    fn deliver_to_group(&self, sender: SessionId, packet: &[u8]) -> usize {
        let inner = self.lock();
        let Some(code) = inner.session_group.get(&sender).cloned() else {
            return 0;
        };
        let Some(group) = inner.groups.get(&code) else {
            return 0;
        };
        group
            .members
            .iter()
            .filter_map(|member| {
                inner
                    .presence
                    .get(member)
                    .map(|entry| (*member, entry.room.clone()))
            })
            .filter(|(session, room)| {
                room.submit(RoomCommand::NotifySession {
                    session: *session,
                    packet: packet.to_vec(),
                })
            })
            .count()
    }

    /// The session's handle/name: the stored record wins, the pure session
    /// derivation fills in for sessions that never joined a world.
    fn identity_of(&self, session: SessionId) -> (String, String) {
        match self.store.peek(session) {
            Some(record) if !record.handle.is_empty() && !record.name.is_empty() => {
                (record.handle, record.name)
            }
            _ => identity_for_session(session),
        }
    }

    /// Six-character invite code from the party alphabet (no ambiguous
    /// glyphs), retried on collision.
    fn generate_code(&self, inner: &SocialInner) -> Result<String, GroupError> {
        const ALPHABET: &[u8] = b"ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        for _ in 0..8 {
            let mut random = [0_u8; 6];
            getrandom::fill(&mut random).map_err(|_| GroupError::EntropyUnavailable)?;
            let code: String = random
                .iter()
                .map(|byte| ALPHABET[usize::from(*byte) % ALPHABET.len()] as char)
                .collect();
            if !inner.groups.contains_key(&code) {
                return Ok(code);
            }
        }
        Err(GroupError::EntropyUnavailable)
    }

    /// Push the current state of `code`'s group to every online member.
    fn push_group_state(&self, code: &str) {
        let (packet, rooms) = {
            let inner = self.lock();
            let Some(group) = inner.groups.get(code) else {
                return;
            };
            let members = Self::member_entries_for_sessions(&inner, &group.members);
            let message = GroupStateMsg::new(Some(code.to_string()), members);
            let Ok(payload) = serde_json::to_vec(&message) else {
                return;
            };
            let Ok(packet) = wire::encode_cold_server(&payload) else {
                return;
            };
            let rooms: Vec<(SessionId, RoomHandle)> = group
                .members
                .iter()
                .filter_map(|member| {
                    inner
                        .presence
                        .get(member)
                        .map(|entry| (*member, entry.room.clone()))
                })
                .collect();
            (packet, rooms)
        };
        for (session, room) in rooms {
            room.submit(RoomCommand::NotifySession {
                session,
                packet: packet.clone(),
            });
        }
    }

    /// Push `{"code": null}` (group gone) to every online session in `members`.
    fn push_group_null(&self, members: &[SessionId]) {
        let (packet, rooms) = {
            let inner = self.lock();
            let message = GroupStateMsg::new(None, Vec::new());
            let Ok(payload) = serde_json::to_vec(&message) else {
                return;
            };
            let Ok(packet) = wire::encode_cold_server(&payload) else {
                return;
            };
            let rooms: Vec<(SessionId, RoomHandle)> = members
                .iter()
                .filter_map(|member| {
                    inner
                        .presence
                        .get(member)
                        .map(|entry| (*member, entry.room.clone()))
                })
                .collect();
            (packet, rooms)
        };
        for (session, room) in rooms {
            room.submit(RoomCommand::NotifySession {
                session,
                packet: packet.clone(),
            });
        }
    }

    /// Social entries for handle-keyed rosters (friends): online targets read
    /// their presence, offline ones fall back to the name directory.
    fn member_entries_for_handles(inner: &SocialInner, handles: &[String]) -> Vec<SocialMemberMsg> {
        handles
            .iter()
            .map(|handle| {
                if let Some(entry) = Self::presence_by_handle(inner, handle) {
                    SocialMemberMsg {
                        device: entry.device,
                        handle: entry.handle.clone(),
                        name: entry.name.clone(),
                        online: true,
                        channel: match entry.kind {
                            PresenceKind::Normal { channel } => Some(channel),
                            PresenceKind::Tower => None,
                        },
                        in_tower: matches!(entry.kind, PresenceKind::Tower),
                    }
                } else {
                    SocialMemberMsg {
                        device: crate::community::Device::Unknown,
                        handle: handle.clone(),
                        name: inner
                            .names
                            .get(handle)
                            .cloned()
                            .unwrap_or_else(|| "Traveler".to_string()),
                        online: false,
                        channel: None,
                        in_tower: false,
                    }
                }
            })
            .collect()
    }

    /// Social entries for session-keyed rosters (groups): offline members
    /// fall back to their stored record, then to the pure identity
    /// derivation (always available for session ids).
    fn member_entries_for_sessions(
        inner: &SocialInner,
        sessions: &[SessionId],
    ) -> Vec<SocialMemberMsg> {
        sessions
            .iter()
            .map(|session| {
                if let Some(entry) = inner.presence.get(session) {
                    SocialMemberMsg {
                        device: entry.device,
                        handle: entry.handle.clone(),
                        name: entry.name.clone(),
                        online: true,
                        channel: match entry.kind {
                            PresenceKind::Normal { channel } => Some(channel),
                            PresenceKind::Tower => None,
                        },
                        in_tower: matches!(entry.kind, PresenceKind::Tower),
                    }
                } else {
                    let (handle, name) = identity_for_session(*session);
                    SocialMemberMsg {
                        device: crate::community::Device::Unknown,
                        handle,
                        name,
                        online: false,
                        channel: None,
                        in_tower: false,
                    }
                }
            })
            .collect()
    }
}

impl SocialInner {
    /// Record a handle → name pair with FIFO eviction at the directory cap.
    fn record_name(&mut self, handle: &str, name: &str) {
        if self.names.contains_key(handle) {
            self.names.insert(handle.to_string(), name.to_string());
            return;
        }
        if self.names_order.len() >= MAX_NAME_DIRECTORY
            && let Some(oldest) = self.names_order.pop_front()
        {
            self.names.remove(&oldest);
        }
        self.names.insert(handle.to_string(), name.to_string());
        self.names_order.push_back(handle.to_string());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::character::MAX_FRIENDS;

    fn test_store() -> SharedCharacterStore {
        crate::character::CharacterStore::shared()
    }

    fn test_hub(store: &SharedCharacterStore) -> Arc<SocialHub> {
        Arc::new(SocialHub::new(
            store.clone(),
            crate::world::character_record_seed(&crate::content::test_content()),
        ))
    }

    fn presence_for(
        hub: &Arc<SocialHub>,
        room: &RoomHandle,
        session: SessionId,
        kind: PresenceKind,
    ) -> PresenceGuard {
        let (handle, name) = identity_for_session(session);
        hub.join_guard(session, kind, handle, name, room.clone())
    }

    #[test]
    fn presence_tracks_joins_leaves_and_takeover_guards() {
        let store = test_store();
        let hub = test_hub(&store);
        let (room, _alive) = RoomHandle::spawn(&store, &hub).expect("spawn room");
        let session = [0xA1; 32];
        let guard = presence_for(&hub, &room, session, PresenceKind::Normal { channel: 2 });
        let snapshot = hub.presence_snapshot();
        assert_eq!(snapshot.len(), 1);
        assert_eq!(snapshot[0].handle, "a1a1a1a1");
        assert_eq!(snapshot[0].name, "Traveler-A1A1");
        assert_eq!(snapshot[0].kind, PresenceKind::Normal { channel: 2 });
        assert_eq!(snapshot[0].session, session);

        // Takeover: the new socket replaces the entry; the old socket's
        // teardown must not remove the fresh one (token guard).
        let takeover = presence_for(&hub, &room, session, PresenceKind::Tower);
        drop(guard);
        let snapshot = hub.presence_snapshot();
        assert_eq!(snapshot.len(), 1, "old guard must not evict the new entry");
        assert_eq!(snapshot[0].kind, PresenceKind::Tower);
        drop(takeover);
        assert!(
            hub.presence_snapshot().is_empty(),
            "socket teardown removes presence"
        );
    }

    #[test]
    fn friend_add_requires_an_online_target_and_rejects_self_and_dedups() {
        let store = test_store();
        let hub = test_hub(&store);
        let (room, _alive) = RoomHandle::spawn(&store, &hub).expect("spawn room");
        let me = [0xA1; 32]; // handle a1a1a1a1
        let target = [0xB2; 32]; // handle b2b2b2b2
        let _guard = presence_for(&hub, &room, target, PresenceKind::Normal { channel: 1 });

        // Unknown handle: no live presence record matches.
        assert_eq!(
            hub.friend_add(me, "c3c3c3c3"),
            Err(FriendError::UnknownPlayer)
        );
        // Self-add is refused.
        assert_eq!(hub.friend_add(me, "a1a1a1a1"), Err(FriendError::SelfAdd));

        let entries = hub.friend_add(me, "b2b2b2b2").expect("friend added");
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].handle, "b2b2b2b2");
        assert_eq!(entries[0].name, "Traveler-B2B2");
        assert!(entries[0].online);
        assert_eq!(entries[0].channel, Some(1));
        assert!(!entries[0].in_tower);
        assert_eq!(store.friends_of(me), vec!["b2b2b2b2".to_string()]);

        // Dedup: a second add succeeds but does not duplicate.
        let again = hub.friend_add(me, "b2b2b2b2").expect("dedup no-op");
        assert_eq!(again.len(), 1);
        assert_eq!(store.friends_of(me).len(), 1);
        // The requester is offline here (no presence): the HTTP response
        // still carries the roster, the cold push is silently skipped.
        assert!(hub.friends_of(me).iter().all(|entry| entry.online));
    }

    #[test]
    fn friend_roster_caps_at_fifty() {
        let store = test_store();
        let hub = test_hub(&store);
        let (room, _alive) = RoomHandle::spawn(&store, &hub).expect("spawn room");
        let me = [0xA1; 32];
        let prefill: Vec<String> = (0..MAX_FRIENDS)
            .map(|index| format!("{index:08x}"))
            .collect();
        store.set_friends(me, CharacterRecord::default, prefill);
        let target = [0xB2; 32];
        let _guard = presence_for(&hub, &room, target, PresenceKind::Normal { channel: 0 });
        assert_eq!(hub.friend_add(me, "b2b2b2b2"), Err(FriendError::Full));
    }

    #[test]
    fn friend_remove_is_idempotent_and_offline_entries_fall_back_to_the_directory() {
        let store = test_store();
        let hub = test_hub(&store);
        let (room, _alive) = RoomHandle::spawn(&store, &hub).expect("spawn room");
        let me = [0xA1; 32];
        // The directory learns b2's name while it is online.
        let target = [0xB2; 32];
        let target_guard = presence_for(&hub, &room, target, PresenceKind::Normal { channel: 0 });
        hub.friend_add(me, "b2b2b2b2").expect("added");
        drop(target_guard); // target goes offline

        let entries = hub.friend_remove(me, "b2b2b2b2");
        assert!(entries.is_empty());
        // Removing an unknown handle is a no-op success.
        let again = hub.friend_remove(me, "b2b2b2b2");
        assert!(again.is_empty());

        // An offline friend entry carries the directory name.
        store.set_friends(
            me,
            CharacterRecord::default,
            vec!["b2b2b2b2".to_string(), "c3c3c3c3".to_string()],
        );
        let roster = hub.friends_of(me);
        assert_eq!(roster.len(), 2);
        let b2 = roster
            .iter()
            .find(|entry| entry.handle == "b2b2b2b2")
            .unwrap();
        assert!(!b2.online);
        assert_eq!(b2.name, "Traveler-B2B2", "directory remembers the name");
        assert_eq!(b2.channel, None);
        assert!(!b2.in_tower);
        let c3 = roster
            .iter()
            .find(|entry| entry.handle == "c3c3c3c3")
            .unwrap();
        assert_eq!(c3.name, "Traveler", "never-seen handles fall back");
    }

    #[test]
    fn groups_create_join_cap_and_disband_on_leader_leave() {
        let store = test_store();
        let hub = test_hub(&store);
        let (room, _alive) = RoomHandle::spawn(&store, &hub).expect("spawn room");
        let leader = [0xA1; 32];
        let _leader_guard = presence_for(&hub, &room, leader, PresenceKind::Normal { channel: 0 });

        let code = hub.group_create(leader).expect("created");
        assert_eq!(code.len(), 6);
        assert!(
            code.bytes()
                .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit())
        );
        // One group per session: leaving is required first.
        assert_eq!(hub.group_create(leader), Err(GroupError::AlreadyInGroup));

        // Joiners up to the cap of 4.
        let mut joiners = Vec::new();
        for index in 0u8..3 {
            let mut session = [0xB0_u8; 32];
            session[0] = index;
            let guard = presence_for(
                &hub,
                &room,
                session,
                PresenceKind::Normal { channel: index },
            );
            joiners.push((session, guard));
            assert!(
                hub.group_join(session, &code).is_ok(),
                "joiner {index} joins"
            );
        }
        // Members see a four-person online roster.
        let view = hub
            .group_view(leader)
            .expect("view")
            .expect("leader is in a group");
        assert_eq!(view.code, code);
        assert_eq!(view.members.len(), 4);
        assert!(view.members.iter().all(|member| member.online));

        // The fifth joiner hits the cap; unknown codes are distinct errors.
        let fifth = [0xC0; 32];
        assert_eq!(hub.group_join(fifth, &code), Err(GroupError::Full));
        assert_eq!(
            hub.group_join(fifth, "ZZZZZZ"),
            Err(GroupError::UnknownGroup)
        );
        assert_eq!(
            hub.group_join(leader, &code),
            Err(GroupError::AlreadyInGroup)
        );

        // The leader leaving disbands: every member is out.
        hub.group_leave(leader).expect("leader leaves");
        assert!(
            hub.group_view(leader).expect("view").is_none(),
            "leader is out"
        );
        for (session, _guard) in &joiners {
            assert!(
                hub.group_view(*session).expect("view").is_none(),
                "disband clears every member"
            );
        }
        // The freed code can be reused by a fresh group.
        let reused = hub.group_create(fifth).expect("group after disband");
        assert_eq!(reused.len(), 6);
    }

    #[test]
    fn group_store_caps_at_sixty_four_live_groups() {
        let store = test_store();
        let hub = test_hub(&store);
        for index in 0..MAX_GROUPS {
            let mut session = [0u8; 32];
            session[0] = (index % 255) as u8 + 1;
            session[1] = (index / 255) as u8;
            assert!(hub.group_create(session).is_ok(), "group {index} created");
        }
        assert_eq!(hub.group_create([0xEE; 32]), Err(GroupError::StoreFull));
    }

    #[tokio::test]
    async fn group_chat_reaches_members_across_two_instances() {
        async fn next_json(rx: &mut tokio::sync::mpsc::Receiver<crate::room::QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(std::time::Duration::from_secs(3), rx.recv())
                    .await
                    .expect("push arrives")
                    .expect("queue stays open");
                assert_eq!(packet[3], 0x90, "cold envelope");
                let json: serde_json::Value =
                    serde_json::from_slice(&packet[6..]).expect("cold payload is JSON");
                if json["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                break json;
            }
        }

        let store = test_store();
        let hub = test_hub(&store);
        let (rooms, _alive) = RoomHandle::spawn_all(2, &store, &hub).expect("rooms");
        let a = [0xA1; 32];
        let b = [0xB2; 32];
        let (_welcome_a, mut outputs_a) = rooms[0].join(a).await.expect("join A");
        let (_welcome_b, mut outputs_b) = rooms[1].join(b).await.expect("join B");
        let (handle_a, name_a) = identity_for_session(a);
        let (handle_b, name_b) = identity_for_session(b);
        let _guard_a = hub.join_guard(
            a,
            PresenceKind::Normal { channel: 0 },
            handle_a,
            name_a.clone(),
            rooms[0].clone(),
        );
        let _guard_b = hub.join_guard(
            b,
            PresenceKind::Normal { channel: 1 },
            handle_b,
            name_b.clone(),
            rooms[1].clone(),
        );

        let code = hub.group_create(a).expect("created");
        // The creator's push arrives on instance 0 with just themselves.
        let created = next_json(&mut outputs_a.reliable).await;
        assert_eq!(created["t"], "group");
        assert_eq!(created["code"], code.as_str());
        assert_eq!(created["members"].as_array().unwrap().len(), 1);

        hub.group_join(b, &code).expect("joined");
        // The join push reaches both instances: fresh roster, both members.
        let joined_a = next_json(&mut outputs_a.reliable).await;
        let joined_b = next_json(&mut outputs_b.reliable).await;
        for push in [&joined_a, &joined_b] {
            assert_eq!(push["t"], "group");
            assert_eq!(push["members"].as_array().unwrap().len(), 2);
        }

        // Group chat from A reaches B's instance and A's own.
        let delivered = hub.group_chat(a, "hi team").expect("routed");
        assert!(delivered >= 2, "both member instances receive the line");
        let chat_a = next_json(&mut outputs_a.reliable).await;
        assert_eq!(chat_a["t"], "chat");
        assert_eq!(chat_a["channel"], "group");
        assert_eq!(chat_a["from"], name_a.as_str());
        assert_eq!(chat_a["text"], "hi team");
        let chat_b = next_json(&mut outputs_b.reliable).await;
        assert_eq!(chat_b["t"], "chat");
        assert_eq!(chat_b["from"], name_a.as_str(), "the sender's name travels");

        // A member leaving pushes the fresh roster to the remainder and
        // `code: null` to the leaver.
        hub.group_leave(b).expect("b leaves");
        let remaining = next_json(&mut outputs_a.reliable).await;
        assert_eq!(remaining["t"], "group");
        assert_eq!(remaining["members"].as_array().unwrap().len(), 1);
        let leaver = next_json(&mut outputs_b.reliable).await;
        assert_eq!(leaver["t"], "group");
        assert!(leaver["code"].is_null());
    }

    #[tokio::test]
    async fn room_chat_broadcasts_inside_one_instance_and_not_beyond() {
        async fn next_json(rx: &mut tokio::sync::mpsc::Receiver<crate::room::QueuedPacket>) -> serde_json::Value {
            loop {
                let packet = tokio::time::timeout(std::time::Duration::from_secs(3), rx.recv())
                    .await
                    .expect("push arrives")
                    .expect("queue stays open");
                assert_eq!(packet[3], 0x90, "cold envelope");
                let json: serde_json::Value =
                    serde_json::from_slice(&packet[6..]).expect("cold payload is JSON");
                if json["t"] == "drops" {
                    continue; // P4 join snapshot
                }
                break json;
            }
        }

        let store = test_store();
        let hub = test_hub(&store);
        let (rooms, _alive) = RoomHandle::spawn_all(2, &store, &hub).expect("rooms");
        let a = [0xA1; 32];
        let b = [0xB2; 32];
        let other = [0xC3; 32];
        let (_welcome_a, mut outputs_a) = rooms[0].join(a).await.expect("join A");
        let (_welcome_b, mut outputs_b) = rooms[0].join(b).await.expect("join B");
        let (_welcome_o, mut outputs_o) = rooms[1].join(other).await.expect("join C");

        // Room chat rides the cold path of the sender's own instance.
        assert!(rooms[0].submit(RoomCommand::Cold {
            conn: outputs_a.conn,
            payload: br#"{"t":"chat","channel":"room","text":"hello field"}"#.to_vec(),
        }));
        let line_a = next_json(&mut outputs_a.reliable).await;
        assert_eq!(line_a["t"], "chat");
        assert_eq!(line_a["channel"], "room");
        assert_eq!(line_a["text"], "hello field");
        assert!(
            line_a["from"]
                .as_str()
                .expect("sender name")
                .starts_with("Traveler-")
        );
        let line_b = next_json(&mut outputs_b.reliable).await;
        assert_eq!(line_b["text"], "hello field");
        // Every join queues a drops snapshot by design; drain C's so the
        // assertion below sees a quiet queue (same pattern as drain_drops).
        while let Ok(packet) = outputs_o.reliable.try_recv() {
            assert!(
                packet.len() > 6 && &packet[6..] == br#"{"t":"drops","entries":[]}"#,
                "C heard a non-drops message before the chat test"
            );
        }
        // The other room hears nothing.
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
        assert!(
            outputs_o.reliable.try_recv().is_err(),
            "room chat must not cross instances"
        );
    }
}
