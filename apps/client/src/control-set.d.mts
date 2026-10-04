import type { ControlPosition, ControlPositions, LayoutProfile } from './hud-control-layout.mjs';
export type ControlArtId = 'native' | 'a02-frostglass' | 'a04-wildwood-jade' | 'a05-astral-orbit' | 'a08-dawn-petal' | 'a10-dragonbone' | 'b04-floating-thumbstick' | 'b09-crystal-silver' | 'b13-celestial-rune';
export type ControlGroup = 'movement' | 'combat' | 'menu';
export interface ControlSet { id: string; name: string; art: ControlArtId; profiles: Partial<Record<LayoutProfile, ControlPositions>> }
export interface ControlSetCollection { version: 2; activeId: string; sets: ControlSet[] }
export interface ControlSetResult { ok: boolean; collection: ControlSetCollection; reason?: string }
export const CONTROL_SET_STORAGE_KEY: string;
export const MAX_CONTROL_SETS: number;
export const MAX_CONTROL_SET_NAME: number;
export const CONTROL_ART_IDS: readonly ControlArtId[];
export const CONTROL_GROUPS: Readonly<Record<ControlGroup, readonly string[]>>;
export function controlSetName(value: unknown): string;
export function emptyControlSets(profiles?: Partial<Record<LayoutProfile, ControlPositions>>): ControlSetCollection;
export function cloneControlSets(collection: ControlSetCollection): ControlSetCollection;
export function activeControlSet(collection: ControlSetCollection): ControlSet;
export function parseControlSets(raw: unknown): ControlSetCollection | null;
export function loadControlSets(storage: Pick<Storage, 'getItem'>): { collection: ControlSetCollection; status: 'loaded' | 'missing' | 'invalid' | 'invalid-recovered' | 'migrated' | 'unavailable' };
export function saveControlSets(storage: Pick<Storage, 'setItem'>, saved: ControlSetCollection, draft: ControlSetCollection): ControlSetResult;
export function createControlSet(collection: ControlSetCollection, name: unknown): ControlSetResult;
export function renameControlSet(collection: ControlSetCollection, name: unknown): ControlSetResult;
export function deleteControlSet(collection: ControlSetCollection): ControlSetResult;
export function selectControlSet(collection: ControlSetCollection, id: string): ControlSetCollection;
export function updateControlSetProfile(collection: ControlSetCollection, profile: LayoutProfile, positions: ControlPositions): ControlSetCollection;
export function updateControlSetArt(collection: ControlSetCollection, art: ControlArtId): ControlSetCollection;
export function translateControlGroup(positions: ControlPositions, sizes: Record<string, { width: number; height: number }>, delta: ControlPosition, viewport: { width: number; height: number }, inset?: Partial<{ left: number; right: number; top: number; bottom: number }>): ControlPositions;
