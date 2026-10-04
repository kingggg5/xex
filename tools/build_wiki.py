#!/usr/bin/env python3
"""Generate the Aetherfield player wiki (static, bilingual, zero-dependency).

Reads the authored content tables in content/source/ and emits static HTML
into wiki/. Numbers on the wiki are rendered from the same data the server
loads, so a tuning edit and a wiki rebuild stay in sync. Run:

    python tools/build_wiki.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content" / "source"
OUT = ROOT / "wiki"

PAGES = ["index", "world", "characters", "quests", "items", "combat", "economy", "controls", "about"]

NAV_LABELS = {
    "index": ("Home", "หน้าแรก"),
    "world": ("World", "โลก"),
    "characters": ("Characters", "ตัวละคร"),
    "quests": ("Quests", "ภารกิจ"),
    "items": ("Items", "ไอเทม"),
    "combat": ("Combat", "การต่อสู้"),
    "economy": ("Economy", "เศรษฐกิจ"),
    "controls": ("Controls", "การควบคุม"),
    "about": ("About", "เกี่ยวกับ"),
}

PAGE_TITLES = {
    "index": ("Welcome to the Frontier", "ยินดีต้อนรับสู่ชายขอบ"),
    "world": ("The World", "โลก"),
    "characters": ("Characters", "ตัวละคร"),
    "quests": ("Quests", "ภารกิจ"),
    "items": ("Items", "ไอเทม"),
    "combat": ("Combat", "การต่อสู้"),
    "economy": ("Economy", "เศรษฐกิจ"),
    "controls": ("Controls", "การควบคุม"),
    "about": ("About", "เกี่ยวกับ"),
}

PAGE_BLURBS = {
    "world": ("The meadow, its route and its landmarks.", "ทุ่งหญ้า เส้นทาง และจุดสำคัญ"),
    "characters": ("Sella, the Trailblade, and the puddlekin.", "เซลล่า นักดาบทุ่ง และพุดเดิลคิน"),
    "quests": ("The Three Windmarks loop and rewards.", "ลูปเครื่องหมายลมทั้งสามและรางวัล"),
    "items": ("Potions, beads, seeds and boxes.", "ยา ลูกปัด เมล็ด และกล่อง"),
    "combat": ("Abilities, telegraphs and counters.", "ทักษะ วงเตือน และการลงโทษ"),
    "economy": ("Gold, the store, and published box odds.", "ทอง ร้านค้า และอัตรากล่องแบบเปิดเผย"),
    "controls": ("Keyboard, touch and comfort settings.", "คีย์บอร์ด หน้าจอสัมผัส และการตั้งค่า"),
    "about": ("What the prototype is, and what it is not.", "โปรโตไทป์นี้คืออะไร และไม่ใช่อะไร"),
}


def load(name: str):
    return json.loads((SOURCE / name).read_text(encoding="utf-8"))


def pair(en: str, th: str) -> str:
    """Bilingual cell: both languages ship; the toggle picks one."""
    return f'<span class="en">{en}</span><span class="th">{th}</span>'


def pretty_name(cosmetic_id: str) -> str:
    tail = cosmetic_id.split("_", 1)[1] if "_" in cosmetic_id else cosmetic_id
    return tail.replace("_", " ").title()


def fmt_ms(ms: int) -> str:
    return f"{ms / 1000:g} s" if ms >= 1000 else f"{ms} ms"


def pct(weight: int, total: int) -> str:
    return f"{100 * weight / total:.0f}%"


def map_svg(zones) -> str:
    """Plot the real POIs and spawn points as a small SVG map."""
    zone = zones["zones"][0]
    extent = zone["half_extent"]
    size = 340

    def px(x: float) -> float:
        return (x + extent) / (2 * extent) * size

    def pz(z: float) -> float:
        return (z + extent) / (2 * extent) * size

    marks = {
        "entry": ("gate", "ประตู / Gate"),
        "regroup": ("camp", "จุดรวมพล / Regroup"),
        "sella": ("npc", "เซลล่า / Sella"),
        "windmark_1": ("mark", "เครื่องหมายลม 1"),
        "windmark_2": ("mark", "เครื่องหมายลม 2"),
        "windmark_3": ("mark", "เครื่องหมายลม 3"),
        "hunt_clearing": ("hunt", "ลานล่า / Hunt"),
        "lookout": ("lookout", "จุดชมวิว / Lookout"),
    }
    colors = {"gate": "#e8c879", "camp": "#f6f1e3", "npc": "#87c86a",
              "mark": "#71d2dc", "hunt": "#dc6b6d", "lookout": "#e8c879"}
    nodes: list[str] = []
    for poi in zone["pois"]:
        kind, label = marks.get(poi["id"], ("mark", poi["id"]))
        cx, cy = px(poi["x"]), pz(poi["z"])
        nodes.append(
            f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="6" fill="{colors[kind]}" stroke="#0e161b" stroke-width="1.5"><title>{label}</title></circle>'
            f'<text x="{cx + 9:.0f}" y="{cy + 4:.0f}" class="map-label">{label}</text>'
        )
    for spawn in zone["monster_spawns"]:
        nodes.append(
            f'<circle cx="{px(spawn["x"]):.0f}" cy="{pz(spawn["z"]):.0f}" r="4.5" fill="#e88eaa" stroke="#0e161b" stroke-width="1.2"><title>พุดเดิลคิน / Puddlekin</title></circle>'
        )
    route = [("entry", "regroup"), ("regroup", "sella"), ("sella", "windmark_1"),
             ("windmark_1", "windmark_2"), ("windmark_2", "hunt_clearing"),
             ("hunt_clearing", "windmark_3"), ("windmark_3", "sella")]
    pois = {poi["id"]: poi for poi in zone["pois"]}
    path_d = " ".join(
        f"{'M' if i == 0 else 'L'} {px(pois[a]['x']):.0f} {pz(pois[a]['z']):.0f}"
        for i, (a, _b) in enumerate(route)
    )
    return (
        f'<svg viewBox="-8 -8 {size + 16} {size + 16}" role="img" aria-label="Sunmeadow Verge map">'
        f'<rect x="-8" y="-8" width="{size + 16}" height="{size + 16}" rx="12" fill="#22392f"/>'
        f'<path d="{path_d}" fill="none" stroke="#d9c68f" stroke-width="2" stroke-dasharray="5 5" opacity="0.75"/>'
        + "".join(nodes) + "</svg>"
    )


def page_shell(page: str, title: str, subtitle: tuple[str, str], body: str, content_hash: str) -> str:
    nav = "".join(
        f'<a href="{name}.html" class="{"active" if name == page else ""}">'
        f'<span class="en">{NAV_LABELS[name][0]}</span><span class="th">{NAV_LABELS[name][1]}</span></a>'
        for name in PAGES
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Aetherfield Wiki</title>
<link rel="stylesheet" href="style.css">
</head>
<body data-lang="en">
<header class="site-header">
	<a class="brand" href="index.html">AETHERFIELD <small>WIKI</small></a>
	<nav class="site-nav">{nav}</nav>
	<button id="lang-toggle" type="button" title="Switch language">ไทย</button>
</header>
<main>
<section class="hero">
	<p class="kicker">AETHERFIELD · VERDANT FRONTIER</p>
	<h1>{pair(PAGE_TITLES[page][0], PAGE_TITLES[page][1])}</h1>
	<p class="lede">{pair(subtitle[0], subtitle[1])}</p>
</section>
{body}
</main>
<footer>
	<p>Aetherfield is an original browser action-RPG prototype. Wiki generated from game content v{content_hash[:8]} — the numbers here are the same tables the server loads.</p>
	<p>{pair("Progress in the current prototype is session-scoped and resets when the room restarts.",
	         "ความคืบหน้าในโปรโตไทป์นี้อยู่แค่ช่วงเซสชัน และจะรีเซ็ตเมื่อห้องรีสตาร์ท")}</p>
</footer>
<script src="app.js"></script>
</body>
</html>
"""


def stat_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body_rows = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div>'


def build() -> None:
    OUT.mkdir(exist_ok=True)
    manifest = load("manifest.json")
    abilities = {a["id"]: a for a in load("abilities.json")["abilities"]}
    enemies = load("enemies.json")["enemies"]
    items = {i["id"]: i for i in load("items.json")["items"]}
    quests = load("quests.json")["quests"]
    zones = load("zones.json")
    vocations = load("vocations.json")["vocations"]
    economy = load("economy.json")
    dialogue_en = load("dialogue/en.json")
    dialogue_th = load("dialogue/th.json")

    # The built-bundle directory name keeps the wiki footer traceable to data.
    build_dir = ROOT / "content" / "build"
    content_hash = "0" * 16
    if build_dir.is_dir():
        for entry in build_dir.iterdir():
            if entry.is_dir():
                content_hash = entry.name
                break

    puddle = enemies[0]
    hero = vocations[0]
    quest = quests[0]
    box = economy["boxes"]["meadow_box"]
    box_total = sum(roll["weight"] for roll in box["table"])
    zone = zones["zones"][0]

    # ---------------------------------------------------------------- index
    cards = "".join(
        f'<article class="card"><h3>{pair(en_h, th_h)}</h3><p>{pair(en_p, th_p)}</p></article>'
        for en_h, th_h, en_p, th_p in [
            ("Explore the verge", "สำรวจชายทุ่ง",
             "Wake the three windmarks along Sunmeadow Verge, from the gate to the lookout.",
             "ปลุกเครื่องหมายลมทั้งสามของทุ่งซันมีโดว์ ตั้งแต่ประตูจนถึงจุดชมวิว"),
            ("Read the fight", "อ่านจังหวะการต่อสู้",
             "Every enemy attack paints a ground telegraph before it lands — dodge on your timing, punish on theirs.",
             "ทุกการโจมตีของศัตรูมีวงเตือนพื้นก่อนตกลงมา — หลบตามจังหวะของคุณ แล้วลงโทษตอนเปิดของมัน"),
            ("Play together", "เล่นด้วยกัน",
             "Up to four travelers share the field; hunt credit and loot are personal and fair.",
             "นักเดินทางถึงสี่คนแบ่งทุ่งเดียวกัน ครีดิตการล่าและของดรอปเป็นส่วนตัวและยุติธรรม"),
        ]
    )
    link_cards = "".join(
        f'<a class="card link-card" href="{name}.html"><h3>{pair(NAV_LABELS[name][0], NAV_LABELS[name][1])}</h3><p>{pair(PAGE_BLURBS[name][0], PAGE_BLURBS[name][1])}</p></a>'
        for name in PAGES[1:]
    )
    index_body = f"""
<section class="cards">{cards}</section>
<h2>{pair("Feature pages", "หน้ารายละเอียด")}</h2>
<section class="cards">{link_cards}</section>
"""
    (OUT / "index.html").write_text(page_shell(
        "index", "Welcome to the Frontier",
        ("An original browser action-RPG: one sunlit meadow, one blade, and windmarks waiting to wake.",
         "เกมแอ็กชัน RPG บนเบราว์เซอร์สายเลือดใหม่: ทุ่งหญ้าแสงแดดหนึ่งผืน ดาบหนึ่งเล่ม และเครื่องหมายลมที่รอการปลุก"),
        index_body, content_hash), encoding="utf-8")

    # ---------------------------------------------------------------- world
    poi_desc = {
        "entry": ("The gate you arrive through.", "ประตูที่คุณเดินทางมาถึง"),
        "regroup": ("Camp where fallen travelers return to their feet.", "แคมป์ที่นักเดินทางที่ล้มลงกลับมาหายใจ"),
        "sella": ("The frontier guide who hands out the meadow's work.", "ผู้นำทางแห่งชายทุ่งผู้มอบงานของทุ่งนี้"),
        "hunt_clearing": ("Open ground where the puddlekin gather.", "พื้นที่โล่งที่พุดเดิลคินชุมนุมกัน"),
        "lookout": ("A quiet rise off the main route.", "เนินเงียบสงบที่แยกออกจากเส้นทางหลัก"),
    }
    poi_rows = [
        [poi["id"], f"{poi['x']:g}, {poi['z']:g}", pair(*poi_desc.get(
            poi["id"], ("An ancient stone that holds the meadow's wind.", "หินโบราณที่เก็บลมหายใจของทุ่ง")))]
        for poi in zone["pois"]
    ]
    world_body = f"""
<h2>{pair("Sunmeadow Verge", "ทุ่งซันมีโดว์")}</h2>
<p>{pair(
    "The frontier's first meadow: a warm stretch of grass ending at a limestone keep on the northern rise. Travelers enter from the southern gate, meet the guide Sella, and follow the dashed route past three windmarks — stones that hold the meadow's breath — before returning. Off the main loop, a lookout rewards the curious.",
    "ชายทุ่งแห่งแรกของชายขอบ: แผ่นหญ้าอบอุ่นปลายทิศเหนือจบที่ปราการหินปูนบนเนิน นักเดินทางเข้าจากประตูทิศใต้ พบเซลล่าผู้นำทาง แล้วไล่ตามเส้นทางเส้นประผ่านเครื่องหมายลมทั้งสาม — หินที่เก็บลมหายใจของทุ่ง — ก่อนเดินทางกลับ ส่วนจุดชมวิวรอบนอกไว้รางวัลผู้ที่แวะสำรวจ")}</p>
<div class="map-figure">{map_svg(zones)}
<figcaption>{pair("The verge route, plotted from the game's own map data. Pink dots are puddlekin spawns.",
                  "เส้นทางของทุ่ง พล็อตจากข้อมูลแผนที่ในเกมจริง จุดชมพูคือจุดเกิดพุดเดิลคิน")}</figcaption></div>
<h2>{pair("Points of interest", "จุดสำคัญ")}</h2>
{stat_table([pair("POI", "จุด"), pair("Position", "ตำแหน่ง"), pair("Description", "คำอธิบาย")], poi_rows)}
<p class="note">{pair(
    f"The verge spans {zone['half_extent']:g} m from center to edge. Bridges, cliffs and stacked floors are deliberately absent until the world grows a second layer.",
    f"ทุ่งกว้าง {zone['half_extent']:g} เมตรจากกึ่งกลางถึงขอบ สะพาน หน้าผา และพื้นซ้อนถูกตัดออกโดยตั้งใจจนกว่าโลกจะมีชั้นที่สอง")}</p>
"""
    (OUT / "world.html").write_text(page_shell(
        "world", "The World",
        ("Sunmeadow Verge — the first meadow of the frontier.", "ทุ่งซันมีโดว์ — ชายทุ่งแห่งแรกของชายขอบ"),
        world_body, content_hash), encoding="utf-8")

    # ----------------------------------------------------------- characters
    char_body = f"""
<h2>{dialogue_en['npc_sella']} <small class="th-inline">{dialogue_th['npc_sella']}</small></h2>
<p>{pair(
    "The verge's guide. Sella hands out the meadow's work, pays in seeds, and remembers everyone who walks out of the grass. Find her just past the regroup camp.",
    "ผู้นำทางแห่งชายทุ่ง เซลล่าเป็นคนมอบงานของทุ่ง จ่ายค่าจ้างเป็นเมล็ด และจดจำทุกคนที่เดินออกจากหญ้า พบเธอได้ไม่ไกลจากแคมป์จุดรวมพล")}</p>
<blockquote>{pair(f"“{dialogue_en['sella_greet']}”", f"“{dialogue_th['sella_greet']}”")}</blockquote>
<blockquote>{pair(f"“{dialogue_en['sella_farewell']}”", f"“{dialogue_th['sella_farewell']}”")}</blockquote>

<h2>{pair(f"The Traveler — {dialogue_en['vocation_trailblade']}", f"นักเดินทาง — {dialogue_th['vocation_trailblade']}")}</h2>
<p>{pair(
    "The frontier's opening vocation: a sword-and-cloak duelist built for reading enemies, not out-tanking them.",
    "อาชีพเปิดเกมของชายขอบ: นักดาบคลุกผ้าคลุมที่เน้นอ่านศัตรู ไม่ใช่แลกเลือด")}</p>
{stat_table([pair("Stat", "ค่า"), pair("Value", "ค่า")], [
    [pair("HP", "พลังชีวิต"), str(hero["hp"])],
    [pair("Move speed", "ความเร็วเดิน"), f"{hero['speed']:g} m/s"],
    [pair("Starting wallet", "กระเป๋าเริ่มต้น"), f"{economy['starting']['gold']} gold / {economy['starting']['coin']} coin"],
])}

<h2>{dialogue_en['enemy_puddlekin']} <small class="th-inline">{dialogue_th['enemy_puddlekin']}</small></h2>
<p>{pair(
    "A squishy meadow spirit currently making a nuisance of itself. When it squashes flat, its Splash Hop is coming — step out of the painted circle, then punish the dazed landing.",
    "วิญญาณทุ่งเหนียวหนึบที่กำลังสร้างความวุ่นวาย เมื่อมันแบนราบคือ Splash Hop กำลังมา — ก้าวออกนอกวงที่วาดไว้ แล้วลงโทษตอนมันมึนตายหลังลงพื้น")}</p>
{stat_table([pair("Stat", "ค่า"), pair("Value", "ค่า")], [
    [pair("HP", "พลังชีวิต"), str(puddle["hp"])],
    [pair("Move speed", "ความเร็วเดิน"), f"{puddle['speed']:g} m/s"],
    [pair("Aggro / leash", "ระยะเกาะติด / ไล่ล่า"), f"{puddle['aggro']:g} m / {puddle['leash']:g} m"],
    [pair("Respawn", "เกิดใหม่"), f"{puddle['respawn_s']} s"],
    [pair("EXP", "ค่าประสบการณ์"), str(puddle["exp"])],
    [pair("Splash Hop", "Splash Hop"), pair(
        f"{puddle['splash_damage']} damage in a {puddle['splash_radius']:g} m circle, {fmt_ms(puddle['splash_windup_ms'])} windup, {fmt_ms(puddle['splash_cooldown_ms'])} cooldown",
        f"ดาเมจ {puddle['splash_damage']} ในวง {puddle['splash_radius']:g} ม. ลุ่นนำ {fmt_ms(puddle['splash_windup_ms'])} คูลดาวน์ {fmt_ms(puddle['splash_cooldown_ms'])}")],
])}
"""
    (OUT / "characters.html").write_text(page_shell(
        "characters", "Characters",
        ("Who keeps the verge — and who messes it up.", "ใครรักษาชายทุ่ง — และใครทำให้มันวุ่นวาย"),
        char_body, content_hash), encoding="utf-8")

    # --------------------------------------------------------------- quests
    objective_items = []
    for o in quest["objectives"]:
        if o["kind"] == "activate":
            objective_items.append(pair(
                f"Activate {o['count']} distinct windmarks — channel for 1 s within 2 m; damage or moving breaks the channel.",
                f"ปลุกเครื่องหมายลม {o['count']} อันที่ต่างกัน — ชาร์จ 1 วินาทีในรัศมี 2 ม. การโดนตีหรือขยับจะตัดชาร์จ"))
        else:
            objective_items.append(pair(
                f"Defeat {o['count']} puddlekin — party members in range get personal credit.",
                f"ปราบพุดเดิลคิน {o['count']} ตัว — สมาชิกปาร์ตี้ในระยะได้ครีดิตเป็นส่วนตัว"))
    objectives = "".join(f"<li>{item}</li>" for item in objective_items)
    quest_body = f"""
<h2>{dialogue_en['quest_three_windmarks']} <small class="th-inline">{dialogue_th['quest_three_windmarks']}</small></h2>
<p>{pair(
    "The verge's opening loop: talk to Sella, wake the windmarks, cull the puddlekin, and claim your seed. The route is paced to a comfortable 8–15 minute walk, with a lookout detour if you like high ground.",
    "ลูปเปิดเกมของชายทุ่ง: คุยกับเซลล่า ปลุกเครื่องหมายลม กำจัดพุดเดิลคิน แล้วกลับไปรับเมล็ด เส้นทางออกแบบให้เดินสบาย 8–15 นาที มีทางแยกไปจุดชมวิวสำหรับคนชอบความสูง")}</p>
<ol class="steps">{objectives}</ol>
<h2>{pair("Rewards", "รางวัล")}</h2>
{stat_table([pair("Reward", "รางวัล"), pair("Value", "ค่า")], [
    [pair("Base EXP", "ค่าประสบการณ์"), str(quest["reward"]["exp"])],
    [f"{dialogue_en['item_gale_seed']} / {dialogue_th['item_gale_seed']}", "×1"],
    [pair("Claim gold", "ทองจากการรับรางวัล"), f"+{economy['quest_claim_gold']} gold"],
])}
<p class="note">{pair(
    f"Three puddlekin kills ({puddle['exp']} EXP each) plus the {quest['reward']['exp']} EXP claim lands level 2 exactly at the turn-in — the intended reward moment.",
    f"ฆ่าพุดเดิลคินสามตัว (EXP ตัวละ {puddle['exp']}) บวก {quest['reward']['exp']} EXP จากการส่งภารกิจ ไต้เลเวล 2 พอดีที่จังหวะส่งงาน — จังหวะรางวัลที่ตั้งใจไว้")}</p>
"""
    (OUT / "quests.html").write_text(page_shell(
        "quests", "Quests",
        ("The Three Windmarks — the verge's first full loop.", "เครื่องหมายลมทั้งสาม — ลูปแรกครบวงจรของทุ่ง"),
        quest_body, content_hash), encoding="utf-8")

    # --------------------------------------------------------------- items
    item_rows = [
        [f"{dialogue_en[item['name_key']]} <small class=\"th-inline\">{dialogue_th[item['name_key']]}</small>",
         item["type"],
         f"{dialogue_en[item['desc_key']]} <small class=\"th-inline\">{dialogue_th[item['desc_key']]}</small>"]
        for item in items.values()
    ]
    items_body = f"""
<p>{pair(
    "Everything the frontier hands out or asks back. The bag holds 12 stacks; materials like dew beads go to an uncapped pouch, so a full bag never destroys field loot.",
    "ของทุกชิ้นที่ชายทุ่งให้และเรียกคืน กระเป๋าจำกัด 12 ช่อง วัสดุอย่างลูกปัดน้ำค้างเก็บในถุงไม่จำกัด กระเป๋าเต็มจึงไม่มีวันทำของดรอปหาย")}</p>
{stat_table([pair("Item", "ไอเทม"), pair("Type", "ประเภท"), pair("Description", "คำอธิบาย")], item_rows)}
<h2>{pair("Where things come from", "ของแต่ละอย่างมาจากไหน")}</h2>
{stat_table([pair("Source", "แหล่ง"), pair("Gives", "ได้รับ")], [
    [pair("Puddlekin defeat", "ปราบพุดเดิลคิน"), pair(f"{puddle['exp']} EXP, a Dew Bead per eligible player, and {economy['kill_gold']} gold", f"{puddle['exp']} EXP, ลูกปัดน้ำค้างต่อผู้เล่นที่มีสิทธิ์, และทอง {economy['kill_gold']}")],
    [pair("Quest turn-in", "ส่งภารกิจ"), pair(f"{quest['reward']['exp']} EXP, a Gale Seed, and {economy['quest_claim_gold']} gold", f"{quest['reward']['exp']} EXP, เมล็ดวายุ, และทอง {economy['quest_claim_gold']}")],
    [pair("Store purchase", "ซื้อจากร้าน"), pair("Trail Potions, Meadow Boxes, cosmetics and pets", "ยาเดินทาง, กล่องลานหญ้า, คอสเมทิก และสัตว์เลี้ยง")],
    [pair("Meadow Box", "กล่องลานหญ้า"), pair("Gold, coins, potions, beads — or the Rose outfit, exclusive to boxes", "ทอง, เหรียญ, ยา, ลูกปัด — หรือชุด Rose ที่ได้จากกล่องเท่านั้น")],
])}
"""
    (OUT / "items.html").write_text(page_shell(
        "items", "Items", ("Potions, seeds, beads and boxes.", "ยา เมล็ด ลูกปัด และกล่อง"),
        items_body, content_hash), encoding="utf-8")

    # --------------------------------------------------------------- combat
    atk, arc, dodge, guard, potion = (abilities[k] for k in ("attack", "arc_slash", "dodge", "guard", "potion"))
    combat_body = f"""
<p>{pair(
    "Combat is a telegraph dance: enemies paint the ground before every hit, and your dodge is invulnerable for its whole dash. Both sides run on fixed 50 ms server ticks, so what you see is what the server sees.",
    "การต่อสู้คือการเต้นกับวงเตือน: ศัตรูวาดพื้นก่อนทุกหมัด และการหลบของคุณอยู่ในสภาพอมตะตลอดการพุ่ง ทั้งสองฝั่งเดินบนเซิร์ฟเวอร์ 50 มิลลิวินาทีคงที่ สิ่งที่เห็นคือสิ่งที่เซิร์ฟเวอร์เห็น")}</p>
<h2>{pair("Trailblade abilities", "ทักษะของนักดาบทุ่ง")}</h2>
{stat_table([pair("Ability", "ทักษะ"), pair("Damage / effect", "ดาเมจ / เอฟเฟกต์"), pair("Shape", "รูปทรง"), pair("Cooldown", "คูลดาวน์"), pair("Timing", "จังหวะ")], [
    [pair("Basic attack", "โจมตีปกติ"), f"{atk['damage']} dmg", f"{atk['arc_deg']}° · {atk['range']:g} m · {atk['targets']} {pair('target', 'เป้า')}", fmt_ms(atk["cooldown_ms"]), f"{fmt_ms(atk['windup_ms'])} + {fmt_ms(atk['active_ms'])} + {fmt_ms(atk['recovery_ms'])}"],
    [pair("Arc Slash", "Arc Slash"), f"{arc['damage']} dmg × {arc['targets']}", f"{arc['arc_deg']}° · {arc['range']:g} m", fmt_ms(arc["cooldown_ms"]), f"{fmt_ms(arc['windup_ms'])} + {fmt_ms(arc['active_ms'])} + {fmt_ms(arc['recovery_ms'])}"],
    [pair("Quickstep (dodge)", "Quickstep (หลบ)"), pair("invulnerable dash", "พุ่งอมตะ"), f"×{dodge['speed_mult']:g} {pair('speed for', 'ความเร็ว นาน')} {fmt_ms(dodge['duration_ms'])}", fmt_ms(dodge["cooldown_ms"]), "—"],
    [pair("Guard Stance", "Guard Stance"), f"−{guard['reduction_pct']}% {pair('frontal damage', 'ดาเมจด้านหน้า')}", pair("front 120° cone", "ทรงหน้า 120°"), fmt_ms(guard["cooldown_ms"]), pair(f"hold up to {fmt_ms(guard['max_hold_ms'])}; block in the first {guard['perfect_ms']} ms = perfect guard", f"กดค้างได้ {fmt_ms(guard['max_hold_ms'])}; การับใน {guard['perfect_ms']} มิลลิวินาทีแรกคือ perfect guard")],
    [pair("Trail Potion", "ยาเดินทาง"), f"+{potion['heal']} HP", pair("self", "ใช้กับตัวเอง"), fmt_ms(potion["cooldown_ms"]), pair(f"carry {potion['carry']}", f"พกได้ {potion['carry']} ขวด")],
])}
<h2>{pair("The Splash Hop telegraph", "วงเตือน Splash Hop")}</h2>
<p>{pair(
    f"The puddlekin's hop is the game's teach-everything attack: a {puddle['splash_radius']:g} m circle fills on your position for {fmt_ms(puddle['splash_windup_ms'])}, deals {puddle['splash_damage']} damage if you are still inside, then leaves the puddlekin dazed for {fmt_ms(puddle['splash_recovery_ms'])} — the counter window. On a typical 100 ms mobile connection the windup still leaves over 400 ms to react, because telegraphs are drawn straight from server snapshots, never through the smoothed replay.",
    f"Splash Hop ของพุดเดิลคินคือท่าสอนทุกอย่างของเกม: วง {puddle['splash_radius']:g} เมตรเต็มที่ตำแหน่งคุณใน {fmt_ms(puddle['splash_windup_ms'])} ถ้ายังอยู่ในวงจะโดน {puddle['splash_damage']} ดาเมจ จากนั้นพุดเดิลคินมึน {fmt_ms(puddle['splash_recovery_ms'])} — นั่นคือช่องลงโทษ บนมือถือที่ดีเลย์ราว 100 ms ยังเหลือเวลาปฏิกิริยามากกว่า 400 ms เพราะวงเตือนวาดตรงจากสแนปช็อตเซิร์ฟเวอร์ ไม่ผ่านระบบเกลี่ยภาพ")}</p>
<p class="note">{pair(
    "Dodge verdicts are resolved in server time. If your screen still showed the windup when your dodge arrived, the game counts it — unfair hits are tracked and capped by design.",
    "ผลการหลบถูกตัดสินบนเวลาเซิร์ฟเวอร์ ถ้าจอคุณยังเห็นวงเตือนตอนที่คำสั่งหลบไปถึง เกมถือว่าคุณหลบได้ — การโดนแบบไม่แฟร์ถูกนับและจำกัดไว้ในดีไซน์")}</p>
"""
    (OUT / "combat.html").write_text(page_shell(
        "combat", "Combat", ("Telegraphs, dodges and the counter window.", "วงเตือน การหลบ และช่องลงโทษ"),
        combat_body, content_hash), encoding="utf-8")

    # -------------------------------------------------------------- economy
    store_table_rows = []
    for entry in economy["store"]:
        if "item" in entry:
            label = pair(dialogue_en[items[entry["item"]]["name_key"]], dialogue_th[items[entry["item"]]["name_key"]])
        else:
            label = pretty_name(entry["cosmetic"])
        store_table_rows.append([label, entry["currency"], str(entry["price"])])
    odds_rows = []
    for roll in box["table"]:
        chance = pct(roll["weight"], box_total)
        if "gold" in roll:
            odds_rows.append([pair("Gold", "ทอง"), str(roll["gold"]), chance])
        elif "coin" in roll:
            odds_rows.append([pair("Coin", "เหรียญ"), str(roll["coin"]), chance])
        elif "cosmetic" in roll:
            odds_rows.append([pair(f"{pretty_name(roll['cosmetic'])} outfit", f"ชุด {pretty_name(roll['cosmetic'])}"), "×1", chance])
        else:
            mn, mx = roll.get("min", 1), roll.get("max", 1)
            amount = f"{mn}–{mx}" if mx != mn else "1"
            odds_rows.append([pair(dialogue_en[items[roll["item"]]["name_key"]], dialogue_th[items[roll["item"]]["name_key"]]), amount, chance])
    economy_body = f"""
<p>{pair(
    "The frontier runs on two earnable currencies — nothing here is bought with real money, and there is no paid randomness. Gold comes from hunting and questing; coins come from duplicate cosmetics.",
    "ชายขอบใช้เงินสองชนิดที่หาได้จากการเล่น — ไม่มีอะไรซื้อด้วยเงินจริง และไม่มีกล่องสุ่มแบบจ่ายเงิน ทองมาจากการล่าและภารกิจ เหรียญมาจากคอสเมทิกที่ได้ซ้ำ")}</p>
<h2>{pair("Earning", "การหาเงิน")}</h2>
{stat_table([pair("Activity", "กิจกรรม"), pair("Reward", "รางวัล")], [
    [pair("Puddlekin defeat", "ปราบพุดเดิลคิน"), f"+{economy['kill_gold']} gold"],
    [pair("Quest claim", "รับรางวัลภารกิจ"), f"+{economy['quest_claim_gold']} gold"],
    [pair("Duplicate cosmetic (box)", "คอสเมทิกซ้ำ (จากกล่อง)"), f"+{economy['duplicate_cosmetic_coin']} coin"],
])}
<h2>{pair("Store", "ร้านค้า")}</h2>
{stat_table([pair("Goods", "สินค้า"), pair("Currency", "สกุล"), pair("Price", "ราคา")], store_table_rows)}
<h2>{pair("Meadow Box odds", "อัตรารางวัลกล่องลานหญ้า")}</h2>
<p>{pair(
    "These are the exact, published odds — the same table the server rolls, shown before you spend a single gold.",
    "นี่คืออัตราจริงที่ประกาศไว้ — เป็นตารางเดียวกับที่เซิร์ฟเวอร์สุ่ม แสดงให้คุณก่อนจ่ายทองแม้แต่เหรียญเดียว")}</p>
{stat_table([pair("Reward", "รางวัล"), pair("Amount", "จำนวน"), pair("Chance", "โอกาส")], odds_rows)}
<p class="note">{pair(
    "Wallet, store and cosmetics are session-scoped in the current prototype: they reset when the room restarts. Durable accounts and ledgers arrive with the persistence milestone.",
    "กระเป๋าเงิน ร้านค้า และคอสเมทิกในโปรโตไทป์นี้อยู่แค่ช่วงเซสชัน: รีเซ็ตเมื่อห้องรีสตาร์ท ระบบบัญชีและบันทึกธุรกรรมแบบถาวรจะมาพร้อมไมล์สโตน persistence")}</p>
"""
    (OUT / "economy.html").write_text(page_shell(
        "economy", "Economy", ("Gold, the store, and honest box odds.", "ทอง ร้านค้า และอัตรากล่องแบบตรงไปตรงมา"),
        economy_body, content_hash), encoding="utf-8")

    # ------------------------------------------------------------- controls
    controls_body = f"""
<h2>{pair("Desktop", "เดสก์ท็อป")}</h2>
{stat_table([pair("Input", "ปุ่ม"), pair("Action", "การกระทำ")], [
    ["WASD / ←↑↓→", pair("Move", "เดิน")],
    [pair("Left-drag", "ลากเมาส์ซ้าย"), pair("Orbit the camera", "หมุนกล้อง")],
    ["F", pair("Basic attack", "โจมตีปกติ")],
    ["1", pair("Arc Slash", "Arc Slash")],
    ["Space", pair("Quickstep (dodge)", "Quickstep (หลบ)")],
    ["G", pair("Guard Stance (hold)", "Guard Stance (กดค้าง)")],
    [pair("Potion button", "ปุ่มยา"), pair("Drink a Trail Potion", "ดื่มยาเดินทาง")],
    ["E", pair("Interact with NPCs and windmarks", "คุยกับ NPC และปลุกเครื่องหมายลม")],
    ["C / B / K / P / J", pair("Character, Bag, Skills, Party, Journal panels", "แผงตัวละคร กระเป๋า ทักษะ ปาร์ตี้ สมุด")],
])}
<h2>{pair("Touch", "สัมผัส")}</h2>
<p>{pair(
    "A left joystick moves; the right cluster holds attack, Arc Slash, Quickstep and the potion. A context button appears when something nearby needs you. The game is landscape-only by design — portrait shows a rotate-device gate. Controls neutralize on blur, lost pointers and backgrounding, so nothing walks without you.",
    "จอยซ้ายเดิน คลัสเตอร์ขวามีโจมตี Arc Slash Quickstep และยา ปุ่มบริบทจะโผล่เมื่อมีอะไรใกล้ ๆ ต้องการคุณ เกมออกแบบให้เล่นแนวนอนเท่านั้น — แนวตั้งจะขึ้นหน้าบังคับหมุนจอ ตัวควบคุมจะปลดทันทีเมื่อหน้าต่างเสียโฟกัส นิ้วหลุด หรือสลับแอป เพื่อไม่ให้ตัวละครเดินเอง")}</p>
<h2>{pair("Settings", "ตั้งค่า")}</h2>
<p>{pair(
    "The Settings panel scales the HUD, toggles camera shake and damage flashes, and adjusts volume. Everything persists on this device.",
    "แผงตั้งค่าปรับขนาด HUD เปิดปิดกล้องสั่นและแฟลชดาเมจ และปรับความดัง ทุกค่าบันทึกไว้บนเครื่องนี้")}</p>
"""
    (OUT / "controls.html").write_text(page_shell(
        "controls", "Controls", ("Keyboard, mouse, touch and comfort settings.", "คีย์บอร์ด เมาส์ หน้าจอสัมผัส และการตั้งค่า"),
        controls_body, content_hash), encoding="utf-8")

    # ---------------------------------------------------------------- about
    about_body = f"""
<h2>{pair("What this is", "นี่คืออะไร")}</h2>
<p>{pair(
    "Aetherfield is an original browser and mobile action-RPG prototype — an honest, small frontier slice grown only as fast as evidence allows. It runs entirely in your browser (WebGPU with a WebGL2 fallback) against a tiny authoritative server. No downloads, no accounts, no real-money purchases — and paid randomness is excluded from the design outright.",
    "Aetherfield เป็นโปรโตไทป์เกมแอ็กชัน RPG บนเบราว์เซอร์และมือถือสายเลือดใหม่ — ชายขอบชิ้นเล็กที่ซื่อสัตย์และโตเท่าที่หลักฐานยืนยัน เล่นได้ทั้งหมดในเบราว์เซอร์ (WebGPU พร้อม WebGL2 สำรอง) กับเซิร์ฟเวอร์เล็ก ๆ ที่เป็นผู้ตัดสิน ไม่ต้องดาวน์โหลด ไม่มีบัญชี ไม่มีการซื้อด้วยเงินจริง — และกล่องสุ่มแบบจ่ายเงินถูกตัดออกจากดีไซน์เด็ดขาด")}</p>
<h2>{pair("Progress and resets", "ความคืบหน้าและการรีเซ็ต")}</h2>
<p>{pair(
    "Current playtests are session-scoped on purpose: your wallet, cosmetics and quest progress reset when the room restarts. The join screen says the same thing. Durable identity and inventories are the next milestone after the first player gates.",
    "การทดสอบช่วงนี้ตั้งใจให้อยู่แค่ช่วงเซสชัน: กระเป๋าเงิน คอสเมทิก และความคืบหน้าภารกิจจะรีเซ็ตเมื่อห้องรีสตาร์ท หน้า join ก็บอกแบบเดียวกัน ตัวตนถาวรและคลังของถาวรคือไมล์สโตนถัดไปหลังประตูผู้เล่นแรก")}</p>
<h2>{pair("Under the hood", "ใต้ฝาเครื่อง")}</h2>
{stat_table([pair("Piece", "ส่วนประกอบ"), pair("Choice", "เลือกใช้")], [
    [pair("Client", "ลูกค้า"), "Babylon.js + TypeScript (WebGPU / WebGL2)"],
    [pair("Server", "เซิร์ฟเวอร์"), "Rust + Tokio · authoritative 20 Hz tick"],
    [pair("Protocol", "โปรโตคอล"), "Binary v5 hot path + tagged-JSON cold path"],
    [pair("Content", "คอนเทนต์"), pair("a validated data bundle — this wiki renders from the same tables", "ชุดข้อมูลที่ตรวจสอบแล้ว — วิกินี้เรนเดอร์จากตารางเดียวกัน")],
])}
<h2>{pair("Languages", "ภาษา")}</h2>
<p>{pair(
    "The game and this wiki ship Thai and English together; the game picks your browser language by default, and the button in the header switches the wiki.",
    "เกมและวิกินี้ส่งภาษาไทยกับอังกฤษพร้อมกัน เกมเลือกตามภาษาเบราว์เซอร์เป็นค่าเริ่มต้น และปุ่มบนหัวเว็บสลับภาษาวิกิ")}</p>
"""
    (OUT / "about.html").write_text(page_shell(
        "about", "About", ("An original prototype, built in the open.", "โปรโตไทป์สายเลือดใหม่ สร้างอย่างเปิดเผย"),
        about_body, content_hash), encoding="utf-8")

    write_assets()
    print(f"wiki built at {OUT} (content {content_hash[:8]})")


def write_assets() -> None:
    (OUT / "style.css").write_text("""/* Aetherfield wiki — generated; palette mirrors the game HUD. */
:root {
	--ink: #f7f1df; --muted: #c9c8ba; --panel: rgba(17, 27, 34, 0.86);
	--line: rgba(222, 195, 134, 0.35); --gold: #e8c879; --green: #87c86a;
	--bg: #15252a; --bg2: #0f1a1f;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; font-family: Inter, "Segoe UI", system-ui, sans-serif; background: linear-gradient(180deg, var(--bg), var(--bg2)); color: var(--ink); line-height: 1.65; }
a { color: var(--gold); text-decoration: none; }
a:hover { text-decoration: underline; }
small.th-inline { color: var(--muted); font-weight: 400; }

.site-header { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding: 14px 22px; position: sticky; top: 0; background: rgba(15, 26, 31, 0.94); border-bottom: 1px solid var(--line); backdrop-filter: blur(8px); z-index: 5; }
.brand { font-weight: 800; letter-spacing: 0.12em; color: var(--gold); }
.brand small { color: var(--muted); font-weight: 600; letter-spacing: 0.28em; margin-left: 6px; }
.site-nav { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; }
.site-nav a { padding: 6px 10px; border-radius: 8px; color: var(--muted); font-size: 14px; }
.site-nav a:hover { color: var(--ink); text-decoration: none; background: rgba(232, 200, 121, 0.08); }
.site-nav a.active { color: var(--gold); background: rgba(232, 200, 121, 0.12); }
#lang-toggle { border: 1px solid var(--line); background: transparent; color: var(--ink); border-radius: 8px; padding: 6px 12px; cursor: pointer; font: inherit; }
#lang-toggle:hover { background: rgba(232, 200, 121, 0.1); }

main { max-width: 940px; margin: 0 auto; padding: 20px 22px 60px; }
.hero { padding: 42px 0 10px; }
.kicker { color: var(--gold); letter-spacing: 0.3em; font-size: 11px; font-weight: 800; margin: 0 0 6px; }
h1 { font-size: 34px; margin: 0 0 10px; }
.lede { font-size: 17px; color: var(--muted); margin: 0 0 8px; max-width: 62ch; }
h2 { margin-top: 40px; border-bottom: 1px solid var(--line); padding-bottom: 6px; }
h3 { margin: 0 0 6px; }
.note { color: var(--muted); font-size: 14px; border-left: 3px solid var(--gold); padding-left: 12px; }
blockquote { margin: 14px 0; padding: 10px 16px; border-left: 3px solid var(--green); background: rgba(135, 200, 106, 0.06); border-radius: 0 10px 10px 0; font-style: italic; }
.steps li { margin: 8px 0; }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 18px 0; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; box-shadow: 0 8px 22px rgba(6, 12, 15, 0.35); }
.card p { margin: 0; color: var(--muted); font-size: 14px; }
.card.link-card { color: inherit; transition: transform 0.12s ease, border-color 0.12s ease; }
.card.link-card:hover { text-decoration: none; transform: translateY(-2px); border-color: var(--gold); }
.card.link-card h3 { color: var(--gold); }

.table-wrap { overflow-x: auto; margin: 14px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid rgba(222, 195, 134, 0.16); vertical-align: top; }
th { color: var(--gold); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }
tr:hover td { background: rgba(232, 200, 121, 0.05); }

.map-figure { margin: 18px 0; }
.map-figure svg { max-width: 460px; width: 100%; height: auto; display: block; }
.map-label { font-size: 10.5px; fill: var(--ink); paint-order: stroke; stroke: #14211b; stroke-width: 3px; }
.map-figure figcaption { color: var(--muted); font-size: 13px; margin-top: 6px; }

footer { border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; max-width: 940px; margin: 0 auto; padding: 18px 22px 40px; }

/* Language pairs: the toggle flips body[data-lang]. */
body[data-lang="en"] span.th { display: none; }
body[data-lang="th"] span.en { display: none; }

@media (max-width: 640px) {
	h1 { font-size: 26px; }
	.site-header { padding: 10px 14px; gap: 10px; }
	main { padding: 14px 16px 50px; }
}
""", encoding="utf-8")

    (OUT / "app.js").write_text("""// Language toggle (D-06): both languages ship in the page; this flips which renders.
const KEY = "aetherfield_wiki_lang";
const apply = (lang) => {
	document.body.dataset.lang = lang;
	const button = document.getElementById("lang-toggle");
	if (button) button.textContent = lang === "en" ? "ไทย" : "EN";
};
const saved = localStorage.getItem(KEY);
if (saved === "th" || saved === "en") apply(saved);
document.getElementById("lang-toggle")?.addEventListener("click", () => {
	const next = document.body.dataset.lang === "en" ? "th" : "en";
	localStorage.setItem(KEY, next);
	apply(next);
});
""", encoding="utf-8")


if __name__ == "__main__":
    build()
