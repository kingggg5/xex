<script lang="ts">
  import PortraitMedallion from "./PortraitMedallion.svelte";
  import type { HudPlayer } from "./hud-types";
  let { player, th,reviewV1=false }: { player: HudPlayer; th: boolean;reviewV1?:boolean } = $props();
  const ratio=(value:number,maximum:number)=>maximum>0?Math.max(0,Math.min(1,value/maximum)):0;
  const hp=$derived(ratio(player.hp,player.hpMaximum));
  const critical=$derived(player.hpMaximum>0 && player.hp>0 && hp<=.25);
</script>
<section class="player-card panel" class:is-critical={critical} aria-label={th?"สถานะตัวละคร":"Player status"}>
  <div class="portrait" aria-hidden="true">{#if reviewV1}<svg viewBox="0 0 48 56" fill="none"><path d="m24 3 19 9v20c-2 10-10 16-19 21C15 48 7 42 5 32V12Z" stroke="#c9a76b"/><path d="m24 8 9 13-9 15-9-15Z" fill="#5ab5e340" stroke="#98d5f6"/><path d="M24 8v28m-9-15h18" stroke="#b5e0f6"/></svg><span>{player.name.slice(0,1).toUpperCase()}</span>{:else}<PortraitMedallion initial={player.name.slice(0,1).toUpperCase()}/>{/if}</div>
  <div class="player-info">
    <div class="player-heading"><strong id="player-name">{player.name}</strong><span class="level-badges"><span id="player-level" class="level-badge" title={player.baseLevel===null?(th?"กำลังโหลดเลเวลพื้นฐาน":"Loading base level"):player.footerLevel}><small>BASE</small><b>{player.baseLevel??"—"}</b></span><span class="level-badge job-badge" title={player.jobLevel===null?(th?"กำลังโหลดเลเวลอาชีพ":"Loading job level"):player.footerJob}><small>JOB</small><b>{player.jobLevel??"—"}</b></span></span></div>
    <div class="bar-row"><span class="vital-label">HP</span><span class="bar hp" role="progressbar" aria-label="HP" aria-valuemin="0" aria-valuemax={player.hpMaximum>0?player.hpMaximum:undefined} aria-valuenow={player.hpMaximum>0?Math.max(0,Math.min(player.hpMaximum,player.hp)):undefined} style={`--fill:${hp}`}><i class="hp-ghost"></i><i id="hp-fill"></i></span><small id="hp-text">{player.hpMaximum>0?`${Math.round(player.hp)} / ${Math.round(player.hpMaximum)}`:"—"}</small></div>
    <div class="bar-row"><span class="vital-label">SP</span><span class="bar sp" aria-label={player.sp===null?"SP unavailable":`SP ${player.sp} / ${player.spMaximum}`}><i id="sp-fill" style={`--fill:${ratio(player.sp??0,player.spMaximum??0)}`}></i></span><small id="sp-text">{player.sp===null||player.spMaximum===null?"—":`${Math.round(player.sp)} / ${Math.round(player.spMaximum)}`}</small></div>
    <div class="bar-row exp-row"><span class="vital-label">EXP</span><span class="bar xp"><i id="xp-fill" style={`--fill:${ratio(player.expRatio,1)}`}></i></span><small id="xp-text">{player.expText}</small></div>
    <div class="bar-row exp-row job-row"><span class="vital-label">JOB</span><span class="bar xp job"><i id="jobxp-fill" style={`--fill:${ratio(player.jobExpRatio,1)}`}></i></span><small id="jobxp-text">{player.jobExpText}</small></div>
    {#if critical}<span class="critical-label" role="status">{th?"พลังชีวิตต่ำ":"Low health"}</span>{/if}
  </div>
</section>

<style>
  /* The reference's ruby HP material; resource values and fill transforms stay live. */
  #hp-fill { background: linear-gradient(#efb6a3 0%, #cc6b65 23%, #963f49 65%, #592b3b 100%) !important; box-shadow: inset 0 1px 0 #ffe1b780; }
  .is-critical #hp-fill { background: #e17b7f !important; }
</style>
