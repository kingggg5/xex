// In-page half of tools/capture/responsive-audit.mjs: layout measurements and issues for one viewport state.
(() => {
	if (window.__xexAudit) return;
	const OVERLAYS = [".mobile-web-app-overlay", "#rotate-device", ".scene-loading", "#modal-backdrop:not([hidden])", ".hud-layout-editor:not([hidden])"];
	const INTERACTIVE = "button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=tab], [role=slider], [role=switch], [role=checkbox], [role=menuitem], [tabindex]:not([tabindex='-1']), [data-action], #joystick";
	const WIDGET = ".panel, #joystick, .bottom-nav, .desktop-hotbar, .mobile-actions, .world-info, .quests, .party, .map-panel, .chat, #connection-toast, #performance-stats, .progress-footer, #context-action, .weapon-wheel, .top-actions, .right-rail, [data-mobile-web-app-dialog], .mobile-web-app-card, #rotate-device > *, .scene-loading > *, #lookdev-panel";
	const round = value => Math.round(value * 10) / 10;
	const rectOf = el => { const r = el.getBoundingClientRect(); return { x: round(r.left), y: round(r.top), w: round(r.width), h: round(r.height), right: round(r.right), bottom: round(r.bottom) }; };
	function isVisible(el) {
		if (!(el instanceof Element)) return false;
		const options = { opacityProperty: true, visibilityProperty: true, checkOpacity: true, checkVisibilityCSS: true };
		if (typeof el.checkVisibility === "function" && !el.checkVisibility(options)) return false;
		const style = getComputedStyle(el);
		if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
		const r = el.getBoundingClientRect();
		return r.width >= 1 && r.height >= 1;
	}
	function selectorOf(el) {
		if (el.id) return `#${CSS.escape(el.id)}`;
		const parts = [];
		let node = el;
		while (node && node.nodeType === 1 && node !== document.body && parts.length < 6) {
			if (node.id) { parts.unshift(`#${CSS.escape(node.id)}`); break; }
			let part = node.tagName.toLowerCase();
			const classes = [...node.classList].filter(name => !/^svelte-/.test(name)).slice(0, 2);
			if (classes.length) part += "." + classes.map(name => CSS.escape(name)).join(".");
			const key = ["data-action", "data-modal", "data-view", "aria-label"].find(name => node.hasAttribute(name));
			if (key) part += `[${key}="${node.getAttribute(key).replace(/"/g, "\\\"").slice(0, 40)}"]`;
			else if (node.parentElement) {
				const siblings = [...node.parentElement.children].filter(sibling => sibling.tagName === node.tagName);
				if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
			}
			parts.unshift(part);
			node = node.parentElement;
		}
		return parts.join(" > ");
	}
	const labelOf = el => (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 48);
	const intersect = (a, b) => { const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y), right = Math.min(a.right, b.right), bottom = Math.min(a.bottom, b.bottom); return right > x && bottom > y ? { x: round(x), y: round(y), w: round(right - x), h: round(bottom - y), area: (right - x) * (bottom - y) } : null; };
	function effectiveFont(el) {
		const size = parseFloat(getComputedStyle(el).fontSize) || 0;
		const height = el.getBoundingClientRect().height, layout = el instanceof HTMLElement ? el.offsetHeight : 0;
		const scale = layout > 0 && height > 0 ? height / layout : 1;
		return round(size * (Number.isFinite(scale) && scale > 0 ? scale : 1));
	}
	function blockingOverlay(width, height) {
		const found = [];
		for (const selector of OVERLAYS) for (const el of document.querySelectorAll(selector)) {
			if (!isVisible(el)) continue;
			const r = el.getBoundingClientRect();
			if (r.width * r.height >= .85 * width * height) found.push({ el, selector, z: Number(getComputedStyle(el).zIndex) || 0 });
		}
		found.sort((a, b) => b.z - a.z);
		return found[0] || null;
	}
	function snapshot({ insets = { top: 0, right: 0, bottom: 0, left: 0 }, touch = false, minTarget = 44, minFont = 11, expectControls = false } = {}) {
		const width = innerWidth, height = innerHeight, issues = [];
		const overlay = blockingOverlay(width, height);
		const inScope = el => !overlay || overlay.el === el || overlay.el.contains(el);
		const scroller = document.scrollingElement || document.documentElement;
		const startX = scrollX, startY = scrollY;
		window.scrollTo(1e6, 1e6);
		const scrolled = { x: scrollX, y: scrollY };
		window.scrollTo(startX, startY);
		const scroll = { scrollWidth: scroller.scrollWidth, scrollHeight: scroller.scrollHeight, clientWidth: scroller.clientWidth, clientHeight: scroller.clientHeight, maxScrollX: scrolled.x, maxScrollY: scrolled.y };
		if (scrolled.x > 0 || scrolled.y > 0 || scroll.scrollWidth > width + 1 || scroll.scrollHeight > height + 1)
			issues.push({ type: "page-scroll", severity: "critical", measured: scroll, expected: `no scroll inside ${width}x${height}` });
		const vv = window.visualViewport ? { width: round(visualViewport.width), height: round(visualViewport.height), scale: round(visualViewport.scale), offsetTop: round(visualViewport.offsetTop) } : null;
		if (vv && (Math.abs(vv.scale - 1) > .01 || Math.abs(vv.width - width) > 1 || Math.abs(vv.height - height) > 1))
			issues.push({ type: "visual-viewport", severity: "high", measured: vv, expected: `scale 1, ${width}x${height}` });
		const canvas = document.querySelector("#game-canvas") || document.querySelector("canvas");
		const canvasRect = canvas ? rectOf(canvas) : null;
		if (!canvas) issues.push({ type: "canvas-missing", severity: "critical" });
		else if (Math.abs(canvasRect.x) > 1 || Math.abs(canvasRect.y) > 1 || Math.abs(canvasRect.w - width) > 1 || Math.abs(canvasRect.h - height) > 1)
			issues.push({ type: "canvas-fill", severity: "critical", selector: selectorOf(canvas), measured: canvasRect, expected: `0,0 ${width}x${height}` });
		const safe = { left: insets.left || 0, top: insets.top || 0, right: width - (insets.right || 0), bottom: height - (insets.bottom || 0) };
		const all = [...document.body.querySelectorAll("*")].filter(el => !(el instanceof SVGElement && el.ownerSVGElement) && !["SCRIPT", "STYLE", "LINK", "META", "NOSCRIPT", "TEMPLATE", "CANVAS"].includes(el.tagName));
		const visible = all.filter(el => inScope(el) && isVisible(el));
		const interactive = visible.filter(el => el.matches(INTERACTIVE) && !el.closest("[inert]"));
		const widgets = visible.filter(el => el.matches(WIDGET) || el.matches(INTERACTIVE));
		const widgetSet = new Set(widgets);
		const topLevel = widgets.filter(el => { for (let node = el.parentElement; node; node = node.parentElement) if (widgetSet.has(node)) return false; return true; })
			.filter(el => { const r = el.getBoundingClientRect(); return r.width * r.height < .85 * width * height; });
		const describe = el => ({ selector: selectorOf(el), label: labelOf(el), rect: rectOf(el) });
		const boxes = topLevel.map(describe);
		for (const box of boxes) {
			const r = box.rect;
			const outside = { left: round(Math.max(0, -r.x)), top: round(Math.max(0, -r.y)), right: round(Math.max(0, r.right - width)), bottom: round(Math.max(0, r.bottom - height)) };
			if (Object.values(outside).some(value => value > 1)) {
				const fully = r.right <= 0 || r.bottom <= 0 || r.x >= width || r.y >= height;
				issues.push({ type: fully ? "offscreen-hidden" : "offscreen", severity: fully ? "info" : "high", selector: box.selector, label: box.label, measured: r, outsideBy: outside });
				continue;
			}
			const intrusion = { left: round(Math.max(0, safe.left - r.x)), top: round(Math.max(0, safe.top - r.y)), right: round(Math.max(0, r.right - safe.right)), bottom: round(Math.max(0, r.bottom - safe.bottom)) };
			if (Object.values(intrusion).some(value => value > 1)) issues.push({ type: "safe-area", severity: "high", selector: box.selector, label: box.label, measured: r, insets, intrudesBy: intrusion });
		}
		for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
			const overlap = intersect(boxes[i].rect, boxes[j].rect);
			if (!overlap) continue;
			const smaller = Math.min(boxes[i].rect.w * boxes[i].rect.h, boxes[j].rect.w * boxes[j].rect.h);
			const pct = overlap.area / Math.max(1, smaller) * 100;
			if (overlap.area >= 64 && pct >= 5) issues.push({ type: "overlap", severity: pct >= 25 ? "high" : "medium", a: boxes[i].selector, b: boxes[j].selector, labels: [boxes[i].label, boxes[j].label],
				rectA: boxes[i].rect, rectB: boxes[j].rect, intersection: { x: overlap.x, y: overlap.y, w: overlap.w, h: overlap.h }, pctOfSmaller: round(pct) });
		}
		if (touch) for (const el of interactive) {
			const r = rectOf(el);
			if (r.w < minTarget - .5 || r.h < minTarget - .5) issues.push({ type: "touch-target", severity: Math.min(r.w, r.h) < 32 ? "high" : "medium", selector: selectorOf(el), label: labelOf(el), measured: { w: r.w, h: r.h }, rect: r, minimum: minTarget });
		}
		const fonts = new Map();
		const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
		for (let node = walker.nextNode(); node; node = walker.nextNode()) {
			if (!node.textContent || !node.textContent.trim()) continue;
			const parent = node.parentElement;
			if (!parent || !inScope(parent) || !isVisible(parent) || parent.closest("script,style,noscript,[aria-hidden='true']")) continue;
			const size = effectiveFont(parent);
			if (size < minFont) {
				const selector = selectorOf(parent);
				if (!fonts.has(selector)) fonts.set(selector, { type: "small-text", severity: size < 9 ? "medium" : "low", selector, measured: { fontPx: size }, minimum: minFont, sample: node.textContent.trim().slice(0, 40), rect: rectOf(parent) });
			}
		}
		issues.push(...fonts.values());
		const joystick = document.querySelector("#joystick");
		const actionButtons = [...document.querySelectorAll(".mobile-controls [data-action], .mobile-actions button")].filter(el => isVisible(el) && inScope(el));
		const controls = { joystick: !!joystick && isVisible(joystick) && inScope(joystick), joystickRect: joystick && isVisible(joystick) ? rectOf(joystick) : null, actions: actionButtons.length,
			actionLabels: actionButtons.map(labelOf).slice(0, 12), desktopHotbar: !!document.querySelector(".desktop-hotbar") && isVisible(document.querySelector(".desktop-hotbar")) };
		if (expectControls && !overlay && (!controls.joystick || controls.actions < 4))
			issues.push({ type: "touch-controls-missing", severity: "critical", measured: controls, expected: "visible #joystick and at least 4 action buttons on touch devices" });
		return {
			viewport: { width, height, dpr: devicePixelRatio, orientation: screen.orientation ? screen.orientation.type : null }, visualViewport: vv, scroll, canvas: canvasRect, insets,
			safeAreaCss: (() => { const probe = document.querySelector(".hud-layout-safe-probe"); if (!probe) return null; const s = getComputedStyle(probe); return { top: s.paddingTop, right: s.paddingRight, bottom: s.paddingBottom, left: s.paddingLeft }; })(),
			media: { coarse: matchMedia("(pointer: coarse)").matches, anyCoarse: matchMedia("(any-pointer: coarse)").matches, hover: matchMedia("(hover: hover)").matches, maxTouchPoints: navigator.maxTouchPoints },
			overlay: overlay ? { selector: overlay.selector, element: selectorOf(overlay.el), rect: rectOf(overlay.el) } : null,
			widgets: boxes, interactiveCount: interactive.length, controls, issues,
			game: { scene: !!(window.__xexoria && window.__xexoria.scene), frames: window.__xexoria && window.__xexoria.scene ? window.__xexoria.scene.getFrameId() : null,
				backend: window.__xexoria && window.__xexoria.engine ? (window.__xexoria.engine.isWebGPU ? "WebGPU" : "WebGL2") : null,
				loading: !!document.querySelector(".scene-loading") && isVisible(document.querySelector(".scene-loading")), connection: (document.querySelector("#connection-label") || {}).textContent || null },
		};
	}
	window.__xexAudit = { version: 1, snapshot, isVisible: selector => { const el = document.querySelector(selector); return !!el && isVisible(el); } };
})();
