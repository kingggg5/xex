import type { BootstrapPhaseEvent, BootstrapPhaseId } from '../bootstrap-progress.mjs';
import type { ChannelRoom, ChannelSelectionService } from '../connection-service.mjs';

export type LobbyLanguage = 'th' | 'en';
export interface ConnectionLobbyView {
	language: LobbyLanguage;
	worldName: string;
	mode: 'channels' | 'loading' | 'ready';
	rooms: ChannelRoom[];
	latencyMs: number | null;
	autoAvailable: boolean;
	selected: number | null;
	hasSelection: boolean;
	loadingRooms: boolean;
	applying: boolean;
	error: string;
	warnings: string[];
	canRetry: boolean;
	retrying: boolean;
	phases: BootstrapPhaseEvent[];
	recent: BootstrapPhaseEvent[];
	completed: number;
	total: number;
}
export interface ConnectionLobbyController {
	chooseChannel(service: ChannelSelectionService): Promise<{ channel: number | null }>;
	beginLoading(phaseIds?: readonly BootstrapPhaseId[]): void;
	updatePhase(event: BootstrapPhaseEvent): void;
	ready(): void;
	showError(message: string, retry?: () => void | Promise<void>): void;
	dispose(): void;
}
