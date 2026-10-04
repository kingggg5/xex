//! Protocol v4 cold path (V5-02, plan §9 and Appendix B).
//!
//! One envelope type per direction (`0x10` client → server, `0x90` server →
//! client) carries UTF-8 JSON tagged by `"t"`. Client payloads are capped at
//! 512 bytes, server payloads at 4 KiB. The Rust types below, with unknown
//! fields denied, are the schema; the TypeScript bindings checked in at
//! `apps/client/src/cold_v4.gen.ts` are generated from them (see
//! [`typescript_bindings`]).

use crate::wire::DecodeError;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const MAX_COLD_CLIENT_BYTES: usize = 512;
/// Enforced by [`encode_server_payload`]; first oversized producer is V5-06+.
#[allow(dead_code)]
pub const MAX_COLD_SERVER_BYTES: usize = 4096;
pub const MAX_COLD_TAG_LEN: usize = 32;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ColdTag {
    MageTrial,
    MageCast,
    MoveItemInstance,
    ClaimReward,
    ReturnToTown,
    Community,
    Interact,
    Activate,
    Choose,
    Claim,
    UseItem,
    StoreBuy,
    BoxOpen,
    CosmeticsEquip,
    EquipItem,
    PickupDrop,
    StatAllocate,
    RefineItem,
    PartyCreate,
    PartyJoin,
    PartyLeave,
    Resync,
    Chat,
    FriendAdd,
    FriendRemove,
    GroupCreate,
    GroupJoin,
    GroupLeave,
}

impl ColdTag {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::MageTrial => "mage_trial",
            Self::MageCast => "mage_cast",
            Self::MoveItemInstance => "move_item_instance",
            Self::ClaimReward => "claim_reward",
            Self::ReturnToTown => "return_to_town",
            Self::Community => "community",
            Self::Interact => "interact",
            Self::Activate => "activate",
            Self::Choose => "choose",
            Self::Claim => "claim",
            Self::UseItem => "use_item",
            Self::StoreBuy => "store_buy",
            Self::BoxOpen => "box_open",
            Self::CosmeticsEquip => "cosmetics_equip",
            Self::EquipItem => "equip_item",
            Self::PickupDrop => "pickup_drop",
            Self::StatAllocate => "stat_allocate",
            Self::RefineItem => "refine_item",
            Self::PartyCreate => "party_create",
            Self::PartyJoin => "party_join",
            Self::PartyLeave => "party_leave",
            Self::Resync => "resync",
            Self::Chat => "chat",
            Self::FriendAdd => "friend_add",
            Self::FriendRemove => "friend_remove",
            Self::GroupCreate => "group_create",
            Self::GroupJoin => "group_join",
            Self::GroupLeave => "group_leave",
        }
    }

    pub fn parse(tag: &str) -> Option<Self> {
        Some(match tag {
            "mage_trial" => Self::MageTrial,
            "mage_cast" => Self::MageCast,
            "move_item_instance" => Self::MoveItemInstance,
            "claim_reward" => Self::ClaimReward,
            "return_to_town" => Self::ReturnToTown,
            "community" => Self::Community,
            "interact" => Self::Interact,
            "activate" => Self::Activate,
            "choose" => Self::Choose,
            "claim" => Self::Claim,
            "use_item" => Self::UseItem,
            "store_buy" => Self::StoreBuy,
            "box_open" => Self::BoxOpen,
            "cosmetics_equip" => Self::CosmeticsEquip,
            "equip_item" => Self::EquipItem,
            "pickup_drop" => Self::PickupDrop,
            "stat_allocate" => Self::StatAllocate,
            "refine_item" => Self::RefineItem,
            "party_create" => Self::PartyCreate,
            "party_join" => Self::PartyJoin,
            "party_leave" => Self::PartyLeave,
            "resync" => Self::Resync,
            "chat" => Self::Chat,
            "friend_add" => Self::FriendAdd,
            "friend_remove" => Self::FriendRemove,
            "group_create" => Self::GroupCreate,
            "group_join" => Self::GroupJoin,
            "group_leave" => Self::GroupLeave,
            _ => return None,
        })
    }
}

/// Cosmetic equip slots (D-14). Validated at the cold layer so the world owner
/// only ever sees a known slot.
fn valid_equip_slot(value: &str) -> bool {
    matches!(value, "skin" | "pet")
}

/// Content identifiers: 1–64 chars of `[A-Za-z0-9_]` (NPCs, quests, items,
/// text keys, reasons, grant defs).
fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

/// Party invite codes: exactly 6 chars of `[A-Z0-9]`.
fn valid_code(value: &str) -> bool {
    value.len() == 6
        && value
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit())
}

/// Operation ids: UUID shape `8-4-4-4-12` lowercase/uppercase hex.
fn valid_op_id(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 36 {
        return false;
    }
    for (index, byte) in bytes.iter().enumerate() {
        let hyphen = matches!(index, 8 | 13 | 18 | 23);
        if hyphen {
            if *byte != b'-' {
                return false;
            }
        } else if !byte.is_ascii_hexdigit() {
            return false;
        }
    }
    true
}

fn valid_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'))
}

/// Player handles: exactly 8 lowercase hex chars (the first 8 hex chars of a
/// session id, the session's public social handle).
fn valid_handle(value: &str) -> bool {
    value.len() == 8
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Visible chat length cap after sanitizing (the [`sanitize_text`] discipline).
pub const MAX_CHAT_CHARS: usize = 160;

/// Sanitize a player-supplied free-text string with the same discipline as
/// `SessionIdentity::new`: control characters become spaces, whitespace runs
/// collapse, and the result is capped at `max_chars` visible characters.
pub fn sanitize_text(raw: &str, max_chars: usize) -> String {
    let mapped: String = raw
        .chars()
        .map(|character| {
            if character.is_control() {
                ' '
            } else {
                character
            }
        })
        .collect();
    let collapsed = mapped.split_whitespace().collect::<Vec<_>>().join(" ");
    if collapsed.chars().count() > max_chars {
        collapsed.chars().take(max_chars).collect()
    } else {
        collapsed
    }
}

// ---------------------------------------------------------------------------
// Client → server messages
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InteractMsg {
    t: String,
    npc: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ActivateMsg {
    t: String,
    marker: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ChooseMsg {
    t: String,
    npc: String,
    token: String,
    choice: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ClaimMsg {
    t: String,
    quest: String,
    op_id: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct UseItemMsg {
    t: String,
    item: String,
    op_id: String,
}

#[derive(Debug, Deserialize, Clone, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ReturnToTownRequest {
    pub t: String,
    pub op_id: String,
    pub death_revision: u32,
}

#[derive(Debug, Deserialize, Clone, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ClaimRewardRequest {
    pub t: String,
    pub op_id: String,
    pub receipt_id: String,
}

#[derive(Debug,Clone,PartialEq,Eq,Deserialize,Serialize)]
#[serde(deny_unknown_fields)]
pub struct MoveItemInstanceRequest {
    pub t:String,
    pub op_id:String,
    pub instance_id:String,
    pub expected_revision:u32,
    pub to:String,
}
pub fn decode_move_item_instance_request(bytes:&[u8])->Result<MoveItemInstanceRequest,DecodeError> {
    if bytes.len()>MAX_COLD_CLIENT_BYTES {return Err(DecodeError::TooLarge);}
    let request:MoveItemInstanceRequest=serde_json::from_slice(bytes).map_err(|_|DecodeError::InvalidField)?;
    if request.t!="move_item_instance" || !valid_op_id(&request.op_id) || !valid_op_id(&request.instance_id) || request.expected_revision==0 || !matches!(request.to.as_str(),"bag"|"weapon"|"armor") {return Err(DecodeError::InvalidField);}
    Ok(request)
}
pub fn decode_claim_reward_request(bytes: &[u8]) -> Result<ClaimRewardRequest, DecodeError> {
    if bytes.len()>MAX_COLD_CLIENT_BYTES {return Err(DecodeError::TooLarge);}
    let request:ClaimRewardRequest=serde_json::from_slice(bytes).map_err(|_|DecodeError::InvalidField)?;
    if request.t!="claim_reward" || !valid_op_id(&request.op_id) || !valid_op_id(&request.receipt_id) {return Err(DecodeError::InvalidField);}
    Ok(request)
}

pub fn decode_return_to_town_request(bytes: &[u8]) -> Result<ReturnToTownRequest, DecodeError> {
    if bytes.len() > MAX_COLD_CLIENT_BYTES { return Err(DecodeError::TooLarge); }
    let request: ReturnToTownRequest = serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    if request.t != "return_to_town" || !valid_op_id(&request.op_id) || request.death_revision == 0 {
        return Err(DecodeError::InvalidField);
    }
    Ok(request)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct StoreBuyMsg {
    t: String,
    item: String,
    op_id: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BoxOpenMsg {
    t: String,
    item: String,
    op_id: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CosmeticsEquipMsg {
    t: String,
    slot: String,
    id: String,
    op_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UseItemRequest {
    pub item: String,
    pub op_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoreBuyRequest {
    pub item: String,
    pub op_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoxOpenRequest {
    pub item: String,
    pub op_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CosmeticsEquipRequest {
    pub slot: String,
    pub id: String,
    pub op_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InteractRequest {
    pub npc: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActivateRequest {
    pub marker: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChooseRequest {
    pub npc: String,
    pub token: String,
    pub choice: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClaimRequest {
    pub quest: String,
    pub op_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PartyRequest {
    Create,
    Join { code: String },
    Leave,
}

/// Chat channel requested by a `chat` cold message.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChatChannel {
    Room,
    Group,
}

impl ChatChannel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Room => "room",
            Self::Group => "group",
        }
    }

    fn parse(value: &str) -> Option<Self> {
        match value {
            "room" => Some(Self::Room),
            "group" => Some(Self::Group),
            _ => None,
        }
    }
}

/// A decoded chat intent: the channel plus the sanitized text (1..=160
/// visible characters; the validator refuses empty results).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChatRequest {
    pub channel: ChatChannel,
    pub text: String,
}

/// One social op decoded from the friend cold tags.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FriendOp {
    Add { handle: String },
    Remove { handle: String },
}

/// One social op decoded from the group cold tags.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GroupOp {
    Create,
    Join { code: String },
    Leave,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PartyCreateMsg {
    t: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PartyJoinMsg {
    t: String,
    code: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PartyLeaveMsg {
    t: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ResyncMsg {
    t: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ChatMsg {
    t: String,
    channel: String,
    text: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FriendAddMsg {
    t: String,
    handle: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FriendRemoveMsg {
    t: String,
    handle: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupCreateMsg {
    t: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupJoinMsg {
    t: String,
    code: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GroupLeaveMsg {
    t: String,
}

fn tag_is(value: &str, expected: ColdTag) -> bool {
    value == expected.as_str()
}

/// Validate one bounded client cold-path payload before world-owner dispatch.
pub fn validate_client_payload(bytes: &[u8]) -> Result<ColdTag, DecodeError> {
    if bytes.len() > MAX_COLD_CLIENT_BYTES {
        return Err(DecodeError::TooLarge);
    }
    let text = std::str::from_utf8(bytes).map_err(|_| DecodeError::InvalidField)?;
    let value: serde_json::Value =
        serde_json::from_str(text).map_err(|_| DecodeError::InvalidField)?;
    let fields = value.as_object().ok_or(DecodeError::InvalidField)?;
    let tag_text = fields
        .get("t")
        .and_then(serde_json::Value::as_str)
        .ok_or(DecodeError::InvalidField)?;
    if tag_text.len() > MAX_COLD_TAG_LEN {
        return Err(DecodeError::InvalidField);
    }
    let tag = ColdTag::parse(tag_text).ok_or(DecodeError::InvalidField)?;
    let typed: Result<(), DecodeError> = (|| {
        match tag {
            ColdTag::MageTrial => {
                let r:crate::mage_trial::TrialRequest=serde_json::from_slice(bytes).map_err(|_|DecodeError::InvalidField)?;
                if r.t!="mage_trial" || !valid_op_id(&r.op_id) {return Err(DecodeError::InvalidField);}
            }
            ColdTag::MageCast => {
                let r:crate::mage_trial::CastRequest=serde_json::from_slice(bytes).map_err(|_|DecodeError::InvalidField)?;
                if r.t!="mage_cast" || r.epoch==0 || r.sequence==0 || r.target_id==0 {return Err(DecodeError::InvalidField);}
            }
            ColdTag::MoveItemInstance => {decode_move_item_instance_request(bytes)?;}
            ColdTag::ClaimReward => {decode_claim_reward_request(bytes)?;}
            ColdTag::ReturnToTown => { decode_return_to_town_request(bytes)?; }
            ColdTag::Community => { crate::community::decode(bytes)?; }
            ColdTag::Interact => {
                let message: InteractMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) || !valid_id(&message.npc) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::Activate => {
                let message: ActivateMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) || !valid_id(&message.marker) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::Choose => {
                let message: ChooseMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_id(&message.npc)
                    || !valid_token(&message.token)
                    || !valid_id(&message.choice)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::Claim => {
                let message: ClaimMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_id(&message.quest)
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::UseItem => {
                let message: UseItemMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_id(&message.item)
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::StoreBuy => {
                let message: StoreBuyMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_id(&message.item)
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::BoxOpen => {
                let message: BoxOpenMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_id(&message.item)
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::CosmeticsEquip => {
                let message: CosmeticsEquipMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_equip_slot(&message.slot)
                    || !valid_id(&message.id)
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::EquipItem => {
                let message: EquipItemMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !valid_id(&message.item)
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::PickupDrop => {
                let message: PickupDropMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || message.encounter.len() != 36
                    || !message
                        .encounter
                        .bytes()
                        .all(|byte| byte.is_ascii_hexdigit() || byte == b'-')
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::StatAllocate => {
                let message: StatAllocateMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !matches!(message.stat.as_str(), "str" | "agi" | "vit" | "int" | "dex" | "luk")
                    || message.points == 0
                    || message.points > 100
                    || !valid_op_id(&message.op_id)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::RefineItem => {
                let message: RefineItemMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || !matches!(message.slot.as_str(), "weapon" | "armor")
                    || !valid_op_id(&message.op_id)
                    || message.instance_id.is_some()!=message.expected_revision.is_some()
                    || message.instance_id.as_deref().is_some_and(|id|!valid_op_id(id))
                    || message.expected_revision==Some(0)
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::PartyCreate => {
                let message: PartyCreateMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::PartyJoin => {
                let message: PartyJoinMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) || !valid_code(&message.code) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::PartyLeave => {
                let message: PartyLeaveMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::Resync => {
                let message: ResyncMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::Chat => {
                let message: ChatMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag)
                    || ChatChannel::parse(&message.channel).is_none()
                    || sanitize_text(&message.text, MAX_CHAT_CHARS).is_empty()
                {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::FriendAdd | ColdTag::FriendRemove => {
                if tag == ColdTag::FriendAdd {
                    let message: FriendAddMsg = serde_json::from_value(value.clone())
                        .map_err(|_| DecodeError::InvalidField)?;
                    if !tag_is(&message.t, tag) || !valid_handle(&message.handle) {
                        return Err(DecodeError::InvalidField);
                    }
                } else {
                    let message: FriendRemoveMsg = serde_json::from_value(value.clone())
                        .map_err(|_| DecodeError::InvalidField)?;
                    if !tag_is(&message.t, tag) || !valid_handle(&message.handle) {
                        return Err(DecodeError::InvalidField);
                    }
                }
            }
            ColdTag::GroupCreate => {
                let message: GroupCreateMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::GroupJoin => {
                let message: GroupJoinMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) || !valid_code(&message.code) {
                    return Err(DecodeError::InvalidField);
                }
            }
            ColdTag::GroupLeave => {
                let message: GroupLeaveMsg =
                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;
                if !tag_is(&message.t, tag) {
                    return Err(DecodeError::InvalidField);
                }
            }
        }
        Ok(())
    })();
    typed.map(|()| tag)
}

/// Decode a previously validated item-use intent for the world owner.
pub fn decode_use_item_request(bytes: &[u8]) -> Result<UseItemRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::UseItem {
        return Err(DecodeError::InvalidField);
    }
    let message: UseItemMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(UseItemRequest {
        item: message.item,
        op_id: message.op_id,
    })
}

/// E07: equip an owned weapon/armor item into its slot (the item leaves the
/// bag; the previously equipped piece returns to it).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EquipItemRequest {
    pub item: String,
    pub op_id: String,
}

#[derive(Debug, Deserialize)]
struct EquipItemMsg {
    t: String,
    item: String,
    op_id: String,
}

/// Decode a validated equip intent for the world owner (E07).
pub fn decode_equip_item_request(bytes: &[u8]) -> Result<EquipItemRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::EquipItem {
        return Err(DecodeError::InvalidField);
    }
    let message: EquipItemMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(EquipItemRequest {
        item: message.item,
        op_id: message.op_id,
    })
}

/// P4: pick up one owned ground drop (walk-over range enforced world-side).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PickupDropRequest {
    pub encounter: String,
    pub op_id: String,
}

#[derive(Debug, Deserialize)]
struct PickupDropMsg {
    t: String,
    encounter: String,
    op_id: String,
}

/// Decode a validated pickup intent for the world owner (P4).
pub fn decode_pickup_drop_request(bytes: &[u8]) -> Result<PickupDropRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::PickupDrop {
        return Err(DecodeError::InvalidField);
    }
    let message: PickupDropMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(PickupDropRequest {
        encounter: message.encounter,
        op_id: message.op_id,
    })
}

/// Allocate status points (STR, AGI, VIT, INT, DEX, LUK).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StatAllocateRequest {
    pub stat: String,
    pub points: u32,
    pub op_id: String,
}

#[derive(Debug, Deserialize)]
struct StatAllocateMsg {
    t: String,
    stat: String,
    points: u32,
    op_id: String,
}

pub fn decode_stat_allocate_request(bytes: &[u8]) -> Result<StatAllocateRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::StatAllocate {
        return Err(DecodeError::InvalidField);
    }
    let message: StatAllocateMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(StatAllocateRequest {
        stat: message.stat,
        points: message.points,
        op_id: message.op_id,
    })
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RefineItemRequest {
    pub slot: String,
    pub op_id: String,
    pub instance_id: Option<String>,
    pub expected_revision: Option<u32>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RefineItemMsg {
    t: String,
    slot: String,
    op_id: String,
    #[serde(default)]
    instance_id: Option<String>,
    #[serde(default)]
    expected_revision: Option<u32>,
}

pub fn decode_refine_item_request(bytes: &[u8]) -> Result<RefineItemRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::RefineItem {
        return Err(DecodeError::InvalidField);
    }
    let message: RefineItemMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(RefineItemRequest {
        slot: message.slot,
        op_id: message.op_id,
        instance_id: message.instance_id,
        expected_revision: message.expected_revision,
    })
}

pub fn decode_interact_request(bytes: &[u8]) -> Result<InteractRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::Interact {
        return Err(DecodeError::InvalidField);
    }
    let message: InteractMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(InteractRequest { npc: message.npc })
}

pub fn decode_activate_request(bytes: &[u8]) -> Result<ActivateRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::Activate {
        return Err(DecodeError::InvalidField);
    }
    let message: ActivateMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(ActivateRequest {
        marker: message.marker,
    })
}

pub fn decode_choose_request(bytes: &[u8]) -> Result<ChooseRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::Choose {
        return Err(DecodeError::InvalidField);
    }
    let message: ChooseMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(ChooseRequest {
        npc: message.npc,
        token: message.token,
        choice: message.choice,
    })
}

pub fn decode_claim_request(bytes: &[u8]) -> Result<ClaimRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::Claim {
        return Err(DecodeError::InvalidField);
    }
    let message: ClaimMsg = serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(ClaimRequest {
        quest: message.quest,
        op_id: message.op_id,
    })
}

/// Decode a validated store-purchase intent for the world owner (D-14).
pub fn decode_store_buy_request(bytes: &[u8]) -> Result<StoreBuyRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::StoreBuy {
        return Err(DecodeError::InvalidField);
    }
    let message: StoreBuyMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(StoreBuyRequest {
        item: message.item,
        op_id: message.op_id,
    })
}

/// Decode a validated box-open intent for the world owner (D-14).
pub fn decode_box_open_request(bytes: &[u8]) -> Result<BoxOpenRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::BoxOpen {
        return Err(DecodeError::InvalidField);
    }
    let message: BoxOpenMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(BoxOpenRequest {
        item: message.item,
        op_id: message.op_id,
    })
}

/// Decode a validated cosmetic-equip intent for the world owner (D-14).
pub fn decode_cosmetics_equip_request(bytes: &[u8]) -> Result<CosmeticsEquipRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::CosmeticsEquip {
        return Err(DecodeError::InvalidField);
    }
    let message: CosmeticsEquipMsg =
        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    Ok(CosmeticsEquipRequest {
        slot: message.slot,
        id: message.id,
        op_id: message.op_id,
    })
}

pub fn decode_party_request(bytes: &[u8]) -> Result<PartyRequest, DecodeError> {
    match validate_client_payload(bytes)? {
        ColdTag::PartyCreate => {
            serde_json::from_slice::<PartyCreateMsg>(bytes)
                .map_err(|_| DecodeError::InvalidField)?;
            Ok(PartyRequest::Create)
        }
        ColdTag::PartyJoin => {
            let message: PartyJoinMsg =
                serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
            Ok(PartyRequest::Join { code: message.code })
        }
        ColdTag::PartyLeave => {
            serde_json::from_slice::<PartyLeaveMsg>(bytes)
                .map_err(|_| DecodeError::InvalidField)?;
            Ok(PartyRequest::Leave)
        }
        _ => Err(DecodeError::InvalidField),
    }
}

/// Decode a validated chat intent. The text comes back sanitized
/// ([`sanitize_text`] discipline), 1..=[`MAX_CHAT_CHARS`] visible characters.
pub fn decode_chat_request(bytes: &[u8]) -> Result<ChatRequest, DecodeError> {
    if validate_client_payload(bytes)? != ColdTag::Chat {
        return Err(DecodeError::InvalidField);
    }
    let message: ChatMsg = serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
    let channel = ChatChannel::parse(&message.channel).ok_or(DecodeError::InvalidField)?;
    let text = sanitize_text(&message.text, MAX_CHAT_CHARS);
    if text.is_empty() {
        return Err(DecodeError::InvalidField);
    }
    Ok(ChatRequest { channel, text })
}

/// Decode a validated friend add/remove intent (8 lowercase hex handles).
pub fn decode_friend_request(bytes: &[u8]) -> Result<FriendOp, DecodeError> {
    match validate_client_payload(bytes)? {
        ColdTag::FriendAdd => {
            let message: FriendAddMsg =
                serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
            if !valid_handle(&message.handle) {
                return Err(DecodeError::InvalidField);
            }
            Ok(FriendOp::Add {
                handle: message.handle,
            })
        }
        ColdTag::FriendRemove => {
            let message: FriendRemoveMsg =
                serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
            if !valid_handle(&message.handle) {
                return Err(DecodeError::InvalidField);
            }
            Ok(FriendOp::Remove {
                handle: message.handle,
            })
        }
        _ => Err(DecodeError::InvalidField),
    }
}

/// Decode a validated group create/join/leave intent (6-char invite codes).
pub fn decode_group_request(bytes: &[u8]) -> Result<GroupOp, DecodeError> {
    match validate_client_payload(bytes)? {
        ColdTag::GroupCreate => {
            serde_json::from_slice::<GroupCreateMsg>(bytes)
                .map_err(|_| DecodeError::InvalidField)?;
            Ok(GroupOp::Create)
        }
        ColdTag::GroupJoin => {
            let message: GroupJoinMsg =
                serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;
            Ok(GroupOp::Join { code: message.code })
        }
        ColdTag::GroupLeave => {
            serde_json::from_slice::<GroupLeaveMsg>(bytes)
                .map_err(|_| DecodeError::InvalidField)?;
            Ok(GroupOp::Leave)
        }
        _ => Err(DecodeError::InvalidField),
    }
}

// ---------------------------------------------------------------------------
// Server → client messages
// ---------------------------------------------------------------------------

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BagEntry {
    pub slot: u8,
    pub item: String,
    pub count: u8,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
/// `count` is u32 so wallet grants (gold/coin amounts) fit alongside item
/// counts; the JSON wire shape is unchanged for existing producers.
#[allow(dead_code)]
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GrantEntry {
    pub def: String,
    pub count: u32,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChoiceEntry {
    pub id: String,
    pub label_key: String,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemberEntry {
    pub id: u32,
    pub name: String,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
/// D-14 adds the session wallet, cosmetic equip slots and owned cosmetics.
/// Field naming matches the existing snake_case wire style (`max_hp`, `op_id`).
/// The social layer adds the stable per-session identity: `handle` (8 lowercase
/// hex chars, the public social handle) and `name` (`Traveler-XXXX`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct CharacterStats {
    #[serde(rename = "str")]
    pub str_: u16,
    pub agi: u16,
    pub vit: u16,
    #[serde(rename = "int")]
    pub int_: u16,
    pub dex: u16,
    pub luk: u16,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EquipmentBonus {pub atk:u16,pub def:u16,pub max_hp:u16}

#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CharacterStateMsg {
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub vocation:Option<String>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub combat_profile:Option<String>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub magic_power:Option<u16>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub stats_base:Option<CharacterStats>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub stats_allocated:Option<CharacterStats>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub equipment_bonus:Option<EquipmentBonus>,
    pub character_id: String,
    #[serde(default)]
    pub item_instances: Vec<crate::inventory_instances::ItemInstance>,
    pub t: String,
    pub rev: u32,
    pub level: u32,
    pub exp: u32,
    /// E07: EXP needed for the next base level (curve from the vocation).
    pub base_exp_next: u32,
    /// E07: job track (level, EXP, EXP-to-next).
    pub job_level: u32,
    pub job_exp: u32,
    pub job_exp_next: u32,
    /// E07 derived stats (golden formulas): attack and defense.
    pub atk: u16,
    pub def: u16,
    /// E07 equipped gear (slot -> item id).
    pub equipment: Vec<EquipEntry>,
    pub hp: u16,
    pub max_hp: u16,
    #[serde(default)]
    pub sp: u16,
    #[serde(default)]
    pub max_sp: u16,
    pub bag: Vec<BagEntry>,
    pub pouch: BTreeMap<String, u32>,
    pub gold: u32,
    pub coin: u32,
    pub skin: Option<String>,
    pub pet: Option<String>,
    pub owned_cosmetics: Vec<String>,
    pub handle: String,
    pub name: String,
    #[serde(default)]
    pub stat_points: u32,
    #[serde(default)]
    pub stats: CharacterStats,
    #[serde(default)]
    pub refine: BTreeMap<String, u8>,
}

/// P4: one owned ground drop (`encounter` is the UUIDv7 kill identity).
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DropEntry {
    pub encounter: String,
    pub item: String,
    pub count: u32,
    pub x: f32,
    pub z: f32,
}

/// P4: the player's live ground drops (private loot; full replace on push).
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DropsMsg {
    pub t: String,
    pub entries: Vec<DropEntry>,
}

/// E07: one equipped piece (`slot` = "weapon" | "armor").
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EquipEntry {
    pub slot: String,
    pub item: String,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuestStateMsg {
    pub t: String,
    pub rev: u32,
    pub quest: String,
    pub state: String,
    pub objectives: BTreeMap<String, u32>,
    pub step_ticks: BTreeMap<String, u64>,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DialogueMsg {
    pub t: String,
    pub npc: String,
    pub token: String,
    pub text_key: String,
    pub choices: Vec<ChoiceEntry>,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DialogueClosedMsg {
    pub t: String,
    pub npc: String,
    pub reason: String,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OpResultMsg {
    pub t: String,
    pub op_id: String,
    pub status: String,
    pub reason: String,
    /// Absolute room-clock expiry; old persisted results have no usable deadline.
    #[serde(default)]
    pub ends_at_ms: u64,
    pub grants: Vec<GrantEntry>,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PartyStateMsg {
    pub t: String,
    pub rev: u32,
    pub members: Vec<MemberEntry>,
    pub leader: u32,
    pub code: String,
    pub expires_s: u16,
}

/// Schema for V5-06+; first constructor lands with its gameplay item.
#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NoticeMsg {
    pub t: String,
    pub key: String,
    pub params: serde_json::Value,
}

/// One social roster entry (a friend, or a group member): the public handle,
/// the display name, and the live presence snapshot. `channel` is the room
/// channel for a player in a normal room, `null` otherwise; `in_tower` marks
/// tower instances.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SocialMemberMsg {
    #[serde(default, skip_serializing_if = "crate::community::unknown_device")]
    pub device: crate::community::Device,
    pub handle: String,
    pub name: String,
    pub online: bool,
    pub channel: Option<u8>,
    pub in_tower: bool,
}

/// Server → client chat line (room or group channel).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChatBroadcastMsg {
    #[serde(default, skip_serializing_if = "crate::community::unknown_device")]
    pub device: crate::community::Device,
    pub t: String,
    pub channel: String,
    pub from: String,
    pub text: String,
}

/// Server → client friends roster push (`friend_add`/`friend_remove` acks and
/// roster refreshes).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FriendsMsg {
    pub t: String,
    pub entries: Vec<SocialMemberMsg>,
}

/// Server → client group state push. `code: null` means the group is gone
/// (disbanded or left): the client resets its panel.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GroupStateMsg {
    pub t: String,
    pub code: Option<String>,
    pub members: Vec<SocialMemberMsg>,
}

impl ChatBroadcastMsg {
    pub fn with_device(mut self, device: crate::community::Device) -> Self { self.device = device; self }
    pub fn new(channel: &str, from: &str, text: &str) -> Self {
        Self {
            device: crate::community::Device::Unknown,
            t: "chat".to_string(),
            channel: channel.to_string(),
            from: from.to_string(),
            text: text.to_string(),
        }
    }
}

impl FriendsMsg {
    pub fn new(entries: Vec<SocialMemberMsg>) -> Self {
        Self {
            t: "friends".to_string(),
            entries,
        }
    }
}

impl GroupStateMsg {
    pub fn new(code: Option<String>, members: Vec<SocialMemberMsg>) -> Self {
        Self {
            t: "group".to_string(),
            code,
            members,
        }
    }
}

/// Encode one server cold message. The 4 KiB cap is enforced here so a future
/// handler cannot accidentally emit an oversized envelope.
#[allow(dead_code)]
pub fn encode_server_payload(json: &str) -> Result<Vec<u8>, DecodeError> {
    if json.len() > MAX_COLD_SERVER_BYTES {
        return Err(DecodeError::TooLarge);
    }
    if serde_json::from_str::<serde_json::Value>(json).is_err() {
        return Err(DecodeError::InvalidField);
    }
    Ok(json.as_bytes().to_vec())
}

// ---------------------------------------------------------------------------
// TypeScript bindings generated from the Rust types above
// ---------------------------------------------------------------------------

/// Render the checked-in `apps/client/src/cold_v4.gen.ts`. Field order and
/// tag literals match the structs above; the binding test fails on drift.
#[allow(dead_code)]
pub fn typescript_bindings() -> String {
    let mut out = String::new();
    out.push_str("// GENERATED from apps/server/src/cold.rs — do not edit by hand.\n");
    out.push_str(
        "// Regen: UPDATE_BINDINGS=1 cargo test --manifest-path apps/server/Cargo.toml cold\n",
    );
    out.push_str("export type ColdClientTag =\n");
    for tag in [
        ColdTag::MageTrial,
        ColdTag::MageCast,
        ColdTag::MoveItemInstance,
        ColdTag::ReturnToTown,
        ColdTag::ClaimReward,
        ColdTag::Community,
        ColdTag::Interact,
        ColdTag::Activate,
        ColdTag::Choose,
        ColdTag::Claim,
        ColdTag::UseItem,
        ColdTag::StoreBuy,
        ColdTag::BoxOpen,
        ColdTag::CosmeticsEquip,
        ColdTag::EquipItem,
        ColdTag::PickupDrop,
        ColdTag::StatAllocate,
        ColdTag::RefineItem,
        ColdTag::PartyCreate,
        ColdTag::PartyJoin,
        ColdTag::PartyLeave,
        ColdTag::Resync,
        ColdTag::Chat,
        ColdTag::FriendAdd,
        ColdTag::FriendRemove,
        ColdTag::GroupCreate,
        ColdTag::GroupJoin,
        ColdTag::GroupLeave,
    ] {
        out.push_str(&format!("  | \"{}\"\n", tag.as_str()));
    }
    out.push_str(";\n");
    out.push_str("export interface InteractMessage { t: \"interact\"; npc: string; }\n");
    out.push_str("export interface ActivateMessage { t: \"activate\"; marker: string; }\n");
    out.push_str("export interface ChooseMessage { t: \"choose\"; npc: string; token: string; choice: string; }\n");
    out.push_str("export interface ClaimMessage { t: \"claim\"; quest: string; op_id: string; }\n");
    out.push_str(
        "export interface UseItemMessage { t: \"use_item\"; item: string; op_id: string; }\n",
    );
    out.push_str(
        "export interface StoreBuyMessage { t: \"store_buy\"; item: string; op_id: string; }\n",
    );
    out.push_str(
        "export interface BoxOpenMessage { t: \"box_open\"; item: string; op_id: string; }\n",
    );
    out.push_str("export interface CosmeticsEquipMessage { t: \"cosmetics_equip\"; slot: string; id: string; op_id: string; }\n");
    out.push_str(
        "export interface EquipItemMessage { t: \"equip_item\"; item: string; op_id: string; }\n",
    );
    out.push_str("export interface PickupDropMessage { t: \"pickup_drop\"; encounter: string; op_id: string; }\n");
    out.push_str("export interface StatAllocateMessage { t: \"stat_allocate\"; stat: \"str\" | \"agi\" | \"vit\" | \"int\" | \"dex\" | \"luk\"; points: number; op_id: string; }\n");
    out.push_str("export interface RefineItemMessage { t: \"refine_item\"; slot: \"weapon\" | \"armor\"; op_id: string; instance_id?: string; expected_revision?: number; }\n");
    out.push_str("export interface PartyCreateMessage { t: \"party_create\"; }\n");
    out.push_str("export interface PartyJoinMessage { t: \"party_join\"; code: string; }\n");
    out.push_str("export interface PartyLeaveMessage { t: \"party_leave\"; }\n");
    out.push_str("export interface ResyncMessage { t: \"resync\"; }\n");
    out.push_str("export interface ChatMessage { t: \"chat\"; channel: \"room\" | \"group\"; text: string; }\n");
    out.push_str("export interface FriendAddMessage { t: \"friend_add\"; handle: string; }\n");
    out.push_str(
        "export interface FriendRemoveMessage { t: \"friend_remove\"; handle: string; }\n",
    );
    out.push_str("export interface GroupCreateMessage { t: \"group_create\"; }\n");
    out.push_str("export interface GroupJoinMessage { t: \"group_join\"; code: string; }\n");
    out.push_str("export interface GroupLeaveMessage { t: \"group_leave\"; }\n");
    out.push_str("export interface CommunityMessage { t: \"community\"; action: import(\"./community\").CommunityAction; }\n");
    out.push_str("export interface ItemInstanceDTO { instance_id: string; def: string; location: \"bag\" | \"weapon\" | \"armor\"; refine: number; }\nexport interface MoveItemInstanceMessage { t: \"move_item_instance\"; op_id: string; instance_id: string; expected_revision: number; to: \"bag\" | \"weapon\" | \"armor\"; }\nexport interface ReturnToTownMessage { t: \"return_to_town\"; op_id: string; death_revision: number; }\nexport interface ClaimRewardMessage { t: \"claim_reward\"; op_id: string; receipt_id: string; }\n");
    out.push_str("export type ColdClientMessage =\n  | MageTrialMessage\n  | MageCastMessage\n  | MoveItemInstanceMessage\n  | ReturnToTownMessage\n  | ClaimRewardMessage\n  | CommunityMessage\n  | InteractMessage\n  | ActivateMessage\n  | ChooseMessage\n  | ClaimMessage\n  | UseItemMessage\n  | StoreBuyMessage\n  | BoxOpenMessage\n  | CosmeticsEquipMessage\n  | EquipItemMessage\n  | PickupDropMessage\n  | StatAllocateMessage\n  | RefineItemMessage\n  | PartyCreateMessage\n  | PartyJoinMessage\n  | PartyLeaveMessage\n  | ResyncMessage\n  | ChatMessage\n  | FriendAddMessage\n  | FriendRemoveMessage\n  | GroupCreateMessage\n  | GroupJoinMessage\n  | GroupLeaveMessage;\n");
    out.push_str("export type MageSkillId = \"h02_basic\" | \"h02_star_lance\";\nexport interface MageTrialMessage { t: \"mage_trial\"; enabled: boolean; op_id: string; }\nexport interface MageCastMessage { t: \"mage_cast\"; epoch: number; sequence: number; skill_id: MageSkillId; target_id: number; }\nexport interface MageTrialSkill { skill_id: MageSkillId; range_m: number; windup_ms: number; cooldown_ms: number; recovery_ms: number; sp_cost: number; projectile_speed_m_s: number; available: boolean; power: number; }\nexport interface MageTrialStateMessage { t: \"mage_trial_state\"; capability_enabled: boolean; profile: \"trailblade\" | \"mage_trial\"; focus_equipped: boolean; epoch: number; skills: MageTrialSkill[]; }\nexport interface MageCastStateMessage { t: \"mage_cast_state\"; cast_id: string; source_id: number; epoch: number; sequence: number; skill_id: MageSkillId; phase: \"started\" | \"released\" | \"impact\" | \"cancelled\" | \"rejected\"; reason: string; server_ms: number; start_ms: number; release_ms: number; impact_ms: number | null; recovery_end_ms: number; cooldown_end_ms: number; target_id: number; origin: [number,number,number]; target: [number,number,number]; damage: number; flags: number; }\n");
    out.push_str("export interface BagEntry { slot: number; item: string; count: number; }\n");
    out.push_str("export interface EquipEntry { slot: string; item: string; }\n");
    out.push_str("export interface DropEntry { encounter: string; item: string; count: number; x: number; z: number; }\n");
    out.push_str("export interface GrantEntry { def: string; count: number; }\n");
    out.push_str("export interface ChoiceEntry { id: string; label_key: string; }\n");
    out.push_str("export interface MemberEntry { id: number; name: string; }\n");
    out.push_str("export interface CharacterStats { str: number; agi: number; vit: number; int: number; dex: number; luk: number; }\n");
    out.push_str("export interface CharacterStateMessage {\n  vocation?: string; combat_profile?: \"trailblade\" | \"mage_trial\"; magic_power?: number; stats_base?: CharacterStats; stats_allocated?: CharacterStats; equipment_bonus?: {atk:number;def:number;max_hp:number}; character_id: string; item_instances: ItemInstanceDTO[]; t: \"character_state\"; rev: number; level: number; exp: number; base_exp_next: number; job_level: number; job_exp: number; job_exp_next: number; atk: number; def: number; equipment: EquipEntry[]; hp: number; max_hp: number; sp?: number; max_sp?: number; bag: BagEntry[]; pouch: Record<string, number>; gold: number; coin: number; skin: string | null; pet: string | null; owned_cosmetics: string[]; handle: string; name: string; stat_points: number; stats: CharacterStats; refine?: Record<string, number>; }\n");
    out.push_str("export interface QuestStateMessage { t: \"quest_state\"; rev: number; quest: string; state: string; objectives: Record<string, number>; step_ticks: Record<string, number>; }\n");
    out.push_str("export interface DialogueMessage { t: \"dialogue\"; npc: string; token: string; text_key: string; choices: ChoiceEntry[]; }\n");
    out.push_str("export interface DialogueClosedMessage { t: \"dialogue_closed\"; npc: string; reason: string; }\n");
    out.push_str("export interface OpResultMessage { t: \"op_result\"; op_id: string; status: string; reason: string; ends_at_ms: number; grants: GrantEntry[]; }\n");
    out.push_str("export interface PartyStateMessage { t: \"party_state\"; rev: number; members: MemberEntry[]; leader: number; code: string; expires_s: number; }\n");
    out.push_str("export interface NoticeMessage { t: \"notice\"; key: string; params: Record<string, unknown>; }\n");
    out.push_str("export interface SocialMemberEntry { device?: \"desktop\" | \"mobile\" | \"unknown\"; handle: string; name: string; online: boolean; channel: number | null; in_tower: boolean; }\n");
    out.push_str("export interface ChatBroadcastMessage { device?: \"desktop\" | \"mobile\" | \"unknown\"; t: \"chat\"; channel: string; from: string; text: string; }\n");
    out.push_str(
        "export interface FriendsMessage { t: \"friends\"; entries: SocialMemberEntry[]; }\n",
    );
    out.push_str("export interface GroupStateMessage { t: \"group\"; code: string | null; members: SocialMemberEntry[]; }\n");
    out.push_str("export interface DropsMessage { t: \"drops\"; entries: DropEntry[]; }\n");
    out.push_str("export type ColdServerMessage =\n  | MageTrialStateMessage\n  | MageCastStateMessage\n  | CharacterStateMessage\n  | QuestStateMessage\n  | DialogueMessage\n  | DialogueClosedMessage\n  | OpResultMessage\n  | PartyStateMessage\n  | NoticeMessage\n  | ChatBroadcastMessage\n  | FriendsMessage\n  | GroupStateMessage\n  | DropsMessage;\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const GEN_PATH: &str = "../../client/src/cold_v4.gen.ts";

    #[test]
    fn typescript_bindings_match_the_checked_in_file() {
        let expected = typescript_bindings();
        if std::env::var("UPDATE_BINDINGS").as_deref() == Ok("1") {
            let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("client/src/cold_v4.gen.ts");
            std::fs::write(path, &expected).expect("regen TS bindings");
            return;
        }
        let checked_in = include_str!("../../client/src/cold_v4.gen.ts");
        assert_eq!(
            checked_in, expected,
            "cold_v4.gen.ts drifted: regen with UPDATE_BINDINGS=1"
        );
        let _ = GEN_PATH;
    }

    #[test]
    fn tag_literals_round_trip() {
        for tag in [
            ColdTag::Interact,
            ColdTag::Activate,
            ColdTag::Choose,
            ColdTag::Claim,
            ColdTag::UseItem,
            ColdTag::StoreBuy,
            ColdTag::BoxOpen,
            ColdTag::CosmeticsEquip,
            ColdTag::EquipItem,
            ColdTag::PickupDrop,
            ColdTag::StatAllocate,
            ColdTag::RefineItem,
            ColdTag::PartyCreate,
            ColdTag::PartyJoin,
            ColdTag::PartyLeave,
            ColdTag::Resync,
            ColdTag::Chat,
            ColdTag::FriendAdd,
            ColdTag::FriendRemove,
            ColdTag::GroupCreate,
            ColdTag::GroupJoin,
            ColdTag::GroupLeave,
        ] {
            assert_eq!(ColdTag::parse(tag.as_str()), Some(tag));
        }
        assert_eq!(ColdTag::parse("party_create "), None);
        assert_eq!(ColdTag::parse(""), None);
    }

    #[test]
    fn id_code_and_op_id_shapes_are_enforced() {
        assert!(valid_id("sella"));
        assert!(valid_id("three_windmarks"));
        assert!(!valid_id(""));
        assert!(!valid_id("has space"));
        assert!(!valid_id("trail-potion"));
        assert!(!valid_id(&"x".repeat(65)));
        assert!(valid_code("K7Q2XA"));
        assert!(!valid_code("k7q2xa"));
        assert!(!valid_code("SHORT"));
        assert!(valid_op_id("123e4567-e89b-12d3-a456-426614174000"));
        assert!(!valid_op_id("not-a-uuid"));
        assert!(!valid_op_id("123e4567e89b12d3a456426614174000"));
    }

    #[test]
    fn every_client_tag_validates_and_rejects_shapes() {
        assert_eq!(
            validate_client_payload(br#"{"t":"interact","npc":"sella"}"#),
            Ok(ColdTag::Interact)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"activate","marker":"windmark_1"}"#),
            Ok(ColdTag::Activate)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"party_create"}"#),
            Ok(ColdTag::PartyCreate)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"resync"}"#),
            Ok(ColdTag::Resync)
        );
        // Unknown fields are denied even when the tag is known.
        assert_eq!(
            validate_client_payload(br#"{"t":"resync","extra":1}"#),
            Err(DecodeError::InvalidField)
        );
        // Tag/value mismatches and bad shapes are rejected.
        assert_eq!(
            validate_client_payload(br#"{"t":"claim","quest":"q","op_id":"nope"}"#),
            Err(DecodeError::InvalidField)
        );
        // Economy ops validate ids, op ids and the equip slot strictly.
        assert_eq!(
            validate_client_payload(
                br#"{"t":"store_buy","item":"trail_potion","op_id":"123e4567-e89b-12d3-a456-426614174000"}"#
            ),
            Ok(ColdTag::StoreBuy)
        );
        assert_eq!(
            validate_client_payload(
                br#"{"t":"box_open","item":"wooden_box","op_id":"123e4567-e89b-12d3-a456-426614174000"}"#
            ),
            Ok(ColdTag::BoxOpen)
        );
        assert_eq!(
            validate_client_payload(
                br#"{"t":"cosmetics_equip","slot":"skin","id":"skin_ember","op_id":"123e4567-e89b-12d3-a456-426614174000"}"#
            ),
            Ok(ColdTag::CosmeticsEquip)
        );
        assert_eq!(
            validate_client_payload(
                br#"{"t":"cosmetics_equip","slot":"hat","id":"skin_ember","op_id":"123e4567-e89b-12d3-a456-426614174000"}"#
            ),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(
                br#"{"t":"store_buy","item":"trail_potion","op_id":"not-a-uuid"}"#
            ),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"box_open","item":"wooden box","op_id":"123e4567-e89b-12d3-a456-426614174000"}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"store_buy","item":"trail_potion","op_id":"123e4567-e89b-12d3-a456-426614174000","price":1}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"party_join","code":"lower1"}"#),
            Err(DecodeError::InvalidField)
        );
        // Social tags: chat channels, sanitized text, handles and codes.
        assert_eq!(
            validate_client_payload(br#"{"t":"chat","channel":"room","text":"hello there"}"#),
            Ok(ColdTag::Chat)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"chat","channel":"group","text":"  hi  "}"#),
            Ok(ColdTag::Chat)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"chat","channel":"world","text":"hi"}"#),
            Err(DecodeError::InvalidField)
        );
        // All-control-character text sanitizes to nothing and is refused.
        assert_eq!(
            validate_client_payload(br#"{"t":"chat","channel":"room","text":"\u0007\t "}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"chat","channel":"room"}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"friend_add","handle":"a1b2c3d4"}"#),
            Ok(ColdTag::FriendAdd)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"friend_add","handle":"A1B2C3D4"}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"friend_add","handle":"short"}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"friend_remove","handle":"a1b2c3d4"}"#),
            Ok(ColdTag::FriendRemove)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"group_create"}"#),
            Ok(ColdTag::GroupCreate)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"group_join","code":"A1B2C3"}"#),
            Ok(ColdTag::GroupJoin)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"group_join","code":"a1b2c3"}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"group_leave"}"#),
            Ok(ColdTag::GroupLeave)
        );
        assert_eq!(
            validate_client_payload(br#"{"t":"nope"}"#),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(b"[1,2]"),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(b"{oops"),
            Err(DecodeError::InvalidField)
        );
        assert_eq!(
            validate_client_payload(&[0xff, 0xfe]),
            Err(DecodeError::InvalidField)
        );
        let oversized = format!(r#"{{"t":"resync","pad":"{}"}}"#, "x".repeat(600));
        assert_eq!(
            validate_client_payload(oversized.as_bytes()),
            Err(DecodeError::TooLarge)
        );
    }

    #[test]
    fn server_messages_serialize_to_their_canonical_json() {
        let character = CharacterStateMsg {
            vocation:None,combat_profile:None,magic_power:None,stats_base:None,stats_allocated:None,equipment_bonus:None,
            character_id:"00000000-0000-4000-8000-000000000001".into(),
            item_instances:Vec::new(),
            t: "character_state".to_string(),
            rev: 3,
            level: 2,
            exp: 117,
            base_exp_next: 120,
            job_level: 1,
            job_exp: 33,
            job_exp_next: 80,
            atk: 45,
            def: 8,
            equipment: vec![EquipEntry {
                slot: "weapon".to_string(),
                item: "frontier_blade".to_string(),
            }],
            hp: 80,
            max_hp: 100,
            sp: 30,
            max_sp: 30,
            bag: vec![BagEntry {
                slot: 0,
                item: "trail_potion".to_string(),
                count: 2,
            }],
            pouch: BTreeMap::from([("dew_bead".to_string(), 5)]),
            gold: 250,
            coin: 10,
            skin: Some("skin_ember".to_string()),
            pet: None,
            owned_cosmetics: vec!["skin_ember".to_string()],
            handle: "a1b2c3d4".to_string(),
            name: "Traveler-5678".to_string(),
            stat_points: 0,
            stats: CharacterStats {
                str_: 10,
                agi: 8,
                vit: 6,
                int_: 4,
                dex: 8,
                luk: 4,
            },
            refine: BTreeMap::new(),
        };
        assert_eq!(
            serde_json::to_string(&character).unwrap(),
            r#"{"character_id":"00000000-0000-4000-8000-000000000001","item_instances":[],"t":"character_state","rev":3,"level":2,"exp":117,"base_exp_next":120,"job_level":1,"job_exp":33,"job_exp_next":80,"atk":45,"def":8,"equipment":[{"slot":"weapon","item":"frontier_blade"}],"hp":80,"max_hp":100,"sp":30,"max_sp":30,"bag":[{"slot":0,"item":"trail_potion","count":2}],"pouch":{"dew_bead":5},"gold":250,"coin":10,"skin":"skin_ember","pet":null,"owned_cosmetics":["skin_ember"],"handle":"a1b2c3d4","name":"Traveler-5678","stat_points":0,"stats":{"str":10,"agi":8,"vit":6,"int":4,"dex":8,"luk":4},"refine":{}}"#
        );
        let quest = QuestStateMsg {
            t: "quest_state".to_string(),
            rev: 7,
            quest: "three_windmarks".to_string(),
            state: "active".to_string(),
            objectives: BTreeMap::from([("hunt".to_string(), 1), ("windmark".to_string(), 2)]),
            step_ticks: BTreeMap::from([("accepted".to_string(), 42)]),
        };
        assert_eq!(
            serde_json::to_string(&quest).unwrap(),
            r#"{"t":"quest_state","rev":7,"quest":"three_windmarks","state":"active","objectives":{"hunt":1,"windmark":2},"step_ticks":{"accepted":42}}"#
        );
        let dialogue = DialogueMsg {
            t: "dialogue".to_string(),
            npc: "sella".to_string(),
            token: "abc123".to_string(),
            text_key: "sella_greet".to_string(),
            choices: vec![
                ChoiceEntry {
                    id: "accept".to_string(),
                    label_key: "quest_accept".to_string(),
                },
                ChoiceEntry {
                    id: "later".to_string(),
                    label_key: "quest_later".to_string(),
                },
            ],
        };
        assert_eq!(
            serde_json::to_string(&dialogue).unwrap(),
            r#"{"t":"dialogue","npc":"sella","token":"abc123","text_key":"sella_greet","choices":[{"id":"accept","label_key":"quest_accept"},{"id":"later","label_key":"quest_later"}]}"#
        );
        let closed = DialogueClosedMsg {
            t: "dialogue_closed".to_string(),
            npc: "sella".to_string(),
            reason: "done".to_string(),
        };
        assert_eq!(
            serde_json::to_string(&closed).unwrap(),
            r#"{"t":"dialogue_closed","npc":"sella","reason":"done"}"#
        );
        let op = OpResultMsg {
            t: "op_result".to_string(),
            op_id: "123e4567-e89b-12d3-a456-426614174000".to_string(),
            status: "ok".to_string(),
            reason: "claimed".to_string(),
            ends_at_ms: 0,
            grants: vec![GrantEntry {
                def: "gale_seed".to_string(),
                count: 1,
            }],
        };
        assert_eq!(
            serde_json::to_string(&op).unwrap(),
            r#"{"t":"op_result","op_id":"123e4567-e89b-12d3-a456-426614174000","status":"ok","reason":"claimed","ends_at_ms":0,"grants":[{"def":"gale_seed","count":1}]}"#
        );
        let party = PartyStateMsg {
            t: "party_state".to_string(),
            rev: 1,
            members: vec![MemberEntry {
                id: 2,
                name: "Ash".to_string(),
            }],
            leader: 2,
            code: "K7Q2XA".to_string(),
            expires_s: 600,
        };
        assert_eq!(
            serde_json::to_string(&party).unwrap(),
            r#"{"t":"party_state","rev":1,"members":[{"id":2,"name":"Ash"}],"leader":2,"code":"K7Q2XA","expires_s":600}"#
        );
        let notice = NoticeMsg {
            t: "notice".to_string(),
            key: "welcome".to_string(),
            params: serde_json::json!({"motd": 1}),
        };
        assert_eq!(
            serde_json::to_string(&notice).unwrap(),
            r#"{"t":"notice","key":"welcome","params":{"motd":1}}"#
        );
        let chat = ChatBroadcastMsg::new("room", "Traveler-5678", "hello there");
        assert_eq!(
            serde_json::to_string(&chat).unwrap(),
            r#"{"t":"chat","channel":"room","from":"Traveler-5678","text":"hello there"}"#
        );
        let member =
            |handle: &str, name: &str, online: bool, channel: Option<u8>, in_tower: bool| {
                SocialMemberMsg {
                    device: crate::community::Device::Unknown,
                    handle: handle.to_string(),
                    name: name.to_string(),
                    online,
                    channel,
                    in_tower,
                }
            };
        let friends = FriendsMsg::new(vec![
            member("a1b2c3d4", "Traveler-5678", true, Some(2), false),
            member("e5f6a7b8", "Traveler-9abc", false, None, false),
        ]);
        assert_eq!(
            serde_json::to_string(&friends).unwrap(),
            r#"{"t":"friends","entries":[{"handle":"a1b2c3d4","name":"Traveler-5678","online":true,"channel":2,"in_tower":false},{"handle":"e5f6a7b8","name":"Traveler-9abc","online":false,"channel":null,"in_tower":false}]}"#
        );
        let group = GroupStateMsg::new(
            Some("A1B2C3".to_string()),
            vec![member("a1b2c3d4", "Traveler-5678", true, None, true)],
        );
        assert_eq!(
            serde_json::to_string(&group).unwrap(),
            r#"{"t":"group","code":"A1B2C3","members":[{"handle":"a1b2c3d4","name":"Traveler-5678","online":true,"channel":null,"in_tower":true}]}"#
        );
        let disbanded = GroupStateMsg::new(None, Vec::new());
        assert_eq!(
            serde_json::to_string(&disbanded).unwrap(),
            r#"{"t":"group","code":null,"members":[]}"#
        );
    }

    #[test]
    fn chat_text_sanitizes_with_the_identity_discipline() {
        // Control characters become spaces, whitespace collapses, caps apply.
        assert_eq!(
            sanitize_text("  hello   world  ", MAX_CHAT_CHARS),
            "hello world"
        );
        assert_eq!(sanitize_text("a\u{7}b\n\rc", MAX_CHAT_CHARS), "a b c");
        let long = "x".repeat(MAX_CHAT_CHARS + 40);
        assert_eq!(
            sanitize_text(&long, MAX_CHAT_CHARS).chars().count(),
            MAX_CHAT_CHARS
        );
        assert!(sanitize_text("\u{1}\u{2}", MAX_CHAT_CHARS).is_empty());
        // Unicode text survives and counts characters, not bytes.
        assert_eq!(sanitize_text("héllo wörld", MAX_CHAT_CHARS), "héllo wörld");
    }

    #[test]
    fn chat_friend_and_group_decoders_round_trip_and_refuse_wrong_tags() {
        let chat =
            decode_chat_request(br#"{"t":"chat","channel":"group","text":"  hi   there  "}"#)
                .expect("chat decodes");
        assert_eq!(
            chat,
            ChatRequest {
                channel: ChatChannel::Group,
                text: "hi there".to_string(),
            }
        );
        assert_eq!(
            decode_chat_request(br#"{"t":"resync"}"#).err(),
            Some(DecodeError::InvalidField)
        );
        let friend = decode_friend_request(br#"{"t":"friend_add","handle":"a1b2c3d4"}"#)
            .expect("friend_add decodes");
        assert_eq!(
            friend,
            FriendOp::Add {
                handle: "a1b2c3d4".to_string()
            }
        );
        let remove = decode_friend_request(br#"{"t":"friend_remove","handle":"e5f6a7b8"}"#)
            .expect("friend_remove decodes");
        assert_eq!(
            remove,
            FriendOp::Remove {
                handle: "e5f6a7b8".to_string()
            }
        );
        assert_eq!(
            decode_friend_request(br#"{"t":"friend_add","handle":"a1b2c3d"}"#).err(),
            Some(DecodeError::InvalidField)
        );
        assert_eq!(
            decode_friend_request(br#"{"t":"chat","channel":"room","text":"hi"}"#).err(),
            Some(DecodeError::InvalidField)
        );
        assert_eq!(
            decode_group_request(br#"{"t":"group_create"}"#),
            Ok(GroupOp::Create)
        );
        assert_eq!(
            decode_group_request(br#"{"t":"group_join","code":"A1B2C3"}"#),
            Ok(GroupOp::Join {
                code: "A1B2C3".to_string()
            })
        );
        assert_eq!(
            decode_group_request(br#"{"t":"group_leave"}"#),
            Ok(GroupOp::Leave)
        );
        assert_eq!(
            decode_group_request(br#"{"t":"group_join","code":"SHORT"}"#).err(),
            Some(DecodeError::InvalidField)
        );
        assert_eq!(
            decode_group_request(br#"{"t":"resync"}"#).err(),
            Some(DecodeError::InvalidField)
        );
        assert!(valid_handle("a1b2c3d4"));
        assert!(!valid_handle("a1b2c3d"));
        assert!(!valid_handle("a1b2c3d40"));
        assert!(!valid_handle("A1B2C3D4"));
        assert!(!valid_handle("a1b2c3dg"));
    }

    #[test]
    fn persisted_relative_results_keep_idempotency_without_renewing_a_deadline() {
        let old = r#"{"t":"op_result","op_id":"123e4567-e89b-12d3-a456-426614174000","status":"ok","reason":"claimed","cooldown_ms":10000,"grants":[{"def":"gale_seed","count":1}]}"#;
        let result: OpResultMsg = serde_json::from_str(old).unwrap();
        assert_eq!(result.ends_at_ms, 0);
        assert_eq!(result.grants[0].count, 1);
        let serialized = serde_json::to_value(&result).unwrap();
        assert_eq!(serialized["ends_at_ms"], 0);
        assert!(serialized.get("cooldown_ms").is_none());
    }

    #[test]
    fn golden_cold_fixtures_validate() {
        #[derive(Deserialize)]
        struct GoldenCold {
            cold_client: Vec<NamedJson>,
            cold_server: Vec<NamedJson>,
        }
        #[derive(Deserialize)]
        struct NamedJson {
            name: String,
            json: String,
        }
        let golden: GoldenCold =
            serde_json::from_str(include_str!("../../protocol/golden-v6.json"))
                .expect("golden file parses");
        assert_eq!(golden.cold_client.len(), 18);
        assert_eq!(golden.cold_server.len(), 10);
        for entry in &golden.cold_client {
            let tag = validate_client_payload(entry.json.as_bytes())
                .expect("golden cold client validates");
            // The fixture name is the message tag.
            assert_eq!(tag.as_str(), entry.name, "fixture {}", entry.name);
        }
        for entry in &golden.cold_server {
            let value: serde_json::Value =
                serde_json::from_str(&entry.json).expect("golden cold server parses");
            assert!(value.is_object(), "fixture {}", entry.name);
            assert!(
                encode_server_payload(&entry.json).is_ok(),
                "fixture {}",
                entry.name
            );
        }
        // Every economy op tag decodes through its dedicated decoder, and the
        // decoders refuse payloads carrying a different tag.
        type DecodeCheck = fn(&[u8]) -> Result<(), DecodeError>;
        let decode_cases: [(&str, DecodeCheck); 6] = [
            ("store_buy", |bytes| {
                decode_store_buy_request(bytes).map(|_| ())
            }),
            ("box_open", |bytes| {
                decode_box_open_request(bytes).map(|_| ())
            }),
            ("cosmetics_equip", |bytes| {
                decode_cosmetics_equip_request(bytes).map(|_| ())
            }),
            ("chat", |bytes| decode_chat_request(bytes).map(|_| ())),
            ("friend_add", |bytes| {
                decode_friend_request(bytes).map(|_| ())
            }),
            ("group_join", |bytes| {
                decode_group_request(bytes).map(|_| ())
            }),
        ];
        let by_name: std::collections::BTreeMap<&str, &str> = golden
            .cold_client
            .iter()
            .map(|entry| (entry.name.as_str(), entry.json.as_str()))
            .collect();
        for (tag, decode) in decode_cases {
            decode(by_name[tag].as_bytes()).expect("golden payload decodes");
            decode(by_name["resync"].as_bytes()).expect_err("wrong tag refused");
        }
    }

    #[test]
    fn mage_intents_are_typed_bounded_and_refuse_unapproved_skills_or_extra_authority() {
        let good=serde_json::json!({"t":"mage_cast","epoch":1,"sequence":1,"skill_id":"h02_basic","target_id":123});
        assert_eq!(validate_client_payload(&serde_json::to_vec(&good).unwrap()).unwrap(),ColdTag::MageCast);
        for (key,bad) in [("epoch",serde_json::json!(0)),("sequence",serde_json::json!(0)),("target_id",serde_json::json!(0)),("skill_id",serde_json::json!("h02_meteor")),("damage",serde_json::json!(9999)),("sequence",serde_json::json!(4294967296u64))] {
            let mut value=good.clone();value[key]=bad;assert!(validate_client_payload(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        assert_eq!(validate_client_payload(br#"{"t":"mage_trial","enabled":true,"op_id":"bad"}"#),Err(DecodeError::InvalidField));
    }

    #[test]
    fn server_payload_cap_is_enforced() {
        assert!(encode_server_payload(r#"{"t":"notice","key":"k","params":{}}"#).is_ok());
        assert_eq!(
            encode_server_payload(&format!(
                r#"{{"t":"notice","key":"k","params":{{"pad":"{}"}}}}"#,
                "x".repeat(5000)
            )),
            Err(DecodeError::TooLarge)
        );
        assert_eq!(
            encode_server_payload("not json"),
            Err(DecodeError::InvalidField)
        );
    }
}
