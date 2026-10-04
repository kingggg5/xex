<script lang="ts">
	import type { ShopSnapshot, UiCommands } from "./types";
	let { model, commands }: { model: ShopSnapshot; commands: UiCommands } = $props();
	const th = $derived(model.language === "th");
	const box = $derived(model.catalog.boxes.find((candidate) => candidate.id === "meadow_box") ?? model.catalog.boxes[0] ?? null);
	const totalWeight = $derived(box?.odds.reduce((sum, outcome) => sum + outcome.weight, 0) ?? 0);
	const glyph = (currency: string) => currency === "coin" ? "✦" : "◉";
	const percent = (weight: number) => `${Math.round((totalWeight > 0 ? weight / totalWeight : 0) * 1000) / 10}%`;
	const cosmetic = (id: string) => model.catalog.entries.find((entry) => entry.id === id);
</script>

<div class="shop-view" data-ui-component="shop">
	<div class="wallet-bar" aria-label={th ? "เงินในเกม" : "In-game wallet"}>
		<span class="wallet-badge wallet-gold"><span class="wallet-icon" aria-hidden="true">◉</span><span>{th ? "ทอง" : "Gold"}</span><b>{model.wallet.gold}</b></span>
		<span class="wallet-badge wallet-coin"><span class="wallet-icon" aria-hidden="true">✦</span><span>{th ? "เหรียญ" : "Coin"}</span><b>{model.wallet.coin}</b></span>
	</div>
	{#if !model.online}<p class="econ-note">{th ? "ขาดการเชื่อมต่อ · แสดงข้อมูลล่าสุด · เชื่อมต่อเพื่อทำรายการ" : "Offline · last received data · reconnect before buying"}</p>{/if}
	{#if model.status === "loading"}<p role="status">{th ? "กำลังโหลดร้านค้า…" : "Loading store…"}</p>
	{:else if model.status === "unavailable"}<p role="status">{th ? "ไม่สามารถโหลดข้อมูลร้านค้าได้" : "Store content could not be loaded."}</p>
	{:else}
		<h3>{th ? "ร้านค้า" : "Store"}</h3>
		{#if model.catalog.entries.length === 0}<p class="econ-note">{th ? "ร้านค้ากำลังเติมสินค้า" : "The store is restocking."}</p>{/if}
		<div class="store-list">
			{#each model.catalog.entries as entry (entry.id)}
				{@const owned = entry.slot !== "item" && model.wallet.ownedCosmetics.includes(entry.id)}
				{@const equipped = model.wallet.skin === entry.id || model.wallet.pet === entry.id}
				{@const insufficient = model.wallet[entry.currency] < entry.price}
				<div class="store-entry">
					<div class="store-row">
						{#if entry.color}<span class="skin-swatch" style:--swatch={entry.color} aria-hidden="true"></span>{/if}
						<div class="store-label"><b>{entry.label}</b><small>{entry.slot === "item" ? (th ? "ไอเท็ม" : "Item") : entry.slot === "skin" ? (th ? "ชุด" : "Outfit") : (th ? "สัตว์เลี้ยง" : "Pet")}</small></div>
						<span class="store-price">{entry.price} {glyph(entry.currency)}</span>
						<button type="button" class="store-action" disabled={!model.online || equipped || (!owned && insufficient)} onclick={() => owned && entry.slot !== "item" ? commands.equip(entry.slot, entry.id) : commands.buy(entry.id)}>
							{equipped ? (th ? "สวมอยู่" : "Equipped") : owned ? (th ? "สวมใส่" : "Equip") : (th ? "ซื้อ" : "Buy")}
						</button>
					</div>
					{#if !owned && insufficient}<p class="store-hint">{th ? `ต้องการ ${entry.price} ${glyph(entry.currency)} · มี ${model.wallet[entry.currency]}` : `Need ${entry.price} ${glyph(entry.currency)} · you have ${model.wallet[entry.currency]}`}</p>{/if}
				</div>
			{/each}
		</div>
		<h3>{th ? "กล่องทุ่งหญ้า" : "Meadow Box"}</h3>
		{#if box}
			{@const inBag = model.wallet.bagCounts[box.id] ?? 0}
			<section class="box-card" aria-label={box.label}>
				<div class="box-head"><div class="store-label"><b>{box.label}</b><span class="box-bag">{th ? `ในกระเป๋า: ${inBag}` : `In bag: ${inBag}`}</span></div><span class="store-price">{box.price} {glyph(box.currency)}</span></div>
				<div class="box-actions">
					<button type="button" class="store-action" disabled={!model.online || model.wallet[box.currency] < box.price} onclick={() => commands.buy(box.id)}>{th ? "ซื้อ" : "Buy"}</button>
					<button type="button" class="store-action" disabled={!model.online || inBag <= 0} onclick={() => commands.openBox(box.id)}>{th ? "เปิด" : "Open"}{inBag > 0 ? ` (${inBag})` : ""}</button>
					{#if inBag <= 0}<p class="econ-note">{th ? "ไม่มีกล่องในกระเป๋า โปรดซื้อก่อน" : "No box in your bag — buy one first."}</p>{/if}
				</div>
				{#if box.odds.length > 0}
					<table class="odds-table"><caption>{th ? "เนื้อหา · อัตราได้รางวัลตรงตามจริง" : "Contents · exact odds"}</caption><thead><tr><th scope="col">{th ? "รางวัล" : "Reward"}</th><th scope="col">{th ? "จำนวน" : "Amount"}</th><th scope="col">{th ? "โอกาส" : "Chance"}</th></tr></thead>
						<tbody>{#each box.odds as outcome, index (`${outcome.id}-${index}`)}<tr><td>{outcome.label}</td><td>×{outcome.amount}</td><td class="num">{percent(outcome.weight)}</td></tr>{/each}</tbody>
					</table>
				{:else}<p class="econ-note">{th ? "ยังไม่มีตารางอัตรารางวัลของกล่องนี้" : "The odds table is unavailable."}</p>{/if}
				<p class="odds-note">{th ? "ระบุอัตราก่อนเปิดกล่อง ซื้อด้วยทองในเกมเท่านั้น ไม่มีการใช้เงินจริง" : "Odds are published before opening. Boxes use in-game gold only; no real money is involved."}</p>
			</section>
		{:else}<p class="econ-note">{th ? "ขณะนี้ยังไม่มีกล่องให้เปิด" : "No box is available right now."}</p>{/if}
		<h3>{th ? "คอสมิกที่เป็นเจ้าของ" : "Owned cosmetics"}</h3>
		{#if model.wallet.ownedCosmetics.length === 0}<p class="econ-note">{th ? "คอสมิกที่คุณเป็นเจ้าของจะแสดงที่นี่" : "Cosmetics you own will appear here."}</p>
		{:else}<div class="cosmetic-strip">{#each model.wallet.ownedCosmetics as id (id)}
			{@const entry = cosmetic(id)}
			{@const equipped = model.wallet.skin === id || model.wallet.pet === id}
			<div class="cosmetic-chip" class:is-equipped={equipped}><b>{entry?.label ?? id.replaceAll("_", " ")}</b><button class="store-action" type="button" disabled={!model.online || equipped} onclick={() => commands.equip(entry?.slot === "pet" || id.startsWith("pet") ? "pet" : "skin", id)}>{equipped ? (th ? "สวมอยู่" : "Equipped") : (th ? "สวมใส่" : "Equip")}</button></div>
		{/each}</div>{/if}
	{/if}
</div>

<style>
	.shop-view { display: grid; gap: 14px; }
	h3 { margin: 8px 0 0; color: #f3ddb0; font-size: 17px; }
	.store-row { min-height: 56px; gap: 12px; flex-wrap: wrap; }
	.store-row .store-label b, .box-head .store-label b, .cosmetic-chip b { font-size: 14px; }
	.store-row .store-label small, .box-bag, .econ-note, .odds-note, .store-hint { font-size: 12px; line-height: 1.5; }
	.store-hint { margin: 3px 0 0; }
	.store-price { font-size: 14px; }
	button.store-action { min-height: 44px; min-width: 84px; font-size: 14px; }
	button:focus-visible { outline: 3px solid #f3d993; outline-offset: 3px; }
	.odds-table { font-size: 13px; }
	.odds-table caption, .odds-table th { font-size: 12px; letter-spacing: normal; }
	.odds-table th, .odds-table td { padding: 8px 4px; }
	@media (max-width: 767px) { .store-row .store-label b, button.store-action { font-size: 16px; } .store-row .store-label { flex-basis: calc(100% - 26px); } .store-row .store-action { margin-left: auto; } }
</style>
