export interface ChannelRoom {
	channel: number;
	name?: string | null;
	players: number;
	capacity: number;
}
export interface ChannelLoadResult {
	rooms: ChannelRoom[];
	/** One measured HTTP round trip to the shared server, not individual channels. */
	latencyMs: number | null;
	autoAvailable: boolean;
	warnings?: string[];
}
export interface ChannelSelectionService {
	load(signal?: AbortSignal): Promise<ChannelLoadResult>;
	apply(channel: number | null, signal?: AbortSignal): Promise<void>;
}
export type ChannelSelectionErrorCode =
	| "invalid_channel" | "channel_rejected" | "session_required"
	| "channel_unavailable" | "invalid_response" | "network_error" | "timeout";
export class ChannelSelectionError extends Error {
	readonly code: ChannelSelectionErrorCode;
	constructor(code: ChannelSelectionErrorCode);
}
export function createChannelSelectionCore(dependencies: {
	worldName: string;
	fetchImpl: typeof fetch;
	parseRooms(body: unknown): { channel: number; players: number; capacity: number }[] | null;
	saveStoredChannel(channel: number | null): void;
	now?: () => number;
	/** Tests may shorten the deadline; production defaults to 2,500ms. */
	timeoutMs?: number;
}): ChannelSelectionService;
