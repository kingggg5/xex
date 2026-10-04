import {createSnapshotDecoder, encodeSnapshotAck, ResyncRequired} from './wire.mjs';

/** One delivery controller per WebSocket. Application success, not decoding,
 * acknowledges a baseline. An invalid delta never replaces the visible world. */
export function createSnapshotDelivery(options) {
	const decoder = createSnapshotDecoder();
	let epoch = 0;
	let welcomeTick = 0n;
	let ready = false;
	let ended = false;
	let lastResyncAt = -Infinity;
	const current = () => !ended && options.isCurrent();
	const setReady = value => {
		if (ready === value) return;
		ready = value;
		options.onReadyChange(value);
	};
	function fail(stage, error, messageType) {
		if (!current()) return 'ignored';
		ended = true;
		setReady(false);
		decoder.reset();
		options.onError(stage, error, messageType);
		options.close();
		return 'closed';
	}
	function requestFull(reason) {
		setReady(false);
		const now = options.now();
		if (epoch && Number.isFinite(now) && now - lastResyncAt >= 1000) {
			lastResyncAt = now;
			try { options.sendPacket(encodeSnapshotAck(epoch, 0n, true)); }
			catch (error) { return fail('send', error); }
			options.onResync(reason);
		}
		return 'resync';
	}
	function receive(data) {
		if (!current()) return 'ignored';
		let message;
		try { message = decoder.decode(data, options.zoneLimit); }
		catch (error) {
			if (error instanceof ResyncRequired && epoch) return requestFull(error.reason);
			return fail('decode', error);
		}
		if(!epoch && message.type!=='welcome' && message.type!=='error')return fail('decode',new RangeError('message precedes welcome'),message.type);
		if (message.type === 'snapshot' && message.tick < welcomeTick) {
			return fail('decode', new RangeError('snapshot precedes welcome tick'), message.type);
		}
		// Recovery requires a full snapshot. Pongs/cold authority updates continue,
		// but a later decodable delta must not expose a partially recovered world.
		if (message.type === 'snapshot' && !ready && message.full !== true) {
			return requestFull('full_snapshot_required');
		}
		try { options.applyMessage(message); }
		catch (error) { return fail('handler', error, message.type); }
		// A handler can close/replace its socket (for example a content mismatch).
		if (!current()) return 'ignored';
		if (message.type === 'welcome') {
			epoch = message.epoch;
			welcomeTick = message.tick;
			setReady(false);
			// decode(welcome) already seeded the decoder. Resetting here loses it.
		} else if (message.type === 'snapshot' && message.epoch === epoch) {
			try { options.sendPacket(encodeSnapshotAck(epoch, message.tick)); }
			catch (error) { return fail('send', error, message.type); }
			if (current() && message.full === true) setReady(true);
		}
		return 'applied';
	}
	return {
		receive,
		get ready() { return ready && current(); },
		dispose() { ended = true; ready = false; decoder.reset(); },
	};
}
