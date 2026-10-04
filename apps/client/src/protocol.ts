export { PROTOCOL_VERSION } from "./wire.mjs";
export type {
	ColdClientMessage,
	ColdClientTag,
	ColdServerMessage,
} from "./cold_v4.gen";

export type ActionKind = "attack" | "arc_slash" | "dodge" | "guard";
export type CombatActionKind = ActionKind | "splash_hop";

export type ActionReason =
	| "none"
	| "cooldown"
	| "out_of_range"
	| "no_target"
	| "dead"
	| "busy"
	| "not_allowed"
	| "rate_limited";

export interface PlayerSnapshot {
	y?: number;
	id: number;
	x: number;
	z: number;
	facing: number;
	hp: number;
	max_hp: number;
	connected: boolean;
	flags: number;
	anim: number;
}

export interface MonsterSnapshot {
	id: number;
	kind: number;
	x: number;
	z: number;
	facing: number;
	hp: number;
	max_hp: number;
	active: boolean;
	flags: number;
	state: number;
	ability: number;
	state_ticks: number;
	target_x: number;
	target_z: number;
}

export interface CombatEvent {
	id: bigint;
	source_kind: number;
	source_id: number;
	target_kind: number;
	target_id: number;
	action: CombatActionKind;
	amount: number;
	flags: number;
	world_x: number;
	world_z: number;
}

export interface WelcomeMessage {
	type: "welcome";
	player_id: number;
	epoch: number;
	tick: bigint;
	x: number;
	z: number;
	zone_id: number;
	content_hash: bigint;
	tick_hz: number;
}

export interface SnapshotMessage {
	epoch?: number;
	baseline_tick?: bigint;
	full?: boolean;
	type: "snapshot";
	tick: bigint;
	ack_seq: number;
	own_flags: number;
	ack_x: number;
	ack_z: number;
	players: PlayerSnapshot[];
	monsters: MonsterSnapshot[];
	events: CombatEvent[];
}

export interface ErrorMessage {
	type: "error";
	code: "protocol_mismatch" | "malformed_packet" | "room_full" | "session_active" | "session_expired" | "invalid_join" | "rate_limited";
}

export interface ActionResultMessage {
	type: "action_result";
	seq: number;
	accepted: boolean;
	reason: ActionReason;
	/** Absolute room-clock expiry in milliseconds (tick * 50); zero means none. */
	ends_at_ms: bigint;
}

export interface PongMessage {
	type: "pong";
	nonce: number;
	client_ms: number;
	server_tick: bigint;
}

export interface ColdMessage {
	type: "cold";
	tag: string;
	data: Record<string, unknown>;
}

export type ServerMessage =
	| WelcomeMessage
	| SnapshotMessage
	| ErrorMessage
	| ActionResultMessage
	| PongMessage
	| ColdMessage;
