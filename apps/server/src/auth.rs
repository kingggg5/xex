use std::{
    collections::{HashMap, VecDeque},
    time::{Duration, Instant},
};

use serde::Serialize;

use crate::storage::{PRINCIPAL_COOKIE_NAME, PRINCIPAL_TTL_SECS, PrincipalId};

pub type SessionId = [u8; 32];
pub type JoinTicket = [u8; 32];

/// The single browser origin allowed to talk to this server. OAuth redirect
/// URIs are derived from it (D-13), so both stay in sync by construction.
pub const ALLOWED_ORIGIN: &str = "http://127.0.0.1:5173";
pub const SESSION_COOKIE_NAME: &str = "aetherfield_session";
pub const SESSION_TTL: Duration = Duration::from_secs(60 * 60);
pub const JOIN_TICKET_TTL: Duration = Duration::from_secs(15);
/// Channel count for multi-room routing: sessions pick `0..=CHANNEL_COUNT`.
/// The room layer spawns exactly this many worlds (kept in sync by
/// construction via `main.rs`).
pub const CHANNEL_COUNT: u8 = 20;
const RATE_WINDOW: Duration = Duration::from_secs(60);
const TICKET_HISTORY_TTL: Duration = Duration::from_secs(60);
const MAX_SESSIONS: usize = 256;
const MAX_SESSION_CREATIONS_PER_WINDOW: usize = 20;
const MAX_TICKETS_PER_SESSION_PER_WINDOW: usize = 8;
const MAX_TICKET_HISTORY: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuthError {
    EntropyUnavailable,
    RateLimited,
    CapacityExceeded,
    SessionExpired,
    InvalidTicket,
    TicketExpired,
    TicketReplay,
    TicketWrongSession,
    /// A channel outside `0..CHANNEL_COUNT` was requested for a session.
    UnknownChannel,
}

/// Where a session's identity came from (D-13). `Guest` is the zero-config
/// default; Google and Discord arrive through the OAuth callback.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum AuthProvider {
    Guest,
    Google,
    Discord,
}

/// The human-facing identity bound to a session. Construct only through
/// [`SessionIdentity::guest`] or [`SessionIdentity::new`], which sanitize the
/// provider-supplied strings before they ever reach the HUD or a response.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct SessionIdentity {
    pub provider: AuthProvider,
    pub subject: String,
    pub display_name: String,
}

const MAX_SUBJECT_LEN: usize = 64;
const MAX_DISPLAY_NAME_CHARS: usize = 32;
const GUEST_DISPLAY_NAME: &str = "Traveler";

impl SessionIdentity {
    pub fn guest() -> Self {
        Self {
            provider: AuthProvider::Guest,
            subject: String::new(),
            display_name: GUEST_DISPLAY_NAME.to_string(),
        }
    }

    /// Sanitizes provider-supplied values: the subject must be entirely
    /// URL-safe identifier characters, else it is emptied (the login flow
    /// refuses an empty subject rather than shipping a mangled identifier),
    /// and display names map control characters to spaces, collapse
    /// whitespace and cap length.
    pub fn new(provider: AuthProvider, subject: &str, display_name: &str) -> Self {
        let subject: String = if !subject.is_empty()
            && subject.len() <= MAX_SUBJECT_LEN
            && subject.chars().all(|character| {
                character.is_ascii_alphanumeric() || character == '_' || character == '-'
            }) {
            subject.to_string()
        } else {
            String::new()
        };
        let mut name: String = display_name
            .chars()
            .map(|character| {
                if character.is_control() {
                    ' '
                } else {
                    character
                }
            })
            .collect();
        name = name.split_whitespace().collect::<Vec<_>>().join(" ");
        if name.chars().count() > MAX_DISPLAY_NAME_CHARS {
            name = name.chars().take(MAX_DISPLAY_NAME_CHARS).collect();
        }
        let display_name = if name.is_empty() {
            GUEST_DISPLAY_NAME.to_string()
        } else {
            name
        };
        Self {
            provider,
            subject,
            display_name,
        }
    }
}

#[derive(Debug)]
struct SessionRecord {
    expires_at: Instant,
    identity: SessionIdentity,
    ticket_issues: VecDeque<Instant>,
    outstanding_ticket: Option<JoinTicket>,
    /// The session's channel choice for multi-room routing. `None` means
    /// auto: the join flow routes to the least-occupied room.
    channel: Option<u8>,
    /// The session's assigned tower start floor. `None` = normal routing;
    /// `Some(floor)` means the next join lands in the session's tower
    /// instance (bypassing channel routing).
    tower: Option<u16>,
    /// Highest tower floor the session reached, persisted across instances by
    /// the tower world's floor milestones.
    best_floor: u16,
    /// The durable principal (V5-12) this session plays as. Resolved from the
    /// principal cookie at `POST /session` / the OAuth callback and re-checked
    /// at every join; `None` only for sessions that predate the resolution.
    principal: Option<PrincipalId>,
}

#[derive(Clone, Copy, Debug)]
struct TicketRecord {
    session_id: SessionId,
    expires_at: Instant,
}

#[derive(Clone, Copy, Debug)]
enum TicketDisposition {
    Expired,
    Consumed,
}

#[derive(Clone, Copy, Debug)]
struct TicketHistoryRecord {
    disposition: TicketDisposition,
    keep_until: Instant,
}

#[derive(Debug, Default)]
pub struct AuthManager {
    sessions: HashMap<SessionId, SessionRecord>,
    tickets: HashMap<JoinTicket, TicketRecord>,
    ticket_history: HashMap<JoinTicket, TicketHistoryRecord>,
    ticket_history_order: VecDeque<JoinTicket>,
    session_creations: VecDeque<Instant>,
}

impl AuthManager {

    /// Fresh bounded fixture for a guarded, DB-disabled private process only.
    /// Ordinary creation, privilege, TTL and ticket rules remain unchanged.
    pub fn disposable_guests_for_local_sweep(now:Instant)->Result<(Self,Vec<serde_json::Value>),AuthError> {
        let mut manager=Self::default();let mut rows=Vec::with_capacity(500);
        for _ in 0..500 {
            let session_id=manager.unique_session_id()?;let principal_token=random_session_token()?;
            manager.sessions.insert(session_id,SessionRecord{expires_at:now+SESSION_TTL,identity:SessionIdentity::guest(),ticket_issues:VecDeque::new(),outstanding_ticket:None,channel:None,tower:None,best_floor:0,principal:None});
            rows.push(serde_json::json!({"cookie":format!("aetherfield_session={}; aetherfield_principal={}",encode_token_hex(&session_id),encode_token_hex(&principal_token))}));
        }
        Ok((manager,rows))
    }
    /// Creates a session carrying `identity`, or refreshes an existing one.
    ///
    /// Refresh rule (D-13): a `Guest` identity never overwrites what the
    /// session already holds (a plain `POST /session` refresh keeps a Google
    /// identity), while a provider identity always takes effect (the OAuth
    /// callback upgrades a guest session, and re-login refreshes the name).
    pub fn create_or_refresh_session(
        &mut self,
        existing: Option<SessionId>,
        identity: SessionIdentity,
        now: Instant,
    ) -> Result<SessionId, AuthError> {
        self.prune(now);
        if let Some(session_id) = existing
            && let Some(session) = self.sessions.get_mut(&session_id)
        {
            session.expires_at = now + SESSION_TTL;
            if identity.provider != AuthProvider::Guest {
                session.identity = identity;
            }
            return Ok(session_id);
        }

        trim_times(&mut self.session_creations, now);
        if self.session_creations.len() >= MAX_SESSION_CREATIONS_PER_WINDOW {
            return Err(AuthError::RateLimited);
        }
        if self.sessions.len() >= MAX_SESSIONS {
            return Err(AuthError::CapacityExceeded);
        }

        let session_id = self.unique_session_id()?;
        self.sessions.insert(
            session_id,
            SessionRecord {
                expires_at: now + SESSION_TTL,
                identity,
                ticket_issues: VecDeque::new(),
                outstanding_ticket: None,
                channel: None,
                tower: None,
                best_floor: 0,
                principal: None,
            },
        );
        self.session_creations.push_back(now);
        Ok(session_id)
    }

    /// The durable principal the session plays as (V5-12), or `None` until
    /// the session resolution ran (`POST /session`, the OAuth callback, or
    /// the socket join path fills it in).
    pub fn principal_of(&mut self, session_id: SessionId, now: Instant) -> Option<PrincipalId> {
        self.prune(now);
        self.sessions
            .get(&session_id)
            .and_then(|session| session.principal)
    }

    /// Bind the session to a durable principal. Idempotent re-binding of the
    /// same principal is fine; a different principal replaces the old one
    /// (account linking adopted the browser onto the provider's principal).
    pub fn set_principal(
        &mut self,
        session_id: SessionId,
        principal: PrincipalId,
        now: Instant,
    ) -> Result<(), AuthError> {
        self.prune(now);
        let Some(session) = self.sessions.get_mut(&session_id) else {
            return Err(AuthError::SessionExpired);
        };
        session.expires_at = now + SESSION_TTL;
        session.principal = Some(principal);
        Ok(())
    }

    /// Stores the session's channel choice for multi-room routing. `None`
    /// clears the choice (auto-routing). Out-of-range channels are refused
    /// and leave the previous choice untouched.
    pub fn set_channel(
        &mut self,
        session_id: SessionId,
        channel: Option<u8>,
        now: Instant,
    ) -> Result<(), AuthError> {
        self.prune(now);
        if let Some(channel) = channel
            && usize::from(channel) >= usize::from(CHANNEL_COUNT)
        {
            return Err(AuthError::UnknownChannel);
        }
        let Some(session) = self.sessions.get_mut(&session_id) else {
            return Err(AuthError::SessionExpired);
        };
        session.expires_at = now + SESSION_TTL;
        session.channel = channel;
        Ok(())
    }

    /// The session's stored channel, or `None` when absent (auto) or when the
    /// session is gone.
    pub fn channel_of(&mut self, session_id: SessionId, now: Instant) -> Option<u8> {
        self.prune(now);
        self.sessions
            .get(&session_id)
            .and_then(|session| session.channel)
    }

    /// Stores the session's tower assignment (`Some(floor)`) or clears it
    /// (`None` = normal routing). Unknown sessions are refused.
    pub fn set_tower_assignment(
        &mut self,
        session_id: SessionId,
        floor: Option<u16>,
        now: Instant,
    ) -> Result<(), AuthError> {
        self.prune(now);
        let Some(session) = self.sessions.get_mut(&session_id) else {
            return Err(AuthError::SessionExpired);
        };
        session.expires_at = now + SESSION_TTL;
        session.tower = floor;
        Ok(())
    }

    /// The session's assigned tower start floor, or `None` when absent
    /// (normal routing) or when the session is gone.
    pub fn tower_assignment(&mut self, session_id: SessionId, now: Instant) -> Option<u16> {
        self.prune(now);
        self.sessions
            .get(&session_id)
            .and_then(|session| session.tower)
    }

    /// The session's highest tower floor (0 when the session is unknown).
    pub fn best_floor_of(&mut self, session_id: SessionId, now: Instant) -> u16 {
        self.prune(now);
        self.sessions
            .get(&session_id)
            .map(|session| session.best_floor)
            .unwrap_or(0)
    }

    /// Record a floor milestone from the tower world; the best floor only
    /// ever moves forward. Unknown sessions are ignored (the session may have
    /// expired mid-climb).
    pub fn set_best_floor(&mut self, session_id: SessionId, floor: u16, now: Instant) {
        self.prune(now);
        if let Some(session) = self.sessions.get_mut(&session_id) {
            session.best_floor = session.best_floor.max(floor);
        }
    }

    /// The identity of a live session, for `/session/whoami`.
    pub fn identity_of(&mut self, session_id: SessionId, now: Instant) -> Option<SessionIdentity> {
        self.prune(now);
        self.sessions
            .get(&session_id)
            .map(|session| session.identity.clone())
    }

    pub fn has_live_session(&mut self, session_id: SessionId, now: Instant) -> bool {
        self.prune(now);
        self.sessions.contains_key(&session_id)
    }

    pub fn issue_ticket(
        &mut self,
        session_id: SessionId,
        now: Instant,
    ) -> Result<JoinTicket, AuthError> {
        self.prune(now);
        let previous_ticket = {
            let Some(session) = self.sessions.get_mut(&session_id) else {
                return Err(AuthError::SessionExpired);
            };
            trim_times(&mut session.ticket_issues, now);
            if session.ticket_issues.len() >= MAX_TICKETS_PER_SESSION_PER_WINDOW {
                return Err(AuthError::RateLimited);
            }
            session.expires_at = now + SESSION_TTL;
            session.ticket_issues.push_back(now);
            session.outstanding_ticket.take()
        };

        if let Some(previous_ticket) = previous_ticket {
            self.tickets.remove(&previous_ticket);
            self.remember_ticket(previous_ticket, TicketDisposition::Expired, now);
        }

        let ticket = self.unique_ticket()?;
        self.tickets.insert(
            ticket,
            TicketRecord {
                session_id,
                expires_at: now + JOIN_TICKET_TTL,
            },
        );
        self.sessions
            .get_mut(&session_id)
            .expect("session was checked above")
            .outstanding_ticket = Some(ticket);
        Ok(ticket)
    }

    pub fn consume_ticket(
        &mut self,
        ticket: JoinTicket,
        session_id: SessionId,
        now: Instant,
    ) -> Result<SessionId, AuthError> {
        self.prune(now);
        if !self.sessions.contains_key(&session_id) {
            return Err(AuthError::SessionExpired);
        }
        if let Some(history) = self.ticket_history.get(&ticket) {
            return Err(match history.disposition {
                TicketDisposition::Expired => AuthError::TicketExpired,
                TicketDisposition::Consumed => AuthError::TicketReplay,
            });
        }

        let Some(record) = self.tickets.get(&ticket).copied() else {
            return Err(AuthError::InvalidTicket);
        };
        if record.session_id != session_id {
            return Err(AuthError::TicketWrongSession);
        }
        if record.expires_at <= now {
            self.tickets.remove(&ticket);
            self.clear_outstanding_ticket(record.session_id, ticket);
            self.remember_ticket(ticket, TicketDisposition::Expired, now);
            return Err(AuthError::TicketExpired);
        }

        self.tickets.remove(&ticket);
        if let Some(session) = self.sessions.get_mut(&session_id) {
            session.expires_at = now + SESSION_TTL;
            if session.outstanding_ticket == Some(ticket) {
                session.outstanding_ticket = None;
            }
        }
        self.remember_ticket(ticket, TicketDisposition::Consumed, now);
        Ok(session_id)
    }

    fn prune(&mut self, now: Instant) {
        trim_times(&mut self.session_creations, now);
        let expired_sessions: Vec<_> = self
            .sessions
            .iter()
            .filter_map(|(session_id, session)| (session.expires_at <= now).then_some(*session_id))
            .collect();
        for session_id in expired_sessions {
            if let Some(session) = self.sessions.remove(&session_id)
                && let Some(ticket) = session.outstanding_ticket
            {
                self.tickets.remove(&ticket);
                self.remember_ticket(ticket, TicketDisposition::Expired, now);
            }
        }

        let expired_tickets: Vec<_> = self
            .tickets
            .iter()
            .filter_map(|(ticket, record)| {
                (record.expires_at <= now || !self.sessions.contains_key(&record.session_id))
                    .then_some((*ticket, record.session_id))
            })
            .collect();
        for (ticket, session_id) in expired_tickets {
            self.tickets.remove(&ticket);
            self.clear_outstanding_ticket(session_id, ticket);
            self.remember_ticket(ticket, TicketDisposition::Expired, now);
        }

        while let Some(ticket) = self.ticket_history_order.front().copied() {
            let expired = self
                .ticket_history
                .get(&ticket)
                .is_none_or(|record| record.keep_until <= now);
            if !expired && self.ticket_history.len() <= MAX_TICKET_HISTORY {
                break;
            }
            self.ticket_history_order.pop_front();
            self.ticket_history.remove(&ticket);
        }
    }

    fn clear_outstanding_ticket(&mut self, session_id: SessionId, ticket: JoinTicket) {
        if let Some(session) = self.sessions.get_mut(&session_id)
            && session.outstanding_ticket == Some(ticket)
        {
            session.outstanding_ticket = None;
        }
    }

    fn remember_ticket(
        &mut self,
        ticket: JoinTicket,
        disposition: TicketDisposition,
        now: Instant,
    ) {
        self.ticket_history.insert(
            ticket,
            TicketHistoryRecord {
                disposition,
                keep_until: now + TICKET_HISTORY_TTL,
            },
        );
        self.ticket_history_order.push_back(ticket);
        while self.ticket_history_order.len() > MAX_TICKET_HISTORY {
            if let Some(oldest) = self.ticket_history_order.pop_front() {
                self.ticket_history.remove(&oldest);
            }
        }
    }

    fn unique_session_id(&self) -> Result<SessionId, AuthError> {
        for _ in 0..8 {
            let token = random_token()?;
            if !is_zero_token(&token) && !self.sessions.contains_key(&token) {
                return Ok(token);
            }
        }
        Err(AuthError::EntropyUnavailable)
    }

    fn unique_ticket(&self) -> Result<JoinTicket, AuthError> {
        for _ in 0..8 {
            let token = random_token()?;
            if !is_zero_token(&token)
                && !self.tickets.contains_key(&token)
                && !self.ticket_history.contains_key(&token)
            {
                return Ok(token);
            }
        }
        Err(AuthError::EntropyUnavailable)
    }
}

/// Why a `POST /session/channel` body was refused. `Malformed` is a body
/// that is not the expected JSON shape; `Unknown` is a numeric channel
/// outside the room range.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChannelParseError {
    Malformed,
    Unknown,
}

/// Parses a channel-choice body: `{"channel": <u8 0..CHANNEL_COUNT-1>}` or
/// `{"channel": null}` (auto). A missing field, non-JSON, or a non-numeric
/// channel is [`ChannelParseError::Malformed`]; a numeric channel outside
/// the room range is [`ChannelParseError::Unknown`].
pub fn parse_channel(body: &[u8]) -> Result<Option<u8>, ChannelParseError> {
    if body.is_empty() {
        return Err(ChannelParseError::Malformed);
    }
    let value: serde_json::Value =
        serde_json::from_slice(body).map_err(|_| ChannelParseError::Malformed)?;
    let Some(channel) = value.get("channel") else {
        return Err(ChannelParseError::Malformed);
    };
    if channel.is_null() {
        return Ok(None);
    }
    let number = channel.as_u64().ok_or(ChannelParseError::Malformed)?;
    let channel = u8::try_from(number).map_err(|_| ChannelParseError::Unknown)?;
    if usize::from(channel) >= usize::from(CHANNEL_COUNT) {
        return Err(ChannelParseError::Unknown);
    }
    Ok(Some(channel))
}

pub fn encode_token_hex(token: &[u8; 32]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut encoded = String::with_capacity(64);
    for byte in token {
        encoded.push(HEX[(byte >> 4) as usize] as char);
        encoded.push(HEX[(byte & 0x0f) as usize] as char);
    }
    encoded
}

pub fn decode_token_hex(value: &str) -> Option<[u8; 32]> {
    if value.len() != 64 {
        return None;
    }
    let bytes = value.as_bytes();
    let mut token = [0_u8; 32];
    for (index, byte) in token.iter_mut().enumerate() {
        let high = decode_hex_digit(bytes[index * 2])?;
        let low = decode_hex_digit(bytes[index * 2 + 1])?;
        *byte = high << 4 | low;
    }
    Some(token)
}

fn decode_hex_digit(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

/// A fresh random 32-byte token (OAuth state and PKCE verifiers share the
/// session token's entropy source).
pub fn random_session_token() -> Result<[u8; 32], AuthError> {
    random_token()
}

/// The loopback game origin shared by session endpoints and OAuth
/// navigations. Served from one function so the two checks cannot drift.
pub fn allowed_origin() -> &'static str {
    "http://127.0.0.1:5173"
}

/// Value of a named cookie inside a `Cookie` header, if it appears exactly
/// once (duplicate occurrences are refused, matching session parsing).
pub fn cookie_value(cookie_header: &str, name: &str) -> Option<String> {
    let mut found = None;
    let mut seen = false;
    for part in cookie_header.split(';').map(str::trim) {
        let Some(value) = part.strip_prefix(&format!("{name}=")) else {
            continue;
        };
        if seen {
            return None;
        }
        seen = true;
        found = Some(value.to_string());
    }
    found
}

/// Parses the session id out of a `Cookie` header for `name`, refusing
/// duplicate occurrences the same way the session parser always has.
pub fn decode_session_cookie(cookie_header: &str, name: &str) -> Option<SessionId> {
    cookie_value(cookie_header, name).and_then(|value| decode_token_hex(&value))
}

/// The session cookie the login flow and `POST /session` both set.
///
/// SameSite=Lax (D-13, previously Strict): the OAuth provider returns via a
/// top-level cross-site navigation, and Strict cookies are not sent on those,
/// so the browser's existing session could never be found at the callback.
/// Lax still keeps cookies off cross-site POSTs and subrequests.
pub fn session_cookie(session_id: &SessionId, secure: bool) -> String {
    format!(
        "{SESSION_COOKIE_NAME}={}; HttpOnly; SameSite=Lax; Path=/; Max-Age={}{suffix}",
        encode_token_hex(session_id),
        SESSION_TTL.as_secs(),
        suffix = if secure { "; Secure" } else { "" },
    )
}

/// The durable principal cookie (V5-12): same 32-byte-token shape as the
/// session cookie but a 30-day sliding lifetime (plan v5 §12.3). SameSite=Lax
/// for the same D-13 reason as the session cookie — the OAuth provider
/// returns via a top-level cross-site navigation, and a Strict cookie would
/// not be sent there, breaking login on a fresh browser.
pub fn principal_cookie(token_hex: &str, secure: bool) -> String {
    format!(
        "{PRINCIPAL_COOKIE_NAME}={token_hex}; HttpOnly; SameSite=Lax; Path=/; \
         Max-Age={PRINCIPAL_TTL_SECS}{suffix}",
        suffix = if secure { "; Secure" } else { "" },
    )
}

fn random_token() -> Result<[u8; 32], AuthError> {
    let mut token = [0_u8; 32];
    getrandom::fill(&mut token).map_err(|_| AuthError::EntropyUnavailable)?;
    Ok(token)
}

fn is_zero_token(token: &[u8; 32]) -> bool {
    token.iter().all(|byte| *byte == 0)
}

fn trim_times(times: &mut VecDeque<Instant>, now: Instant) {
    while times
        .front()
        .is_some_and(|time| now.saturating_duration_since(*time) >= RATE_WINDOW)
    {
        times.pop_front();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn random_session_is_opaque_nonzero_and_refreshable() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let first = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        let second = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        assert_ne!(first, [0; 32]);
        assert_ne!(first, second);
        assert_eq!(
            auth.create_or_refresh_session(Some(first), SessionIdentity::guest(), now)
                .unwrap(),
            first
        );
        assert_eq!(decode_token_hex(&encode_token_hex(&first)), Some(first));
        assert!(decode_token_hex("not-a-session-token").is_none());
    }

    #[test]
    fn join_ticket_is_bound_to_session_and_single_use() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let first = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        let second = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        let ticket = auth.issue_ticket(first, now).unwrap();

        assert_eq!(
            auth.consume_ticket(ticket, second, now),
            Err(AuthError::TicketWrongSession)
        );
        assert_eq!(auth.consume_ticket(ticket, first, now), Ok(first));
        assert_eq!(
            auth.consume_ticket(ticket, first, now),
            Err(AuthError::TicketReplay)
        );
    }

    #[test]
    fn expired_ticket_is_rejected_and_classified() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let owner = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        let ticket = auth.issue_ticket(owner, now).unwrap();
        let late = now + JOIN_TICKET_TTL + Duration::from_millis(1);

        assert_eq!(
            auth.consume_ticket(ticket, owner, late),
            Err(AuthError::TicketExpired)
        );
        assert_eq!(
            auth.consume_ticket(ticket, owner, late),
            Err(AuthError::TicketExpired)
        );
    }

    #[test]
    fn issuing_a_new_ticket_invalidates_the_previous_one() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let owner = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        let old = auth.issue_ticket(owner, now).unwrap();
        let new = auth
            .issue_ticket(owner, now + Duration::from_millis(1))
            .unwrap();

        assert_ne!(old, new);
        assert_eq!(
            auth.consume_ticket(old, owner, now),
            Err(AuthError::TicketExpired)
        );
        assert_eq!(auth.consume_ticket(new, owner, now), Ok(owner));
    }

    #[test]
    fn session_and_ticket_creation_are_rate_limited() {
        let start = Instant::now();
        let mut auth = AuthManager::default();
        for index in 0..MAX_SESSION_CREATIONS_PER_WINDOW {
            auth.create_or_refresh_session(
                None,
                SessionIdentity::guest(),
                start + Duration::from_millis(index as u64),
            )
            .unwrap();
        }
        assert_eq!(
            auth.create_or_refresh_session(
                None,
                SessionIdentity::guest(),
                start + Duration::from_secs(1)
            ),
            Err(AuthError::RateLimited)
        );

        let mut ticket_auth = AuthManager::default();
        let owner = ticket_auth
            .create_or_refresh_session(None, SessionIdentity::guest(), start)
            .unwrap();
        for index in 0..MAX_TICKETS_PER_SESSION_PER_WINDOW {
            ticket_auth
                .issue_ticket(owner, start + Duration::from_millis(index as u64))
                .unwrap();
        }
        assert_eq!(
            ticket_auth.issue_ticket(owner, start + Duration::from_secs(1)),
            Err(AuthError::RateLimited)
        );
    }

    #[test]
    fn session_expires_after_idle_ttl() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let owner = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        let expired = now + SESSION_TTL + Duration::from_millis(1);
        assert!(!auth.has_live_session(owner, expired));
        assert_eq!(
            auth.issue_ticket(owner, expired),
            Err(AuthError::SessionExpired)
        );
        assert_eq!(auth.identity_of(owner, expired), None);
    }

    #[test]
    fn session_channel_round_trips_and_rejects_out_of_range() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let session = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        // Absent means auto-routing.
        assert_eq!(auth.channel_of(session, now), None);

        auth.set_channel(session, Some(0), now).unwrap();
        assert_eq!(auth.channel_of(session, now), Some(0));
        auth.set_channel(session, Some(CHANNEL_COUNT - 1), now)
            .unwrap();
        assert_eq!(auth.channel_of(session, now), Some(CHANNEL_COUNT - 1));

        // Out-of-range is refused and keeps the previous choice.
        assert_eq!(
            auth.set_channel(session, Some(CHANNEL_COUNT), now),
            Err(AuthError::UnknownChannel)
        );
        assert_eq!(
            auth.set_channel(session, Some(255), now),
            Err(AuthError::UnknownChannel)
        );
        assert_eq!(auth.channel_of(session, now), Some(CHANNEL_COUNT - 1));

        // `null` clears the choice back to auto.
        auth.set_channel(session, None, now).unwrap();
        assert_eq!(auth.channel_of(session, now), None);

        // Unknown sessions carry no channel and accept none.
        let ghost = [0x11; 32];
        assert_eq!(auth.channel_of(ghost, now), None);
        assert_eq!(
            auth.set_channel(ghost, Some(1), now),
            Err(AuthError::SessionExpired)
        );
    }

    #[test]
    fn tower_assignment_and_best_floor_round_trip_forward_only() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let session = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();
        assert_eq!(auth.tower_assignment(session, now), None);
        assert_eq!(auth.best_floor_of(session, now), 0);

        // An assigned start floor routes the next join into the tower.
        auth.set_tower_assignment(session, Some(7), now).unwrap();
        assert_eq!(auth.tower_assignment(session, now), Some(7));
        // Leaving clears the assignment back to normal routing.
        auth.set_tower_assignment(session, None, now).unwrap();
        assert_eq!(auth.tower_assignment(session, now), None);

        // Best floor is monotonic across milestones and completion.
        auth.set_best_floor(session, 2, now);
        assert_eq!(auth.best_floor_of(session, now), 2);
        auth.set_best_floor(session, 7, now);
        assert_eq!(auth.best_floor_of(session, now), 7);
        auth.set_best_floor(session, 3, now);
        assert_eq!(auth.best_floor_of(session, now), 7);

        // Unknown sessions carry no assignment, no floor, and accept none.
        let ghost = [0x22; 32];
        assert_eq!(auth.tower_assignment(ghost, now), None);
        assert_eq!(auth.best_floor_of(ghost, now), 0);
        assert_eq!(
            auth.set_tower_assignment(ghost, Some(1), now),
            Err(AuthError::SessionExpired)
        );
        auth.set_best_floor(ghost, 99, now);
        assert_eq!(auth.best_floor_of(ghost, now), 0);
    }

    #[test]
    fn channel_body_parses_null_and_in_range_channels() {
        assert_eq!(parse_channel(br#"{"channel":0}"#), Ok(Some(0)));
        assert_eq!(
            parse_channel(br#"{"channel":19}"#),
            Ok(Some(CHANNEL_COUNT - 1))
        );
        // `null` clears the session back to auto-routing.
        assert_eq!(parse_channel(br#"{"channel":null}"#), Ok(None));
        // Unknown keys are tolerated; the channel field decides.
        assert_eq!(parse_channel(br#"{"channel":3,"other":1}"#), Ok(Some(3)));
    }

    #[test]
    fn channel_body_rejects_out_of_range_and_malformed_payloads() {
        // Numeric channels outside the room range name the room problem.
        for out_of_range in [
            br#"{"channel":20}"#.as_slice(),
            br#"{"channel":255}"#.as_slice(),
            br#"{"channel":256}"#.as_slice(),
        ] {
            assert_eq!(
                parse_channel(out_of_range),
                Err(ChannelParseError::Unknown),
                "{:?} must be refused as an unknown channel",
                std::str::from_utf8(out_of_range).unwrap_or("?")
            );
        }
        // Everything else is a malformed body, not a channel statement.
        for malformed in [
            &b""[..],
            b"not json",
            b"{}",
            br#"{"channel":"3"}"#.as_slice(),
            br#"{"channel":-1}"#.as_slice(),
            br#"{"channel":1.5}"#.as_slice(),
            br#"{"channel":true}"#.as_slice(),
        ] {
            assert_eq!(parse_channel(malformed), Err(ChannelParseError::Malformed));
        }
    }

    #[test]
    fn provider_login_upgrades_a_guest_but_refresh_never_downgrades_it() {
        let now = Instant::now();
        let mut auth = AuthManager::default();
        let session = auth
            .create_or_refresh_session(None, SessionIdentity::guest(), now)
            .unwrap();

        // A guest refresh keeps the guest identity.
        auth.create_or_refresh_session(Some(session), SessionIdentity::guest(), now)
            .unwrap();
        assert_eq!(
            auth.identity_of(session, now).unwrap().provider,
            AuthProvider::Guest
        );

        // The OAuth callback upgrades the same session to the provider.
        let google = SessionIdentity::new(AuthProvider::Google, "subject-1", "Ada");
        auth.create_or_refresh_session(Some(session), google.clone(), now)
            .unwrap();
        assert_eq!(auth.identity_of(session, now).unwrap(), google);

        // A later plain refresh keeps the provider identity (no downgrade).
        auth.create_or_refresh_session(Some(session), SessionIdentity::guest(), now)
            .unwrap();
        assert_eq!(auth.identity_of(session, now).unwrap(), google);

        // Another provider login replaces the earlier one (last login wins).
        let discord = SessionIdentity::new(AuthProvider::Discord, "subject-2", "Grace");
        auth.create_or_refresh_session(Some(session), discord.clone(), now)
            .unwrap();
        assert_eq!(auth.identity_of(session, now).unwrap(), discord);
    }

    #[test]
    fn session_cookie_is_http_only_lax_and_parses_back() {
        let session = [0x3d; 32];
        let cookie = session_cookie(&session, false);
        assert!(cookie.starts_with("aetherfield_session="));
        assert!(cookie.contains("HttpOnly"));
        assert!(cookie.contains("SameSite=Lax"));
        assert!(cookie.contains("Path=/"));
        assert!(!cookie.contains("Secure"));
        assert!(session_cookie(&session, true).contains("Secure"));
        assert_eq!(
            decode_session_cookie(&format!("theme=dark; {cookie}"), SESSION_COOKIE_NAME),
            Some(session)
        );
        assert_eq!(
            decode_session_cookie(
                &format!(
                    "{}={}; {}={}",
                    SESSION_COOKIE_NAME,
                    encode_token_hex(&session),
                    SESSION_COOKIE_NAME,
                    encode_token_hex(&session)
                ),
                SESSION_COOKIE_NAME
            ),
            None,
            "duplicate session cookies are refused"
        );
        assert_eq!(decode_session_cookie(&cookie, "other_cookie"), None);
        assert_eq!(cookie_value("a=1; b=2", "b"), Some("2".to_string()));
        assert_eq!(cookie_value("a=1; a=2", "a"), None);
    }
    #[test]
    fn private_sweep_guests_keep_normal_privilege_ttl_and_ticket_rules() {
        let now=Instant::now();let (mut fixture,rows)=AuthManager::disposable_guests_for_local_sweep(now).unwrap();assert_eq!(fixture.sessions.len(),500);assert_eq!(rows.len(),500);
        assert!(fixture.sessions.values().all(|session|session.identity==SessionIdentity::guest()&&session.expires_at==now+SESSION_TTL&&session.channel.is_none()&&session.tower.is_none()&&session.best_floor==0&&session.principal.is_none()));
        let unique=rows.iter().map(|row|row["cookie"].as_str().unwrap()).collect::<std::collections::HashSet<_>>();assert_eq!(unique.len(),500);
        let sid=*fixture.sessions.keys().next().unwrap();assert!(fixture.create_or_refresh_session(Some(sid),SessionIdentity::guest(),now).is_ok());assert!(fixture.create_or_refresh_session(None,SessionIdentity::guest(),now).is_err());
        for _ in 0..MAX_TICKETS_PER_SESSION_PER_WINDOW {assert!(fixture.issue_ticket(sid,now).is_ok());}assert!(fixture.issue_ticket(sid,now).is_err());
        let mut ordinary=AuthManager::default();for _ in 0..MAX_SESSION_CREATIONS_PER_WINDOW {assert!(ordinary.create_or_refresh_session(None,SessionIdentity::guest(),now).is_ok());}assert!(ordinary.create_or_refresh_session(None,SessionIdentity::guest(),now).is_err());
    }

}
