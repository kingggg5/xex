export type BootstrapPhaseId = "content" | "renderer" | "codecs" | "assets" | "shaders" | "room" | "snapshot" | "first_frame";
export type BootstrapPhaseState = "pending" | "active" | "complete" | "error";
export interface BootstrapPhaseEvent {
	id: BootstrapPhaseId;
	state: BootstrapPhaseState;
	/** A short, caller-owned asset identifier, never an arbitrary signed URL. */
	resource?: string;
	/** Transfer counters for this one resource only; both are omitted if not computable. */
	loaded?: number;
	total?: number;
	/** Stable UI translation key, rather than a raw exception or credentials. */
	errorCode?: string;
}
export interface BootstrapProgressSnapshot {
	phases: readonly Readonly<BootstrapPhaseEvent>[];
	/** Most recently changed phases, maximum six. Byte updates do not add duplicate rows. */
	recent: readonly Readonly<BootstrapPhaseEvent>[];
	completed: number;
	total: number;
	unit: "phases";
	ready: boolean;
	failed: boolean;
}
export interface BootstrapProgressModel {
	/** False for malformed events, terminal late callbacks, and duplicates. */
	update(event: unknown): boolean;
	snapshot(): BootstrapProgressSnapshot;
}
export const BOOTSTRAP_PHASE_IDS: readonly BootstrapPhaseId[];
export function parseBootstrapPhaseEvent(value: unknown): BootstrapPhaseEvent | null;
export function bootstrapAssetProgress(resource: string, progress?: { lengthComputable?: boolean; loaded?: number; total?: number }): BootstrapPhaseEvent | null;
export function createBootstrapProgress(ids?: readonly BootstrapPhaseId[]): BootstrapProgressModel;
