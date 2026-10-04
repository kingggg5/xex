/** Seal captured screenshots and this task's exact source roster; never modify image pixels. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
const game=fileURLToPath(new URL("../../../../../",import.meta.url));
const evidence=path.join(game,"planning/evidence/mmo-ui-20261001");
const stems=["before-desktop-day","after-desktop-day","before-desktop-night","after-desktop-night","before-mobile-day","after-mobile-day","before-mobile-night","after-mobile-night"];
const sources=["apps/client/src/style.css","apps/client/src/ui.ts","apps/client/src/ui/Hud.svelte","apps/client/src/ui/HudButton.svelte","apps/client/src/ui/HudMinimap.svelte","apps/client/src/ui/Chat.svelte","apps/client/src/ui/Inventory.svelte","apps/client/src/ui/bridge.svelte.ts","apps/client/src/ui/hud-types.ts","apps/client/src/ui/HudVitals.svelte","apps/client/src/ui/SkillIcon.svelte","apps/client/src/ui/MenuIcon.svelte","apps/client/src/ui/astral-theme.css"];
for(const folder of ["apps/client/src/assets/ui/astral-v1","apps/client/src/ui/review"]){for(const name of await fs.readdir(path.join(game,folder)))sources.push(`${folder}/${name}`);}
const files=[];for(const name of sources){const bytes=await fs.readFile(path.join(game,name));files.push({path:name,bytes:bytes.length,sha256:createHash("sha256").update(bytes).digest("hex")});}
for(const name of await fs.readdir(evidence)) if(name.endsWith(".png")){
  const source=path.join(evidence,name),bytes=await fs.readFile(source);
  if(bytes[0]===255&&bytes[1]===216) await fs.rename(source,path.join(evidence,name.replace(/\.png$/,".jpg")));
}
const screenshots=[];for(const stem of stems){const meta=JSON.parse(await fs.readFile(path.join(evidence,stem+".json"),"utf8"));
  if(meta.coords!=="-3/-3" || !meta.connection.includes("ONLINE") || meta.loading || meta.login) throw new Error(`Invalid matched capture: ${stem}`);
  screenshots.push({path:path.join(evidence,stem+".jpg"),...meta});
}
const report={task:"Xexoria in-game fantasy MMO UI theme",date:"2026-10-01",status:"Implementation complete; visual review candidate",
  files_changed:files,screenshots,camera:{source:"Unmodified scene.ts default follow camera",alpha:-Math.PI/2,beta:1.18,radius:13,fov:1.02,player_coordinates:"-3 / -3",environment:"envHour 14 or 22; envWeather clear"},
  verification:{typescript:"PASS",svelte:"0 errors / 0 warnings",ui_model_tests:"8 PASS",production_build:"PASS; isolated output under Downloads/hero/02/mmo-ui-build-review",baseline_chunks_in_production:"Not found",impeccable_detector:"No findings",mobile_overlap:"Zero intersections across player frame, minimap, chat, joystick and five skill buttons",keyboard_focus:"Observed menu-button :focus-visible with solid 2px rgb(155,220,255) outline",chat_fullscreen:"Observed dialog at 844x390; all combat controls disabled during chat",mobile_inventory:"Observed fullscreen dialog at x0/y0, 844x390",thai_font:"document.fonts.check returned true",cooldown:"Real Guard Stance press: disabled cooling state, 6-second counter; CSS static progress under system Reduce Motion",reduced_motion:"Active on review machine: cooldown animation none, ghost transition delay 0s; normal-motion CSS remains authored but not visually exercised in live combat"},
  design:{materials:"192px original nine-slice SVG slate/bronze frame; sapphire interaction accents; red low-health state",fonts:"Locally served Noto Sans Thai variable + incumbent Marcellus",new_raster_textures:0,new_per_frame_dom_subscriptions:0,cooldown_dom_updates:"Second boundaries while cooling/visible; CSS owns normal-motion sweep",health_feedback:"160ms health fill, 380ms ghost delay then 180ms catch-up; three low-health pulses, suppressed under Reduce Motion"},
  scope:{main_modified:false,engine_or_3d_files_modified:false,store_purchases_or_chat_messages_sent:false,baseline:"DEV-only incumbent markup loaded at the same origin with live game state; no stats or world mock-up"},
  remaining_issues:["Physical iPhone/Android performance and safe-area behavior not hardware qualified","Full normal-motion HP ghost/pulse sequence still needs live combat review with Reduce Motion off","Portrait remains an original heraldic initial; inventory uses category glyphs rather than final illustrated item art","Normal-motion smooth custom-property sweep depends on supported CSS @property; disabled state/count remains authoritative"],
  cleanup_note:"Automatic approval review blocked recursive removal of the task-created .ui-baseline-cache directory; cache retained. Temporary baseline server was stopped."};
await fs.writeFile(path.join(evidence,"review.json"),JSON.stringify(report,null,2));
console.log(JSON.stringify({report:path.join(evidence,"review.json"),sources:files.length,matched_screenshots:screenshots.length}));
