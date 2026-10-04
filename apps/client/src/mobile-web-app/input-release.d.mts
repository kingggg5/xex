import type { createHeldInputLedger, HeldKey, HeldPointer } from './policy.mjs';
export function releaseHeldInputs(ledger: ReturnType<typeof createHeldInputLedger>, events: { keyUp(record: HeldKey): Event; pointerCancel(record: HeldPointer): Event | null; isDisconnected?(target: EventTarget): boolean; globalKeyUp?(record: HeldKey): void }): { keys: number; pointers: number; failures: number };
