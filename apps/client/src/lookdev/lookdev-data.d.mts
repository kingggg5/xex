export type LookdevView = "player" | "side" | "close" | "elevated";
export interface LookdevPoint { x: number; y: number; z: number }
export interface LockedCamera { view: LookdevView; alpha: number; beta: number; radius: number; fov: number; target: LookdevPoint }
export interface SampleSummary { n: number; p50: number | null; p95: number | null; min: number | null; max: number | null }
export type LookdevSampleField = "frameIntervalMs" | "cpuSceneMs" | "cpuSubmissionMs" | "cpuTargetsMs" | "gpuMs" | "drawCalls" | "activeMeshes" | "activeTriangles" | "particles";
export type LookdevSample = Record<LookdevSampleField, number | null> & { focused?: boolean };
export type WindowSnapshot = Record<LookdevSampleField, SampleSummary> & { capacity: number; retained: number; total: number; focus: { focusedFrames: number; unfocusedFrames: number; unknownFrames: number } };
export const LOOKDEV_VIEWS: readonly LookdevView[];
export const LOOKDEV_CAMERAS: Readonly<Record<LookdevView, Readonly<Omit<LockedCamera, "view" | "target">>>>;
export const LOOKDEV_MAX_SAMPLES: number;
export const LOOKDEV_MAX_ARCHIVE_BYTES: number;
export function evidenceSlug(value: unknown, fallback?: string): string;
export function parseLookdevRequest(search: string): { pillar: string; cycle: string; variant: "A" | "B"; lodDistance: 40 | 120 | null } | null;
export function clonePrimitiveMetadata(input: unknown): Record<string, unknown>;
export function lockedCamera(view: LookdevView, target: LookdevPoint, lodDistance?: 40 | 120 | null): LockedCamera;
export function summarize(values: Iterable<number>): SampleSummary;
export class LookdevSampleWindow { capacity: number; length: number; total: number; constructor(capacity?: number); reset(): void; push(sample: LookdevSample): void; snapshot(): WindowSnapshot; }
export function crc32(bytes: Uint8Array): number;
export function createEvidenceZip(files: Array<{ name: string; bytes: Uint8Array }>): Uint8Array;
export function compareLookdevPacks(a: unknown, b: unknown): { comparable: boolean; mismatches: string[]; deltas: Array<{ view: LookdevView; p95FrameMs: number | null; p95CpuMs: number | null; p95GpuMs: number | null; p95DrawCalls: number | null; p95ActiveTriangles: number | null }> };
