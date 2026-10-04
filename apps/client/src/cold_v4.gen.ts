// GENERATED from apps/server/src/cold.rs — do not edit by hand.
// Regen: UPDATE_BINDINGS=1 cargo test --manifest-path apps/server/Cargo.toml cold
export type ColdClientTag =
  | "mage_trial"
  | "mage_cast"
  | "move_item_instance"
  | "return_to_town"
  | "claim_reward"
  | "community"
  | "interact"
  | "activate"
  | "choose"
  | "claim"
  | "use_item"
  | "store_buy"
  | "box_open"
  | "cosmetics_equip"
  | "equip_item"
  | "pickup_drop"
  | "stat_allocate"
  | "refine_item"
  | "party_create"
  | "party_join"
  | "party_leave"
  | "resync"
  | "chat"
  | "friend_add"
  | "friend_remove"
  | "group_create"
  | "group_join"
  | "group_leave"
;
export interface InteractMessage { t: "interact"; npc: string; }
export interface ActivateMessage { t: "activate"; marker: string; }
export interface ChooseMessage { t: "choose"; npc: string; token: string; choice: string; }
export interface ClaimMessage { t: "claim"; quest: string; op_id: string; }
export interface UseItemMessage { t: "use_item"; item: string; op_id: string; }
export interface StoreBuyMessage { t: "store_buy"; item: string; op_id: string; }
export interface BoxOpenMessage { t: "box_open"; item: string; op_id: string; }
export interface CosmeticsEquipMessage { t: "cosmetics_equip"; slot: string; id: string; op_id: string; }
export interface EquipItemMessage { t: "equip_item"; item: string; op_id: string; }
export interface PickupDropMessage { t: "pickup_drop"; encounter: string; op_id: string; }
export interface StatAllocateMessage { t: "stat_allocate"; stat: "str" | "agi" | "vit" | "int" | "dex" | "luk"; points: number; op_id: string; }
export interface RefineItemMessage { t: "refine_item"; slot: "weapon" | "armor"; op_id: string; instance_id?: string; expected_revision?: number; }
export interface PartyCreateMessage { t: "party_create"; }
export interface PartyJoinMessage { t: "party_join"; code: string; }
export interface PartyLeaveMessage { t: "party_leave"; }
export interface ResyncMessage { t: "resync"; }
export interface ChatMessage { t: "chat"; channel: "room" | "group"; text: string; }
export interface FriendAddMessage { t: "friend_add"; handle: string; }
export interface FriendRemoveMessage { t: "friend_remove"; handle: string; }
export interface GroupCreateMessage { t: "group_create"; }
export interface GroupJoinMessage { t: "group_join"; code: string; }
export interface GroupLeaveMessage { t: "group_leave"; }
export interface CommunityMessage { t: "community"; action: import("./community").CommunityAction; }
export interface ItemInstanceDTO { instance_id: string; def: string; location: "bag" | "weapon" | "armor"; refine: number; }
export interface MoveItemInstanceMessage { t: "move_item_instance"; op_id: string; instance_id: string; expected_revision: number; to: "bag" | "weapon" | "armor"; }
export interface ReturnToTownMessage { t: "return_to_town"; op_id: string; death_revision: number; }
export interface ClaimRewardMessage { t: "claim_reward"; op_id: string; receipt_id: string; }
export type ColdClientMessage =
  | MageTrialMessage
  | MageCastMessage
  | MoveItemInstanceMessage
  | ReturnToTownMessage
  | ClaimRewardMessage
  | CommunityMessage
  | InteractMessage
  | ActivateMessage
  | ChooseMessage
  | ClaimMessage
  | UseItemMessage
  | StoreBuyMessage
  | BoxOpenMessage
  | CosmeticsEquipMessage
  | EquipItemMessage
  | PickupDropMessage
  | StatAllocateMessage
  | RefineItemMessage
  | PartyCreateMessage
  | PartyJoinMessage
  | PartyLeaveMessage
  | ResyncMessage
  | ChatMessage
  | FriendAddMessage
  | FriendRemoveMessage
  | GroupCreateMessage
  | GroupJoinMessage
  | GroupLeaveMessage;
export type MageSkillId = "h02_basic" | "h02_star_lance";
export interface MageTrialMessage { t: "mage_trial"; enabled: boolean; op_id: string; }
export interface MageCastMessage { t: "mage_cast"; epoch: number; sequence: number; skill_id: MageSkillId; target_id: number; }
export interface MageTrialSkill { skill_id: MageSkillId; range_m: number; windup_ms: number; cooldown_ms: number; recovery_ms: number; sp_cost: number; projectile_speed_m_s: number; available: boolean; power: number; }
export interface MageTrialStateMessage { t: "mage_trial_state"; capability_enabled: boolean; profile: "trailblade" | "mage_trial"; focus_equipped: boolean; epoch: number; skills: MageTrialSkill[]; }
export interface MageCastStateMessage { t: "mage_cast_state"; cast_id: string; source_id: number; epoch: number; sequence: number; skill_id: MageSkillId; phase: "started" | "released" | "impact" | "cancelled" | "rejected"; reason: string; server_ms: number; start_ms: number; release_ms: number; impact_ms: number | null; recovery_end_ms: number; cooldown_end_ms: number; target_id: number; origin: [number,number,number]; target: [number,number,number]; damage: number; flags: number; }
export interface BagEntry { slot: number; item: string; count: number; }
export interface EquipEntry { slot: string; item: string; }
export interface DropEntry { encounter: string; item: string; count: number; x: number; z: number; }
export interface GrantEntry { def: string; count: number; }
export interface ChoiceEntry { id: string; label_key: string; }
export interface MemberEntry { id: number; name: string; }
export interface CharacterStats { str: number; agi: number; vit: number; int: number; dex: number; luk: number; }
export interface CharacterStateMessage {
  vocation?: string; combat_profile?: "trailblade" | "mage_trial"; magic_power?: number; stats_base?: CharacterStats; stats_allocated?: CharacterStats; equipment_bonus?: {atk:number;def:number;max_hp:number}; character_id: string; item_instances: ItemInstanceDTO[]; t: "character_state"; rev: number; level: number; exp: number; base_exp_next: number; job_level: number; job_exp: number; job_exp_next: number; atk: number; def: number; equipment: EquipEntry[]; hp: number; max_hp: number; sp?: number; max_sp?: number; bag: BagEntry[]; pouch: Record<string, number>; gold: number; coin: number; skin: string | null; pet: string | null; owned_cosmetics: string[]; handle: string; name: string; stat_points: number; stats: CharacterStats; refine?: Record<string, number>; }
export interface QuestStateMessage { t: "quest_state"; rev: number; quest: string; state: string; objectives: Record<string, number>; step_ticks: Record<string, number>; }
export interface DialogueMessage { t: "dialogue"; npc: string; token: string; text_key: string; choices: ChoiceEntry[]; }
export interface DialogueClosedMessage { t: "dialogue_closed"; npc: string; reason: string; }
export interface OpResultMessage { t: "op_result"; op_id: string; status: string; reason: string; ends_at_ms: number; grants: GrantEntry[]; }
export interface PartyStateMessage { t: "party_state"; rev: number; members: MemberEntry[]; leader: number; code: string; expires_s: number; }
export interface NoticeMessage { t: "notice"; key: string; params: Record<string, unknown>; }
export interface SocialMemberEntry { device?: "desktop" | "mobile" | "unknown"; handle: string; name: string; online: boolean; channel: number | null; in_tower: boolean; }
export interface ChatBroadcastMessage { device?: "desktop" | "mobile" | "unknown"; t: "chat"; channel: string; from: string; text: string; }
export interface FriendsMessage { t: "friends"; entries: SocialMemberEntry[]; }
export interface GroupStateMessage { t: "group"; code: string | null; members: SocialMemberEntry[]; }
export interface DropsMessage { t: "drops"; entries: DropEntry[]; }
export type ColdServerMessage =
  | MageTrialStateMessage
  | MageCastStateMessage
  | CharacterStateMessage
  | QuestStateMessage
  | DialogueMessage
  | DialogueClosedMessage
  | OpResultMessage
  | PartyStateMessage
  | NoticeMessage
  | ChatBroadcastMessage
  | FriendsMessage
  | GroupStateMessage
  | DropsMessage;
