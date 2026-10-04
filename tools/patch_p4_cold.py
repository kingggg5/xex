# One-off patch: P4 cold.rs — PickupDrop tag/request/decoder + DropsMsg payload + generator.
import io

NL = chr(10)
p = "apps/server/src/cold.rs"
s = io.open(p, encoding="utf-8").read()

# enum
old = "    BoxOpen," + NL + "    CosmeticsEquip," + NL + "    EquipItem,"
new = "    BoxOpen," + NL + "    CosmeticsEquip," + NL + "    EquipItem," + NL + "    PickupDrop,"
assert old in s, "enum anchor"
s = s.replace(old, new, 1)

old = '            Self::EquipItem => "equip_item",'
new = '            Self::EquipItem => "equip_item",' + NL + '            Self::PickupDrop => "pickup_drop",'
assert old in s, "as_str anchor"
s = s.replace(old, new, 1)

old = '            "equip_item" => Self::EquipItem,'
new = '            "equip_item" => Self::EquipItem,' + NL + '            "pickup_drop" => Self::PickupDrop,'
assert old in s, "parse anchor"
s = s.replace(old, new, 1)

# validation arm
old = "            ColdTag::PartyCreate => {"
new = (
    "            ColdTag::PickupDrop => {" + NL +
    "                let message: PickupDropMsg =" + NL +
    "                    serde_json::from_value(value.clone()).map_err(|_| DecodeError::InvalidField)?;" + NL +
    "                if !tag_is(&message.t, tag)" + NL +
    "                    || message.encounter.len() != 36" + NL +
    "                    || !message.encounter.bytes().all(|byte| byte.is_ascii_hexdigit() || byte == b'-')" + NL +
    "                    || !valid_op_id(&message.op_id)" + NL +
    "                {" + NL +
    "                    return Err(DecodeError::InvalidField);" + NL +
    "                }" + NL +
    "            }" + NL +
    "            ColdTag::PartyCreate => {"
)
assert old in s, "validate anchor"
s = s.replace(old, new, 1)

# request + msg + decoder (after equip decoder)
old = "pub fn decode_interact_request(bytes: &[u8]) -> Result<InteractRequest, DecodeError> {"
new = (
    "/// P4: pick up one owned ground drop (walk-over range enforced world-side)." + NL +
    "#[derive(Debug, Clone, PartialEq, Eq)]" + NL +
    "pub struct PickupDropRequest {" + NL +
    "    pub encounter: String," + NL +
    "    pub op_id: String," + NL +
    "}" + NL +
    "" + NL +
    "#[derive(Debug, Deserialize)]" + NL +
    "struct PickupDropMsg {" + NL +
    "    t: String," + NL +
    "    encounter: String," + NL +
    "    op_id: String," + NL +
    "}" + NL +
    "" + NL +
    "/// Decode a validated pickup intent for the world owner (P4)." + NL +
    "pub fn decode_pickup_drop_request(bytes: &[u8]) -> Result<PickupDropRequest, DecodeError> {" + NL +
    "    if validate_client_payload(bytes)? != ColdTag::PickupDrop {" + NL +
    "        return Err(DecodeError::InvalidField);" + NL +
    "    }" + NL +
    "    let message: PickupDropMsg =" + NL +
    "        serde_json::from_slice(bytes).map_err(|_| DecodeError::InvalidField)?;" + NL +
    "    Ok(PickupDropRequest {" + NL +
    "        encounter: message.encounter," + NL +
    "        op_id: message.op_id," + NL +
    "    })" + NL +
    "}" + NL +
    "" + NL +
    "pub fn decode_interact_request(bytes: &[u8]) -> Result<InteractRequest, DecodeError> {"
)
assert old in s, "decoder anchor"
s = s.replace(old, new, 1)

# server payloads: DropEntry + DropsMsg (next to CharacterStateMsg)
old = "/// E07: one equipped piece (`slot` = \"weapon\" | \"armor\")."
new = (
    "/// P4: one owned ground drop (`encounter` is the UUIDv7 kill identity)." + NL +
    "#[allow(dead_code)]" + NL +
    "#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]" + NL +
    "pub struct DropEntry {" + NL +
    "    pub encounter: String," + NL +
    "    pub item: String," + NL +
    "    pub count: u32," + NL +
    "    pub x: f32," + NL +
    "    pub z: f32," + NL +
    "}" + NL +
    "" + NL +
    "/// P4: the player's live ground drops (private loot; full replace on push)." + NL +
    "#[allow(dead_code)]" + NL +
    "#[derive(Debug, Clone, Serialize, Deserialize)]" + NL +
    "pub struct DropsMsg {" + NL +
    "    pub t: String," + NL +
    "    pub entries: Vec<DropEntry>," + NL +
    "}" + NL +
    "" + NL +
    "/// E07: one equipped piece (`slot` = \"weapon\" | \"armor\")."
)
assert old in s, "payload anchor"
s = s.replace(old, new, 1)

# generator: client tag + message + payload types
old = '        ColdTag::EquipItem,' + NL + '        ColdTag::PartyCreate,'
new = '        ColdTag::EquipItem,' + NL + '        ColdTag::PickupDrop,' + NL + '        ColdTag::PartyCreate,'
assert old in s, "gen tag anchor"
s = s.replace(old, new, 1)

old = '    out.push_str("export interface EquipItemMessage { t: \\"equip_item\\"; item: string; op_id: string; }\\n");'
new = (
    '    out.push_str("export interface EquipItemMessage { t: \\"equip_item\\"; item: string; op_id: string; }\\n");' + NL +
    '    out.push_str("export interface PickupDropMessage { t: \\"pickup_drop\\"; encounter: string; op_id: string; }\\n");'
)
assert old in s, "gen msg anchor"
s = s.replace(old, new, 1)

old = "  | EquipItemMessage" + NL + "  | PartyCreateMessage"
new = "  | EquipItemMessage" + NL + "  | PickupDropMessage" + NL + "  | PartyCreateMessage"
assert old in s, "gen union anchor"
s = s.replace(old, new, 1)

old = '    out.push_str("export interface EquipEntry { slot: string; item: string; }\\n");'
new = (
    '    out.push_str("export interface EquipEntry { slot: string; item: string; }\\n");' + NL +
    '    out.push_str("export interface DropEntry { encounter: string; item: string; count: number; x: number; z: number; }\\n");'
)
assert old in s, "gen entry anchor"
s = s.replace(old, new, 1)

old = '    out.push_str("export type ColdServerMessage =\\n'
new = (
    '    out.push_str("export interface DropsMessage { t: \\"drops\\"; entries: DropEntry[]; }\\n");' + NL +
    '    out.push_str("export type ColdServerMessage =\\n'
)
assert old in s, "gen server union anchor"
s = s.replace(old, new, 1)

old = "  | GroupStateMessage;\\n\");"
new = "  | GroupStateMessage\\n  | DropsMessage;\\n\");"
assert old in s, "gen union tail anchor"
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline=NL).write(s)
print("cold.rs P4 ok")

# ---------------- room.rs: dispatch arms ----------------
p = "apps/server/src/room.rs"
s = io.open(p, encoding="utf-8").read()

old = "                    match crate::cold::validate_client_payload(&payload) {" + NL + "                        Ok(crate::cold::ColdTag::EquipItem) => {"
new = (
    "                    match crate::cold::validate_client_payload(&payload) {" + NL +
    "                        Ok(crate::cold::ColdTag::PickupDrop) => {" + NL +
    "                            let player_id = conns.get(&conn).map(|live| live.player_id);" + NL +
    "                            let request = crate::cold::decode_pickup_drop_request(&payload);" + NL +
    "                            match (player_id, request) {" + NL +
    "                                (Some(player_id), Ok(request)) => {" + NL +
    "                                    if let Some(result) = world.pickup_drop(player_id, request) {" + NL +
    "                                        deliver_cold(&mut conns, &mut conn_sessions, &mut session_conns, &mut metrics, &mut world, conn, &result);" + NL +
    "                                        if let Some(state) = world.character_state(player_id) {" + NL +
    "                                            deliver_cold(&mut conns, &mut conn_sessions, &mut session_conns, &mut metrics, &mut world, conn, &state);" + NL +
    "                                        }" + NL +
    "                                        if let Some(drops) = world.drops_state(player_id) {" + NL +
    "                                            deliver_cold(&mut conns, &mut conn_sessions, &mut session_conns, &mut metrics, &mut world, conn, &drops);" + NL +
    "                                        }" + NL +
    "                                    }" + NL +
    "                                }" + NL +
    "                                _ => metrics.dropped_commands += 1," + NL +
    "                            }" + NL +
    "                        }" + NL +
    "                        Ok(crate::cold::ColdTag::EquipItem) => {"
)
assert old in s, "room pickup anchor"
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline=NL).write(s)
print("room.rs pickup ok")
