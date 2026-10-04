import type { BootstrapPhaseEvent } from '../bootstrap-progress.mjs';
import type { ChannelRoom } from '../connection-service.mjs';
import type { ConnectionLobbyView } from './types';
export function lobbyRooms(rooms: unknown, worldName: string): ChannelRoom[];
export function displayChannel(channel: number): string;
export function displayLatency(value: number | null): string;
export function transferText(event: BootstrapPhaseEvent): string | null;
export function chosenAvailable(model: Pick<ConnectionLobbyView, 'hasSelection' | 'selected' | 'autoAvailable' | 'rooms'>): boolean;
