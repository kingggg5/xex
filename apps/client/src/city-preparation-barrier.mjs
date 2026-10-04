/** Keep city preparation behind an acknowledged neutral movement input.
 * This observes loader state only; it does not change transport clocks,
 * prediction history, reconciliation thresholds, or authoritative movement.
 */
const MAX_SEQUENCE = 0xffff_fffe;
const COVER_PAINT_MS = 300;
const STATES = new Set(['idle', 'loading', 'prepared', 'ready', 'failed']);
const sequenceIsValid = (value, minimum) => Number.isSafeInteger(value) && value >= minimum && value <= MAX_SEQUENCE;

export function createCityPreparationBarrier() {
  let holding = false;
  let eligible = false;
  let terminal = false;
  let state = null;
  let coverAt = null;
  let lastClock = null;
  let firstStop = null;
  let latestNeutral = null;
  let ackSequence = 0;

  function clearPending() {
    coverAt = null;
    firstStop = null;
    latestNeutral = null;
    ackSequence = 0;
  }
  function validClock(now) {
    return Number.isFinite(now) && now >= 0 && (lastClock === null || now >= lastClock);
  }
  function reset() {
    holding = false;
    eligible = false;
    terminal = false;
    state = null;
    lastClock = null;
    clearPending();
  }

  return Object.freeze({
    reset,

    /** Call with the current external state before checking canBegin.
     * Loading/prepared hold independently of a smoothed position crossing
     * backwards over the approach boundary. Ready/failed settle until reset.
     */
    shouldHold(waitingAtApproach, detailState) {
      if (typeof waitingAtApproach !== 'boolean' || !STATES.has(detailState)) throw new TypeError('City barrier needs a boolean approach flag and a valid loader state.');
      state = detailState;
      if (detailState === 'ready' || detailState === 'failed') terminal = true;
      if (terminal) { holding = false; eligible = false; return false; }
      eligible = waitingAtApproach && detailState === 'idle';
      holding = eligible || detailState === 'loading' || detailState === 'prepared';
      // Withdrawing before preparation cancels the old stop/paint proof. A
      // future approach must not reuse an ACK while ordinary motion resumed.
      if (!holding) clearPending();
      return holding;
    },

    /** Mark the first frame in which the loading cover was requested.
     * Zero is a valid clock value. Later calls never restart its paint window.
     */
    markCover(now) {
      if (!holding || terminal || !validClock(now)) return false;
      lastClock = now;
      if (coverAt === null) coverAt = now;
      return true;
    },

    /** Note every forced neutral input, preserving the first stop target. */
    noteStopInput(sequence) {
      if (!holding || terminal || !sequenceIsValid(sequence, 1) || (latestNeutral !== null && sequence <= latestNeutral)) return false;
      if (firstStop === null) firstStop = sequence;
      latestNeutral = sequence;
      return true;
    },

    /** Ignore stale, impossible-ahead and pre-stop ACKs. The caller must also
     * fence messages by connection epoch and call reset on Welcome/reconnect.
     */
    acknowledge(sequence) {
      if (!holding || terminal || firstStop === null || !sequenceIsValid(sequence, 0) || sequence <= ackSequence || sequence > latestNeutral) return false;
      ackSequence = sequence;
      return true;
    },

    /** A query, not a consuming action: the external loader remains the owner
     * of its idle/loading/ready lifecycle and its single preparation request.
     */
    canBegin(online, now) {
      if (typeof online !== 'boolean' || terminal || !eligible || !validClock(now)) return false;
      lastClock = now;
      if (coverAt === null || now - coverAt < COVER_PAINT_MS) return false;
      return !online || (firstStop !== null && ackSequence >= firstStop);
    },

    /** Primitive-only diagnostics. Transport ACK/error metrics stay separate. */
    snapshot() {
      return Object.freeze({ holding, eligible, terminal, state, coverAt, firstStopSequence: firstStop, latestNeutralSequence: latestNeutral, acknowledgedSequence: ackSequence, coverPaintMs: COVER_PAINT_MS, maxSequence: MAX_SEQUENCE });
    },
  });
}
