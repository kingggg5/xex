export function createLobbyKeyQuarantine(): {
	keyDown(event: Pick<KeyboardEvent, 'key' | 'code' | 'repeat' | 'ctrlKey' | 'metaKey' | 'altKey'>, active: boolean): boolean;
	keyUp(event: Pick<KeyboardEvent, 'key' | 'code'>): void;
	size(): number;
	clear(): void;
};
