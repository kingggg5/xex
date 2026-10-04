import type {ServerMessage} from './protocol';

export interface SnapshotDeliveryOptions {
	zoneLimit: number;
	now(): number;
	isCurrent(): boolean;
	applyMessage(message: ServerMessage): void;
	sendPacket(packet: ArrayBuffer): void;
	close(): void;
	onReadyChange(ready: boolean): void;
	onResync(reason: string): void;
	onError(stage: 'decode' | 'handler' | 'send', error: unknown, messageType?: ServerMessage['type']): void;
}
export function createSnapshotDelivery(options: SnapshotDeliveryOptions): {
	receive(data: unknown): 'applied' | 'ignored' | 'resync' | 'closed';
	readonly ready: boolean;
	dispose(): void;
};
