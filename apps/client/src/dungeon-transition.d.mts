export type TransitionState = "Explore" | "Prepare" | "Ready" | "Commit" | "Enter" | "Failure" | "Recover";
export const STATES: Readonly<{
	explore: "Explore"; prepare: "Prepare"; ready: "Ready"; commit: "Commit";
	enter: "Enter"; failure: "Failure"; recover: "Recover";
}>;
export interface Transfer {
	transferId: string;
	dungeonId: string;
	reservationId: string | null;
	contentVersion: string | null;
	expiresAt: number | null;
	assetsReady: boolean;
	destinationReady: boolean;
	committed: boolean;
}
export interface TransitionSnapshot {
	readonly state: TransitionState;
	readonly generation: number;
	readonly deadline: number | null;
	readonly reason: string | null;
	readonly transfer: Readonly<Transfer> | null;
}
interface ScopedEvent { generation: number; transferId: string }
interface DestinationIdentity { reservationId: string; contentVersion: string }
export type TransitionEvent =
	| { type: "begin"; transferId: string; dungeonId: string }
	| (DestinationIdentity & { type: "resume"; transferId: string; dungeonId: string })
	| { type: "tick" | "cancel" | "reconnect" | "request_commit" | "finish" }
	| (ScopedEvent & DestinationIdentity & { type: "reserved"; expiresAt: number })
	| (ScopedEvent & { type: "assets_ready"; contentVersion: string })
	| (ScopedEvent & { type: "rejected"; reason: string; uncommitted?: boolean })
	| (ScopedEvent & { type: "load_failed"; reason: string })
	| (ScopedEvent & DestinationIdentity & { type: "committed" | "status_committed" | "destination_ready" });
export interface TransitionEffect {
	type: "prepare" | "release" | "dispose_staging" | "query_status" | "recovery_timeout" |
		"confirm_and_commit" | "stage_assets" | "request_destination" | "reveal" | "dispose_stale";
	generation: number;
	transferId: string;
	reservationId?: string | null;
	dungeonId?: string;
	contentVersion?: string;
}
export interface TransitionResult { accepted: boolean; snapshot: TransitionSnapshot; effects: TransitionEffect[] }
export class DungeonTransition {
	constructor(options?: { clock?: () => number; prepareMs?: number; commitMs?: number });
	readonly snapshot: TransitionSnapshot;
	dispatch(event: TransitionEvent): TransitionResult;
}
