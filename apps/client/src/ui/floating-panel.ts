import type { ActionReturn } from "svelte/action";

interface FloatingOptions { handle?: HTMLElement; target?: HTMLElement; resetKey?: string | null }
const MOBILE = "(max-width: 767px), (pointer: coarse) and (max-width: 900px)";

/** Event-driven desktop movement; no simulation loop or engine object is involved. */
export function floatingPanel(node: HTMLElement, initial: FloatingOptions): ActionReturn<FloatingOptions> {
	let options = initial;
	let x = 0;
	let y = 0;
	let binding = new AbortController();
	let dragging: AbortController | null = null;
	let stopDrag: (() => void) | null = null;
	const lifetime = new AbortController();
	const mobile = window.matchMedia(MOBILE);
	const target = () => options.target ?? node;
	const apply = (nextX: number, nextY: number) => {
		const bounds = target().getBoundingClientRect();
		x = Math.min(window.innerWidth - bounds.right + x - 8, Math.max(8 - bounds.left + x, nextX));
		y = Math.min(window.innerHeight - bounds.bottom + y - 8, Math.max(8 - bounds.top + y, nextY));
		target().style.setProperty("--svelte-offset-x", `${x}px`);
		target().style.setProperty("--svelte-offset-y", `${y}px`);
	};
	const reset = () => {
		x = y = 0;
		target().style.removeProperty("--svelte-offset-x");
		target().style.removeProperty("--svelte-offset-y");
	};
	const bind = () => {
		binding.abort();
		binding = new AbortController();
		const handle = options.handle;
		if (!handle) return;
		handle.addEventListener("pointerdown", (event) => {
			if (event.button !== 0 || mobile.matches) return;
			event.preventDefault();
			event.stopPropagation();
			handle.focus();
			stopDrag?.();
			dragging = new AbortController();
			const startX = event.clientX, startY = event.clientY, oldX = x, oldY = y;
			handle.setPointerCapture(event.pointerId);
			const stop = () => {
				if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
				dragging?.abort();
				dragging = null;
				stopDrag = null;
			};
			stopDrag = stop;
			handle.addEventListener("pointermove", (move) => apply(oldX + move.clientX - startX, oldY + move.clientY - startY), { signal: dragging.signal });
			handle.addEventListener("pointerup", stop, { signal: dragging.signal, once: true });
			handle.addEventListener("pointercancel", stop, { signal: dragging.signal, once: true });
		}, { signal: binding.signal });
		handle.addEventListener("keydown", (event) => {
			if (mobile.matches || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home"].includes(event.key)) return;
			event.preventDefault();
			event.stopPropagation();
			if (event.key === "Home") reset();
			else apply(x + (event.key === "ArrowRight" ? 24 : event.key === "ArrowLeft" ? -24 : 0), y + (event.key === "ArrowDown" ? 24 : event.key === "ArrowUp" ? -24 : 0));
		}, { signal: binding.signal });
	};
	const resized = () => { if (mobile.matches) { stopDrag?.(); reset(); } else apply(x, y); };
	window.addEventListener("resize", resized, { signal: lifetime.signal, passive: true });
	mobile.addEventListener("change", resized, { signal: lifetime.signal });
	bind();
	return {
		update(next) { if (next.resetKey !== options.resetKey) { stopDrag?.(); reset(); } options = next; bind(); },
		destroy() { stopDrag?.(); binding.abort(); lifetime.abort(); reset(); },
	};
}

export function trapDialogKey(event: KeyboardEvent, dialog: HTMLElement, close: () => void): void {
	if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); return; }
	if (event.key !== "Tab") return;
	const elements = [...dialog.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')].filter((element) => element.getClientRects().length > 0 && !element.closest("[hidden]"));
	const first = elements[0], last = elements.at(-1);
	if (!first || !last) { event.preventDefault(); dialog.focus(); return; }
	if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
	else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}
