import type { Scene } from '@babylonjs/core/scene';
import { snapshotCityRepresentations, type CityRepresentationReviewSnapshot } from './city-representation-review';

const records = new WeakMap<Scene, { panel: HTMLElement; output: HTMLElement; snapshots: CityRepresentationReviewSnapshot[] }>();

/** Visible developer evidence, separate from the product HUD and game state. */
export function recordCityRepresentationPhase(scene: Scene, phase: string): void {
	if (!import.meta.env.DEV || new URLSearchParams(location.search).get('cityWalkReview') !== '1') return;
	let record = records.get(scene);
	if (!record) {
		const panel = document.createElement('details'), heading = document.createElement('summary'), output = document.createElement('pre');
		panel.setAttribute('aria-label', 'City representation review');
		panel.style.cssText = 'position:fixed;left:12px;top:205px;z-index:1100;max-width:330px;max-height:180px;overflow:auto;background:#10212de8;color:#ffe3ac;padding:8px;font:11px system-ui';
		heading.textContent = 'City representation receipts'; output.setAttribute('aria-label', 'City representation receipts');
		output.style.cssText = 'font:10px monospace;white-space:pre-wrap'; panel.append(heading, output); document.body.append(panel);
		record = { panel, output, snapshots: [] }; records.set(scene, record);
		scene.onDisposeObservable.addOnce(() => { panel.remove(); records.delete(scene); });
	}
	if (record.snapshots.some(snapshot => snapshot.phase === phase)) return;
	const snapshot = snapshotCityRepresentations(scene, { phase }); record.snapshots.push(snapshot);
	const heading = record.panel.querySelector('summary');
	if (heading) heading.textContent = `City receipts: ${record.snapshots.map(s => s.phase).join(' → ')}`;
	// Full serializable evidence is readable via DOM; canvas appearance needs captures.
	record.output.textContent = JSON.stringify(record.snapshots);
}
