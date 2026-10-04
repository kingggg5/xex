/** Coverage is projected bounding-sphere area / view area, not polygon count. */
export function configureHeroOakLod(master, medium, distant) {
	master.useLODScreenCoverage = true;
	master.addLODLevel(0.035, medium);
	master.addLODLevel(0.006, distant);
}
