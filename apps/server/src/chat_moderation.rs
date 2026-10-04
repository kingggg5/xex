//! Shared, bounded chat admission. No raw chat/identity is logged or retained.
use crate::auth::SessionId;
use std::collections::hash_map::RandomState;
use std::hash::BuildHasher;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use xexoria_chat_filter::guard::{ChatGuard, GuardConfig, GuardRejection, SenderKey};
use xexoria_chat_filter::{Config, Filter, Verdict};

#[derive(Clone, Copy, Hash)]
pub(crate) enum ChatIdentity {
    Principal(uuid::Uuid),
    Session(SessionId),
}

#[derive(Clone, Copy)]
pub(crate) enum ChatLane {
    Room = 1,
    Group = 2,
    Megaphone = 3,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChatRejection {
    ReviewRequired,
    InvalidMessage,
    RateLimited,
    Duplicate,
    Unavailable,
}
impl ChatRejection {
    pub fn key(self) -> &'static str {
        match self {
            Self::ReviewRequired => "chat_review_required",
            Self::InvalidMessage => "chat_invalid_message",
            Self::RateLimited => "chat_rate_limited",
            Self::Duplicate => "chat_duplicate",
            Self::Unavailable => "chat_unavailable",
        }
    }
}

/// Only successful admission can construct this type; callers cannot broadcast a Review.
pub(crate) struct PreparedChat(String);
impl PreparedChat {
    pub(crate) fn text(&self) -> &str {
        &self.0
    }
}

struct Guards {
    global: ChatGuard,
    channel: ChatGuard,
}
pub(crate) struct ChatModeration {
    filter: Filter,
    guards: Mutex<Guards>,
    identities: RandomState,
    clock: Instant,
}

impl ChatModeration {
    pub(crate) fn new() -> Self {
        let filter = Filter::from_tsv(
            include_str!("../vendor/xexoria-chat-filter/policy.tsv"),
            include_str!("../vendor/xexoria-chat-filter/exceptions.tsv"),
            Config {
                max_input_bytes: 512,
                max_normalized_bytes: 2048,
                max_candidates: 256,
                max_findings: 32,
                ..Config::default()
            },
        )
        .expect("embedded chat policy must be valid");
        let common = GuardConfig {
            max_message_bytes: 512,
            max_entries: 1024,
            ..GuardConfig::default()
        };
        let global = ChatGuard::new(GuardConfig {
            repeat_window: Duration::ZERO,
            ..common.clone()
        })
        .expect("fixed global chat budget must be valid");
        let channel = ChatGuard::new(GuardConfig {
            max_entries: 3072,
            ..common
        })
        .expect("fixed channel chat budget must be valid");
        Self {
            filter,
            guards: Mutex::new(Guards { global, channel }),
            identities: RandomState::new(),
            clock: Instant::now(),
        }
    }

    pub(crate) fn prepare(
        &self,
        sender: ChatIdentity,
        lane: ChatLane,
        text: &str,
    ) -> Result<PreparedChat, ChatRejection> {
        self.prepare_at(sender, lane, text, self.clock.elapsed())
    }

    fn prepare_at(
        &self,
        sender: ChatIdentity,
        lane: ChatLane,
        text: &str,
        now: Duration,
    ) -> Result<PreparedChat, ChatRejection> {
        // Hash the full authenticated identity: UUIDv7 prefixes/public handles are not unique keys.
        let key = SenderKey(self.identities.hash_one(sender));
        {
            let mut guards = self.guards.lock().map_err(|_| ChatRejection::Unavailable)?;
            guards
                .global
                .check(key, 0, text, now)
                .map_err(guard_rejection)?;
            guards
                .channel
                .check(key, lane as u16, text, now)
                .map_err(guard_rejection)?;
        }
        // Policy matching happens outside both the social and quota locks.
        if text.trim().is_empty()
            || text.chars().any(forbidden_format)
            || text.chars().all(|c| c.is_whitespace() || invisible(c))
        {
            return Err(ChatRejection::InvalidMessage);
        }
        let report = self.filter.inspect(text);
        if !report.complete() {
            return Err(ChatRejection::ReviewRequired);
        }
        match report.verdict() {
            Verdict::Allow => Ok(PreparedChat(text.to_owned())),
            Verdict::Mask => Ok(PreparedChat(report.masked())),
            Verdict::Review => Err(ChatRejection::ReviewRequired),
            Verdict::Reject => Err(ChatRejection::InvalidMessage),
        }
    }
}

fn guard_rejection(reason: GuardRejection) -> ChatRejection {
    match reason {
        GuardRejection::Oversize { .. } => ChatRejection::InvalidMessage,
        GuardRejection::RateLimited { .. } => ChatRejection::RateLimited,
        GuardRejection::Duplicate { .. } => ChatRejection::Duplicate,
        GuardRejection::Capacity { .. } | GuardRejection::RecentHistoryFull { .. } => {
            ChatRejection::Unavailable
        }
    }
}
fn forbidden_format(c: char) -> bool {
    c.is_control()
        || matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
}
fn invisible(c: char) -> bool {
    matches!(
        c,
        '\u{00ad}' | '\u{200b}' | '\u{200c}' | '\u{200d}' | '\u{2060}' | '\u{feff}'
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sender(n: u8) -> ChatIdentity {
        ChatIdentity::Session([n; 32])
    }
    #[test]
    fn english_masks_but_safe_thai_and_emoji_survive() {
        let gate = ChatModeration::new();
        assert_eq!(
            gate.prepare(sender(1), ChatLane::Room, "FUCK!")
                .unwrap()
                .text(),
            "****!"
        );
        assert_eq!(
            gate.prepare(sender(2), ChatLane::Group, "สวัสดีครับ 👨‍👩‍👧‍👦")
                .unwrap()
                .text(),
            "สวัสดีครับ 👨‍👩‍👧‍👦"
        );
        assert_eq!(
            gate.prepare(sender(3), ChatLane::Room, "ใบไม้เหี่ยว แมงมุม")
                .unwrap()
                .text(),
            "ใบไม้เหี่ยว แมงมุม"
        );
    }
    #[test]
    fn uncertain_obfuscated_and_invisible_wrappers_never_publish() {
        let gate = ChatModeration::new();
        for (n, text) in ["bitch", "ควย", "f.u.c.k", "\u{200b}fuck", "fuck\u{200d}"]
            .into_iter()
            .enumerate()
        {
            let result = gate.prepare(sender(n as u8), ChatLane::Room, text);
            if let Ok(prepared) = result {
                assert!(!prepared.text().contains("fuck"));
            } else {
                assert!(matches!(result, Err(ChatRejection::ReviewRequired)));
            }
        }
    }
    #[test]
    fn global_budget_cannot_reset_by_switching_channels() {
        let gate = ChatModeration::new();
        let now = Duration::ZERO;
        for n in 0..6 {
            gate.prepare_at(
                sender(7),
                [ChatLane::Room, ChatLane::Group, ChatLane::Megaphone][n % 3],
                &format!("message {n}"),
                now,
            )
            .unwrap();
        }
        assert!(matches!(
            gate.prepare_at(sender(7), ChatLane::Group, "another", now),
            Err(ChatRejection::RateLimited)
        ));
        assert!(
            gate.prepare_at(sender(8), ChatLane::Room, "another", now)
                .is_ok()
        );
        assert!(
            gate.prepare_at(
                sender(7),
                ChatLane::Room,
                "refilled",
                Duration::from_secs(1)
            )
            .is_ok()
        );
    }
    #[test]
    fn exact_repeats_and_invalid_format_withhold_without_banning() {
        let gate = ChatModeration::new();
        gate.prepare_at(sender(9), ChatLane::Room, "hello", Duration::ZERO)
            .unwrap();
        assert!(matches!(
            gate.prepare_at(sender(9), ChatLane::Room, "hello", Duration::from_secs(1)),
            Err(ChatRejection::Duplicate)
        ));
        assert!(
            gate.prepare_at(sender(9), ChatLane::Room, "hello", Duration::from_secs(6))
                .is_ok()
        );
        for (n, text) in ["\u{200b}", "\u{202e}hello", "hello\n"]
            .into_iter()
            .enumerate()
        {
            assert!(matches!(
                gate.prepare(sender(n as u8), ChatLane::Room, text),
                Err(ChatRejection::InvalidMessage)
            ));
        }
        assert!(matches!(
            gate.prepare(sender(12), ChatLane::Room, &"a".repeat(513)),
            Err(ChatRejection::InvalidMessage)
        ));
    }
    #[test]
    fn full_principal_identity_survives_new_sessions_and_clones() {
        let gate = ChatModeration::new();
        let id = uuid::Uuid::from_u128(123);
        gate.prepare_at(
            ChatIdentity::Principal(id),
            ChatLane::Room,
            "same account",
            Duration::ZERO,
        )
        .unwrap();
        assert!(matches!(
            gate.prepare_at(
                ChatIdentity::Principal(id),
                ChatLane::Room,
                "same account",
                Duration::from_secs(1)
            ),
            Err(ChatRejection::Duplicate)
        ));
        assert!(
            gate.prepare_at(
                ChatIdentity::Principal(uuid::Uuid::from_u128(124)),
                ChatLane::Room,
                "same account",
                Duration::from_secs(1)
            )
            .is_ok()
        );
    }
}
