<!--
THESIS: A realm's channel register becomes the threshold to its measured startup journey.
OWN-WORLD: Existing Xexoria navy, antique gold, Marcellus/Trirong and geometric astral ornament.
STORY: Compare actual occupancy, confirm a channel, then follow real startup checkpoints.
FIRST VIEWPORT: Bounded ornamental register, world and logo above, channel rows central, entry below.
FORM: Precisely scoped extension of the incumbent login world; no new visual identity.
-->
<script lang="ts">
	import '../assets/branding/login-v1/fonts/fonts-v2.css';
	import logo from '../assets/branding/login-v1/xexoria-logo.png';
	import Ornament from './Ornament.svelte';
	import { LOBBY_COPY } from './copy';
	import { chosenAvailable, displayChannel, displayLatency, transferText } from './presentation.mjs';
	import type { ConnectionLobbyView } from './types';
	let { model, refresh, select, confirm, retry }: {
		model: ConnectionLobbyView;
		refresh: () => void;
		select: (channel: number | null) => void;
		confirm: () => void;
		retry: () => void;
	} = $props();
	const copy = $derived(LOBBY_COPY[model.language]);
	const busy = $derived(model.loadingRooms || model.applying);
	const canEnter = $derived(chosenAvailable(model) && !busy);
	const activePhase = $derived([...model.recent].reverse().find(phase => phase.state === 'active') ?? model.phases.find(phase => phase.state === 'active'));
	const transfer = $derived(activePhase ? transferText(activePhase) : null);
	const allFull = $derived(model.rooms.length > 0 && model.rooms.every(room => room.players >= room.capacity) && !model.autoAvailable);
	function stateText(state: string) {
		return state === 'complete' ? copy.complete : state === 'active' ? copy.active : state === 'error' ? copy.failed : copy.waiting;
	}
</script>

<div class="connection-lobby" lang={model.language}>
	<div class="lobby-backdrop" aria-hidden="true"></div>
	<div class="lobby-panel" class:loading={model.mode === 'loading'} class:channels={model.mode === 'channels'} role="dialog" aria-modal="true" aria-labelledby="lobby-title" aria-describedby="lobby-subtitle" tabindex="-1" data-lobby-focus>
		<Ornament />
		<header class="lobby-header">
			<div class="lobby-heading">
				<p class="world-name"><span class="world-diamond" aria-hidden="true"></span>{model.worldName}</p>
				<h1 id="lobby-title">{model.mode === 'channels' ? copy.title : model.error ? copy.loadingError : copy.loadingTitle}</h1>
				<p id="lobby-subtitle">{model.mode === 'channels' ? copy.subtitle : copy.loadingSubtitle}</p>
			</div>
			<img class="lobby-logo" src={logo} alt="Xexoria" width="220" height="74" />
		</header>
		{#if model.mode === 'channels'}
			<div class="channel-toolbar">
				<p><span class="signal-icon" aria-hidden="true"><i></i><i></i><i></i></span>{copy.latency}: <strong>{displayLatency(model.latencyMs)}</strong><small>{copy.latencyNote}</small></p>
				<button class="quiet-button refresh-button" type="button" onclick={refresh} disabled={busy} aria-label={copy.refresh}>
					<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M19.5 11a7.5 7.5 0 0 0-13-4.5L4 9m16 6-2.5 2.5A7.5 7.5 0 0 1 4.5 13" /></svg>
					{model.loadingRooms ? copy.refreshing : copy.refresh}
				</button>
			</div>
			<div class="channel-list-shell" aria-busy={model.loadingRooms}>
				<div class="channel-columns" aria-hidden="true"><span>{copy.channel}</span><span>{copy.population}</span><span>{copy.latency}</span></div>
				<div class="channel-list" role="group" aria-label={copy.title}>
					{#if model.loadingRooms && !model.rooms.length}
						<div class="channel-empty" role="status"><span class="waiting-star" aria-hidden="true">✧</span><p>{copy.fetching}</p></div>
					{:else if !model.rooms.length}
						<div class="channel-empty"><span class="empty-star" aria-hidden="true">◇</span><p>{model.autoAvailable ? copy.listUnavailable : copy.empty}</p><small>{model.autoAvailable ? copy.autoFallback : copy.emptyDetail}</small></div>
					{:else}
						{#each model.rooms as room (room.channel)}
							{@const full = room.players >= room.capacity}
							{@const selected = model.hasSelection && model.selected === room.channel}
							<button type="button" class="channel-row" class:selected class:full disabled={full || busy} aria-pressed={selected}
								aria-label={`${copy.channel} ${displayChannel(room.channel)}, ${room.name}, ${room.players} / ${room.capacity}, ${full ? copy.full : copy.available}, ${copy.latency} ${displayLatency(model.latencyMs)}`}
								onclick={() => select(room.channel)} data-channel={room.channel}>
								<span class="channel-identity"><span class="channel-number">{displayChannel(room.channel)}</span><span class="channel-name">{room.name || model.worldName}<small>{full ? copy.full : selected ? copy.selected : copy.available}</small></span></span>
								<span class="channel-population"><span>{room.players} <em>/ {room.capacity}</em></span><span class="occupancy-track" aria-hidden="true"><span style:width={`${Math.min(100, room.players / room.capacity * 100)}%`}></span></span></span>
								<span class="channel-latency">{displayLatency(model.latencyMs)}<span class="selection-gem" aria-hidden="true">{selected ? '◆' : '◇'}</span></span>
							</button>
						{/each}
					{/if}
				</div>
			</div>
			{#if model.autoAvailable}
				<button class="auto-choice" class:selected={model.hasSelection && model.selected === null} type="button" disabled={busy} aria-pressed={model.hasSelection && model.selected === null} onclick={() => select(null)} data-channel="auto">
					<span class="auto-gem" aria-hidden="true">{model.hasSelection && model.selected === null ? '◆' : '◇'}</span><span><strong>{copy.auto}</strong><small>{copy.autoNote}</small></span>
				</button>
			{/if}
			<div class="channel-feedback" aria-live="polite" aria-atomic="true">
				{#if model.error}<p class="lobby-error" role="alert">{model.error}</p>{:else if allFull}<p>{copy.allFull}</p>{/if}
				{#each model.warnings as warning}<p>{warning}</p>{/each}
			</div>
			<footer class="channel-footer">
				<p>{copy.world}<strong>{model.worldName}</strong></p>
				<button class="entry-button" type="button" onclick={confirm} disabled={!canEnter} data-lobby-confirm>
					<span>{model.applying ? copy.applying : copy.confirm}</span><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12h15m-6-6 6 6-6 6" /></svg>
				</button>
			</footer>
		{:else if model.mode === 'loading'}
			<div class="loading-layout">
				<div class="journey-progress">
					<div class="journey-seal" class:interrupted={!!model.error} aria-hidden="true"><svg viewBox="0 0 100 100" fill="none"><path class="seal-outer" d="M50 3 97 50 50 97 3 50ZM50 17 83 50 50 83 17 50Z"/><path d="M50 28 72 50 50 72 28 50ZM50 3v25M97 50H72M50 97V72M3 50h25"/><path class="seal-heart" d="m50 39 11 11-11 11-11-11Z"/></svg></div>
					<p class="phase-count"><strong>{model.completed}<span>/ {model.total}</span></strong>{copy.phaseCount}</p>
					<div class="phase-meter" role="progressbar" aria-label={copy.checkpoints} aria-valuemin="0" aria-valuemax={model.total} aria-valuenow={model.completed} aria-valuetext={`${model.completed} / ${model.total} ${copy.phaseCount}`}>
						{#each model.phases as phase}<span class:complete={phase.state === 'complete'} class:active={phase.state === 'active'} class:failed={phase.state === 'error'}></span>{/each}
					</div>
					<div class="current-operation" aria-live="polite" aria-atomic="true">
						<p>{model.error ? copy.paused : activePhase ? copy.phases[activePhase.id] : copy.preparing}</p>
						{#if activePhase?.resource}<small class="resource-name">{activePhase.resource}</small>{/if}
						{#if transfer && activePhase}
							<progress class="resource-progress" value={activePhase.loaded} max={activePhase.total} aria-label={`${copy.phases[activePhase.id]} ${activePhase.resource}`}></progress><small class="transfer-count">{transfer}</small>
						{:else if !model.error}
							<progress class="resource-progress" aria-label={activePhase ? copy.phases[activePhase.id] : copy.preparing}></progress>
						{/if}
					</div>
				</div>
				<div class="loading-details">
					<h2>{copy.checkpoints}</h2>
					<ol class="phase-list">
						{#each model.phases as phase}
							<li class:complete={phase.state === 'complete'} class:active={phase.state === 'active'} class:failed={phase.state === 'error'}>
								<span class="phase-symbol" aria-hidden="true">{phase.state === 'complete' ? '✓' : phase.state === 'error' ? '!' : '◇'}</span><span>{copy.phases[phase.id]}</span><small>{stateText(phase.state)}</small>
							</li>
						{/each}
					</ol>
				</div>
			</div>
			{#if model.error}
				<div class="loading-error"><p class="lobby-error" role="alert">{model.error}</p>{#if model.canRetry}<button class="entry-button" type="button" onclick={retry} disabled={model.retrying} data-lobby-retry>{model.retrying ? copy.retrying : copy.retry}</button>{/if}</div>
			{/if}
			{#if model.recent.length}
				<div class="recent-updates"><h2>{copy.updates}</h2><ul>{#each model.recent.slice().reverse() as event}<li><span class:failed={event.state === 'error'}>{copy.phases[event.id]}</span><small>{event.resource || stateText(event.state)}{transferText(event) ? ` · ${transferText(event)}` : ''}</small></li>{/each}</ul></div>
			{/if}
		{/if}
	</div>
</div>

<style>
	.connection-lobby { --gold: #d5bd83; --text: #f7eddb; --muted: #b9c8dc; --blue: #718fc0; position: absolute; inset: 0; z-index: 80; display: grid; place-items: center; padding: max(24px, env(safe-area-inset-top)) max(24px, env(safe-area-inset-right)) max(24px, env(safe-area-inset-bottom)) max(24px, env(safe-area-inset-left)); overflow: auto; overscroll-behavior: contain; color: var(--text); font: 400 14px/1.5 'Marcellus', 'Trirong', Georgia, serif; font-synthesis: none; isolation: isolate; }
	.connection-lobby, .connection-lobby :global(*) { box-sizing: border-box; }
	.lobby-backdrop { position: absolute; inset: 0; z-index: -1; background: linear-gradient(180deg, rgba(3, 9, 24, .8), rgba(7, 15, 33, .91)), url('../assets/branding/login-portal-v1/astral-gate.webp') center / cover no-repeat; }
	.lobby-panel { position: relative; width: min(860px, 100%); max-height: calc(100dvh - 48px); padding: 39px 40px 30px; background: #0b152b; box-shadow: 0 24px 70px rgba(0, 3, 12, .62); display: flex; flex-direction: column; min-height: 0; }
	.lobby-panel:focus { outline: none; }
	.lobby-panel:focus-visible { outline: 2px solid #f7deb0; outline-offset: 7px; }
	.lobby-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding-bottom: 24px; border-bottom: 1px solid #35405a; }
	.world-name { margin: 0 0 8px; color: var(--gold); font-size: 13px; letter-spacing: .035em; display: flex; gap: 9px; align-items: center; }
	.world-diamond { width: 6px; height: 6px; border: 1px solid var(--gold); transform: rotate(45deg); flex-shrink: 0; }
	h1 { font: 400 30px/1.4 'Marcellus', 'Trirong', Georgia, serif; margin: 0; color: #fff0d3; text-wrap: balance; }
	#lobby-subtitle { margin: 6px 0 0; color: var(--muted); font-size: 14px; }
	.lobby-logo { width: 202px; height: auto; flex-shrink: 0; object-fit: contain; }
	.channel-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 17px 0 12px; flex-shrink: 0; }
	.channel-toolbar p { margin: 0; font-size: 12px; color: #d6e1ef; }
	.channel-toolbar p strong { color: #f3ddab; font-weight: 400; margin-left: 4px; font-variant-numeric: tabular-nums; }
	.channel-toolbar small { display: block; margin: 3px 0 0 21px; color: var(--muted); font-size: 11px; }
	.signal-icon { display: inline-flex; align-items: flex-end; gap: 2px; margin-right: 7px; height: 12px; }
	.signal-icon i { width: 3px; background: #b6caa2; height: 4px; }.signal-icon i:nth-child(2) { height: 8px; }.signal-icon i:nth-child(3) { height: 12px; }
	button { font: inherit; color: inherit; cursor: pointer; }
	button:disabled { cursor: default; }
	button:focus-visible { outline: 2px solid #f7deb0; outline-offset: 3px; }
	.quiet-button { border: 1px solid #58637a; padding: 9px 12px; min-height: 44px; background: #121f36; color: #e3d5b7; display: flex; align-items: center; justify-content: center; gap: 8px; }
	.quiet-button:hover:enabled { background: #23334f; border-color: #c5ac74; }
	.quiet-button:disabled { color: #8e9ab0; }
	.quiet-button svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 1.4; }
	.channel-list-shell { min-height: 100px; display: flex; flex-direction: column; overflow: hidden; border: 1px solid #3b4760; }
	.channel-columns { display: grid; grid-template-columns: minmax(0, 1fr) 150px 120px; gap: 20px; padding: 10px 18px; background: #111e35; color: var(--gold); font-size: 12px; flex-shrink: 0; }
	.channel-columns span:last-child { text-align: right; padding-right: 21px; }
	.channel-list { overflow-y: auto; min-height: 90px; max-height: 306px; scrollbar-width: thin; scrollbar-color: #6e644e #0b152b; overscroll-behavior: contain; touch-action: pan-y; }
	.channel-row { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) 150px 120px; gap: 20px; align-items: center; text-align: left; min-height: 66px; padding: 11px 18px; border: 0; border-bottom: 1px solid #293750; background: transparent; transition: background-color 140ms ease-out; }
	.channel-row:last-child { border-bottom: 0; }
	.channel-row:hover:enabled { background: #1d2d47; }
	.channel-row.selected { background: #243653; box-shadow: inset 0 0 0 1px #b89d65; }
	.channel-row.full { background: #101a2d; color: #aab7ca; }
	.channel-row:disabled:not(.full) { cursor: wait; }
	.channel-identity { display: flex; gap: 17px; align-items: center; min-width: 0; }
	.channel-number { color: #ebd39e; font-size: 26px; min-width: 31px; font-variant-numeric: tabular-nums; line-height: 1; }
	.full .channel-number { color: #8999b2; }
	.channel-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #f2e9d8; font-size: 15px; }
	.channel-name small { display: block; font-size: 10px; color: #b6caa2; margin-top: 1px; }
	.full .channel-name small { color: #e0a58b; }
	.selected .channel-name small { color: #ead09b; }
	.channel-population { display: flex; flex-direction: column; gap: 5px; font-size: 15px; font-variant-numeric: tabular-nums; }
	.channel-population em { font-size: 12px; color: var(--muted); font-style: normal; }
	.occupancy-track { width: 93px; height: 3px; background: #35425a; overflow: hidden; }
	.occupancy-track span { height: 100%; display: block; background: #95b4bd; }
	.full .occupancy-track span { background: #bd8a74; }
	.channel-latency { display: flex; align-items: center; justify-content: flex-end; gap: 14px; color: #c5d2e6; font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
	.selection-gem { font-size: 17px; color: #8190a9; }
	.selected .selection-gem { color: #f2d38c; }
	.channel-empty { display: grid; justify-items: center; align-content: center; min-height: 150px; padding: 20px; text-align: center; }
	.channel-empty p { margin: 7px 0 4px; font-size: 16px; }
	.channel-empty small { color: var(--muted); font-size: 12px; }
	.empty-star, .waiting-star { font-size: 34px; color: var(--gold); line-height: 1; }
	.waiting-star { animation: waiting 2.2s linear infinite; }
	.auto-choice { display: flex; gap: 12px; align-items: center; background: transparent; text-align: left; border: 1px solid #3b4760; padding: 11px 16px; margin-top: 10px; min-height: 58px; flex-shrink: 0; }
	.auto-choice.selected { background: #1c2a42; border-color: #b89d65; }
	.auto-choice:hover:enabled { background: #1d2d47; }
	.auto-gem { color: var(--gold); font-size: 21px; }
	.auto-choice strong { font-size: 14px; font-weight: 400; }
	.auto-choice small { display: block; font-size: 11px; color: var(--muted); }
	.channel-feedback { font-size: 12px; color: #e2c991; flex-shrink: 0; }
	.channel-feedback p { margin: 9px 0 0; }
	.lobby-error { color: #f5b79e; font-size: 13px; line-height: 1.6; }
	.channel-footer { margin-top: 21px; display: flex; justify-content: space-between; align-items: center; gap: 20px; flex-shrink: 0; }
	.channel-footer p { margin: 0; color: var(--muted); font-size: 11px; }
	.channel-footer strong { display: block; font-weight: 400; color: #d3dded; font-size: 13px; }
	.entry-button { position: relative; min-height: 49px; min-width: 230px; padding: 11px 22px; display: flex; align-items: center; justify-content: center; gap: 18px; border: 1px solid #e5ca8d; background: #c9ad71; color: #151c2b; font: 400 17px/1.4 'Marcellus', 'Trirong', Georgia, serif; box-shadow: inset 0 0 0 3px #c9ad71, inset 0 0 0 4px #705d35; }
	.entry-button:hover:enabled { background: #e1c58a; box-shadow: inset 0 0 0 3px #e1c58a, inset 0 0 0 4px #705d35; }
	.entry-button:disabled { border-color: #566178; color: #99a5b8; background: #24314a; box-shadow: inset 0 0 0 3px #24314a, inset 0 0 0 4px #47546b; }
	.entry-button svg { width: 21px; height: 21px; stroke: currentColor; stroke-width: 1.2; flex-shrink: 0; }
	.loading-layout { display: grid; grid-template-columns: 240px 1fr; gap: 34px; padding-top: 30px; min-height: 0; }
	.journey-progress { text-align: center; padding: 8px 6px 0; }
	.journey-seal { width: 104px; margin: 0 auto 15px; }
	.journey-seal svg { display: block; width: 100%; height: auto; stroke: #ba9b5f; stroke-width: .8; }
	.seal-outer { stroke: #718caf; }.seal-heart { fill: #dfc184; stroke: #f4d69a; }
	.journey-seal:not(.interrupted) .seal-heart { animation: seal-light 2.1s ease-in-out infinite alternate; }
	.phase-count { margin: 0; color: #c4d0e1; font-size: 12px; }
	.phase-count strong { display: block; color: #f7dfab; font: 400 43px/1.15 'Marcellus', Georgia, serif; font-variant-numeric: tabular-nums; margin-bottom: 5px; }
	.phase-count strong span { color: #99abc5; font-size: 24px; margin-left: 7px; }
	.phase-meter { display: flex; gap: 4px; margin: 21px 0 15px; }
	.phase-meter span { flex: 1; height: 5px; background: #33405a; }.phase-meter .complete { background: #ceb37a; }.phase-meter .active { background: #859ec2; }.phase-meter .failed { background: #da9d86; }
	.current-operation p { color: #ead7ae; font-size: 14px; margin: 0 0 5px; }
	.current-operation small { display: block; color: var(--muted); font-size: 10px; }
	.resource-name { overflow-wrap: anywhere; max-width: 35ch; margin: 0 auto; }
	.resource-progress { display: block; width: 100%; height: 3px; margin: 14px 0 7px; border: 0; appearance: none; background: #2e3b54; accent-color: #bfa875; }
	.resource-progress::-webkit-progress-bar { background: #2e3b54; }.resource-progress::-webkit-progress-value { background: #bfa875; }.resource-progress::-moz-progress-bar { background: #bfa875; }
	.resource-progress:indeterminate { background: #2e3b54 linear-gradient(90deg, transparent, #9cbaeb, transparent) 0 0 / 35% 100% no-repeat; animation: transfer-wait 2s linear infinite; }
	.resource-progress:indeterminate::-webkit-progress-bar { background: transparent; }
	.transfer-count { font-variant-numeric: tabular-nums; }
	h2 { font-weight: 400; font-size: 13px; color: #d5bd83; margin: 0 0 10px; }
	.phase-list { list-style: none; padding: 0; margin: 0; }
	.phase-list li { display: grid; grid-template-columns: 19px minmax(0, 1fr) auto; gap: 10px; align-items: center; min-height: 38px; border-bottom: 1px solid #26344c; color: #a6b7d0; font-size: 13px; }
	.phase-list li:last-child { border: 0; }
	.phase-list small { color: #a6b7d0; font-size: 10px; }
	.phase-list .complete { color: #eddfc0; }.phase-list .complete .phase-symbol { color: #b9cea5; }.phase-list .complete small { color: #b9cea5; }
	.phase-list .active { color: #fff0cf; }.phase-list .active .phase-symbol { color: #f0d38f; }.phase-list .active small { color: #edcf92; }
	.phase-list .failed, .phase-list .failed small { color: #f5b79e; }
	.phase-symbol { text-align: center; font-size: 15px; }
	.recent-updates { margin-top: 25px; padding-top: 16px; border-top: 1px solid #35405a; min-height: 0; overflow: auto; scrollbar-width: thin; }
	.recent-updates h2 { font-size: 11px; margin: 0 0 7px; }
	.recent-updates ul { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 25px; list-style: none; padding: 0; margin: 0; }
	.recent-updates li { display: flex; flex-wrap: wrap; gap: 3px 8px; align-items: baseline; font-size: 10px; min-width: 0; }
	.recent-updates li > span { color: #d2dfef; }.recent-updates small { color: var(--muted); font-size: 10px; overflow-wrap: anywhere; }.recent-updates .failed { color: #f5b79e; }
	.loading-error { margin-top: 20px; display: flex; justify-content: space-between; align-items: center; gap: 20px; flex-shrink: 0; }.loading-error p { margin: 0; }.loading-error .entry-button { min-width: 170px; font-size: 14px; }
	@keyframes waiting { to { transform: rotate(180deg); } }
	@keyframes seal-light { from { opacity: .45; } to { opacity: 1; } }
	@keyframes transfer-wait { to { background-position: 150% 0; } }
	@media (max-width: 640px) {
		.connection-lobby { padding: 16px; }.lobby-panel { padding: 29px 20px 22px; max-height: calc(100dvh - 32px); }.lobby-header { padding-bottom: 16px; gap: 10px; }.lobby-logo { width: 105px; }h1 { font-size: 23px; }.world-name { font-size: 11px; }#lobby-subtitle { font-size: 12px; }
		.channel-columns, .channel-row { grid-template-columns: minmax(0, 1fr) 82px 65px; gap: 10px; padding-left: 11px; padding-right: 11px; }.channel-columns { font-size: 10px; }.channel-columns span:last-child { padding: 0; }.channel-identity { gap: 9px; }.channel-number { font-size: 22px; min-width: 25px; }.channel-name { font-size: 12px; }.channel-population { font-size: 12px; }.channel-population em { font-size: 10px; }.occupancy-track { width: 66px; }.channel-latency { font-size: 10px; gap: 6px; }.selection-gem { font-size: 13px; }.channel-toolbar p { font-size: 10px; }.channel-toolbar small { font-size: 9px; max-width: 25ch; }.quiet-button { font-size: 12px; padding: 8px; }.channel-footer { gap: 10px; }.entry-button { min-width: 165px; font-size: 15px; gap: 8px; }.channel-footer p { font-size: 10px; }.channel-footer strong { font-size: 11px; }.channel-list { max-height: 270px; }
		.loading-layout { grid-template-columns: 1fr; gap: 18px; padding-top: 17px; overflow: auto; }.journey-progress { display: grid; grid-template-columns: 72px 1fr; column-gap: 15px; padding: 0; text-align: left; }.journey-seal { width: 65px; margin: 0; grid-row: 1 / 4; align-self: center; }.phase-count { font-size: 10px; }.phase-count strong { font-size: 30px; display: inline; margin-right: 7px; }.phase-count strong span { font-size: 18px; margin-left: 4px; }.phase-meter { margin: 10px 0; }.current-operation p { font-size: 12px; }.resource-progress { margin-top: 7px; }.resource-name { margin: 0; }.phase-list li { min-height: 34px; font-size: 12px; }.recent-updates { margin-top: 16px; padding-top: 12px; }.recent-updates ul { grid-template-columns: 1fr; }.loading-error { flex-direction: column; align-items: stretch; gap: 12px; }
	}
	@media (max-height: 620px) and (min-width: 640px) and (orientation: landscape) {
		.connection-lobby { padding: max(12px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right)) max(12px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left)); }.lobby-panel { max-height: calc(100dvh - 24px); padding: 21px 27px 18px; width: min(860px, 100%); }.lobby-header { padding-bottom: 9px; gap: 15px; }.lobby-logo { width: 147px; }h1 { font-size: 22px; }.world-name { font-size: 10px; margin-bottom: 3px; }#lobby-subtitle { margin-top: 2px; font-size: 11px; }.channel-toolbar { padding: 9px 0 7px; }.channel-toolbar small { display: inline; margin-left: 9px; font-size: 9px; }.channel-toolbar p { font-size: 10px; }.quiet-button { min-height: 34px; padding: 6px 9px; font-size: 11px; }.channel-list-shell { min-height: 83px; }.channel-columns { padding-top: 6px; padding-bottom: 6px; font-size: 10px; }.channel-row { min-height: 47px; padding-top: 5px; padding-bottom: 5px; }.channel-number { font-size: 22px; }.channel-name { font-size: 12px; }.channel-name small { font-size: 9px; }.channel-population { font-size: 12px; gap: 3px; }.channel-latency { font-size: 10px; }.auto-choice { min-height: 44px; margin-top: 7px; padding: 6px 12px; }.auto-choice strong { font-size: 12px; }.auto-choice small { font-size: 9px; }.channel-footer { margin-top: 10px; }.entry-button { min-height: 40px; font-size: 14px; min-width: 220px; }.channel-footer p { font-size: 9px; }.channel-footer strong { font-size: 11px; }.channel-feedback { font-size: 10px; }.channel-feedback p { margin-top: 6px; }.channel-list { max-height: 180px; }
		.loading-layout { grid-template-columns: 185px 1fr; gap: 28px; padding-top: 14px; }.journey-progress { padding-top: 0; }.journey-seal { width: 57px; margin-bottom: 9px; }.phase-count { font-size: 10px; }.phase-count strong { font-size: 30px; margin-bottom: 3px; }.phase-count strong span { font-size: 18px; }.phase-meter { margin: 12px 0 10px; }.current-operation p { font-size: 11px; }.current-operation small { font-size: 9px; }.resource-progress { margin-top: 8px; }.phase-list { display: grid; grid-template-columns: 1fr 1fr; column-gap: 18px; }.phase-list li { grid-template-columns: 15px minmax(0, 1fr); gap: 5px; font-size: 11px; min-height: 39px; padding: 4px 0; }.phase-list small { grid-column: 2; font-size: 9px; margin-top: -5px; }.loading-details h2 { margin-bottom: 4px; font-size: 11px; }.recent-updates { margin-top: 13px; padding-top: 9px; }.recent-updates h2 { font-size: 10px; margin-bottom: 4px; }.recent-updates ul { gap: 3px 18px; }.recent-updates li, .recent-updates small { font-size: 9px; }.loading-error { margin-top: 10px; gap: 12px; }.loading-error p { font-size: 11px; }.loading-error .entry-button { min-height: 36px; font-size: 12px; min-width: 150px; }
	}
	@media (prefers-reduced-motion: reduce) { .waiting-star, .journey-seal .seal-heart, .resource-progress:indeterminate { animation: none; }.channel-row { transition: none; } }
	@media (max-height: 480px) and (min-width: 640px) and (orientation: landscape) {
		.lobby-panel.channels { display: grid; grid-template-columns: 158px minmax(0, 1fr); grid-template-rows: auto minmax(68px, 1fr) auto auto auto; gap: 0 23px; height: calc(100dvh - 24px); padding: 16px 24px; }
		.channels .lobby-header { grid-column: 1; grid-row: 1 / 6; flex-direction: column-reverse; justify-content: center; align-items: flex-start; border: 0; padding: 0; gap: 20px; }.channels .lobby-logo { width: 155px; }.channels h1 { font-size: 22px; }.channels .world-name { font-size: 10px; margin-bottom: 6px; }.channels #lobby-subtitle { margin-top: 10px; font-size: 11px; }
		.channels .channel-toolbar, .channels .channel-list-shell, .channels .auto-choice, .channels .channel-feedback, .channels .channel-footer { grid-column: 2; }.channels .channel-toolbar { padding: 0 0 7px; }.channels .channel-toolbar small { display: block; margin: 2px 0 0 21px; }.channels .quiet-button { min-height: 36px; }.channels .channel-list-shell { min-height: 68px; }.channels .channel-list { max-height: none; }.channels .channel-columns, .channels .channel-row { grid-template-columns: minmax(0, 1fr) 88px 72px; gap: 12px; padding-left: 12px; padding-right: 12px; }.channels .channel-columns span:last-child { padding-right: 0; }.channels .channel-identity { gap: 12px; }.channels .channel-latency { gap: 7px; }.channels .occupancy-track { width: 72px; }.channels .auto-choice { min-height: 40px; padding: 5px 10px; margin-top: 7px; }.channels .channel-footer { margin-top: 10px; }.channels .entry-button { min-height: 40px; min-width: 190px; }
		.loading .lobby-header { padding-bottom: 8px; }.loading #lobby-subtitle { display: none; }.loading .loading-layout { padding-top: 12px; }.loading .recent-updates { max-height: 66px; }
	}
	@media (max-height: 620px) and (min-width: 640px) and (orientation: landscape) {
		.world-name, .channels .world-name { font-size: 11px; }
		.channel-toolbar p, .channels .channel-toolbar p { font-size: 12px; }
		.channel-toolbar small, .channels .channel-toolbar small { font-size: 11px; }
		.quiet-button, .channels .quiet-button { min-height: 44px; font-size: 12px; }
		.channel-columns, .channels .channel-columns { font-size: 11px; }
		.channel-row { min-height: 58px; }
		.channel-name, .channel-population { font-size: 14px; }
		.channel-name small, .channel-population em { font-size: 11px; }
		.channel-latency { font-size: 12px; }
		.auto-choice, .channels .auto-choice { min-height: 44px; }
		.auto-choice strong { font-size: 14px; }.auto-choice small { font-size: 11px; }
		.channel-feedback, .channel-feedback .lobby-error { font-size: 11px; }
		.channel-footer p { font-size: 11px; }.channel-footer strong { font-size: 12px; }
		.entry-button, .channels .entry-button, .loading-error .entry-button { min-height: 44px; font-size: 14px; }
		.phase-count, .current-operation small { font-size: 11px; }.current-operation p { font-size: 12px; }
		.phase-list li { font-size: 12px; min-height: 45px; }.phase-list small { font-size: 11px; }
		.loading-details h2, .recent-updates h2 { font-size: 12px; }
		.recent-updates li, .recent-updates small { font-size: 11px; }
		.loading-error p { font-size: 12px; }
		.loading .loading-layout { flex: 1 1 auto; min-height: 100px; overflow-y: auto; scrollbar-width: thin; overscroll-behavior: contain; }
	}
</style>
