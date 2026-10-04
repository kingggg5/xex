import assert from 'node:assert/strict';
import test from 'node:test';
import { createCityPreparationBarrier } from '../src/city-preparation-barrier.mjs';

function armed(sequence = 42, cover = 0) {
  const barrier = createCityPreparationBarrier();
  assert.equal(barrier.shouldHold(true, 'idle'), true);
  assert.equal(barrier.markCover(cover), true);
  assert.equal(barrier.noteStopInput(sequence), true);
  return barrier;
}

test('online preparation needs the neutral ACK and the complete paint window', () => {
  const barrier = armed();
  assert.equal(barrier.canBegin(true, 299), false);
  assert.equal(barrier.canBegin(true, 300), false);
  assert.equal(barrier.acknowledge(41), true);
  assert.equal(barrier.canBegin(true, 301), false);
  assert.equal(barrier.acknowledge(42), true);
  assert.equal(barrier.canBegin(true, 302), true);
  assert.equal(barrier.canBegin(true, 303), true, 'read-only eligibility queries must not consume preparation');
});

test('an early ACK cannot skip the cover delay and later cover frames do not restart it', () => {
  const barrier = armed(1, 0);
  assert.equal(barrier.acknowledge(1), true);
  assert.equal(barrier.markCover(200), true);
  assert.equal(barrier.snapshot().coverAt, 0);
  assert.equal(barrier.canBegin(true, 299.999), false);
  assert.equal(barrier.canBegin(true, 300), true);
});

test('zero sequence never supplies a stop input or releases an online barrier', () => {
  const barrier = createCityPreparationBarrier();
  barrier.shouldHold(true, 'idle'); barrier.markCover(0);
  assert.equal(barrier.noteStopInput(0), false);
  assert.equal(barrier.acknowledge(0), false);
  assert.equal(barrier.canBegin(true, 300), false);
  assert.equal(barrier.noteStopInput(1), true);
  assert.equal(barrier.acknowledge(0), false);
  assert.equal(barrier.canBegin(true, 301), false);
});

test('latest observed neutral bounds ACKs while the first stop target stays fixed', () => {
  const barrier = armed(44);
  assert.equal(barrier.acknowledge(47), false);
  assert.equal(barrier.noteStopInput(45), true);
  assert.equal(barrier.noteStopInput(47), true);
  assert.equal(barrier.snapshot().firstStopSequence, 44);
  assert.equal(barrier.snapshot().latestNeutralSequence, 47);
  assert.equal(barrier.acknowledge(46), true);
  assert.equal(barrier.canBegin(true, 300), true, 'a newer applied neutral proves the dropped first stop was also superseded safely');
});

test('stale ACKs and duplicate or backwards neutral sequences cannot regress state', () => {
  const barrier = armed(10); barrier.noteStopInput(12); barrier.acknowledge(12);
  assert.equal(barrier.acknowledge(11), false);
  assert.equal(barrier.acknowledge(12), false);
  assert.equal(barrier.noteStopInput(12), false);
  assert.equal(barrier.noteStopInput(9), false);
  assert.equal(barrier.snapshot().acknowledgedSequence, 12);
  assert.equal(barrier.canBegin(true, 300), true);
});

test('offline preparation requires paint time without inventing a server ACK', () => {
  const barrier = createCityPreparationBarrier(); barrier.shouldHold(true, 'idle'); barrier.markCover(0);
  assert.equal(barrier.canBegin(false, 299), false);
  assert.equal(barrier.canBegin(false, 300), true);
  assert.equal(barrier.snapshot().firstStopSequence, null);
  assert.equal(barrier.snapshot().acknowledgedSequence, 0);
  assert.equal(barrier.canBegin(true, 301), false, 'switching online still needs a real neutral ACK');
});

test('loader loading/prepared holds even if smoothing briefly crosses the approach backwards', () => {
  const barrier = armed(2); barrier.acknowledge(2);
  assert.equal(barrier.shouldHold(false, 'loading'), true);
  assert.equal(barrier.canBegin(true, 300), false, 'already-loading assets must not start a second preparation');
  assert.equal(barrier.shouldHold(false, 'prepared'), true);
  assert.equal(barrier.canBegin(true, 301), false);
  assert.equal(barrier.shouldHold(false, 'ready'), false);
});

test('ready cache and failed fallback settle without a cold barrier restart', () => {
  for (const state of ['ready', 'failed']) {
    const barrier = armed(); barrier.acknowledge(42);
    assert.equal(barrier.shouldHold(true, state), false);
    assert.equal(barrier.canBegin(true, 300), false);
    assert.equal(barrier.markCover(301), false);
    assert.equal(barrier.noteStopInput(43), false);
    assert.equal(barrier.shouldHold(true, 'idle'), false, 'a stale external idle observation must not reopen settled preparation');
    assert.equal(barrier.snapshot().terminal, true);
  }
  const cached = createCityPreparationBarrier();
  assert.equal(cached.shouldHold(false, 'ready'), false);
  assert.equal(cached.shouldHold(true, 'idle'), false);
});

test('reconnect reset clears old ACKs, stop targets, covers and terminal state', () => {
  const barrier = armed(744); barrier.acknowledge(744); assert.equal(barrier.canBegin(true, 300), true);
  barrier.shouldHold(true, 'ready'); barrier.reset();
  assert.equal(barrier.snapshot().coverAt, null);
  assert.equal(barrier.snapshot().firstStopSequence, null);
  assert.equal(barrier.snapshot().acknowledgedSequence, 0);
  assert.equal(barrier.acknowledge(744), false, 'old epoch ACK before a new stop cannot arm the barrier');
  barrier.shouldHold(true, 'idle'); barrier.markCover(0); barrier.noteStopInput(1);
  assert.equal(barrier.acknowledge(744), false, 'old epoch high ACK is impossible ahead of the new observed neutral');
  assert.equal(barrier.canBegin(true, 300), false);
  barrier.acknowledge(1); assert.equal(barrier.canBegin(true, 301), true);
});

test('withdrawal before loading needs a fresh stop and cover on reapproach', () => {
  const barrier = armed(7); barrier.acknowledge(7); barrier.canBegin(true, 300);
  assert.equal(barrier.shouldHold(false, 'idle'), false);
  assert.equal(barrier.snapshot().firstStopSequence, null);
  assert.equal(barrier.shouldHold(true, 'idle'), true);
  barrier.markCover(400); barrier.noteStopInput(8);
  assert.equal(barrier.canBegin(true, 700), false);
  barrier.acknowledge(8); assert.equal(barrier.canBegin(true, 701), true);
});

test('sequence bounds reject non-integers, overflow and reserved maximums', () => {
  const barrier = armed(1);
  for (const value of [-1, 1.5, NaN, Infinity, 0xffff_ffff, Number.MAX_SAFE_INTEGER, '2']) {
    assert.equal(barrier.noteStopInput(value), false);
    assert.equal(barrier.acknowledge(value), false);
  }
  assert.equal(barrier.noteStopInput(0xffff_fffe), true);
  assert.equal(barrier.acknowledge(0xffff_fffe), true);
  assert.equal(barrier.canBegin(true, 300), true);
});

test('invalid or backwards clocks never satisfy painting and reset accepts a new clock origin', () => {
  const barrier = armed(1, 100); barrier.acknowledge(1);
  for (const value of [-1, NaN, Infinity, 99]) {
    assert.equal(barrier.markCover(value), false);
    assert.equal(barrier.canBegin(true, value), false);
  }
  assert.equal(barrier.canBegin(true, 399), false);
  assert.equal(barrier.canBegin(true, 400), true);
  assert.equal(barrier.canBegin(true, 399), false);
  barrier.reset(); barrier.shouldHold(true, 'idle'); barrier.markCover(0);
  assert.equal(barrier.canBegin(false, 300), true);
});

test('external state and returned diagnostics cannot be silently forged', () => {
  const barrier = createCityPreparationBarrier();
  assert.throws(() => barrier.shouldHold('yes', 'idle'), TypeError);
  assert.throws(() => barrier.shouldHold(true, 'unknown'), TypeError);
  assert.equal(barrier.markCover(0), false);
  assert.equal(barrier.noteStopInput(1), false);
  assert.equal(barrier.canBegin(false, 300), false);
  const snapshot = barrier.snapshot(); assert.ok(Object.isFrozen(snapshot)); assert.ok(Object.isFrozen(barrier));
  assert.throws(() => { snapshot.acknowledgedSequence = 100; }, TypeError);
  assert.equal(barrier.snapshot().acknowledgedSequence, 0);
});
