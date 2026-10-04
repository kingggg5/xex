//! Real room/social publication tests. No sockets, database or external service.
//! Root registers this sibling module with `#[cfg(test)] mod` in lib.rs.
use crate::auth::SessionId;
use crate::character::{CharacterStore, identity_for_session};
use crate::chat_moderation::ChatRejection;
use crate::community::Device;
use crate::room::{ConnectionOutputs, RELIABLE_BOUND, RoomCommand, RoomHandle};
use crate::social::{PresenceGuard, PresenceKind, SocialHub};
use serde_json::{Value, json};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;

const DEADLINE: Duration = Duration::from_secs(3);

struct PrivateRooms {
    social: Arc<SocialHub>,
    rooms: Vec<RoomHandle>,
}

impl PrivateRooms {
    fn new(count: usize) -> Self {
        let store = CharacterStore::shared();
        let social = Arc::new(SocialHub::new(
            store.clone(),
            crate::world::character_record_seed(&crate::content::test_content()),
        ));
        let (rooms, _) = RoomHandle::spawn_all(count, &store, &social).expect("private rooms");
        Self { social, rooms }
    }

    async fn join(&self, room: usize, byte: u8) -> Peer {
        let session = [byte; 32];
        let (welcome, outputs) = self.rooms[room].join(session).await.expect("private join");
        let (handle, name) = identity_for_session(session);
        let guard = self.social.join_guard(
            session,
            PresenceKind::Normal {
                channel: room as u8,
            },
            handle,
            name.clone(),
            self.rooms[room].clone(),
        );
        Peer {
            session,
            epoch: welcome.epoch,
            name,
            room: self.rooms[room].clone(),
            outputs,
            guard,
        }
    }
}

impl Drop for PrivateRooms {
    fn drop(&mut self) {
        // Stop every owned world thread, including when an assertion unwinds.
        for room in &self.rooms {
            room.close_instance();
        }
    }
}

struct Peer {
    session: SessionId,
    epoch: u32,
    name: String,
    room: RoomHandle,
    outputs: ConnectionOutputs,
    guard: PresenceGuard,
}

impl Peer {
    fn principal(&mut self, rooms: &PrivateRooms, channel: u8, principal: uuid::Uuid) {
        let (handle, name) = identity_for_session(self.session);
        let replacement = rooms.social.join_guard_principal(
            self.session,
            PresenceKind::Normal { channel },
            handle,
            name,
            self.room.clone(),
            principal,
        );
        // Old guard removal must not delete the replacement's fresh token.
        self.guard = replacement;
        assert!(self.room.submit(RoomCommand::BindChatPrincipal {
            conn: self.outputs.conn,
            epoch: self.epoch,
            principal,
        }));
    }

    fn cold(&self, value: Value) {
        let payload = serde_json::to_vec(&value).expect("fixture JSON");
        assert!(self.room.submit(RoomCommand::Cold {
            conn: self.outputs.conn,
            payload
        }));
    }

    fn chat(&self, channel: &str, text: &str) {
        self.cold(json!({"t":"chat", "channel":channel, "text":text}));
    }

    fn megaphone(&self, text: &str) {
        self.cold(json!({"t":"community", "action":{"kind":"megaphone", "text":text}}));
    }
}

fn decode_cold(packet: &[u8]) -> Value {
    assert!(packet.len() >= 6, "complete wire envelope");
    assert_eq!(packet[3], 0x90, "existing cold-server envelope");
    serde_json::from_slice(&packet[6..]).expect("valid server JSON")
}

async fn next_tag(rx: &mut mpsc::Receiver<crate::room::QueuedPacket>, tag: &str) -> Value {
    tokio::time::timeout(DEADLINE, async {
        for _ in 0..128 {
            let packet = rx.recv().await.expect("recipient queue stays open");
            let value = decode_cold(&packet);
            if value["t"] == tag {
                return value;
            }
            assert_ne!(
                value["t"], "chat",
                "unexpected publication while awaiting {tag}"
            );
        }
        panic!("bounded fixture message scan exhausted waiting for {tag}");
    })
    .await
    .expect("recipient event before deadline")
}

// FIFO inbox barrier: observes queued messages before a real room-generated pong.
// This avoids assuming that sleeping a particular number of milliseconds flushed a room.
async fn barrier(peer: &mut Peer) -> Vec<Value> {
    assert!(peer.room.submit(RoomCommand::Ping {
        conn: peer.outputs.conn,
        nonce: 0x4348_4154,
        client_ms: 0,
    }));
    tokio::time::timeout(DEADLINE, async {
        let mut observed = Vec::new();
        for _ in 0..128 {
            let packet = peer
                .outputs
                .reliable
                .recv()
                .await
                .expect("live barrier queue");
            assert!(packet.len() >= 6);
            if packet[3] == 0x85 {
                return observed;
            }
            observed.push(decode_cold(&packet));
        }
        panic!("bounded queue barrier exhausted");
    })
    .await
    .expect("room barrier before deadline")
}

async fn no_chat(peer: &mut Peer) {
    for message in barrier(peer).await {
        assert_ne!(message["t"], "chat", "withheld message reached a recipient");
    }
}

async fn make_group(rooms: &PrivateRooms, a: &mut Peer, b: &mut Peer) {
    let code = rooms
        .social
        .group_create(a.session)
        .expect("create fixture group");
    next_tag(&mut a.outputs.reliable, "group").await;
    rooms
        .social
        .group_join(b.session, &code)
        .expect("join fixture group");
    next_tag(&mut a.outputs.reliable, "group").await;
    next_tag(&mut b.outputs.reliable, "group").await;
}

fn assert_chat(value: &Value, channel: &str, sender: &str, text: &str, device: Option<&str>) {
    let mut expected = json!({"t":"chat", "channel":channel, "from":sender, "text":text});
    if let Some(device) = device {
        expected["device"] = json!(device);
    }
    assert_eq!(
        value, &expected,
        "mask changes only text in the existing DTO"
    );
}

#[tokio::test]
async fn room_mask_is_authoritative_and_preserves_sender_device_and_scope() {
    let rooms = PrivateRooms::new(2);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(0, 0xB2).await;
    let mut outside = rooms.join(1, 0xC3).await;
    a.cold(json!({"t":"community", "action":{"kind":"sync", "device":"mobile"}}));
    barrier(&mut a).await;
    a.chat("room", "  FUCK!  ");
    let own = next_tag(&mut a.outputs.reliable, "chat").await;
    let other = next_tag(&mut b.outputs.reliable, "chat").await;
    assert_chat(&own, "room", &a.name, "****!", Some("mobile"));
    assert_eq!(own, other);
    no_chat(&mut outside).await;
}

#[tokio::test]
async fn group_cold_path_masks_before_cross_instance_publication() {
    let rooms = PrivateRooms::new(2);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(1, 0xB2).await;
    let mut outsider = rooms.join(1, 0xC3).await;
    rooms.social.set_device(b.session, Device::Desktop);
    make_group(&rooms, &mut a, &mut b).await;
    b.chat("group", "SHIT!");
    let on_a = next_tag(&mut a.outputs.reliable, "chat").await;
    let on_b = next_tag(&mut b.outputs.reliable, "chat").await;
    assert_chat(&on_a, "group", &b.name, "****!", Some("desktop"));
    assert_eq!(on_a, on_b);
    no_chat(&mut outsider).await;
}

#[tokio::test]
async fn room_and_group_review_send_typed_notice_without_publication() {
    let rooms = PrivateRooms::new(2);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(1, 0xB2).await;
    make_group(&rooms, &mut a, &mut b).await;
    for (channel, text) in [("room", "ควย"), ("group", "f u c k")] {
        a.chat(channel, text);
        let notice = next_tag(&mut a.outputs.reliable, "notice").await;
        assert_eq!(
            notice,
            json!({"t":"notice", "key":"chat_review_required", "params":{}})
        );
        no_chat(&mut a).await;
        no_chat(&mut b).await;
    }
}

#[tokio::test]
async fn safe_thai_family_emoji_and_rule_exceptions_survive_actual_room_chat() {
    let rooms = PrivateRooms::new(1);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(0, 0xB2).await;
    for text in ["สวัสดีครับ 👨‍👩‍👧‍👦", "นักรบเหี้ยม แม่งานพร้อมแล้ว", "ใบไม้เหี่ยว แมงมุม"]
    {
        a.chat("room", text);
        let own = next_tag(&mut a.outputs.reliable, "chat").await;
        let other = next_tag(&mut b.outputs.reliable, "chat").await;
        assert_chat(&own, "room", &a.name, text, None);
        assert_eq!(own, other);
    }
}

#[tokio::test]
async fn megaphone_review_is_withheld_and_does_not_burn_announcement_cooldown() {
    let rooms = PrivateRooms::new(2);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(1, 0xB2).await;
    rooms.social.set_device(a.session, Device::Mobile);
    a.megaphone("ควย");
    let notice = next_tag(&mut a.outputs.reliable, "notice").await;
    assert_eq!(notice["key"], "community_result");
    assert_eq!(notice["params"]["reason"], "chat_review_required");
    no_chat(&mut a).await;
    no_chat(&mut b).await;
    // A valid follow-up can publish immediately; there is no 30-second test sleep.
    a.megaphone("FUCK!");
    let own = next_tag(&mut a.outputs.reliable, "chat").await;
    let other = next_tag(&mut b.outputs.reliable, "chat").await;
    assert_chat(&own, "megaphone", &a.name, "****!", Some("mobile"));
    assert_eq!(own, other);
    a.megaphone("another announcement");
    let cooldown = next_tag(&mut a.outputs.reliable, "notice").await;
    assert_eq!(cooldown["params"]["reason"], "megaphone_cooldown");
    no_chat(&mut b).await;
}

#[tokio::test]
async fn principal_repeat_and_global_quota_survive_new_session_and_room() {
    let rooms = PrivateRooms::new(2);
    // All joins happen before exercising quotas, so slow room admission cannot
    // replenish a burst between the checks whose identity continuity is under test.
    let mut old = rooms.join(0, 0xA1).await;
    let mut replacement = rooms.join(1, 0xA2).await;
    let mut independent = rooms.join(1, 0xB2).await;
    let principal = uuid::Uuid::from_u128(1);
    old.principal(&rooms, 0, principal);
    independent.principal(&rooms, 1, uuid::Uuid::from_u128(2));
    assert!(
        rooms
            .social
            .prepare_room_chat(old.session, "same principal post")
            .is_ok()
    );
    replacement.principal(&rooms, 1, principal);
    assert!(matches!(
        rooms
            .social
            .prepare_room_chat(replacement.session, "same principal post"),
        Err(ChatRejection::Duplicate)
    ));
    // A rejected repeat still consumes a global attempt. Four more unique
    // attempts exhaust the original six-token burst across both session IDs.
    for n in 0..4 {
        assert!(
            rooms
                .social
                .prepare_room_chat(replacement.session, &format!("unique {n}"))
                .is_ok()
        );
    }
    assert!(matches!(
        rooms
            .social
            .prepare_room_chat(replacement.session, "cannot reset quota"),
        Err(ChatRejection::RateLimited)
    ));
    // The UUIDs share their public prefix: full principal identity must differ.
    assert!(
        rooms
            .social
            .prepare_room_chat(independent.session, "same principal post")
            .is_ok()
    );
}

#[tokio::test]
async fn bound_principal_quota_survives_social_presence_removal() {
    let rooms = PrivateRooms::new(1);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(0, 0xB2).await;
    a.principal(&rooms, 0, uuid::Uuid::from_u128(77));
    // Prefill the real shared gate. Bind and Cold remain ordered in the same
    // room inbox, with no timing sleep or presence lookup required for Cold.
    for n in 0..6 {
        assert!(
            rooms
                .social
                .prepare_room_chat(a.session, &format!("bound quota {n}"))
                .is_ok()
        );
    }
    let Peer {
        session,
        room,
        mut outputs,
        guard,
        ..
    } = a;
    drop(guard);
    assert!(
        !rooms
            .social
            .presence_snapshot()
            .iter()
            .any(|entry| entry.session == session)
    );
    assert!(
        room.submit(RoomCommand::Cold {
            conn: outputs.conn,
            payload: serde_json::to_vec(&json!({
                "t":"chat", "channel":"room", "text":"attempt after presence removal"
            }))
            .unwrap(),
        })
    );
    let notice = next_tag(&mut outputs.reliable, "notice").await;
    assert_eq!(
        notice,
        json!({"t":"notice", "key":"chat_rate_limited", "params":{}})
    );
    no_chat(&mut b).await;
}

#[tokio::test]
async fn stale_epoch_principal_bind_cannot_replace_live_chat_identity() {
    let rooms = PrivateRooms::new(1);
    let mut a = rooms.join(0, 0xA1).await;
    let mut b = rooms.join(0, 0xB2).await;
    a.principal(&rooms, 0, uuid::Uuid::from_u128(88));
    for n in 0..6 {
        assert!(
            rooms
                .social
                .prepare_room_chat(a.session, &format!("stale bind quota {n}"))
                .is_ok()
        );
    }
    let stale_epoch = a.epoch.wrapping_add(1).max(1);
    assert_ne!(stale_epoch, a.epoch);
    assert!(a.room.submit(RoomCommand::BindChatPrincipal {
        conn: a.outputs.conn,
        epoch: stale_epoch,
        principal: uuid::Uuid::from_u128(89),
    }));
    a.chat("room", "attempt under forged replacement identity");
    let notice = next_tag(&mut a.outputs.reliable, "notice").await;
    assert_eq!(
        notice,
        json!({"t":"notice", "key":"chat_rate_limited", "params":{}})
    );
    no_chat(&mut b).await;
}

#[tokio::test]
async fn full_recipient_queue_does_not_block_masked_chat_for_another_player() {
    let rooms = PrivateRooms::new(1);
    let mut a = rooms.join(0, 0xA1).await;
    let mut stalled = rooms.join(0, 0xB2).await;
    let fill = crate::wire::encode_cold_server(
        &serde_json::to_vec(&json!({"t":"notice", "key":"private_queue_fixture", "params":{}}))
            .unwrap(),
    )
    .unwrap();
    for _ in 0..RELIABLE_BOUND {
        assert!(stalled.room.notify(stalled.outputs.conn, fill.clone()));
    }
    barrier(&mut a).await;
    assert_eq!(stalled.outputs.reliable.len(), RELIABLE_BOUND);
    assert!(!*stalled.outputs.closed.borrow());
    a.chat("room", "FUCK!");
    let delivered = next_tag(&mut a.outputs.reliable, "chat").await;
    assert_chat(&delivered, "room", &a.name, "****!", None);
    // Existing consecutive-drop policy closes only the slow recipient.
    for _ in 0..16 {
        assert!(stalled.room.notify(stalled.outputs.conn, fill.clone()));
    }
    barrier(&mut a).await;
    assert!(*stalled.outputs.closed.borrow());
    assert!(!*a.outputs.closed.borrow());
    a.chat("room", "SHIT!");
    let later = next_tag(&mut a.outputs.reliable, "chat").await;
    assert_chat(&later, "room", &a.name, "****!", None);
    while let Ok(packet) = stalled.outputs.reliable.try_recv() {
        assert_ne!(
            decode_cold(&packet)["t"],
            "chat",
            "full queue never retained raw or masked chat"
        );
    }
}
