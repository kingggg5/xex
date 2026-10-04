import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {deflateSync,crc32} from 'node:zlib';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {performance} from 'node:perf_hooks';
import {createWaterTerrainSampler} from '../../apps/client/src/nature-water.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const args=process.argv.slice(2);
if(args.length && (args.length!==4 || args[0]!=='--derived' || args[2]!=='--out'))
 throw new Error('Usage: build-water-host-mask.mjs [--derived <repo-relative JSON> --out <repo-relative candidate directory>]');
const withinRepo=value=>{
 const resolved=path.resolve(root,value),relative=path.relative(root,resolved);
 if(!relative || relative==='..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative))
  throw new Error('Water mask paths must remain inside the repository');
 return resolved;
};
const input=args.length?withinRepo(args[1]):path.join(root,'planning/evidence/water-20261002/water-derived.json');
const out=args.length?withinRepo(args[3]):path.join(root,'apps/client/src/assets/world/water-host-v3');
if(args.length && out.toLowerCase()===path.join(root,'apps/client/src/assets/world/water-host-v3').toLowerCase())
 throw new Error('Candidate mask generation must not overwrite the baseline mask');
const bytes=readFileSync(input),derived=JSON.parse(bytes);
const sample=createWaterTerrainSampler({...derived,lakes:derived.lakes.filter(lake=>!lake.id.startsWith('blueprint_'))});
const sampleAll=createWaterTerrainSampler(derived);
const deckInput=readFileSync(path.join(root,'planning/evidence/sunmeadow-v3-features/integration-contract.json'));
const decks=JSON.parse(deckInput).decks.map(deck=>{
 const poly=deck.polygon_xz;
 if(poly.length!==4||poly.some((p,i)=>p[0]!==poly[(i+1)%4][0]&&p[1]!==poly[(i+1)%4][1]))throw new Error('Deck mask needs an axis-aligned rectangular contract');
 return [Math.min(...poly.map(p=>p[0])),Math.min(...poly.map(p=>p[1])),Math.max(...poly.map(p=>p[0])),Math.max(...poly.map(p=>p[1]))];
});
const size=512,bounds=[-76,-108,52,24],rows=Buffer.alloc(size*(size*4+1));
const began=performance.now();let cutTexels=0;
for(let y=0;y<size;y++)for(let x=0;x<size;x++){
 const wx=bounds[0]+(x+.5)/size*(bounds[2]-bounds[0]);
 const wz=bounds[1]+(y+.5)/size*(bounds[3]-bounds[1]);
 const bed=sample(wx,wz),cut=bed!==null&&bed.heightY<-.02;
 const p0=sampleAll(wx,wz),cutP0=p0!==null&&p0.body.startsWith('blueprint_')&&p0.heightY<-.02;
 const offset=y*(size*4+1)+1+x*4;
 rows[offset]=cut?255:0;rows[offset+1]=decks.some(d=>wx>=d[0]&&wx<=d[2]&&wz>=d[1]&&wz<=d[3])?255:0;
 rows[offset+2]=cutP0?255:0;rows[offset+3]=255;if(cut)cutTexels++;
}
function chunk(kind,data){const content=Buffer.concat([Buffer.from(kind),data]),size=Buffer.alloc(4),crc=Buffer.alloc(4);size.writeUInt32BE(data.length);crc.writeUInt32BE(crc32(content)>>>0);return Buffer.concat([size,content,crc]);}
const header=Buffer.alloc(13);header.writeUInt32BE(size,0);header.writeUInt32BE(size,4);header[8]=8;header[9]=6;
const png=Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(rows,{level:9})),chunk('IEND',Buffer.alloc(0))]);
const hash=b=>createHash('sha256').update(b).digest('hex');mkdirSync(out,{recursive:true});
writeFileSync(path.join(out,'land-cutout-v3.png'),png);
const receipt={schema:'xexoria.water-host-mask/1',derivedSha256:hash(bytes),deckContractSha256:hash(deckInput),channels:'R=base water/banks,G=Y0 decks,B=blueprint P0 water',maskSha256:hash(png),boundsXZ:bounds,size,cutTexels,fileBytes:png.length,gpuRgba8Bytes:size*size*4,offlineGenerationMs:performance.now()-began,physicalHazardsAdmitted:false};
writeFileSync(path.join(out,'land-cutout-v3.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
