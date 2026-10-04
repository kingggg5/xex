export interface MobileWebAppPolicyInput { width: number; height: number; coarse?: boolean; maxTouchPoints?: number; orientationType?: string; legacyAngle?: number; displayStandalone?: boolean; navigatorStandalone?: boolean; guideOpen?: boolean }
export interface MobileWebAppPolicy { viewportPortrait: boolean; physicalPortrait: boolean; portrait: boolean; standalone: boolean; guideOpen: boolean; blocked: boolean }
export function mobileWebAppPolicy(input: MobileWebAppPolicyInput): MobileWebAppPolicy;
export const GAMEPLAY_CODES: ReadonlySet<string>;
export function keepGuideEntry(kind: string, connected: boolean, isCurrentContext: boolean): boolean;
export interface HeldKey { target: EventTarget; code: string; key: string; location: number; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }
export interface HeldPointer { target: EventTarget; pointerId: number; pointerType: string; isPrimary: boolean; clientX: number; clientY: number }
export function createHeldInputLedger(): { keyDown(record: HeldKey): void; keyUp(code: string, ownedRelease?: boolean): void; isKeyQuarantined(code: string): boolean; pointerDown(record: HeldPointer): void; pointerCapture(pointerId: number, target: EventTarget): void; pointerEnd(pointerId: number): void; drain(): { keys: HeldKey[]; pointers: HeldPointer[] }; clear(): void; size(): { keys: number; pointers: number; quarantined: number } };
