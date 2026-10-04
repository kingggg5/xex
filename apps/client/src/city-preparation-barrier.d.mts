export type CityPreparationState = 'idle' | 'loading' | 'prepared' | 'ready' | 'failed';
export interface CityPreparationBarrierSnapshot {
  readonly holding: boolean;
  readonly eligible: boolean;
  readonly terminal: boolean;
  readonly state: CityPreparationState | null;
  readonly coverAt: number | null;
  readonly firstStopSequence: number | null;
  readonly latestNeutralSequence: number | null;
  readonly acknowledgedSequence: number;
  readonly coverPaintMs: number;
  readonly maxSequence: number;
}
export interface CityPreparationBarrier {
  reset(): void;
  shouldHold(waitingAtApproach: boolean, detailState: CityPreparationState): boolean;
  markCover(now: number): boolean;
  noteStopInput(sequence: number): boolean;
  acknowledge(sequence: number): boolean;
  canBegin(online: boolean, now: number): boolean;
  snapshot(): CityPreparationBarrierSnapshot;
}
export function createCityPreparationBarrier(): CityPreparationBarrier;
