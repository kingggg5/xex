/** Only the mounted Character tab bar owns these modal scroll styles. */
export function characterScrollClearance(tabs: HTMLElement): { destroy(): void } {
	const content = tabs.closest<HTMLElement>(".modal-content");
	if (!content) return { destroy() {} };
	const properties = ["scroll-padding-top", "--character-scroll-pad"];
	const previous = properties.map(property => ({ property, value: content.style.getPropertyValue(property), priority: content.style.getPropertyPriority(property) }));
	const owned = new Map<string, string>();
	let disposed = false;
	const measure = () => {
		if (disposed) return;
		const padding = Number.parseFloat(getComputedStyle(content).paddingTop) || 0;
		const height = tabs.getBoundingClientRect().height;
		if (!Number.isFinite(height) || height <= 0) return;
		const values = [Math.ceil(height + padding + 8) + "px", Math.max(0, padding) + "px"];
		properties.forEach((property, index) => {
			if (content.style.getPropertyValue(property) !== values[index]) content.style.setProperty(property, values[index]);
			owned.set(property, values[index]);
		});
	};
	measure();
	const observer = new ResizeObserver(measure);
	observer.observe(tabs);
	observer.observe(content);
	return { destroy() {
		disposed = true;
		observer.disconnect();
		for (const { property, value, priority } of previous) {
			if (content.style.getPropertyValue(property) !== owned.get(property)) continue;
			if (value) content.style.setProperty(property, value, priority);
			else content.style.removeProperty(property);
		}
	} };
}
