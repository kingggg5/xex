/**
 * THESIS: arrange the real controls in named sets, then deliberately save or discard.
 * OWN-WORLD: inherit Xexoria's sapphire/slate panels and restrained gold controls.
 * STORY: Settings → Edit controls → choose a set/group/artwork → move → Save on this device.
 * FIRST VIEWPORT: a compact toolbar keeps Save/Cancel visible; artwork details expand on demand.
 * FORM: a local extension with transparent handles over incumbent HUD controls.
 */
import {
	beginControlDrag, clampControl, clonePositions, createLayoutSession,
	endControlDrag, layoutProfile, resetLayoutSession, updateControlDrag,
	type ControlPosition, type ControlPositions, type LayoutSession,
} from "./hud-control-layout.mjs";
import {
	CONTROL_GROUPS, CONTROL_SET_STORAGE_KEY, MAX_CONTROL_SETS, MAX_CONTROL_SET_NAME,
	activeControlSet, cloneControlSets, createControlSet, deleteControlSet, emptyControlSets,
	loadControlSets, renameControlSet, saveControlSets, selectControlSet, translateControlGroup,
	updateControlSetArt, updateControlSetProfile,
	type ControlArtId, type ControlGroup, type ControlSetCollection, type ControlSetResult,
} from './control-set.mjs';
import { controlArtOptions, createControlArtStyler, renderControlArtPreview } from './control-art';

interface LayoutOptions {
	language?: "en" | "th";
	onEditingChange(editing: boolean): void;
	/** Optional test/embed boundary; production defaults to the browser's device-local storage. */
	storage?: Pick<Storage, "getItem" | "setItem">;
}
interface ControlTarget { id: string; selector: string; label: string; thai: string }
interface OriginalStyle { value: string; priority: string }
const targets: ControlTarget[] = [
	{ id: "joystick", selector: "#joystick", label: "Movement joystick", thai: "จอยเคลื่อนที่" },
	...["attack", "arc_slash", "guard", "dodge"].map((id, i) => ({ id, selector: `[data-action="${id}"]`, label: ["Attack", "Arc slash", "Guard", "Dodge"][i], thai: ["โจมตี", "ฟันโค้ง", "ตั้งรับ", "หลบหลีก"][i] })),
	{ id: "potion", selector: "#potion-button, #mobile-potion", label: "Potion", thai: "ยา" },
	{ id: "bag", selector: "#bag-button", label: "Bag", thai: "กระเป๋า" },
	{ id: "menu", selector: "#menu-button", label: "Menu", thai: "เมนู" },
	{ id: "fullscreen", selector: "#fullscreen-button", label: "Fullscreen", thai: "เต็มจอ" },
	{ id: "context", selector: "#context-action", label: "Interact", thai: "โต้ตอบ" },
	...["character", "bag", "skills", "friends", "group", "map", "store", "tower", "settings"].map(id => ({ id: `nav-${id}`, selector: `.bottom-nav [data-modal="${id}"]`, label: id[0].toUpperCase() + id.slice(1), thai: ({ character: "ตัวละคร", bag: "กระเป๋า", skills: "ทักษะ", friends: "เพื่อน", group: "กลุ่ม", map: "แผนที่", store: "ร้านค้า", tower: "หอคอย", settings: "ตั้งค่า" } as Record<string, string>)[id] })),
];
const stylesheet = `
.hud-layout-editor{position:fixed;inset:0;z-index:90;touch-action:none;pointer-events:auto;font:inherit;color:#f2e5c0;background:#06132619}
.hud-layout-toolbar{position:absolute;top:max(8px,env(safe-area-inset-top));left:50%;transform:translateX(-50%);width:min(580px,calc(100% - env(safe-area-inset-left) - env(safe-area-inset-right) - 20px));padding:10px 12px;background:#0c1c30f5;border:1px solid #bba371;border-radius:8px}
.hud-layout-title{margin:0 0 5px;font-size:15px;font-weight:700}.hud-layout-copy,.hud-layout-status{font-size:12px;line-height:1.5;margin:0;color:#dbe7f4}.hud-layout-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.hud-layout-editor button,.hud-layout-settings button{min-width:44px;min-height:44px;padding:7px 12px;border:1px solid #a48a58;border-radius:5px;background:#19314d;color:#f4e6bc;font:inherit;cursor:pointer}
.hud-layout-editor button:focus-visible,.hud-layout-settings button:focus-visible{outline:3px solid #aadfff;outline-offset:2px}
.hud-layout-actions button:first-child{background:#355b7c;border-color:#c7daeb;color:#fff}.hud-layout-actions button:disabled{opacity:.5;cursor:default}
.hud-layout-editor .hud-layout-handle{position:absolute;padding:0;z-index:1;background:#16395622;border:2px dashed #eed399;border-radius:8px;touch-action:none;cursor:grab;overflow:visible}
.hud-layout-handle span{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);padding:2px 5px;background:#0b1b30;color:#fff0c7;font-size:11px;white-space:nowrap;pointer-events:none}
.hud-layout-toolbar{z-index:2}.hud-layout-settings{margin-top:18px;padding-top:14px;border-top:1px solid #a48a5880}.hud-layout-settings p{font-size:13px;line-height:1.5;margin:7px 0;color:#dbe7f4}
.hud-layout-safe-probe{position:fixed;visibility:hidden;pointer-events:none;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
.hud-layout-receipt{position:fixed;z-index:91;left:50%;bottom:max(16px,env(safe-area-inset-bottom));transform:translateX(-50%);max-width:calc(100vw - 24px);padding:10px 14px;border-radius:6px;background:#0c1c30f5;color:#f4e6bc;font:inherit;font-size:13px;pointer-events:none}
.hud-layout-toolbar{max-height:calc(100dvh - 24px);overflow:auto;overscroll-behavior:contain}.hud-layout-fields{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-top:8px}.hud-layout-field{display:grid;gap:3px;font-size:12px;flex:1;min-width:140px}.hud-layout-field select,.hud-layout-field input{min-height:44px;min-width:0;box-sizing:border-box;width:100%;padding:7px 9px;border:1px solid #a48a58;border-radius:5px;background:#152c44;color:#f4e6bc;font:inherit}.hud-layout-field :is(select,input):focus-visible,.hud-layout-toolbar summary:focus-visible{outline:3px solid #aadfff;outline-offset:2px}.hud-layout-group-option{display:flex;align-items:center;gap:7px;min-height:44px;font-size:12px}.hud-layout-group-option input{width:20px;height:20px}.hud-layout-advanced{margin-top:8px;border-top:1px solid #a48a5860}.hud-layout-advanced summary{cursor:pointer;min-height:44px;display:flex;align-items:center;font-size:13px}.hud-layout-art-preview{display:flex;align-items:center;justify-content:center;gap:20px;min-height:86px;font-size:12px;color:#dbe7f4}.hud-layout-art-part{margin:0;display:grid;justify-items:center;align-content:end;gap:5px}.hud-layout-art-sprite{display:block}.hud-layout-art-part figcaption{font-size:11px;text-align:center}.hud-layout-set-note{font-size:11px;margin:8px 0 0;color:#dbe7f4}.hud-layout-toolbar button:hover:enabled,.hud-layout-settings button:hover:enabled{background:#284b6b}.hud-layout-toolbar :is(input,select,button):disabled{opacity:.5;cursor:default}#hud [data-control-art] .joystick-ring::before,#hud [data-control-art] .joystick-ring::after{display:none}
@media(max-height:520px){.hud-layout-toolbar{padding:6px 10px;width:min(610px,calc(100% - 20px))}.hud-layout-actions{margin-top:5px}.hud-layout-copy{font-size:11px}.hud-layout-toolbar .hud-layout-title{display:none}}
`;

/** Imperative DOM positions only; Svelte retains ownership of every actual game button. */
export function createHudControlLayout(options: LayoutOptions): { isEditing(): boolean; beginEdit(): void; dispose(): void } {
	const th = options.language === "th";
	const copy = (en: string, thai: string) => th ? thai : en;
	const events = new AbortController();
	const style = document.createElement("style"); style.textContent = stylesheet; document.head.append(style);
	const probe = document.createElement("div"); probe.className = "hud-layout-safe-probe"; document.body.append(probe);
	const editor = document.createElement("section"); editor.className = "hud-layout-editor"; editor.hidden = true;
	const receipt = document.createElement("p"); receipt.className = "hud-layout-receipt"; receipt.hidden = true; receipt.setAttribute("role", "status"); receipt.setAttribute("aria-live", "polite"); document.body.append(receipt);
	editor.setAttribute("aria-label", copy("Control layout editor", "แก้ไขตำแหน่งปุ่ม"));
	editor.setAttribute('role', 'dialog'); editor.setAttribute('aria-modal', 'true');
	const toolbar = document.createElement("div"); toolbar.className = "hud-layout-toolbar";
	const title = document.createElement("p"); title.className = "hud-layout-title"; title.textContent = copy("Arrange your controls", "จัดวางปุ่มของคุณ");
	const instructions = document.createElement("p"); instructions.className = "hud-layout-copy";
	instructions.textContent = copy("Drag a control, or focus its handle and use arrow keys. Shift moves farther. Game controls are paused while editing.", "ลากปุ่ม หรือเลือกกรอบแล้วใช้ลูกศร กด Shift เพื่อเลื่อนมากขึ้น ปุ่มเกมหยุดทำงานระหว่างแก้ไข");
	const status = document.createElement("p"); status.className = "hud-layout-status"; status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
	const actions = document.createElement("div"); actions.className = "hud-layout-actions";
	const button = (en: string, thai: string, fn: () => void) => {
		const node = document.createElement("button"); node.type = "button"; node.textContent = copy(en, thai);
		node.setAttribute("aria-label", copy(en, thai)); node.addEventListener("click", fn, { signal: events.signal }); return node;
	};
	const save = button("Save layout", "บันทึกตำแหน่ง", saveDraft);
	const cancel = button("Cancel changes", "ยกเลิกการแก้ไข", () => finish(false));
	const reset = button("Reset layout", "คืนตำแหน่งเริ่มต้น", () => {
		if (!session) return; stopDrag(true); resetLayoutSession(session); applyPositions({}); updateHandles();
		setStatus(copy("Default positions restored. Choose Save to keep them, or Cancel to undo.", "คืนตำแหน่งเริ่มต้นแล้ว กดบันทึกเพื่อใช้ หรือยกเลิกเพื่อกลับตำแหน่งเดิม"));
	});
	actions.append(save, cancel, reset); toolbar.append(title, instructions, status, actions);
	const field = (en: string, thai: string, control: HTMLElement) => {
		const label = document.createElement('label'); label.className = 'hud-layout-field';
		const text = document.createElement('span'); text.textContent = copy(en, thai); label.append(text, control); return label;
	};
	const setSelect = document.createElement('select'); setSelect.id = 'hud-control-set';
	const groupSelect = document.createElement('select'); groupSelect.id = 'hud-control-group';
	for (const [id, en, thai] of [['all', 'All controls', 'ปุ่มทั้งหมด'], ['movement', 'Movement', 'เคลื่อนที่'], ['combat', 'Combat', 'ต่อสู้'], ['menu', 'Menu', 'เมนู']]) {
		const option = document.createElement('option'); option.value = id; option.textContent = copy(en, thai); groupSelect.append(option);
	}
	const together = document.createElement('input'); together.type = 'checkbox'; together.id = 'hud-control-group-together';
	const togetherLabel = document.createElement('label'); togetherLabel.className = 'hud-layout-group-option';
	togetherLabel.append(together, document.createTextNode(copy('Move this group together', 'เลื่อนกลุ่มนี้พร้อมกัน')));
	const fields = document.createElement('div'); fields.className = 'hud-layout-fields';
	fields.append(field('Saved set', 'ชุดที่บันทึก', setSelect), field('Controls to arrange', 'กลุ่มที่จะจัดวาง', groupSelect), togetherLabel); toolbar.append(fields);
	const advanced = document.createElement('details'); advanced.className = 'hud-layout-advanced';
	const summary = document.createElement('summary'); summary.textContent = copy('Artwork and named sets', 'ภาพปุ่มและชื่อชุด');
	const artSelect = document.createElement('select'); artSelect.id = 'hud-control-art';
	for (const art of controlArtOptions) { const option = document.createElement('option'); option.value = art.id; option.textContent = th ? art.thai : art.name; artSelect.append(option); }
	const nameInput = document.createElement('input'); nameInput.id = 'hud-control-set-name'; nameInput.type = 'text'; nameInput.maxLength = MAX_CONTROL_SET_NAME; nameInput.autocomplete = 'off';
	const namedFields = document.createElement('div'); namedFields.className = 'hud-layout-fields';
	namedFields.append(field('Joystick artwork', 'ภาพจอย', artSelect), field('Set name', 'ชื่อชุด', nameInput));
	const create = button('Create set', 'สร้างชุด', () => changeSets('create'));
	const rename = button('Rename set', 'เปลี่ยนชื่อชุด', () => changeSets('rename'));
	const remove = button('Delete set', 'ลบชุด', () => changeSets('delete'));
	const namedActions = document.createElement('div'); namedActions.className = 'hud-layout-actions'; namedActions.append(create, rename, remove);
	const artPreview = document.createElement('div'); artPreview.className = 'hud-layout-art-preview';
	const setNote = document.createElement('p'); setNote.className = 'hud-layout-set-note';
	advanced.append(summary, namedFields, namedActions, artPreview, setNote); toolbar.append(advanced); editor.append(toolbar); document.body.append(editor);
	const storage = () => options.storage ?? window.localStorage;
	let collection: ControlSetCollection = emptyControlSets();
	let draftSets: ControlSetCollection | null = null;
	let initialStatus = "";
	try { const result = loadControlSets(storage()); collection = result.collection; initialStatus = result.status; } catch { initialStatus = "unavailable"; }
	const artStyler = createControlArtStyler();
	let session: LayoutSession | null = null;
	let profile = currentProfile();
	let editingProfile = profile;
	let frame = 0;
	let editFrame = 0;
	let receiptTimer = 0;
	let disposed = false;
	let settingsEntry: HTMLElement | null = null;
	let returnFocus: HTMLElement | null = null;
	let dragHandle: HTMLButtonElement | null = null;
	let pointerOffset = { x: 0, y: 0 };
	let group = 'all' as ControlGroup | 'all';
	let groupDrag: null | { positions: ControlPositions; before: ControlPositions; sizes: Record<string, { width: number; height: number }> } = null;
	let savedMessage = initialStatus === "unavailable" ? copy("Device storage is unavailable. A layout cannot be saved until storage is allowed.", "อุปกรณ์ไม่อนุญาตให้บันทึกข้อมูล จึงยังบันทึกตำแหน่งไม่ได้")
		: initialStatus === "invalid" ? copy("Saved control sets were invalid; default positions are in use.", "ชุดปุ่มที่บันทึกไว้ไม่ถูกต้อง จึงใช้ตำแหน่งเริ่มต้น")
		: initialStatus === 'invalid-recovered' ? copy('Saved sets were invalid; your earlier layout was recovered. Save to keep it.', 'ชุดปุ่มไม่ถูกต้อง กู้คืนตำแหน่งเดิมแล้ว กดบันทึกเพื่อเก็บไว้')
		: initialStatus === 'migrated' ? copy('Your earlier layout is preserved. Named sets are saved on this device, separately for each screen orientation.', 'เก็บตำแหน่งเดิมไว้แล้ว บันทึกชุดเฉพาะอุปกรณ์นี้ แยกตามแนวหน้าจอ')
		: copy("Layouts are stored on this device, separately for desktop and each mobile orientation.", "บันทึกเฉพาะอุปกรณ์นี้ แยกคอมพิวเตอร์ มือถือแนวตั้ง และแนวนอน");
	const originalStyles = new Map<HTMLElement, Map<string, OriginalStyle>>();
	const debugOutput = import.meta.env.DEV && new URLSearchParams(location.search).get('debugControls')==='1' ? document.createElement('output') : null;
	if(debugOutput){debugOutput.setAttribute('aria-label','Control layout diagnostics');debugOutput.style.cssText='position:fixed;left:12px;top:220px;z-index:1101;max-width:400px;max-height:160px;overflow:auto;white-space:pre-wrap;background:#10212def;color:#ffe8ab;padding:8px;font:11px monospace';document.body.append(debugOutput);}
	const handles = new Map<string, HTMLButtonElement>();
	function currentProfile() { return layoutProfile(window.innerWidth, window.innerHeight, window.matchMedia("(any-pointer: coarse)").matches); }
	function viewport() { const view = window.visualViewport; return { width: view?.width ?? window.innerWidth, height: view?.height ?? window.innerHeight, left: view?.offsetLeft ?? 0, top: view?.offsetTop ?? 0 }; }
	function insets() { const css = getComputedStyle(probe); return { left: parseFloat(css.paddingLeft) || 0, right: parseFloat(css.paddingRight) || 0, top: parseFloat(css.paddingTop) || 0, bottom: parseFloat(css.paddingBottom) || 0 }; }
	function visibleTarget(target: ControlTarget): HTMLElement | null {
		return [...document.querySelectorAll<HTMLElement>(`#hud ${target.selector.split(",").join(", #hud ")}`)].find(node => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden") ?? null;
	}
	function remember(node: HTMLElement, key: string) {
		let entries = originalStyles.get(node); if (!entries) { entries = new Map(); originalStyles.set(node, entries); }
		if (!entries.has(key)) entries.set(key, { value: node.style.getPropertyValue(key), priority: node.style.getPropertyPriority(key) });
	}
	function restore(node: HTMLElement, keys?: string[]) {
		const entries = originalStyles.get(node); if (!entries) return;
		for (const [key, before] of entries) if (!keys || keys.includes(key)) {
			if (before.value) node.style.setProperty(key, before.value, before.priority); else node.style.removeProperty(key);
		}
	}
	function ensureReachable(node: HTMLElement) {
		const rect = node.getBoundingClientRect();
		const scaleX = rect.width / Math.max(1, node.offsetWidth), scaleY = rect.height / Math.max(1, node.offsetHeight);
		if (rect.width > 0 && rect.width < 44) { remember(node, "min-width"); node.style.setProperty("min-width", `${44 / scaleX}px`, "important"); }
		if (rect.height > 0 && rect.height < 44) { remember(node, "min-height"); node.style.setProperty("min-height", `${44 / scaleY}px`, "important"); }
	}
	function controlCenter(node: HTMLElement): ControlPosition { const rect = node.getBoundingClientRect(), view = viewport(); return { x: (rect.left + rect.width / 2 - view.left) / view.width, y: (rect.top + rect.height / 2 - view.top) / view.height }; }
	function applyPositions(positions: ControlPositions) {
		for (const node of originalStyles.keys()) restore(node);
		artStyler.apply(activeControlSet(draftSets ?? collection).art);
		for (const target of targets) {
			const node = visibleTarget(target); if (!node) continue;
			ensureReachable(node);
			const position = positions[target.id]; if (!position) continue;
			const rect = node.getBoundingClientRect(), view = viewport();
			const center = clampControl(position, rect, view, insets());
			const scaleX = rect.width / Math.max(1, node.offsetWidth), scaleY = rect.height / Math.max(1, node.offsetHeight);
			remember(node, "translate");
			node.style.setProperty("translate", `${(view.left + center.x * view.width - rect.left - rect.width / 2) / scaleX}px ${(view.top + center.y * view.height - rect.top - rect.height / 2) / scaleY}px`, "important");
		}
	}
	function setStatus(message: string) { if (status.textContent !== message) status.textContent = message; }
	function announce(message: string) { receipt.textContent = message; receipt.hidden = false; window.clearTimeout(receiptTimer); receiptTimer = window.setTimeout(() => { receipt.hidden = true; }, 5000); }
	function neutralize() { window.dispatchEvent(new Event("blur")); options.onEditingChange(session !== null); }
	function storeCurrentDraft() {
		if (session && draftSets) draftSets = updateControlSetProfile(draftSets, editingProfile, session.draft);
	}
	function updateSetControls() {
		const data = draftSets ?? collection, selected = activeControlSet(data);
		setSelect.replaceChildren();
		for (const set of data.sets) { const option = document.createElement('option'); option.value = set.id; option.textContent = set.id === 'default' ? copy('Original set', 'ชุดเดิม') : set.name; setSelect.append(option); }
		setSelect.value = data.activeId; artSelect.value = selected.art;
		artSelect.disabled = data.activeId === 'default'; rename.disabled = artSelect.disabled; remove.disabled = artSelect.disabled;
		create.disabled = data.sets.length >= MAX_CONTROL_SETS;
		nameInput.value = selected.id === 'default' ? copy('My controls', 'ชุดปุ่มของฉัน') : selected.name;
		together.disabled = group === 'all'; if (together.disabled) together.checked = false;
		setNote.textContent = selected.id === 'default'
			? copy('Create a named set to choose artwork. The original set stays available. Up to 12 sets on this device.', 'สร้างชุดที่มีชื่อเพื่อเลือกภาพ เก็บชุดเดิมไว้เสมอ บันทึกได้สูงสุด 12 ชุดบนอุปกรณ์นี้')
			: copy('Artwork and set changes are previews until Save. Sit artwork has no game action.', 'ภาพและชุดเป็นตัวอย่างจนกดบันทึก ภาพนั่งยังไม่มีคำสั่งในเกม');
		renderControlArtPreview(artPreview, selected.art, th);
	}
	function showDraftSet() {
		if (!draftSets || !session) return;
		session = createLayoutSession(activeControlSet(draftSets).profiles[editingProfile] ?? {});
		applyPositions(session.draft); updateSetControls(); updateHandles(); neutralize();
	}
	function changeSets(action: 'create' | 'rename' | 'delete') {
		if (!session || !draftSets) return; stopDrag(true); storeCurrentDraft();
		const result = action === 'create' ? createControlSet(draftSets, nameInput.value) : action === 'rename' ? renameControlSet(draftSets, nameInput.value) : deleteControlSet(draftSets);
		if (!result.ok) {
			setStatus(result.reason === 'limit' ? copy('You can save up to 12 sets. Delete a named set to make room.', 'บันทึกได้สูงสุด 12 ชุด ลบชุดที่มีชื่อเพื่อเพิ่มพื้นที่')
				: result.reason === 'duplicate-name' ? copy('That name already exists. Enter a different set name.', 'ชื่อนี้มีแล้ว โปรดใช้ชื่ออื่น')
				: result.reason === 'protected' ? copy('The original set is preserved. Create a named set to customize its artwork.', 'เก็บชุดเดิมไว้เสมอ สร้างชุดที่มีชื่อเพื่อเลือกภาพ')
				: copy('Enter a set name first.', 'โปรดใส่ชื่อชุดก่อน')); nameInput.focus(); return;
		}
		draftSets = result.collection; showDraftSet();
		setStatus(copy('Set changed in this preview. Choose Save to keep it, or Cancel to undo.', 'เปลี่ยนชุดในตัวอย่างแล้ว กดบันทึกเพื่อเก็บไว้ หรือยกเลิกเพื่อย้อนกลับ'));
	}
	function groupSnapshot() {
		const positions: ControlPositions = {}, sizes: Record<string, { width: number; height: number }> = {};
		if (group === 'all' || !together.checked) return null;
		for (const target of targets) {
			if (!CONTROL_GROUPS[group].includes(target.id)) continue;
			const node = visibleTarget(target); if (!node) continue;
			positions[target.id] = controlCenter(node); const rect = node.getBoundingClientRect(); sizes[target.id] = { width: rect.width, height: rect.height };
		}
		return { positions, sizes, before: clonePositions(session?.draft ?? {}) };
	}
	setSelect.addEventListener('change', () => {
		if (!session || !draftSets) return; stopDrag(true); storeCurrentDraft(); draftSets = selectControlSet(draftSets, setSelect.value); showDraftSet();
		setStatus(copy('Selected set is a preview. Save to apply it, or Cancel to keep the earlier set.', 'ชุดที่เลือกเป็นตัวอย่าง กดบันทึกเพื่อใช้ หรือยกเลิกเพื่อใช้ชุดก่อนหน้า'));
	}, { signal: events.signal });
	artSelect.addEventListener('change', () => {
		if (!session || !draftSets) return; stopDrag(true); draftSets = updateControlSetArt(draftSets, artSelect.value as ControlArtId);
		applyPositions(session.draft); renderControlArtPreview(artPreview, activeControlSet(draftSets).art, th); updateHandles();
		setStatus(copy('Artwork preview applied. Choose Save to keep it, or Cancel to undo.', 'แสดงภาพตัวอย่างแล้ว กดบันทึกเพื่อเก็บไว้ หรือยกเลิกเพื่อย้อนกลับ'));
	}, { signal: events.signal });
	groupSelect.addEventListener('change', () => {
		stopDrag(true); group = Object.hasOwn(CONTROL_GROUPS, groupSelect.value) ? groupSelect.value as ControlGroup : 'all';
		together.disabled = group === 'all'; if (together.disabled) together.checked = false; updateHandles();
	}, { signal: events.signal });
	together.addEventListener('change', () => stopDrag(true), { signal: events.signal });
	advanced.addEventListener('toggle', () => { if (session) updateHandles(); }, { signal: events.signal });
	function injectSettingsEntry() {
		const content = document.getElementById("settings-ui-scale")?.closest("#modal-content, .modal-content");
		if (!content) { settingsEntry?.remove(); settingsEntry = null; return; }
		if (settingsEntry?.parentElement === content) return;
		settingsEntry?.remove(); settingsEntry = document.createElement("section"); settingsEntry.className = "hud-layout-settings";
		settingsEntry.setAttribute("aria-label", copy("Control layout settings", "ตั้งค่าตำแหน่งปุ่ม"));
		const edit = button("Edit controls", "แก้ไขตำแหน่งปุ่ม", beginEdit);
		const label = document.createElement('p'); label.textContent = copy('Choose artwork, named sets and control groups.', 'เลือกภาพ ชุดที่มีชื่อ และกลุ่มปุ่มควบคุม');
		const note = document.createElement("p"); note.setAttribute("role", "status"); note.textContent = savedMessage;
		settingsEntry.append(edit, label, note); content.append(settingsEntry);
	}
	function updateHandles() {
		for (const target of targets) {
			const handle = handles.get(target.id), node = group === 'all' || CONTROL_GROUPS[group].includes(target.id) ? visibleTarget(target) : null; if (!handle) continue;
			if (handle.hidden === !!node) handle.hidden = !node; if (!node) continue;
			const rect = node.getBoundingClientRect();
			handle.style.left = `${rect.left}px`; handle.style.top = `${rect.top}px`;
			handle.style.width = `${Math.max(44, rect.width)}px`; handle.style.height = `${Math.max(44, rect.height)}px`;
		}
		// The toolbar must not cover a draggable control, particularly top-right mobile buttons.
		const view = viewport(), safe = insets(), bar = toolbar.getBoundingClientRect();
		const controlRects = [...handles.values()].filter(handle => !handle.hidden).map(handle => handle.getBoundingClientRect());
		const low = safe.top + 8, high = Math.max(low, view.height - safe.bottom - bar.height - 8);
		const bound = (top: number) => Math.max(low, Math.min(high, top));
		const candidates = [low, bound((view.height - bar.height) / 2), high,
			...controlRects.flatMap(rect => [bound(rect.bottom + 18), bound(rect.top - bar.height - 18)])];
		const overlap = (top: number) => controlRects.filter(rect => rect.right > bar.left && rect.left < bar.right && rect.bottom > top && rect.top < top + bar.height).length;
		const chosen = candidates.reduce((best, top) => overlap(top) < overlap(best) ? top : best, candidates[0]);
		toolbar.style.top = `${chosen}px`;
	}
	function beginEdit() {
		if (disposed || session) return;
		receipt.hidden = true; window.clearTimeout(receiptTimer);
		returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		const close = settingsEntry?.closest('[role="dialog"], .game-modal')?.querySelector<HTMLButtonElement>('.modal-close, #modal-close')
			?? document.getElementById('modal-close');
		close?.click();
		profile = currentProfile(); editingProfile = profile; draftSets = cloneControlSets(collection); session = createLayoutSession(activeControlSet(draftSets).profiles[profile] ?? {});
		updateSetControls();
		editor.hidden = false; neutralize();
		setStatus(copy("Preparing controls…", "กำลังเตรียมปุ่ม…"));
		// The modal close command may flush on Svelte's microtask; measure after that flush.
		editFrame = requestAnimationFrame(() => {
			editFrame = 0; if (!session || disposed) return;
			createHandles();
		});
	}
	function createHandles() {
		for (const target of targets) {
			const node = visibleTarget(target); if (!node) continue;
			ensureReachable(node);
			const handle = document.createElement("button"); handle.type = "button"; handle.className = "hud-layout-handle";
			handle.dataset.controlId = target.id; handle.setAttribute("aria-label", copy(`Move ${target.label}`, `เลื่อน${target.thai}`));
			handle.title = copy("Drag or use arrow keys; Shift for a larger step", "ลากหรือใช้ปุ่มลูกศร กด Shift เพื่อเลื่อนมากขึ้น");
			const label = document.createElement("span"); label.textContent = th ? target.thai : target.label; handle.append(label);
			editor.append(handle); handles.set(target.id, handle);
		}
		updateHandles(); ([...handles.values()].find(handle => !handle.hidden) ?? save).focus({ preventScroll: true });
		setStatus(copy("Editing this screen layout. Changes are not saved yet.", "กำลังแก้ไขตำแหน่งบนหน้าจอนี้ ยังไม่ได้บันทึก"));
	}
	function stopDrag(cancelled: boolean) {
		const pointer = session?.pointer; if (!pointer || !session) return;
		endControlDrag(session, pointer.pointerId, cancelled);
		if (cancelled && groupDrag) session.draft = clonePositions(groupDrag.before);
		groupDrag = null;
		if (dragHandle?.hasPointerCapture(pointer.pointerId)) dragHandle.releasePointerCapture(pointer.pointerId);
		dragHandle = null;
		if (cancelled) { applyPositions(session.draft); updateHandles(); neutralize(); }
	}
	function finish(saved: boolean) {
		if (!session) return; stopDrag(true);
		cancelAnimationFrame(editFrame); editFrame = 0;
		const positions = activeControlSet(collection).profiles[editingProfile] ?? {};
		session = null; draftSets = null; editor.hidden = true;
		for (const handle of handles.values()) handle.remove(); handles.clear();
		applyPositions(positions); neutralize();
		if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true }); else document.getElementById("menu-button")?.focus({ preventScroll: true });
		returnFocus = null;
		if (!saved) setStatus(copy('Changes cancelled.', 'ยกเลิกการแก้ไขแล้ว'));
	}
	function saveDraft() {
		if (!session || !draftSets) return; stopDrag(false); storeCurrentDraft();
		let result: ControlSetResult;
		try { result = saveControlSets(storage(), collection, draftSets); } catch { result = { ok: false, collection }; }
		if (!result.ok) { setStatus(copy("Could not save on this device. Allow browser storage and retry, or Cancel changes.", "บันทึกบนอุปกรณ์นี้ไม่ได้ โปรดอนุญาตพื้นที่จัดเก็บแล้วลองอีกครั้ง หรือยกเลิกการแก้ไข")); return; }
		collection = result.collection; savedMessage = copy("Control set saved on this device. Open Edit controls to change it again.", "บันทึกชุดปุ่มบนอุปกรณ์นี้แล้ว เปิดแก้ไขตำแหน่งปุ่มเพื่อแก้ไขอีกครั้ง"); finish(true); announce(savedMessage);
	}
	function refresh() {
		frame = 0; if (disposed) return;
		const next = currentProfile();
		if (next !== profile && session) { finish(false); savedMessage = copy("Screen orientation changed; unsaved edits were cancelled.", "เปลี่ยนแนวหน้าจอแล้ว ยกเลิกการแก้ไขที่ยังไม่ได้บันทึก"); }
		profile = next;
		if(debugOutput)debugOutput.textContent=JSON.stringify({profile,editingProfile,initialStatus,width:window.innerWidth,height:window.innerHeight,viewport:viewport(),activeSet:collection.activeId,profiles:activeControlSet(collection).profiles});
		if (!session) applyPositions(activeControlSet(collection).profiles[profile] ?? {}); else { applyPositions(session.draft); updateHandles(); }
		injectSettingsEntry();
	}
	function scheduleRefresh() { if (!frame && !disposed) frame = requestAnimationFrame(refresh); }
	const observer = new MutationObserver(records => {
		if (records.some(record => record.type === "attributes" || [...record.addedNodes, ...record.removedNodes].some(node => node instanceof Element))) scheduleRefresh();
	});
	// Text counters and world labels do not require reapplying every control's geometry.
	for (const host of [document.getElementById("hud"), document.getElementById("modal-backdrop")]) if (host) observer.observe(host, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
	window.matchMedia("(any-pointer: coarse)").addEventListener("change", scheduleRefresh, { signal: events.signal });
	window.addEventListener("resize", () => {
		// A mobile keyboard may resize the viewport while the player types a set name.
		if (session && document.activeElement === nameInput && currentProfile() === editingProfile) { stopDrag(true); applyPositions(session.draft); updateHandles(); }
		else if (session) { finish(false); savedMessage = copy("Screen size changed; unsaved edits were cancelled.", "ขนาดหน้าจอเปลี่ยนแล้ว ยกเลิกการแก้ไขที่ยังไม่ได้บันทึก"); }
		scheduleRefresh();
	}, { passive: true, signal: events.signal });
	window.visualViewport?.addEventListener("resize", scheduleRefresh, { passive: true, signal: events.signal });
	document.addEventListener("input", event => { if ((event.target as HTMLElement)?.id === "settings-ui-scale") scheduleRefresh(); }, { signal: events.signal });
	window.addEventListener("pointerdown", event => {
		if (!session) return;
		const handle = event.target instanceof Element ? event.target.closest<HTMLButtonElement>(".hud-layout-handle") : null;
		if (!handle || !editor.contains(handle)) { if (!editor.contains(event.target as Node)) { event.preventDefault(); event.stopImmediatePropagation(); } return; }
		event.preventDefault(); event.stopImmediatePropagation();
		const target = targets.find(value => value.id === handle.dataset.controlId), node = target && visibleTarget(target); if (!node || event.button !== 0) return;
		const center = controlCenter(node), view = viewport();
		if (!beginControlDrag(session, target.id, event.pointerId, clampControl(center, node.getBoundingClientRect(), view, insets()))) return;
		groupDrag = groupSnapshot();
		pointerOffset = { x: event.clientX - (view.left + center.x * view.width), y: event.clientY - (view.top + center.y * view.height) };
		dragHandle = handle; handle.focus({ preventScroll: true }); handle.setPointerCapture(event.pointerId);
	}, { capture: true, signal: events.signal });
	window.addEventListener("pointermove", event => {
		if (!session?.pointer || session.pointer.pointerId !== event.pointerId) return;
		event.preventDefault(); event.stopImmediatePropagation();
		const target = targets.find(value => value.id === session?.pointer?.id), node = target && visibleTarget(target); if (!node) return;
		const view = viewport();
		const position = clampControl({ x: (event.clientX - view.left - pointerOffset.x) / view.width, y: (event.clientY - view.top - pointerOffset.y) / view.height }, node.getBoundingClientRect(), view, insets());
		if (groupDrag) {
			const delta = { x: position.x - session.pointer.start.x, y: position.y - session.pointer.start.y };
			session.draft = { ...groupDrag.before, ...translateControlGroup(groupDrag.positions, groupDrag.sizes, delta, view, insets()) };
		} else updateControlDrag(session, event.pointerId, position);
		applyPositions(session.draft); updateHandles();
	}, { capture: true, signal: events.signal });
	for (const name of ["pointerup", "pointercancel", "lostpointercapture"] as const) window.addEventListener(name, event => {
		if (!session?.pointer || session.pointer.pointerId !== event.pointerId) return;
		event.preventDefault(); event.stopImmediatePropagation(); stopDrag(name !== "pointerup");
	}, { capture: true, signal: events.signal });
	window.addEventListener("click", event => { if (session && !editor.contains(event.target as Node)) { event.preventDefault(); event.stopImmediatePropagation(); } }, { capture: true, signal: events.signal });
	window.addEventListener("keydown", event => {
		if (!session) return;
		if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); finish(false); return; }
		if (event.key === "Tab") {
			event.preventDefault(); event.stopImmediatePropagation();
			const focusable = [...editor.querySelectorAll<HTMLElement>('button,input,select,summary')].filter(node => node.getClientRects().length > 0 && !node.hasAttribute('disabled'));
			const current = focusable.indexOf(document.activeElement as HTMLElement), direction = event.shiftKey ? -1 : 1;
			focusable[(current + direction + focusable.length) % focusable.length]?.focus({ preventScroll: true }); return;
		}
		const handle = event.target instanceof HTMLElement ? event.target.closest<HTMLElement>(".hud-layout-handle") : null;
		if (handle && event.key.startsWith("Arrow")) {
			event.preventDefault(); event.stopImmediatePropagation();
			const target = targets.find(value => value.id === handle.dataset.controlId), node = target && visibleTarget(target); if (!node) return;
			const current = controlCenter(node), view = viewport(), step = event.shiftKey ? 24 : 4;
			const x = Number(event.key === "ArrowRight") - Number(event.key === "ArrowLeft"), y = Number(event.key === "ArrowDown") - Number(event.key === "ArrowUp");
			const snapshot = groupSnapshot();
			if (snapshot) session.draft = { ...session.draft, ...translateControlGroup(snapshot.positions, snapshot.sizes, { x: x * step / view.width, y: y * step / view.height }, view, insets()) };
			else session.draft[target.id] = clampControl({ x: current.x + x * step / view.width, y: current.y + y * step / view.height }, node.getBoundingClientRect(), view, insets());
			applyPositions(session.draft); updateHandles(); return;
		}
		if (event.target instanceof HTMLElement && editor.contains(event.target) && ['INPUT', 'SELECT', 'TEXTAREA', 'SUMMARY'].includes(event.target.tagName)) { event.stopImmediatePropagation(); return; }
		if (event.key !== "Tab") { event.stopImmediatePropagation(); if (!(editor.contains(event.target as Node) && ["Enter", " "].includes(event.key))) event.preventDefault(); }
	}, { capture: true, signal: events.signal });
	window.addEventListener("keyup", event => { if (session && event.key !== "Tab") { event.stopImmediatePropagation(); } }, { capture: true, signal: events.signal });
	window.addEventListener("blur", () => { if (session?.pointer) stopDrag(true); }, { signal: events.signal });
	document.addEventListener("visibilitychange", () => { if (document.hidden && session) finish(false); }, { signal: events.signal });
	window.addEventListener("aetherfield:renderer-lost", () => { if (session) finish(false); }, { signal: events.signal });
	window.addEventListener("storage", event => {
		if (![CONTROL_SET_STORAGE_KEY, 'xexoria_control_layout_v1'].includes(event.key ?? '') || session) return;
		try { const loaded = loadControlSets(storage()); if (loaded.status !== 'unavailable') collection = loaded.collection; scheduleRefresh(); } catch { /* Existing device layout remains usable. */ }
	}, { signal: events.signal });
	scheduleRefresh();
	return {
		isEditing: () => session !== null, beginEdit,
		dispose() { if (disposed) return; if (session) finish(false); disposed = true; events.abort(); observer.disconnect(); cancelAnimationFrame(frame); cancelAnimationFrame(editFrame); window.clearTimeout(receiptTimer); for (const node of originalStyles.keys()) restore(node); originalStyles.clear(); artStyler.dispose(); settingsEntry?.remove(); editor.remove(); receipt.remove(); probe.remove(); style.remove(); debugOutput?.remove(); },
	};
}
