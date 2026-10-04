// Transport-independent authoritative server integration.
//
// Adapt AuthenticatedSession only at your auth boundary. NEVER deserialize it,
// SenderKey, permissions, or receive timestamps from the client's JSON packet.
// This example deliberately contains no networking, raw chat logging, or bans.
use std::{
    collections::HashMap,
    time::{Duration, Instant},
};
use xexoria_chat_filter::{
    guard::{ChatGuard, GuardConfig, GuardRejection, SenderKey},
    Filter, Verdict,
};

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
enum Channel {
    World,
    Party,
    Trade,
}
impl Channel {
    fn id(self) -> u16 {
        match self {
            Self::World => 1,
            Self::Party => 2,
            Self::Trade => 3,
        }
    }
}
struct AuthenticatedSession {
    account: SenderKey,
    in_party: bool,
    may_trade: bool,
}
impl AuthenticatedSession {
    fn may_send(&self, channel: Channel) -> bool {
        match channel {
            Channel::World => true,
            Channel::Party => self.in_party,
            Channel::Trade => self.may_trade,
        }
    }
}
#[derive(Debug, PartialEq)]
enum Outcome {
    Broadcast { text: String },
    Withheld { code: &'static str }, // generic response; don't reveal dictionary to clients
}
struct ChatService {
    started: Instant,
    global_guard: ChatGuard,
    channel_guards: HashMap<Channel, ChatGuard>,
    filter: Filter,
}
impl ChatService {
    fn new() -> Self {
        // Across every channel: each account gets six attempts, then 2/sec.
        // Global duplicate suppression also catches EXACT repeats across channels.
        let global_guard = ChatGuard::new(GuardConfig::default()).unwrap();
        let mut channel_guards = HashMap::new();
        for channel in [Channel::World, Channel::Party, Channel::Trade] {
            let (burst, rate) = match channel {
                Channel::World => (4, 1.0),
                Channel::Party => (6, 2.0),
                Channel::Trade => (2, 0.2),
            };
            let config = GuardConfig {
                burst,
                tokens_per_second: rate,
                repeat_window: Duration::ZERO,
                ..GuardConfig::default()
            };
            channel_guards.insert(channel, ChatGuard::new(config).unwrap());
        }
        Self {
            started: Instant::now(),
            global_guard,
            channel_guards,
            filter: Filter::seed().unwrap(),
        }
    }
    fn receive(&mut self, session: &AuthenticatedSession, channel: Channel, text: &str) -> Outcome {
        self.receive_at(session, channel, text, self.started.elapsed())
    }
    fn receive_at(
        &mut self,
        session: &AuthenticatedSession,
        channel: Channel,
        text: &str,
        now: Duration,
    ) -> Outcome {
        // Edge/transport must also enforce maximum frame size BEFORE decoding.
        if !session.may_send(channel) {
            return Outcome::Withheld {
                code: "channel_forbidden",
            };
        }
        // Charge attempts before control checks, normalization, moderation, or publish.
        if let Err(reason) = self.global_guard.check(session.account, 0, text, now) {
            return guard_response(reason);
        }
        let guard = self
            .channel_guards
            .get_mut(&channel)
            .expect("closed server-owned channel enum");
        if let Err(reason) = guard.check(session.account, channel.id(), text, now) {
            return guard_response(reason);
        }
        if text.trim().is_empty()
            || text.chars().any(forbidden_format_or_control)
            || text.chars().all(spacing_or_invisible)
        {
            return Outcome::Withheld {
                code: "invalid_message",
            };
        }
        let report = self.filter.inspect(text);
        match report.verdict() {
            Verdict::Allow => Outcome::Broadcast {
                text: text.to_owned(),
            },
            Verdict::Mask => Outcome::Broadcast {
                text: report.masked(),
            },
            Verdict::Review => {
                // Count aggregate reason/rule IDs without raw chat text or account IDs.
                // This runnable example simply holds/rejects the message. A real review
                // queue must be explicitly bounded; overflow also withholds.
                Outcome::Withheld {
                    code: "review_required",
                }
            }
            Verdict::Reject => Outcome::Withheld {
                code: "invalid_message",
            },
        }
    }
}
// Targeted ingress safety for English/Thai channels, not full Unicode spoof analysis.
// Do not reject ZWJ globally: it is needed by emoji sequences.
fn forbidden_format_or_control(c: char) -> bool {
    c.is_control()
        || matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
}
fn spacing_or_invisible(c: char) -> bool {
    c.is_whitespace()
        || unicode_normalization::char::is_combining_mark(c)
        || matches!(c, '\u{00ad}' | '\u{200b}'..='\u{200d}' | '\u{2060}' | '\u{feff}' | '\u{fe00}'..='\u{fe0f}' | '\u{e0100}'..='\u{e01ef}')
}
fn guard_response(reason: GuardRejection) -> Outcome {
    let code = match reason {
        GuardRejection::Oversize { .. } => "message_too_long",
        GuardRejection::RateLimited { .. } => "slow_down",
        GuardRejection::Duplicate { .. } => "duplicate",
        GuardRejection::Capacity { .. } | GuardRejection::RecentHistoryFull { .. } => "chat_busy",
    };
    Outcome::Withheld { code }
}
fn main() {
    let mut service = ChatService::new();
    // Represents a successful trusted server authentication result.
    let session = AuthenticatedSession {
        account: SenderKey(42),
        in_party: true,
        may_trade: false,
    };
    println!(
        "{:?}",
        service.receive(&session, Channel::Party, "สวัสดีครับ ไปตีบอสกัน")
    );
    println!("{:?}", service.receive(&session, Channel::Party, "fuck!"));
}
#[test]
fn held_and_forbidden_messages_never_reach_broadcast() {
    let mut service = ChatService::new();
    let session = AuthenticatedSession {
        account: SenderKey(42),
        in_party: true,
        may_trade: false,
    };
    assert!(matches!(
        service.receive_at(&session, Channel::Party, "ควย", Duration::ZERO),
        Outcome::Withheld {
            code: "review_required"
        }
    ));
    assert!(
        matches!(service.receive_at(&session, Channel::Party, "fuck!", Duration::from_secs(1)), Outcome::Broadcast { text } if text == "****!")
    );
    assert!(matches!(
        service.receive_at(&session, Channel::Trade, "hello", Duration::from_secs(2)),
        Outcome::Withheld {
            code: "channel_forbidden"
        }
    ));
}
#[test]
fn cross_channel_repeats_and_floods_are_held() {
    let mut service = ChatService::new();
    let session = AuthenticatedSession {
        account: SenderKey(99),
        in_party: true,
        may_trade: true,
    };
    assert!(matches!(
        service.receive_at(&session, Channel::World, "hello", Duration::ZERO),
        Outcome::Broadcast { .. }
    ));
    assert!(matches!(
        service.receive_at(&session, Channel::Party, "hello", Duration::ZERO),
        Outcome::Withheld { code: "duplicate" }
    ));
    for i in 0..4 {
        let _ = service.receive_at(
            &session,
            Channel::Party,
            &format!("message {i}"),
            Duration::ZERO,
        );
    }
    assert!(matches!(
        service.receive_at(&session, Channel::Trade, "more", Duration::ZERO),
        Outcome::Withheld { code: "slow_down" }
    ));
}

#[test]
fn formatting_only_and_bidi_controls_are_held_but_emoji_survives() {
    let mut service = ChatService::new();
    let session = AuthenticatedSession {
        account: SenderKey(88),
        in_party: true,
        may_trade: false,
    };
    for (i, text) in ["\u{202e}hello", "\u{2066}hello\u{2069}", "\u{200b}\u{200d}"]
        .iter()
        .enumerate()
    {
        assert!(matches!(
            service.receive_at(
                &session,
                Channel::Party,
                text,
                Duration::from_secs(i as u64)
            ),
            Outcome::Withheld {
                code: "invalid_message"
            }
        ));
    }
    assert!(matches!(
        service.receive_at(&session, Channel::Party, "👩‍👩‍👧‍👦", Duration::from_secs(4)),
        Outcome::Broadcast { .. }
    ));
}
