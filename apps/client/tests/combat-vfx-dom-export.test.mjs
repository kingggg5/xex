import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
const bundled=await build({stdin:{contents:"export {isVfxDomExport,createNativeVfxResultExport,vfxCaptureBatch} from './src/combat-vfx-demo';",resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent',loader:{'.png':'empty','.glb':'empty','.svg':'empty'}});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
const ids=['xs_bladeward_nova','xs_gale_palm','xs_void_rift'];
const png='data:image/png;base64,'+Buffer.from([137,80,78,71,13,10,26,10,0,0,0,0]).toString('base64');
function host(){const nodes=new Map();return {nodes,body:{append(node){nodes.set(node.id,node);}},getElementById:id=>nodes.get(id),createElement(tag){return {tag,dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;},remove(){nodes.delete(this.id);}};}};}
test('DOM export is explicit opt-in and only retains three inert bounded native PNG results',()=>{
 assert.equal(api.isVfxDomExport('?vfxexport=dom'),true);for(const search of ['','?vfxexport=file','?vfxexport=DOM','?other=dom'])assert.equal(api.isVfxDomExport(search),false);
 const document=host(),output=api.createNativeVfxResultExport(document),node=document.nodes.get('vfx-native-results');assert.equal(node.type,'application/json');assert.equal(node.inert,true);assert.equal(node.hidden,true);
 for(const skillId of ids)output.add({skillId,png,probe:{renderer:'WebGL2',frames:8}});output.complete();assert.equal(output.count,3);assert.equal(node.dataset.state,'complete');assert.equal(node.dataset.count,'3');assert.equal(JSON.parse(node.textContent).results.length,3);
 assert.throws(()=>output.add({skillId:ids[0],png,probe:{}}),/count or identity/);
 const replacement=api.createNativeVfxResultExport(document);assert.equal(replacement.count,0);assert.notEqual(document.nodes.get('vfx-native-results'),node);
});
test('native evidence rejects over-size PNGs, external URLs, unknown IDs and unbounded probes',()=>{
 const output=api.createNativeVfxResultExport(host());
 const huge='data:image/png;base64,'+'iVBORw0KGgo'+('A'.repeat(7*1024*1024+1));assert.throws(()=>output.add({skillId:ids[0],png:huge,probe:{}}),/5 MiB/);
 assert.throws(()=>output.add({skillId:ids[0],png:'https://image.test/a.png',probe:{}}),/PNG data URL/);
 assert.throws(()=>output.add({skillId:'unknown',png,probe:{}}),/identity/);
 assert.throws(()=>output.add({skillId:ids[0],png,probe:{text:'x'.repeat(300000)}}),/metadata bound/);assert.equal(output.count,0);
});
test('DOM route precedes evidence upload and provides an observable completion status',async()=>{
 const code=await readFile(new URL('../src/combat-vfx-demo.ts',import.meta.url),'utf8');assert.match(code,/if\(nativeExport\)\{nativeExport.add[\s\S]*?continue;\}[\s\S]*?fetch\(`/);
 assert.match(code,/VFX native results ready: \$\{nativeExport.count\}\/3/);assert.match(code,/vfx-native-capture/);assert.doesNotMatch(code,/\.download\s*=|\.createObjectURL\(/);
});
test('six-effect library exports two explicit batches while preserving the original three-result default',()=>{
 assert.deepEqual(api.vfxCaptureBatch(''),ids);assert.deepEqual(api.vfxCaptureBatch('?vfxlook=2'),ids);
 assert.deepEqual(api.vfxCaptureBatch('?vfxlook=2&vfxbatch=witch-new'),['h02_star_lance','h02_moonveil_ward','h02_celestial_orrery']);
 const output=api.createNativeVfxResultExport(host());for(const skillId of api.vfxCaptureBatch('?vfxbatch=witch-new'))output.add({skillId,png,probe:{visualOnly:true}});assert.equal(output.count,3);
});
