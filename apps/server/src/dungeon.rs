//! D0 pure core; no world, socket, persistence, reward, or runtime integration.
//! The owner serializes calls and supplies monotonic milliseconds and authenticated IDs.
//! Terminal records are retained for replay safety. A full table fails closed; D1
//! must journal/compact them durably before using this as a long-running service.

use std::collections::{BTreeMap, BTreeSet};

pub type CharacterId = u128;
pub type TransferId = u128;
pub type ReservationId = u128;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Location {
    Overworld { channel: u16 },
    Dungeon { instance_id: u64 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LocationState {
    pub location: Location,
    pub version: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Member {
    pub character_id: CharacterId,
    pub source: LocationState,
}

/// IDs, party snapshot, destination and deadline are assigned/validated by the server adapter.
/// Member order is canonical (ascending character ID); retries must reuse the same payload.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CreateReservation {
    pub transfer_id: TransferId,
    pub reservation_id: ReservationId,
    pub party_id: u128,
    pub party_version: u64,
    pub content_version: String,
    pub destination: Location,
    pub members: Vec<Member>,
    pub expires_at_ms: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReservationState {
    Prepared,
    Ready,
    Committed,
    Expired,
    Released,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reservation {
    pub request: CreateReservation,
    pub state: ReservationState,
    pub confirmed: BTreeSet<CharacterId>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    pub max_records: usize,
    pub max_characters: usize,
    pub party_capacity: usize,
    pub max_ttl_ms: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    InvalidLimits,
    InvalidRequest,
    TableFull,
    CharacterCapacity,
    PartyCapacity,
    DuplicateMember,
    UnknownCharacter,
    CharacterAlreadyRegistered,
    CharacterBusy,
    SourceMismatch,
    IdConflict,
    InstanceInUse,
    UnknownTransfer,
    WrongReservation,
    NotMember,
    ContentMismatch,
    NotReady,
    Expired,
    Released,
    AlreadyCommitted,
    VersionOverflow,
}

pub struct ReservationTable {
    limits: Limits,
    records: BTreeMap<TransferId, Reservation>,
    locations: BTreeMap<CharacterId, LocationState>,
    pending: BTreeMap<CharacterId, TransferId>,
}

impl ReservationTable {
    pub fn new(limits: Limits) -> Result<Self, Error> {
        if limits.max_records == 0
            || limits.max_characters == 0
            || limits.party_capacity == 0
            || limits.party_capacity > limits.max_characters
            || limits.max_ttl_ms == 0
        {
            return Err(Error::InvalidLimits);
        }
        Ok(Self {
            limits,
            records: BTreeMap::new(),
            locations: BTreeMap::new(),
            pending: BTreeMap::new(),
        })
    }

    /// Bootstrap from authoritative location state. Never overwrites an existing owner.
    pub fn register(&mut self, character: CharacterId, state: LocationState) -> Result<(), Error> {
        if character == 0
            || state.version == 0
            || matches!(state.location, Location::Dungeon { instance_id: 0 })
        {
            return Err(Error::InvalidRequest);
        }
        if self.locations.contains_key(&character) {
            return Err(Error::CharacterAlreadyRegistered);
        }
        if self.locations.len() >= self.limits.max_characters {
            return Err(Error::CharacterCapacity);
        }
        self.locations.insert(character, state);
        Ok(())
    }

    pub fn location(&self, character: CharacterId) -> Option<LocationState> {
        self.locations.get(&character).copied()
    }

    pub fn get(&self, transfer: TransferId) -> Option<&Reservation> {
        self.records.get(&transfer)
    }

    pub fn create(
        &mut self,
        request: CreateReservation,
        now_ms: u64,
    ) -> Result<Reservation, Error> {
        self.expire(now_ms);
        if let Some(existing) = self.records.get(&request.transfer_id) {
            return if existing.request == request {
                Ok(existing.clone())
            } else {
                Err(Error::IdConflict)
            };
        }
        if request.transfer_id == 0
            || request.reservation_id == 0
            || request.party_id == 0
            || request.party_version == 0
            || request.content_version.is_empty()
            || request.content_version.len() > 128
            || request.members.is_empty()
            || matches!(request.destination, Location::Dungeon { instance_id: 0 })
            || request.expires_at_ms <= now_ms
            || request.expires_at_ms - now_ms > self.limits.max_ttl_ms
        {
            return Err(Error::InvalidRequest);
        }
        if request.members.len() > self.limits.party_capacity {
            return Err(Error::PartyCapacity);
        }
        if self.records.len() >= self.limits.max_records {
            return Err(Error::TableFull);
        }
        if self
            .records
            .values()
            .any(|r| r.request.reservation_id == request.reservation_id)
        {
            return Err(Error::IdConflict);
        }
        // Private dungeon identities are never reused, including after exit/expiry.
        if let Location::Dungeon { instance_id } = request.destination {
            if self
                .records
                .values()
                .any(|r| r.request.destination == Location::Dungeon { instance_id })
                || self
                    .locations
                    .values()
                    .any(|s| s.location == request.destination)
            {
                return Err(Error::InstanceInUse);
            }
        }
        let mut seen = BTreeSet::new();
        let mut previous = 0;
        for member in &request.members {
            if !seen.insert(member.character_id) {
                return Err(Error::DuplicateMember);
            }
            if member.character_id == 0 || member.character_id < previous {
                return Err(Error::InvalidRequest);
            }
            previous = member.character_id;
            if self.pending.contains_key(&member.character_id) {
                return Err(Error::CharacterBusy);
            }
            let current = self
                .location(member.character_id)
                .ok_or(Error::UnknownCharacter)?;
            if current != member.source || current.location == request.destination {
                return Err(Error::SourceMismatch);
            }
            if current.version == u64::MAX {
                return Err(Error::VersionOverflow);
            }
        }
        for member in &request.members {
            self.pending
                .insert(member.character_id, request.transfer_id);
        }
        let record = Reservation {
            request,
            state: ReservationState::Prepared,
            confirmed: BTreeSet::new(),
        };
        self.records
            .insert(record.request.transfer_id, record.clone());
        Ok(record)
    }

    fn checked(
        &self,
        transfer: TransferId,
        reservation: ReservationId,
    ) -> Result<&Reservation, Error> {
        let record = self.records.get(&transfer).ok_or(Error::UnknownTransfer)?;
        if record.request.reservation_id != reservation {
            return Err(Error::WrongReservation);
        }
        Ok(record)
    }

    fn live(record: &Reservation) -> Result<(), Error> {
        match record.state {
            ReservationState::Expired => Err(Error::Expired),
            ReservationState::Released => Err(Error::Released),
            _ => Ok(()),
        }
    }

    /// Confirmation is each member's consent to commit, after all critical resources are ready.
    pub fn confirm(
        &mut self,
        transfer: TransferId,
        reservation: ReservationId,
        character: CharacterId,
        content_version: &str,
        now_ms: u64,
    ) -> Result<Reservation, Error> {
        self.expire(now_ms);
        let record = self.checked(transfer, reservation)?;
        Self::live(record)?;
        if !record
            .request
            .members
            .iter()
            .any(|m| m.character_id == character)
        {
            return Err(Error::NotMember);
        }
        if record.request.content_version != content_version {
            return Err(Error::ContentMismatch);
        }
        if record.state == ReservationState::Committed {
            return Ok(record.clone());
        }
        let record = self.records.get_mut(&transfer).expect("checked record");
        record.confirmed.insert(character);
        if record.confirmed.len() == record.request.members.len() {
            record.state = ReservationState::Ready;
        }
        Ok(record.clone())
    }

    /// One atomic in-memory party move. Durable journaling and world epoch fencing belong to D1.
    /// A replay returns the original result even if members have subsequently returned elsewhere.
    pub fn commit(
        &mut self,
        transfer: TransferId,
        reservation: ReservationId,
        now_ms: u64,
    ) -> Result<Reservation, Error> {
        self.expire(now_ms);
        let record = self.checked(transfer, reservation)?;
        Self::live(record)?;
        if record.state == ReservationState::Committed {
            return Ok(record.clone());
        }
        if record.state != ReservationState::Ready {
            return Err(Error::NotReady);
        }
        for member in &record.request.members {
            if self.location(member.character_id) != Some(member.source) {
                return Err(Error::SourceMismatch);
            }
            if member.source.version == u64::MAX {
                return Err(Error::VersionOverflow);
            }
        }
        let committed = {
            let record = self.records.get_mut(&transfer).expect("checked record");
            record.state = ReservationState::Committed;
            record.clone()
        };
        for member in &committed.request.members {
            self.locations.insert(
                member.character_id,
                LocationState {
                    location: committed.request.destination,
                    version: member.source.version + 1,
                },
            );
            self.pending.remove(&member.character_id);
        }
        Ok(committed)
    }

    /// Releases only uncommitted reservations. A committed destination is never rolled back.
    pub fn release(
        &mut self,
        transfer: TransferId,
        reservation: ReservationId,
        now_ms: u64,
    ) -> Result<Reservation, Error> {
        self.expire(now_ms);
        let record = self.checked(transfer, reservation)?;
        if record.state == ReservationState::Committed {
            return Err(Error::AlreadyCommitted);
        }
        if matches!(
            record.state,
            ReservationState::Released | ReservationState::Expired
        ) {
            return Ok(record.clone());
        }
        let record = self.records.get_mut(&transfer).expect("checked record");
        record.state = ReservationState::Released;
        for member in &record.request.members {
            self.pending.remove(&member.character_id);
        }
        Ok(record.clone())
    }

    /// Returns expired transfer IDs for the adapter's resource cleanup, once each.
    pub fn expire(&mut self, now_ms: u64) -> Vec<TransferId> {
        let mut expired = Vec::new();
        for (id, record) in &mut self.records {
            if matches!(
                record.state,
                ReservationState::Prepared | ReservationState::Ready
            ) && now_ms >= record.request.expires_at_ms
            {
                record.state = ReservationState::Expired;
                for member in &record.request.members {
                    self.pending.remove(&member.character_id);
                }
                expired.push(*id);
            }
        }
        expired
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source() -> LocationState {
        LocationState {
            location: Location::Overworld { channel: 0 },
            version: 1,
        }
    }
    fn table() -> ReservationTable {
        let mut table = ReservationTable::new(Limits {
            max_records: 8,
            max_characters: 4,
            party_capacity: 2,
            max_ttl_ms: 100,
        })
        .unwrap();
        for id in 1..=3 {
            table.register(id, source()).unwrap();
        }
        table
    }
    fn request() -> CreateReservation {
        CreateReservation {
            transfer_id: 10,
            reservation_id: 20,
            party_id: 30,
            party_version: 1,
            content_version: "temple-v1".into(),
            destination: Location::Dungeon { instance_id: 40 },
            members: vec![
                Member {
                    character_id: 1,
                    source: source(),
                },
                Member {
                    character_id: 2,
                    source: source(),
                },
            ],
            expires_at_ms: 100,
        }
    }
    fn ready(table: &mut ReservationTable) {
        table.create(request(), 0).unwrap();
        for id in [1, 2] {
            table.confirm(10, 20, id, "temple-v1", 1).unwrap();
        }
    }

    #[test]
    fn dungeon_party_commit_is_atomic_and_idempotent() {
        let mut t = table();
        let r = request();
        assert_eq!(t.create(r.clone(), 0), t.create(r, 1));
        assert_eq!(t.location(1), Some(source()));
        assert_eq!(t.commit(10, 20, 1), Err(Error::NotReady));
        t.confirm(10, 20, 1, "temple-v1", 1).unwrap();
        t.confirm(10, 20, 1, "temple-v1", 2).unwrap();
        assert_eq!(t.get(10).unwrap().confirmed.len(), 1);
        assert_eq!(t.commit(10, 20, 2), Err(Error::NotReady));
        t.confirm(10, 20, 2, "temple-v1", 3).unwrap();
        let committed = t.commit(10, 20, 4).unwrap();
        assert_eq!(t.commit(10, 20, 500).unwrap(), committed);
        for id in [1, 2] {
            assert_eq!(
                t.location(id),
                Some(LocationState {
                    location: Location::Dungeon { instance_id: 40 },
                    version: 2
                })
            );
        }
        assert_eq!(t.location(3), Some(source()));
        assert_eq!(t.release(10, 20, 501), Err(Error::AlreadyCommitted));
        assert!(t.expire(600).is_empty());
    }

    #[test]
    fn dungeon_expiry_boundary_retains_tombstone_and_unlocks_members() {
        let mut t = table();
        ready(&mut t);
        assert_eq!(t.expire(100), vec![10]);
        assert!(t.expire(100).is_empty());
        assert_eq!(t.commit(10, 20, 100), Err(Error::Expired));
        assert_eq!(t.confirm(10, 20, 1, "temple-v1", 100), Err(Error::Expired));
        assert_eq!(
            t.create(request(), 100).unwrap().state,
            ReservationState::Expired
        );
        assert_eq!(t.location(1), Some(source()));
        let mut next = request();
        next.transfer_id = 11;
        next.reservation_id = 21;
        next.destination = Location::Dungeon { instance_id: 41 };
        next.expires_at_ms = 200;
        assert!(t.create(next, 100).is_ok());
    }

    #[test]
    fn dungeon_release_is_idempotent_and_does_not_move_characters() {
        let mut t = table();
        t.create(request(), 0).unwrap();
        let released = t.release(10, 20, 1).unwrap();
        assert_eq!(released.state, ReservationState::Released);
        assert_eq!(t.release(10, 20, 2).unwrap(), released);
        assert_eq!(t.create(request(), 2).unwrap(), released);
        assert_eq!(t.commit(10, 20, 2), Err(Error::Released));
        assert_eq!(t.location(1), Some(source()));
    }

    #[test]
    fn dungeon_identity_membership_and_content_are_checked() {
        let mut t = table();
        t.create(request(), 0).unwrap();
        assert_eq!(
            t.confirm(10, 99, 1, "temple-v1", 1),
            Err(Error::WrongReservation)
        );
        assert_eq!(t.confirm(10, 20, 3, "temple-v1", 1), Err(Error::NotMember));
        assert_eq!(
            t.confirm(10, 20, 1, "temple-v2", 1),
            Err(Error::ContentMismatch)
        );
        let mut changed = request();
        changed.party_version = 2;
        assert_eq!(t.create(changed, 1), Err(Error::IdConflict));
        let mut duplicate_reservation = request();
        duplicate_reservation.transfer_id = 11;
        assert_eq!(t.create(duplicate_reservation, 1), Err(Error::IdConflict));
        assert_eq!(t.commit(999, 20, 1), Err(Error::UnknownTransfer));
    }

    #[test]
    fn dungeon_capacity_and_source_rejections_do_not_partially_lock() {
        let mut t = table();
        let mut r = request();
        r.members.push(Member {
            character_id: 3,
            source: source(),
        });
        assert_eq!(t.create(r, 0), Err(Error::PartyCapacity));
        let mut r = request();
        r.members[1].character_id = 1;
        assert_eq!(t.create(r, 0), Err(Error::DuplicateMember));
        let mut r = request();
        r.members[1].source.version = 2;
        assert_eq!(t.create(r, 0), Err(Error::SourceMismatch));
        let mut r = request();
        r.members[1].character_id = 4;
        assert_eq!(t.create(r, 0), Err(Error::UnknownCharacter));
        t.create(request(), 0).unwrap();
        let mut r = request();
        r.transfer_id = 11;
        r.reservation_id = 21;
        r.destination = Location::Dungeon { instance_id: 41 };
        assert_eq!(t.create(r, 1), Err(Error::CharacterBusy));
        let mut r = request();
        r.transfer_id = 12;
        r.reservation_id = 22;
        r.members = vec![Member {
            character_id: 3,
            source: source(),
        }];
        assert_eq!(t.create(r, 1), Err(Error::InstanceInUse));
    }

    #[test]
    fn dungeon_return_and_old_commit_replay_cannot_teleport_back() {
        let mut t = table();
        ready(&mut t);
        let original = t.commit(10, 20, 3).unwrap();
        let mut back = request();
        back.transfer_id = 11;
        back.reservation_id = 21;
        back.destination = Location::Overworld { channel: 0 };
        for m in &mut back.members {
            m.source = t.location(m.character_id).unwrap();
        }
        t.create(back, 4).unwrap();
        for id in [1, 2] {
            t.confirm(11, 21, id, "temple-v1", 5).unwrap();
        }
        t.commit(11, 21, 6).unwrap();
        assert_eq!(t.commit(10, 20, 7).unwrap(), original);
        assert_eq!(
            t.location(1),
            Some(LocationState {
                location: source().location,
                version: 3
            })
        );
    }

    #[test]
    fn dungeon_bounds_and_invalid_requests_fail_closed() {
        assert!(matches!(
            ReservationTable::new(Limits {
                max_records: 0,
                max_characters: 1,
                party_capacity: 1,
                max_ttl_ms: 1
            }),
            Err(Error::InvalidLimits)
        ));
        let mut t = table();
        for deadline in [0, 101] {
            let mut r = request();
            r.expires_at_ms = deadline;
            assert_eq!(t.create(r, 0), Err(Error::InvalidRequest));
        }
        assert_eq!(
            t.register(1, source()),
            Err(Error::CharacterAlreadyRegistered)
        );
        t.register(4, source()).unwrap();
        assert_eq!(t.register(5, source()), Err(Error::CharacterCapacity));
        t.limits.max_records = 1;
        t.create(request(), 0).unwrap();
        t.release(10, 20, 1).unwrap();
        let mut r = request();
        r.transfer_id = 11;
        r.reservation_id = 21;
        assert_eq!(t.create(r, 1), Err(Error::TableFull));
    }

    #[test]
    fn dungeon_version_overflow_cannot_partially_commit() {
        let mut t = table();
        t.locations.get_mut(&2).unwrap().version = u64::MAX;
        let mut r = request();
        r.members[1].source.version = u64::MAX;
        assert_eq!(t.create(r, 0), Err(Error::VersionOverflow));
        assert_eq!(t.location(1), Some(source()));
        assert!(t.pending.is_empty());
    }
}
