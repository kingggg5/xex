//! Shared cross-instance character state.
//!
//! Every world instance used to keep its own per-session player record, so
//! switching channels or entering a tower instance reset the wallet, bag and
//! quest progress (tower rewards would vanish on the way home). This module
//! extracts exactly what must survive an instance switch into one process-wide
//! store: [`CharacterStore`], created once in `main.rs` and threaded through
//! `RoomHandle::spawn`/`spawn_all` into every world.
//!
//! Everything transient — position, connection/epoch, input queues, combat
//! state, hp — stays per-world. The store is also the seam for V5-12
//! (PostgreSQL durability later): one type, cleanly bounded, with worlds as
//! the only writers.

use crate::auth::SessionId;
use crate::cold::OpResultMsg;

fn default_job_level() -> u32 {
    1
}
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::sync::{Arc, Mutex, MutexGuard};

/// One cached economy-op result: `(op_id, request_key, result)`.
pub type OpCache = VecDeque<(String, String, OpResultMsg)>;

/// Maximum friends per character (P1 contact list cap).
pub const MAX_FRIENDS: usize = 50;

/// The stable per-session social identity: a public `handle` (the first 8 hex
/// chars of the session id, lowercase) and a display `name`
/// (`Traveler-XXXX` from the last 4 hex chars, uppercase). Pure derivation
/// from the session id, so any layer can compute it before the record exists.
pub fn identity_for_session(session_id: SessionId) -> (String, String) {
    identity_from_bytes(&session_id)
}

/// The durable variant: identity derived from the V5-12 principal, so the
/// same character carries the same handle and name across server restarts
/// (the session id is ephemeral and would rename the character every time).
pub fn identity_for_principal(principal: uuid::Uuid) -> (String, String) {
    identity_from_bytes(principal.as_bytes())
}

fn identity_from_bytes(bytes: &[u8]) -> (String, String) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    const UPPER: &[u8; 16] = b"0123456789ABCDEF";
    let mut handle = String::with_capacity(8);
    for byte in &bytes[..4] {
        handle.push(HEX[usize::from(byte >> 4)] as char);
        handle.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    let name = format!(
        "Traveler-{}{}{}{}",
        UPPER[usize::from(bytes[bytes.len() - 2] >> 4)] as char,
        UPPER[usize::from(bytes[bytes.len() - 2] & 0x0f)] as char,
        UPPER[usize::from(bytes[bytes.len() - 1] >> 4)] as char,
        UPPER[usize::from(bytes[bytes.len() - 1] & 0x0f)] as char,
    );
    (handle, name)
}

/// The cross-instance slice of a character. Worlds copy this in on join and
/// publish it back whenever it changes; `generation` is bumped by the store on
/// every write so a resuming world can tell whether another instance advanced
/// the record meanwhile. V5-12: the whole record serializes into the durable
/// `characters.record` JSONB snapshot, so every field must round-trip.
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct CharacterRecord {
    #[serde(default)]
    pub inventory_schema: u8,
    #[serde(default)]
    pub inventory_namespace: String,
    #[serde(default)]
    pub item_instances: BTreeMap<String,crate::inventory_instances::ItemInstance>,
    #[serde(default)]
    pub death_revision: u32,
    #[serde(default)]
    pub down: bool,
    #[serde(default)]
    pub reward_receipts: VecDeque<String>,
    #[serde(default)]
    pub reward_mail: BTreeMap<String, BTreeMap<String, u32>>,
    #[serde(default)]
    pub mvp_rune_pity: u32,
    /// Process-local world writer lease, never stored in PostgreSQL or sent to clients.
    #[serde(skip)]
    pub cache_owner: u64,
    #[serde(default)]
    pub community: crate::community::Progress,
    /// Monotonic write counter maintained by [`CharacterStore::save`].
    pub generation: u64,
    pub gold: u32,
    pub coin: u32,
    /// Base track (E07): `level`/`exp` are the base level and its EXP.
    pub level: u32,
    pub exp: u32,
    /// Job track (E07): job level and its EXP, curves from the vocation.
    #[serde(default = "default_job_level")]
    pub job_level: u32,
    #[serde(default)]
    pub job_exp: u32,
    /// Equipped gear (E07, non-instance): slot ("weapon"/"armor") -> item id.
    #[serde(default)]
    pub equipment: BTreeMap<String, String>,
    /// Character-state revision (`character_state.rev`); carried so revisions
    /// stay monotonic across instances.
    pub state_revision: u32,
    pub bag: BTreeMap<String, u8>,
    pub pouch: BTreeMap<String, u32>,
    pub skin: Option<String>,
    pub pet: Option<String>,
    pub owned_cosmetics: BTreeSet<String>,
    pub quest_revision: u32,
    /// Which quest the quest-state fields describe (V5-13 normalized
    /// quest_progress rows are keyed by this). Empty = no quest tracked.
    #[serde(default)]
    pub quest_id: String,
    pub quest_state: String,
    pub quest_objectives: BTreeMap<String, u32>,
    pub quest_step_ticks: BTreeMap<String, u64>,
    pub activated_windmarks: BTreeSet<String>,
    /// Stable social identity, derived from the session id at first seed and
    /// never rewritten: `handle` is the session's public social handle, `name`
    /// the display name shown in chat, rosters and presence.
    pub handle: String,
    pub name: String,
    /// P1 contact list (one-directional friendship): friend handles, capped at
    /// [`MAX_FRIENDS`], deduplicated. Written only through
    /// [`CharacterStore::set_friends`] (the HTTP/social layer); world
    /// publishes never touch it, so a mid-session friend change cannot be
    /// clobbered by the next instance save.
    pub friends: Vec<String>,
    pub item_operations: OpCache,
    pub quest_operations: OpCache,
    pub store_operations: OpCache,
    pub box_operations: OpCache,
    pub equip_operations: OpCache,
    #[serde(default)]
    pub stat_points: u32,
    #[serde(default)]
    pub allocated_str: u16,
    #[serde(default)]
    pub allocated_agi: u16,
    #[serde(default)]
    pub allocated_vit: u16,
    #[serde(default)]
    pub allocated_int: u16,
    #[serde(default)]
    pub allocated_dex: u16,
    #[serde(default)]
    pub allocated_luk: u16,
    #[serde(default)]
    pub stat_operations: OpCache,
    #[serde(default)]
    pub equipment_refine: BTreeMap<String, u8>,
    #[serde(default)]
    pub refine_operations: OpCache,
}

/// Process-wide store of [`CharacterRecord`]s keyed by session. Cheap to
/// clone (an `Arc`); world threads lock it only for the duration of one
/// copy-in or copy-out, never across a tick boundary.
#[derive(Debug, Default)]
pub struct CharacterStore {
    players: Mutex<HashMap<SessionId, CharacterRecord>>,
}

/// The shared handle threaded into every world instance.
pub type SharedCharacterStore = Arc<CharacterStore>;

impl CharacterStore {
    pub fn claim(&self,session:SessionId,owner:u64,canonical:Option<CharacterRecord>)->Option<CharacterRecord> {
        let mut players=self.lock();
        let generation=players.get(&session).map_or(0,|r|r.generation);
        let mut record=canonical.or_else(||players.get(&session).cloned())?;
        record.cache_owner=owner;record.generation=generation.wrapping_add(1).max(1);
        players.insert(session,record.clone());Some(record)
    }
    pub fn owns(&self,session:SessionId,owner:u64)->bool {self.lock().get(&session).is_some_and(|r|r.cache_owner==owner)}
    pub fn save_owned(&self,session:SessionId,record:&mut CharacterRecord,owner:u64)->Option<u64> {
        let mut players=self.lock();
        let existing=players.get(&session)?;
        if existing.cache_owner!=owner {return None;}
        record.friends=existing.friends.clone();record.cache_owner=owner;
        record.generation=existing.generation.wrapping_add(1).max(1);
        players.insert(session,record.clone());Some(record.generation)
    }
    pub fn new() -> Self {
        Self::default()
    }

    /// A new `Arc`-shared store (what `main.rs` builds once and threads
    /// through every `RoomHandle::spawn`).
    pub fn shared() -> SharedCharacterStore {
        Arc::new(Self::new())
    }

    /// Copy the record out, seeding it with `seed` on first sight. Seeding is
    /// part of the store so two worlds racing a first join cannot disagree:
    /// the winner's seed is what everyone else reads. The social identity
    /// (`handle`/`name`) is derived from the session id when the seed leaves
    /// it blank, so every seed path produces a complete record.
    pub fn load_or_seed(
        &self,
        session_id: SessionId,
        seed: impl FnOnce() -> CharacterRecord,
    ) -> CharacterRecord {
        let mut players = self.lock();
        if let Some(record) = players.get(&session_id) {
            return record.clone();
        }
        let mut record = seed();
        record.generation = 1;
        fill_identity(&mut record, session_id);
        players.insert(session_id, record.clone());
        record
    }

    /// Read the current record without seeding, for resume-time
    /// reconciliation (a world adopts the record when its generation moved).
    pub fn peek(&self, session_id: SessionId) -> Option<CharacterRecord> {
        self.lock().get(&session_id).cloned()
    }

    /// Publish `record` for `session_id`, bumping and returning the record's
    /// generation so the writer can detect later external writes. `friends`
    /// is owned by the HTTP/social layer ([`CharacterStore::set_friends`] is
    /// its only writer): an incoming world publish keeps the stored list so a
    /// friend change between two gameplay saves always survives.
    pub fn save(&self, session_id: SessionId, record: &mut CharacterRecord) -> u64 {
        record.generation = record.generation.wrapping_add(1).max(1);
        let mut players = self.lock();
        if let Some(existing) = players.get(&session_id) {
            record.friends = existing.friends.clone();
        }
        players.insert(session_id, record.clone());
        record.generation
    }

    /// The session's stored friends list (empty when the session has no
    /// record yet; a read, so nothing is seeded).
    pub fn friends_of(&self, session_id: SessionId) -> Vec<String> {
        self.lock()
            .get(&session_id)
            .map(|record| record.friends.clone())
            .unwrap_or_default()
    }

    /// Replace the session's friends list (the social layer's single write
    /// path). A read-modify-write under the store lock, so gameplay fields the
    /// world published concurrently are preserved. When the session has no
    /// record yet (a friend write before the first world join), it is seeded
    /// from `seed` — the caller supplies the same first-join template the
    /// world would apply, so the wallet is not silently zeroed.
    pub fn set_friends(
        &self,
        session_id: SessionId,
        seed: impl FnOnce() -> CharacterRecord,
        friends: Vec<String>,
    ) -> Vec<String> {
        let mut players = self.lock();
        let record = players.entry(session_id).or_insert_with(|| {
            let mut record = seed();
            record.generation = 1;
            fill_identity(&mut record, session_id);
            record
        });
        record.friends = friends;
        // Bump the generation line (like `save`) so resuming instances
        // re-adopt the record. One critical section: a concurrent world save
        // can never interleave and move the generation backwards.
        record.generation = record.generation.wrapping_add(1).max(1);
        record.friends.clone()
    }

    fn lock(&self) -> MutexGuard<'_, HashMap<SessionId, CharacterRecord>> {
        // A panicked world thread must not permanently poison every other
        // instance's access to shared state.
        self.players
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

/// Stamp the derived identity onto a freshly built record when the seed left
/// the fields blank (all store seeding paths share this so identity is
/// seed-once stable no matter who seeds first).
fn fill_identity(record: &mut CharacterRecord, session_id: SessionId) {
    if record.handle.is_empty() || record.name.is_empty() {
        let (handle, name) = identity_for_session(session_id);
        if record.handle.is_empty() {
            record.handle = handle;
        }
        if record.name.is_empty() {
            record.name = name;
        }
    }
    record.state_revision = record.state_revision.max(1);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record(gold: u32) -> CharacterRecord {
        CharacterRecord {
            gold,
            state_revision: 1,
            quest_state: "not_started".to_string(),
            ..CharacterRecord::default()
        }
    }

    #[test]
    fn load_or_seed_seeds_once_and_save_bumps_the_generation() {
        let store = CharacterStore::new();
        let session = [7_u8; 32];
        let seeded = store.load_or_seed(session, || record(250));
        assert_eq!(seeded.generation, 1);
        assert_eq!(store.load_or_seed(session, || record(999)).gold, 250);

        let mut updated = store.peek(session).expect("record exists");
        assert_eq!(updated.generation, 1);
        let generation = store.save(session, &mut updated);
        assert_eq!(generation, 2);
        assert_eq!(store.peek(session).expect("saved").generation, 2);

        // An unknown session has nothing to peek at.
        assert!(store.peek([8_u8; 32]).is_none());
    }

    #[test]
    fn identity_is_derived_from_the_session_id_and_seed_once_stable() {
        let mut session = [0_u8; 32];
        session[0] = 0xa1;
        session[1] = 0xb2;
        session[2] = 0xc3;
        session[3] = 0xd4;
        session[30] = 0x5e;
        session[31] = 0x6f;
        let (handle, name) = identity_for_session(session);
        assert_eq!(handle, "a1b2c3d4");
        assert_eq!(name, "Traveler-5E6F");

        // The store stamps the identity at first seed and never rewrites it.
        let store = CharacterStore::new();
        let seeded = store.load_or_seed(session, || record(1));
        assert_eq!(seeded.handle, "a1b2c3d4");
        assert_eq!(seeded.name, "Traveler-5E6F");
        // A second load with a wildly different seed keeps the identity.
        let reloaded = store.load_or_seed(session, || {
            let mut other = record(99_999);
            other.handle = "would-be-clobbered".to_string();
            other.name = "Wrong".to_string();
            other
        });
        assert_eq!(reloaded.handle, "a1b2c3d4");
        assert_eq!(reloaded.name, "Traveler-5E6F");
        assert_eq!(reloaded.gold, 1, "first seed wins");
    }

    #[test]
    fn friend_writes_survive_world_publishes_and_seed_the_record_when_missing() {
        let store = CharacterStore::new();
        let session = [9_u8; 32];

        // A friend write before the first world join seeds from the given
        // template (identity included) instead of zeroing the wallet.
        let friends = store.set_friends(
            session,
            || {
                let mut template = record(250);
                template.coin = 10;
                template
            },
            vec!["a1b2c3d4".to_string()],
        );
        assert_eq!(friends, vec!["a1b2c3d4".to_string()]);
        let seeded = store.peek(session).expect("seeded by friend write");
        assert_eq!(seeded.gold, 250, "template wallet survives");
        assert_eq!(seeded.coin, 10);
        assert!(!seeded.handle.is_empty(), "identity filled in");
        assert_eq!(seeded.friends, vec!["a1b2c3d4".to_string()]);

        // A world-style publish (a record built without friends) keeps the
        // stored friend list instead of clobbering it.
        let mut gameplay = store.load_or_seed(session, || record(300));
        assert_eq!(gameplay.gold, 250, "existing record wins over the seed");
        gameplay.gold = 400;
        store.save(session, &mut gameplay);
        let after_publish = store.peek(session).expect("published");
        assert_eq!(after_publish.gold, 400);
        assert_eq!(after_publish.friends, vec!["a1b2c3d4".to_string()]);

        // set_friends is a read-modify-write: gameplay fields it did not touch
        // stay as the world published them.
        let updated = store.set_friends(session, || record(1), Vec::new());
        assert!(updated.is_empty());
        assert_eq!(store.peek(session).expect("present").gold, 400);
        // Generation keeps moving forward so instances re-adopt.
        let before = store.peek(session).expect("present").generation;
        store.set_friends(session, || record(1), vec!["e5f6a7b8".to_string()]);
        let after = store.peek(session).expect("present").generation;
        assert!(after > before);
        // Reading friends without a record is an empty list, not a seed.
        assert!(store.friends_of([0x99; 32]).is_empty());
        assert!(store.peek([0x99; 32]).is_none());
    }
}
