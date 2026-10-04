//! Bounded, process-local rate and exact-repeat protection for chat ingress.
//!
//! The caller must derive [`SenderKey`] from the authenticated session and the
//! channel from a server-validated channel enum. Never trust either field from a
//! chat packet. Pass elapsed time from a server-owned `std::time::Instant`;
//! timestamps supplied by clients and wall-clock time are unsuitable.
//!
//! One guard partitions its budgets by `(sender, channel)`. To prevent channel
//! hopping, first check a separate whole-user guard using a constant channel
//! (for example, `0`), then check this channel's guard with its actual channel ID.
//! Set the whole-user guard's `repeat_window` to [`Duration::ZERO`] if repeats
//! should only be suppressed within each channel. Both checks must happen before
//! expensive normalization, policy matching, or broadcast. A later rejection
//! deliberately does not refund either guard's token.
//!
//! Repeat protection stores keyed hashes, never message text. Its `RandomState`
//! key is generated when the guard is constructed and is not persisted. Hash
//! collisions can reject a different message (unlikely, but not impossible).
//! Matching is byte-exact: case, whitespace and Unicode-equivalent variants are
//! different unless the caller passes already-normalized content. Rate limits
//! apply even when messages differ. This module never bans an account.
//!
//! This is one process's state, not a distributed quota. Keep a guard alive and
//! route each account consistently to its owner, or use a shared authoritative
//! limiter. Synchronize shared access outside this module; checks require
//! exclusive `&mut self` access and have no hidden global state.

use std::collections::{hash_map::RandomState, HashMap, VecDeque};
use std::fmt;
use std::hash::BuildHasher;
use std::time::Duration;

/// Server-derived authenticated account identifier, not a packet-supplied ID.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct SenderKey(pub u64);

/// Limits for one guard. Configure independent guards for different policies.
#[derive(Debug, Clone, PartialEq)]
pub struct GuardConfig {
    /// Maximum tokens, including the initial burst; each attempt costs one.
    pub burst: u32,
    /// Finite, positive refill rate. Fractional rates are supported.
    pub tokens_per_second: f64,
    /// Reject larger UTF-8 payloads in O(1), before hashing or allocating state.
    pub max_message_bytes: usize,
    /// Maximum number of tracked `(sender, channel)` pairs.
    pub max_entries: usize,
    /// Idle entries can expire after this interval. Must cover full bucket
    /// refill plus `repeat_window`, so expiration cannot reset a live penalty.
    pub idle_ttl: Duration,
    /// Suppress an exact message accepted in this interval; zero disables it.
    pub repeat_window: Duration,
    /// Maximum accepted message hashes retained per entry. When all slots are
    /// live, new unique messages fail closed until one expires. Size this for
    /// the intended burst and accepted traffic during `repeat_window`.
    pub max_recent_messages: usize,
    /// Maximum entries inspected for idle expiration per check/maintenance call.
    pub prune_per_check: usize,
}

impl Default for GuardConfig {
    fn default() -> Self {
        Self {
            burst: 6,
            tokens_per_second: 2.0,
            max_message_bytes: 4096,
            max_entries: 16_384,
            idle_ttl: Duration::from_secs(60),
            repeat_window: Duration::from_secs(5),
            max_recent_messages: 16,
            prune_per_check: 8,
        }
    }
}

/// Invalid configuration is rejected before a guard can receive traffic.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GuardConfigError {
    ZeroBurst,
    InvalidRefillRate,
    ZeroMessageLimit,
    ZeroEntryLimit,
    ZeroRecentMessageLimit,
    ZeroPruneBudget,
    IdleTtlTooShort,
    StateSizeOverflow,
}

impl fmt::Display for GuardConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::ZeroBurst => "burst must be nonzero",
            Self::InvalidRefillRate => "tokens_per_second must be finite and positive",
            Self::ZeroMessageLimit => "max_message_bytes must be nonzero",
            Self::ZeroEntryLimit => "max_entries must be nonzero",
            Self::ZeroRecentMessageLimit => {
                "max_recent_messages must be nonzero when repeat protection is enabled"
            }
            Self::ZeroPruneBudget => "prune_per_check must be nonzero",
            Self::IdleTtlTooShort => "idle_ttl must cover full burst refill plus the repeat window",
            Self::StateSizeOverflow => "configured state size exceeds addressable memory",
        })
    }
}

impl std::error::Error for GuardConfigError {}

impl GuardConfig {
    pub fn validate(&self) -> Result<(), GuardConfigError> {
        if self.burst == 0 {
            return Err(GuardConfigError::ZeroBurst);
        }
        if !self.tokens_per_second.is_finite() || self.tokens_per_second <= 0.0 {
            return Err(GuardConfigError::InvalidRefillRate);
        }
        if self.max_message_bytes == 0 {
            return Err(GuardConfigError::ZeroMessageLimit);
        }
        if self.max_entries == 0 {
            return Err(GuardConfigError::ZeroEntryLimit);
        }
        if !self.repeat_window.is_zero() && self.max_recent_messages == 0 {
            return Err(GuardConfigError::ZeroRecentMessageLimit);
        }
        if self.prune_per_check == 0 {
            return Err(GuardConfigError::ZeroPruneBudget);
        }
        let refill_time = self
            .idle_ttl
            .checked_sub(self.repeat_window)
            .ok_or(GuardConfigError::IdleTtlTooShort)?;
        if refill_time.is_zero()
            || refill_time.as_secs_f64() * self.tokens_per_second < f64::from(self.burst)
        {
            return Err(GuardConfigError::IdleTtlTooShort);
        }
        // These are configuration values, never attacker-controlled inputs.
        // Check their product too, rather than allowing an accidental wrapping
        // size estimate when the server provisions a guard.
        self.max_entries
            .checked_mul(std::mem::size_of::<Entry>())
            .and_then(|entries| {
                self.max_entries
                    .checked_mul(self.max_recent_messages)
                    .and_then(|slots| slots.checked_mul(std::mem::size_of::<RecentMessage>()))
                    .and_then(|history| entries.checked_add(history))
            })
            .ok_or(GuardConfigError::StateSizeOverflow)?;
        Ok(())
    }
}

/// The reason a message must not proceed to policy matching or broadcast.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GuardRejection {
    /// Oversized input incurs no hashing, state allocation, or token charge.
    Oversize {
        limit_bytes: usize,
        actual_bytes: usize,
    },
    /// No live entry is evicted to admit an unknown key. Existing senders can
    /// still use their own quotas; bounded cleanup may free capacity later.
    Capacity {
        max_entries: usize,
    },
    RateLimited {
        retry_after: Duration,
    },
    /// A token was consumed before checking this repeated message.
    Duplicate {
        retry_after: Duration,
    },
    /// A token was consumed, but all bounded repeat-history slots are live.
    RecentHistoryFull {
        retry_after: Duration,
    },
}

impl fmt::Display for GuardRejection {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Oversize {
                limit_bytes,
                actual_bytes,
            } => write!(
                f,
                "message has {actual_bytes} bytes; limit is {limit_bytes}"
            ),
            Self::Capacity { max_entries } => {
                write!(f, "chat guard is at its {max_entries}-entry capacity")
            }
            Self::RateLimited { retry_after } => {
                write!(f, "rate limited; retry after {retry_after:?}")
            }
            Self::Duplicate { retry_after } => {
                write!(f, "duplicate message; retry after {retry_after:?}")
            }
            Self::RecentHistoryFull { retry_after } => {
                write!(
                    f,
                    "repeat-history capacity reached; retry after {retry_after:?}"
                )
            }
        }
    }
}

impl std::error::Error for GuardRejection {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct EntryKey {
    sender: SenderKey,
    channel: u16,
}

struct RecentMessage {
    fingerprint: u64,
    accepted_at: Duration,
}

struct Entry {
    tokens: f64,
    updated_at: Duration,
    last_activity: Duration,
    recent: VecDeque<RecentMessage>,
}

/// Bounded token buckets with exact-repeat suppression.
///
/// State is O(`max_entries * (1 + max_recent_messages)`), and a check does no
/// full-map scan. Repeat processing is O(`max_recent_messages`); hashing costs
/// O(message bytes) and only happens after the byte limit and rate check.
/// The single pruning-queue record per map entry never grows with message count.
pub struct ChatGuard {
    config: GuardConfig,
    entries: HashMap<EntryKey, Entry>,
    prune_queue: VecDeque<EntryKey>,
    repeat_hasher: RandomState,
    last_now: Duration,
}

impl ChatGuard {
    pub fn new(config: GuardConfig) -> Result<Self, GuardConfigError> {
        config.validate()?;
        Ok(Self {
            config,
            entries: HashMap::new(),
            prune_queue: VecDeque::new(),
            repeat_hasher: RandomState::new(),
            last_now: Duration::ZERO,
        })
    }

    /// Check one ingress message, atomically updating this guard's own state.
    ///
    /// `now` is elapsed monotonic time from the same server-owned origin for all
    /// calls. A reversed time is clamped to the highest previously observed time,
    /// never grants extra refill, and never panics. Rejected in-limit attempts
    /// keep existing entries active; repeated rejected floods are not free.
    /// The retry interval describes this rejection, not a reservation or promise
    /// that other guards, the bucket, or policy matching will accept a retry.
    pub fn check(
        &mut self,
        sender: SenderKey,
        channel: u16,
        content: &str,
        now: Duration,
    ) -> Result<(), GuardRejection> {
        if content.len() > self.config.max_message_bytes {
            return Err(GuardRejection::Oversize {
                limit_bytes: self.config.max_message_bytes,
                actual_bytes: content.len(),
            });
        }
        let now = self.advance_time(now);
        self.prune_at(now);
        let key = EntryKey { sender, channel };
        if !self.entries.contains_key(&key) {
            if self.entries.len() >= self.config.max_entries {
                return Err(GuardRejection::Capacity {
                    max_entries: self.config.max_entries,
                });
            }
            self.entries.insert(
                key,
                Entry {
                    tokens: f64::from(self.config.burst),
                    updated_at: now,
                    last_activity: now,
                    recent: VecDeque::new(),
                },
            );
            self.prune_queue.push_back(key);
        }
        // The entry is present: either it survived bounded pruning or it was
        // inserted immediately above. No pruning occurs while it is borrowed.
        let entry = self.entries.get_mut(&key).expect("entry was just ensured");
        let elapsed = now.saturating_sub(entry.updated_at).as_secs_f64();
        entry.tokens = (entry.tokens + elapsed * self.config.tokens_per_second)
            .min(f64::from(self.config.burst));
        entry.updated_at = now;
        entry.last_activity = now;
        if entry.tokens < 1.0 {
            // Add one nanosecond to avoid rounding a fractional interval down
            // and inviting an immediate retry before a token is available.
            let retry_after =
                Duration::try_from_secs_f64((1.0 - entry.tokens) / self.config.tokens_per_second)
                    .unwrap_or(Duration::MAX)
                    .saturating_add(Duration::from_nanos(1));
            return Err(GuardRejection::RateLimited { retry_after });
        }
        entry.tokens -= 1.0;

        if self.config.repeat_window.is_zero() {
            return Ok(());
        }
        while entry.recent.front().is_some_and(|recent| {
            now.saturating_sub(recent.accepted_at) >= self.config.repeat_window
        }) {
            entry.recent.pop_front();
        }
        let fingerprint = self.repeat_hasher.hash_one(content);
        if let Some(recent) = entry
            .recent
            .iter()
            .find(|recent| recent.fingerprint == fingerprint)
        {
            return Err(GuardRejection::Duplicate {
                retry_after: self
                    .config
                    .repeat_window
                    .saturating_sub(now.saturating_sub(recent.accepted_at)),
            });
        }
        if entry.recent.len() >= self.config.max_recent_messages {
            let oldest = entry.recent.front().expect("positive full history");
            return Err(GuardRejection::RecentHistoryFull {
                retry_after: self
                    .config
                    .repeat_window
                    .saturating_sub(now.saturating_sub(oldest.accepted_at)),
            });
        }
        entry.recent.push_back(RecentMessage {
            fingerprint,
            accepted_at: now,
        });
        Ok(())
    }

    /// Perform one bounded cleanup step, useful when traffic is quiet.
    ///
    /// Inspects at most `prune_per_check` entries, returning the count removed.
    /// Capacity may remain full while expired entries await a later queue turn;
    /// admission fails closed during that interval.
    pub fn prune_expired(&mut self, now: Duration) -> usize {
        let now = self.advance_time(now);
        self.prune_at(now)
    }

    pub fn tracked_entries(&self) -> usize {
        self.entries.len()
    }

    pub fn config(&self) -> &GuardConfig {
        &self.config
    }

    fn advance_time(&mut self, now: Duration) -> Duration {
        self.last_now = self.last_now.max(now);
        self.last_now
    }

    fn prune_at(&mut self, now: Duration) -> usize {
        let mut removed = 0;
        let budget = self.config.prune_per_check.min(self.prune_queue.len());
        for _ in 0..budget {
            let key = self.prune_queue.pop_front().expect("bounded queue length");
            let expired = self.entries.get(&key).is_some_and(|entry| {
                now.saturating_sub(entry.last_activity) >= self.config.idle_ttl
            });
            if expired {
                self.entries.remove(&key);
                removed += 1;
            } else {
                self.prune_queue.push_back(key);
            }
        }
        removed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> GuardConfig {
        GuardConfig {
            burst: 3,
            tokens_per_second: 1.0,
            max_message_bytes: 64,
            max_entries: 4,
            idle_ttl: Duration::from_secs(10),
            repeat_window: Duration::from_secs(2),
            max_recent_messages: 8,
            prune_per_check: 1,
        }
    }

    fn no_repeats() -> GuardConfig {
        GuardConfig {
            repeat_window: Duration::ZERO,
            max_recent_messages: 0,
            ..config()
        }
    }

    #[test]
    fn burst_and_fractional_refill_are_enforced() {
        let mut guard = ChatGuard::new(no_repeats()).unwrap();
        let sender = SenderKey(7);
        for _ in 0..3 {
            assert_eq!(guard.check(sender, 0, "message", Duration::ZERO), Ok(()));
        }
        assert!(matches!(
            guard.check(sender, 0, "message", Duration::ZERO),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert!(matches!(
            guard.check(sender, 0, "message", Duration::from_millis(500)),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(
            guard.check(sender, 0, "message", Duration::from_secs(1)),
            Ok(())
        );
        assert!(matches!(
            guard.check(sender, 0, "message", Duration::from_secs(1)),
            Err(GuardRejection::RateLimited { .. })
        ));
    }

    #[test]
    fn retries_have_a_positive_safe_delay() {
        let mut cfg = no_repeats();
        cfg.burst = 1;
        cfg.tokens_per_second = f64::MAX;
        let mut guard = ChatGuard::new(cfg).unwrap();
        assert_eq!(guard.check(SenderKey(1), 0, "x", Duration::ZERO), Ok(()));
        assert_eq!(
            guard.check(SenderKey(1), 0, "x", Duration::ZERO),
            Err(GuardRejection::RateLimited {
                retry_after: Duration::from_nanos(1)
            })
        );
        assert_eq!(
            guard.check(SenderKey(1), 0, "x", Duration::from_nanos(1)),
            Ok(())
        );
    }

    #[test]
    fn backward_time_never_refills_or_panics() {
        let mut cfg = no_repeats();
        cfg.burst = 1;
        let mut guard = ChatGuard::new(cfg).unwrap();
        assert_eq!(
            guard.check(SenderKey(1), 0, "a", Duration::from_secs(10)),
            Ok(())
        );
        for time in [
            Duration::ZERO,
            Duration::from_secs(9),
            Duration::from_secs(10),
        ] {
            assert!(matches!(
                guard.check(SenderKey(1), 0, "b", time),
                Err(GuardRejection::RateLimited { .. })
            ));
        }
        assert_eq!(
            guard.check(SenderKey(1), 0, "b", Duration::from_secs(11)),
            Ok(())
        );
        assert_eq!(guard.prune_expired(Duration::ZERO), 0);
    }

    #[test]
    fn duplicate_rejections_cost_tokens_and_keep_original_expiry() {
        let mut guard = ChatGuard::new(config()).unwrap();
        assert_eq!(guard.check(SenderKey(1), 0, "a", Duration::ZERO), Ok(()));
        for _ in 0..2 {
            assert_eq!(
                guard.check(SenderKey(1), 0, "a", Duration::ZERO),
                Err(GuardRejection::Duplicate {
                    retry_after: Duration::from_secs(2)
                })
            );
        }
        assert!(matches!(
            guard.check(SenderKey(1), 0, "a", Duration::ZERO),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(
            guard.check(SenderKey(1), 0, "a", Duration::from_secs(2)),
            Ok(())
        );
    }

    #[test]
    fn alternating_messages_do_not_evict_repeat_history() {
        let mut cfg = config();
        cfg.burst = 5;
        cfg.max_recent_messages = 2;
        let mut guard = ChatGuard::new(cfg).unwrap();
        for message in ["a", "b"] {
            assert_eq!(
                guard.check(SenderKey(1), 0, message, Duration::ZERO),
                Ok(())
            );
        }
        assert!(matches!(
            guard.check(SenderKey(1), 0, "a", Duration::ZERO),
            Err(GuardRejection::Duplicate { .. })
        ));
        assert!(matches!(
            guard.check(SenderKey(1), 0, "c", Duration::ZERO),
            Err(GuardRejection::RecentHistoryFull { .. })
        ));
        assert!(matches!(
            guard.check(SenderKey(1), 0, "b", Duration::ZERO),
            Err(GuardRejection::Duplicate { .. })
        ));
        assert!(matches!(
            guard.check(SenderKey(1), 0, "c", Duration::ZERO),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(
            guard.check(SenderKey(1), 0, "c", Duration::from_secs(2)),
            Ok(())
        );
    }

    #[test]
    fn hashes_are_byte_exact_and_scoped_to_sender_and_channel() {
        let mut guard = ChatGuard::new(config()).unwrap();
        for (sender, channel, message) in [
            (1, 0, "hello"),
            (1, 0, "Hello"),
            (1, 1, "hello"),
            (2, 0, "hello"),
        ] {
            assert_eq!(
                guard.check(SenderKey(sender), channel, message, Duration::ZERO),
                Ok(())
            );
        }
        assert!(matches!(
            guard.check(SenderKey(1), 0, "hello", Duration::ZERO),
            Err(GuardRejection::Duplicate { .. })
        ));
    }

    #[test]
    fn whole_user_guard_prevents_channel_hopping() {
        let mut global_config = no_repeats();
        global_config.burst = 2;
        let mut global = ChatGuard::new(global_config).unwrap();
        let mut per_channel = ChatGuard::new(no_repeats()).unwrap();
        let mut ingress = |channel| {
            global.check(SenderKey(42), 0, "x", Duration::ZERO)?;
            per_channel.check(SenderKey(42), channel, "x", Duration::ZERO)
        };
        assert_eq!(ingress(1), Ok(()));
        assert_eq!(ingress(2), Ok(()));
        assert!(matches!(
            ingress(3),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(global.tracked_entries(), 1);
        assert_eq!(per_channel.tracked_entries(), 2);
    }

    #[test]
    fn capacity_is_fail_closed_and_does_not_evict_existing_senders() {
        let mut cfg = no_repeats();
        cfg.burst = 1;
        cfg.max_entries = 1;
        let mut guard = ChatGuard::new(cfg).unwrap();
        assert_eq!(guard.check(SenderKey(1), 0, "x", Duration::ZERO), Ok(()));
        for sender in 2..100 {
            assert_eq!(
                guard.check(SenderKey(sender), 0, "x", Duration::ZERO),
                Err(GuardRejection::Capacity { max_entries: 1 })
            );
        }
        assert!(matches!(
            guard.check(SenderKey(1), 0, "x", Duration::ZERO),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(
            guard.check(SenderKey(1), 0, "x", Duration::from_secs(1)),
            Ok(())
        );
        assert_eq!(guard.tracked_entries(), 1);
        assert_eq!(guard.prune_queue.len(), 1);
    }

    #[test]
    fn expiration_is_incremental_and_reclaims_capacity() {
        let mut cfg = no_repeats();
        cfg.max_entries = 4;
        let mut guard = ChatGuard::new(cfg).unwrap();
        for sender in 0..4 {
            assert_eq!(
                guard.check(SenderKey(sender), 0, "x", Duration::ZERO),
                Ok(())
            );
        }
        assert_eq!(guard.prune_expired(Duration::from_secs(9)), 0);
        assert_eq!(guard.prune_expired(Duration::from_secs(10)), 1);
        assert_eq!(guard.tracked_entries(), 3);
        assert_eq!(guard.prune_expired(Duration::from_secs(10)), 1);
        assert_eq!(guard.tracked_entries(), 2);
        assert_eq!(
            guard.check(SenderKey(100), 0, "x", Duration::from_secs(10)),
            Ok(())
        );
        assert_eq!(guard.tracked_entries(), 2);
        assert_eq!(guard.prune_queue.len(), guard.tracked_entries());
    }

    #[test]
    fn repeated_activity_cannot_grow_the_pruning_queue() {
        let mut cfg = no_repeats();
        cfg.burst = 1;
        let mut guard = ChatGuard::new(cfg).unwrap();
        for _ in 0..10_000 {
            let _ = guard.check(SenderKey(1), 0, "x", Duration::ZERO);
        }
        assert_eq!(guard.entries.len(), 1);
        assert_eq!(guard.prune_queue.len(), 1);
    }

    #[test]
    fn rejected_attempts_prevent_idle_expiration_of_live_penalties() {
        let mut cfg = no_repeats();
        cfg.burst = 1;
        cfg.tokens_per_second = 0.1;
        cfg.idle_ttl = Duration::from_secs(10);
        let mut guard = ChatGuard::new(cfg).unwrap();
        assert_eq!(guard.check(SenderKey(1), 0, "x", Duration::ZERO), Ok(()));
        assert!(matches!(
            guard.check(SenderKey(1), 0, "x", Duration::from_secs(9)),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(guard.prune_expired(Duration::from_secs(10)), 0);
        assert_eq!(guard.tracked_entries(), 1);
        assert_eq!(guard.prune_expired(Duration::from_secs(18)), 0);
        assert_eq!(guard.prune_expired(Duration::from_secs(19)), 1);
    }

    #[test]
    fn mixed_adversarial_traffic_preserves_all_state_bounds() {
        use std::collections::HashSet;

        let cfg = config();
        let mut guard = ChatGuard::new(cfg.clone()).unwrap();
        let mut random = 42_u64;
        for step in 0..20_000_u64 {
            random = random.wrapping_mul(6364136223846793005).wrapping_add(1);
            let sender = SenderKey((random >> 32) % 20);
            let channel = ((random >> 20) % 3) as u16;
            // Include same-time and backwards observations, unique messages,
            // duplicate messages, idle expiration, and more keys than capacity.
            let now = Duration::from_millis(step.saturating_sub(random % 100) * 20);
            let message = match random % 3 {
                0 => "first",
                1 => "second",
                _ => "third",
            };
            let _ = guard.check(sender, channel, message, now);
            assert!(guard.entries.len() <= cfg.max_entries);
            assert_eq!(guard.entries.len(), guard.prune_queue.len());
            assert_eq!(
                guard
                    .prune_queue
                    .iter()
                    .copied()
                    .collect::<HashSet<_>>()
                    .len(),
                guard.entries.len()
            );
            assert!(guard
                .prune_queue
                .iter()
                .all(|key| guard.entries.contains_key(key)));
            assert!(guard.entries.values().all(|entry| {
                entry.recent.len() <= cfg.max_recent_messages
                    && entry.tokens.is_finite()
                    && entry.tokens >= 0.0
                    && entry.tokens <= f64::from(cfg.burst)
            }));
        }
    }

    #[test]
    fn oversize_is_rejected_before_state_allocation_or_token_use() {
        let mut cfg = no_repeats();
        cfg.burst = 1;
        cfg.max_message_bytes = 3;
        let mut guard = ChatGuard::new(cfg).unwrap();
        assert_eq!(
            guard.check(SenderKey(99), 0, "abcd", Duration::ZERO),
            Err(GuardRejection::Oversize {
                limit_bytes: 3,
                actual_bytes: 4
            })
        );
        assert_eq!(guard.tracked_entries(), 0);
        assert_eq!(guard.check(SenderKey(99), 0, "abc", Duration::ZERO), Ok(()));
        assert!(matches!(
            guard.check(SenderKey(99), 0, "abcd", Duration::ZERO),
            Err(GuardRejection::Oversize { .. })
        ));
        assert!(matches!(
            guard.check(SenderKey(99), 0, "abc", Duration::ZERO),
            Err(GuardRejection::RateLimited { .. })
        ));
    }

    #[test]
    fn large_elapsed_times_are_safe_and_buckets_stay_capped() {
        let mut guard = ChatGuard::new(no_repeats()).unwrap();
        assert_eq!(guard.check(SenderKey(1), 0, "x", Duration::ZERO), Ok(()));
        for _ in 0..3 {
            assert_eq!(guard.check(SenderKey(1), 0, "x", Duration::MAX), Ok(()));
        }
        assert!(matches!(
            guard.check(SenderKey(1), 0, "x", Duration::MAX),
            Err(GuardRejection::RateLimited { .. })
        ));
        assert_eq!(guard.prune_expired(Duration::ZERO), 0);
    }

    #[test]
    fn configuration_validation_covers_invalid_and_edge_values() {
        assert_eq!(config().validate(), Ok(()));
        assert_eq!(GuardConfig::default().validate(), Ok(()));
        assert_eq!(no_repeats().validate(), Ok(()));
        for rate in [0.0, -1.0, f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(
                GuardConfig {
                    tokens_per_second: rate,
                    ..config()
                }
                .validate(),
                Err(GuardConfigError::InvalidRefillRate)
            );
        }
        for (cfg, expected) in [
            (
                GuardConfig {
                    burst: 0,
                    ..config()
                },
                GuardConfigError::ZeroBurst,
            ),
            (
                GuardConfig {
                    max_message_bytes: 0,
                    ..config()
                },
                GuardConfigError::ZeroMessageLimit,
            ),
            (
                GuardConfig {
                    max_entries: 0,
                    ..config()
                },
                GuardConfigError::ZeroEntryLimit,
            ),
            (
                GuardConfig {
                    max_recent_messages: 0,
                    ..config()
                },
                GuardConfigError::ZeroRecentMessageLimit,
            ),
            (
                GuardConfig {
                    prune_per_check: 0,
                    ..config()
                },
                GuardConfigError::ZeroPruneBudget,
            ),
            (
                GuardConfig {
                    idle_ttl: Duration::ZERO,
                    ..config()
                },
                GuardConfigError::IdleTtlTooShort,
            ),
            (
                GuardConfig {
                    idle_ttl: Duration::from_secs(4),
                    ..config()
                },
                GuardConfigError::IdleTtlTooShort,
            ),
            (
                GuardConfig {
                    tokens_per_second: f64::MIN_POSITIVE,
                    ..config()
                },
                GuardConfigError::IdleTtlTooShort,
            ),
            (
                GuardConfig {
                    max_entries: usize::MAX,
                    ..config()
                },
                GuardConfigError::StateSizeOverflow,
            ),
        ] {
            assert_eq!(cfg.validate(), Err(expected));
            assert!(ChatGuard::new(cfg).is_err());
        }
        assert_eq!(
            GuardConfig {
                idle_ttl: Duration::from_secs(5),
                ..config()
            }
            .validate(),
            Ok(())
        );
    }
}
