# One-off patch: E07 client — job EXP bar, character modal, bag equip action.
import io

# ---------- index.html: job bar + footer job label ----------
p = "apps/client/index.html"
s = io.open(p, encoding="utf-8").read()
old = '''						<div class="bar-row exp-row"><span class="bar xp"><i id="xp-fill"></i></span><small id="xp-text">0%</small></div>
					</div>'''
new = '''						<div class="bar-row exp-row"><span class="bar xp"><i id="xp-fill"></i></span><small id="xp-text">0%</small></div>
						<div class="bar-row exp-row job-row"><span class="bar xp job"><i id="jobxp-fill"></i></span><small id="jobxp-text">Job 0%</small></div>
					</div>'''
assert old in s, "index bar anchor"
s = s.replace(old, new, 1)
old = '''<div class="progress-footer"><span id="footer-level">Base Lv. 01</span><b id="footer-xp">0%</b><i><em id="footer-xp-fill"></em></i>'''
new = '''<div class="progress-footer"><span id="footer-level">Base Lv. 01</span><span id="footer-job">Job Lv. 01</span><b id="footer-xp">0%</b><i><em id="footer-xp-fill"></em></i>'''
assert old in s, "index footer anchor"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("index.html ok")

# ---------- style.css: job bar tint ----------
p = "apps/client/src/style.css"
s = io.open(p, encoding="utf-8").read()
anchor = ".bar.xp"
idx = s.find(anchor)
assert idx != -1, "css xp anchor"
# append a job modifier right after the xp bar rule block
close = s.find("}", idx)
insert = close + 1
rule = "\n\n/* E07: the job track tints indigo against the base bar's green */\n.bar.xp.job { --bar-tint: #8f7bff; }\n.bar.xp.job i { background: var(--bar-tint, #8f7bff); }"
s = s[:insert] + rule + s[insert:]
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("style.css ok")

# ---------- ui.ts ----------
p = "apps/client/src/ui.ts"
s = io.open(p, encoding="utf-8").read()

# hooks
old = '''	onEquip?(slot: CosmeticSlot, id: string): void;'''
new = '''	onEquip?(slot: CosmeticSlot, id: string): void;
	// E07: equip a weapon/armor bag item; `equippable` reports whether the
	// bundle marks the item as gear (main.ts reads the content bundle).
	onEquipItem?(item: string): void;
	equippable?(item: string): boolean;'''
assert old in s, "hooks anchor"
s = s.replace(old, new, 1)

# private fields + ctor defaults
old = '''	private readonly equipCosmetic: (slot: CosmeticSlot, id: string) => void;'''
new = '''	private readonly equipCosmetic: (slot: CosmeticSlot, id: string) => void;
	private readonly equipItem: (item: string) => void;
	private readonly isEquippable: (item: string) => boolean;'''
assert old in s, "fields anchor"
s = s.replace(old, new, 1)

old = '''		this.equipCosmetic = hooks.onEquip ?? (() => comingSoon());'''
new = '''		this.equipCosmetic = hooks.onEquip ?? (() => comingSoon());
		this.equipItem = hooks.onEquipItem ?? (() => comingSoon());
		this.isEquippable = hooks.equippable ?? (() => false);'''
assert old in s, "ctor anchor"
s = s.replace(old, new, 1)

# setCharacterState: dual bars + character modal refresh
old = '''		byId("footer-xp").textContent = `${state.exp} / 100`;
		byId("xp-text").textContent = `${state.exp} / 100`;
		const ratio = Math.max(0, Math.min(1, state.exp / 100));
		byId("xp-fill").style.setProperty("--fill", String(ratio));
		byId("footer-xp-fill").style.setProperty("--progress", String(ratio));
		this.setHp(state.hp, state.max_hp);
		this.renderPotionCount();
		return true;
	}'''
new = '''		const baseNext = Math.max(1, state.base_exp_next ?? 0);
		byId("footer-xp").textContent = `${state.exp} / ${baseNext}`;
		byId("xp-text").textContent = `${state.exp} / ${baseNext}`;
		const ratio = Math.max(0, Math.min(1, state.exp / baseNext));
		byId("xp-fill").style.setProperty("--fill", String(ratio));
		byId("footer-xp-fill").style.setProperty("--progress", String(ratio));
		// E07 job track.
		byId("footer-job").textContent = this.hooks.language === "th" ? `อาชีพ ${state.job_level}` : `Job Lv. ${String(state.job_level).padStart(2, "0")}`;
		const jobNext = Math.max(1, state.job_exp_next ?? 0);
		byId("jobxp-text").textContent = `${state.job_exp} / ${jobNext}`;
		byId("jobxp-fill").style.setProperty("--fill", String(Math.max(0, Math.min(1, state.job_exp / jobNext))));
		this.setHp(state.hp, state.max_hp);
		this.renderPotionCount();
		if (byId("modal-title").textContent === "Character") {
			this.openModal("character");
		}
		return true;
	}'''
assert old in s, "setCharacterState anchor"
s = s.replace(old, new, 1)

# setConnection resets: find both blocks and add jobxp resets
s = s.replace('''		this.characterRevision = 0;''','''		this.characterRevision = 0;
		byId("jobxp-fill").style.setProperty("--fill", "0");
		byId("jobxp-text").textContent = "Job 0%";''', 1)

# character modal case: insert before the bag case
old = '''		if (name === "bag") {'''
new = '''		if (name === "character") {
			const state = this.characterState;
			const panel = document.createElement("div");
			panel.className = "social-panel";
			const th = this.hooks.language === "th";
			if (!this.online || !state) {
				panel.append(offlineNote(th));
				content.append(panel);
				return;
			}
			const row = (label: string, value: string) => {
				const line = document.createElement("p");
				line.className = "econ-note";
				line.textContent = `${label}: ${value}`;
				return line;
			};
			panel.append(
				row(th ? "เลเวลพื้นฐาน" : "Base Lv.", `${state.level}`),
				row(th ? "เลเวลอาชีพ" : "Job Lv.", `${state.job_level}`),
				row(th ? "โจมตี" : "ATK", `${state.atk}`),
				row(th ? "ป้องกัน" : "DEF", `${state.def}`),
				row(th ? "พลังชีวิต" : "HP", `${state.hp} / ${state.max_hp}`),
			);
			const baseNext = Math.max(1, state.base_exp_next ?? 0);
			const jobNext = Math.max(1, state.job_exp_next ?? 0);
			panel.append(
				row(th ? "ค่าศาสตร์ฐาน" : "Base EXP", `${state.exp} / ${baseNext}`),
				row(th ? "ค่าศาสตร์อาชีพ" : "Job EXP", `${state.job_exp} / ${jobNext}`),
			);
			const gearTitle = document.createElement("div");
			gearTitle.className = "panel-kicker";
			gearTitle.textContent = th ? "อุปกรณ์" : "EQUIPMENT";
			panel.append(gearTitle);
			const slots = state.equipment ?? [];
			if (slots.length === 0) {
				const none = document.createElement("p");
				none.className = "econ-note";
				none.textContent = th ? "ยังไม่สวมอุปกรณ์" : "Nothing equipped.";
				panel.append(none);
			}
			for (const entry of slots) {
				const line = document.createElement("p");
				line.className = "econ-note";
				const label = entry.slot === "weapon" ? (th ? "อาวุธ" : "Weapon") : th ? "เกราะ" : "Armor";
				line.textContent = `${label}: ${this.hooks.itemName(entry.item)}`;
				panel.append(line);
			}
			const hint = document.createElement("small");
			hint.textContent = th ? "สวมอุปกรณ์จากกระเป๋า (ปุ่ม B)" : "Equip gear from your field bag (B).";
			panel.append(hint);
			content.append(panel);
			return;
		}
		if (name === "bag") {'''
assert old in s, "modal anchor"
s = s.replace(old, new, 1)

# offline note helper + bag equip buttons
old = '''		if (name === "bag") {
			const grid = document.createElement("div");'''
new = '''		if (name === "bag") {
			const grid = document.createElement("div");'''
assert old in s, "bag anchor"
s = s.replace(old, new, 1)

# bag cells: equip button for gear
old = '''			for (const entry of entries) {
				const item = this.hooks.itemName(entry.item);
				const note = `${entry.count} ×`;
				const cell = document.createElement("div");
				cell.className = "inventory-cell";
				const itemName = document.createElement("span");
				itemName.textContent = item;
				const itemNote = document.createElement("small");
				itemNote.textContent = note;
				cell.append(itemName, itemNote);
				grid.append(cell);
			}'''
new = '''			for (const entry of entries) {
				const item = this.hooks.itemName(entry.item);
				const note = `${entry.count} ×`;
				const cell = document.createElement("div");
				cell.className = "inventory-cell";
				const itemName = document.createElement("span");
				itemName.textContent = item;
				const itemNote = document.createElement("small");
				itemNote.textContent = note;
				cell.append(itemName, itemNote);
				if (this.online && this.isEquippable(entry.item)) {
					const equip = document.createElement("button");
					equip.className = "social-action";
					equip.textContent = this.hooks.language === "th" ? "สวม" : "Equip";
					equip.addEventListener("click", () => this.equipItem(entry.item));
					cell.append(equip);
				}
				grid.append(cell);
			}'''
assert old in s, "bag cells anchor"
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ui.ts ok")

# ---------- main.ts: hook wiring ----------
p = "apps/client/src/main.ts"
s = io.open(p, encoding="utf-8").read()
old = '''			onEquip: (slot, id) => {'''
new = '''			onEquipItem: (item) => {
				sendColdIntent({ t: "equip_item", item, op_id: crypto.randomUUID() });
			},
			equippable: (item) => {
				const def = contentBundle?.items?.[item] as { equip_slot?: string } | undefined;
				return typeof def?.equip_slot === "string";
			},
			onEquip: (slot, id) => {'''
assert old in s, "main hooks anchor"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("main.ts ok")
