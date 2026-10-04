export type LayoutProfile = "desktop" | "mobile-portrait" | "mobile-landscape";
export interface ControlPosition { x: number; y: number }
export type ControlPositions = Record<string, ControlPosition>;
export interface ControlLayout { version: 1; profiles: Partial<Record<LayoutProfile, ControlPositions>> }
export interface LayoutSession { original: ControlPositions; draft: ControlPositions; pointer: null | { id: string; pointerId: number; original: ControlPosition | null; start: ControlPosition } }
export const LAYOUT_STORAGE_KEY: string;
export const LAYOUT_PROFILES: readonly LayoutProfile[];
export const CONTROL_IDS: readonly string[];
export function layoutProfile(width: number, height: number, touch?: boolean): LayoutProfile;
export function clonePositions(positions: ControlPositions): ControlPositions;
export function emptyLayout(): ControlLayout;
export function parseLayout(raw: unknown): ControlLayout | null;
export function loadLayout(storage: Pick<Storage, "getItem">): { layout: ControlLayout; status: "missing" | "loaded" | "invalid" | "unavailable" };
export function saveLayoutProfile(storage: Pick<Storage, "setItem">, layout: ControlLayout, profile: LayoutProfile, positions: ControlPositions): { ok: boolean; layout: ControlLayout };
export function clampControl(point: ControlPosition, size: { width: number; height: number }, viewport: { width: number; height: number }, inset?: Partial<{ left: number; right: number; top: number; bottom: number }>): ControlPosition;
export function createLayoutSession(positions: ControlPositions): LayoutSession;
export function resetLayoutSession(session: LayoutSession): void;
export function cancelLayoutSession(session: LayoutSession): ControlPositions;
export function beginControlDrag(session: LayoutSession, id: string, pointerId: number, point: ControlPosition): boolean;
export function updateControlDrag(session: LayoutSession, pointerId: number, point: ControlPosition): boolean;
export function endControlDrag(session: LayoutSession, pointerId: number, cancelled?: boolean): boolean;
