/** Read-only baseline view: reverse only this UI task's edits in Vite's in-memory transform.
 * The live client files, 3D scene and server are never rolled back or copied. */
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
const root=fileURLToPath(new URL("../../../",import.meta.url));
const require=createRequire(new URL("../../../package.json",import.meta.url));
const {createServer}=await import(pathToFileURL(require.resolve("vite")));
const {svelte,vitePreprocess}=await import(pathToFileURL(require.resolve("@sveltejs/vite-plugin-svelte")));
const oldVitals=`<section class="player-card panel" aria-label={th ? "สถานะตัวละคร" : "Player status"}>
  <div class="portrait" aria-hidden="true"><span>{view.player.name.slice(0, 1).toUpperCase()}</span></div>
  <div class="player-info">
    <div class="player-heading"><strong id="player-name">{view.player.name}</strong><span id="player-level">{view.player.levelText}</span></div>
    <div class="bar-row"><span class="bar hp" aria-label={\`HP \${Math.round(view.player.hp)} / \${Math.round(view.player.hpMaximum)}\`}><i id="hp-fill" style={\`--fill:\${ratio(view.player.hp, view.player.hpMaximum)}\`}></i></span><small id="hp-text">{Math.round(view.player.hp)} / {Math.round(view.player.hpMaximum)}</small></div>
    <div class="bar-row"><span class="bar sp" aria-label={view.player.sp === null || view.player.spMaximum === null ? "SP —" : \`SP \${view.player.sp} / \${view.player.spMaximum}\`}><i id="sp-fill" style={\`--fill:\${ratio(view.player.sp ?? 0, view.player.spMaximum ?? 0)}\`}></i></span><small id="sp-text">{view.player.sp === null || view.player.spMaximum === null ? "—" : \`\${Math.round(view.player.sp)} / \${Math.round(view.player.spMaximum)}\`}</small></div>
    <div class="bar-row exp-row"><span class="bar xp"><i id="xp-fill" style={\`--fill:\${ratio(view.player.expRatio)}\`}></i></span><small id="xp-text">{view.player.expText}</small></div>
    <div class="bar-row exp-row job-row"><span class="bar xp job"><i id="jobxp-fill" style={\`--fill:\${ratio(view.player.jobExpRatio)}\`}></i></span><small id="jobxp-text">{view.player.jobExpText}</small></div>
  </div>
</section>`;
function baseline(code,id){
  const path=id.replaceAll("\\","/").split("?")[0];
  if(path.endsWith("/src/style.css")) return code.replace('@import url("./ui/astral-theme.css");','');
  if(id.includes("?")) return null;
  if(path.endsWith("/src/ui/Hud.svelte")) return code
    .replace(/\s*import HudVitals[^;]+;/,'').replace(/\s*import MenuIcon[^;]+;/,'')
    .replace('<HudVitals player={view.player} {th} />',oldVitals)
    .replace('<span class="nav-symbol"><MenuIcon name={item.name} /></span>','<span class={`nav-icon ${item.icon}`} aria-hidden="true">{item.glyph}</span>');
  if(path.endsWith("/src/ui/HudMinimap.svelte")) return code
    .replace('<span class="zone-name" title={`${areaName} · ${zoneThai}`}><b>{areaName}</b><small lang="th">{zoneThai}</small></span>','<span title={areaName}>{areaName}</span>');
  if(path.endsWith("/src/ui/Chat.svelte")) return code
    .replaceAll('(max-width: 900px), (any-pointer: coarse)','(max-width: 767px), (pointer: coarse) and (max-width: 900px)')
    .replace(/\s*\.chat-ui:not\(\.is-expanded\) :is\(\.chat-tabs,#chat-lines,#chat-form\) \{ display: none; \}/,'');
  if(path.endsWith("/src/ui/HudButton.svelte")) return code
    .replace(/\s*import SkillIcon[^;]+;/,'')
    .replace('<span class={`ability-art ${art}`}><SkillIcon {action} {potion} /></span>','{#if potion}<span class="potion-bottle" aria-hidden="true"></span>{:else}<span class={`skill-art ${art}`} aria-hidden="true"></span>{/if}')
    .replace(/<span class="skill-tooltip"[^>]*>[^<]*<\/span>/,'');
  return null;
}
const server=await createServer({root,configFile:false,cacheDir:fileURLToPath(new URL("../../../../../.ui-baseline-cache",import.meta.url)),
  plugins:[{name:"ui-baseline-review-only",enforce:"pre",transform:baseline},svelte({preprocess:vitePreprocess(),compilerOptions:{runes:true}})],
  server:{host:"127.0.0.1",port:5196,strictPort:true,proxy:{"/healthz":"http://127.0.0.1:3001","/session":"http://127.0.0.1:3001","/auth":"http://127.0.0.1:3001","/rooms":"http://127.0.0.1:3001","/ws":{target:"ws://127.0.0.1:3001",ws:true}}}});
await server.listen();console.log("Read-only baseline game ready: http://127.0.0.1:5196/ (shared source unchanged)");
for(const signal of ["SIGINT","SIGTERM"])process.on(signal,()=>void server.close().then(()=>process.exit(0)));
