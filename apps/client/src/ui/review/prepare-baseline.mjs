/** Preserve the incumbent components for DEV-only, same-origin screenshot comparison. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here=path.dirname(fileURLToPath(import.meta.url)), ui=path.dirname(here);
const serverPath=path.join(here,"serve-baseline.mjs");
const source=await fs.readFile(serverPath,"utf8");
const start=source.indexOf("const oldVitals="),end=source.indexOf("const server=");
if(start<0||end<start) throw new Error("Baseline source boundary changed");
const pure=source.slice(start,end).replace("function baseline(","export function baseline(");
await fs.writeFile(path.join(here,"baseline-source.mjs"),pure);
const {baseline}=await import("./baseline-source.mjs");
const aliases={"./HudButton.svelte":"./LegacyHudButton.svelte","./HudMinimap.svelte":"./LegacyHudMinimap.svelte"};
for(const name of ["Hud","HudButton","HudMinimap","Chat"]){
  const original=await fs.readFile(path.join(ui,`${name}.svelte`),"utf8");
  let result=baseline(original,`/src/ui/${name}.svelte`);
  result=result.replace(/from "(\.\.?\/[^\"]+)"/g,(_,specifier)=>`from "${aliases[specifier]??'../'+specifier}"`);
  if(name==="HudMinimap") result=result.replace(/\s*const zoneThai = \$derived\([^\n]+\);/,'');
  if(name==="HudButton") result=result.replace(/<style>[\s\S]*?<\/style>/,`<style>
button { min-width:44px; min-height:44px; }
.cooldown-shade { position:absolute; inset:0; border-radius:inherit; background:conic-gradient(rgba(8,13,20,.72) var(--hud-cooldown),transparent 0); animation:hud-cooldown-sweep var(--cd-duration) linear var(--cd-delay) both; pointer-events:none; }
.cooldown-seconds,.pending-mark { position:absolute; z-index:1; inset:0; display:grid; place-items:center; color:#fff7dd; font-size:17px; font-weight:800; pointer-events:none; }
button.cooling:disabled { opacity:.8; filter:none; }
@media(max-height:520px) and (max-width:900px){button.mobile-skill{min-width:58px;min-height:58px;}}
</style>`);
  await fs.writeFile(path.join(here,`Legacy${name}.svelte`),'<!-- Incumbent UI preserved for DEV-only screenshot review; live world/server data unchanged. -->\n'+result);
}
console.log("Prepared original UI review components; engine/auth/source outside ui unchanged.");
