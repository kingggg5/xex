// Read-only source-geometry check for cloth faces overlapping the fountain.
// Does not import Blender files, mutate source assets, or use browser internals.
import fs from 'node:fs';
import crypto from 'node:crypto';
const file = 'assets/models/reference-city/r5/city-source.glb';
const bytes = fs.readFileSync(file);
if (bytes.readUInt32LE(0) !== 0x46546c67) throw new Error('Not a GLB');
const jsonLength = bytes.readUInt32LE(12);
const doc = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString());
const binary = bytes.subarray(28 + jsonLength);
const readers = {5126: ['readFloatLE', 4], 5125: ['readUInt32LE', 4], 5123: ['readUInt16LE', 2], 5121: ['readUInt8', 1]};
function readAccessor(index, components) {
  const accessor = doc.accessors[index], view = doc.bufferViews[accessor.bufferView];
  if (view.extensions?.EXT_meshopt_compression || accessor.sparse || (view.buffer ?? 0) !== 0) throw new Error('Expected uncompressed embedded source accessor');
  const [method, size] = readers[accessor.componentType] ?? [];
  if (!method) throw new Error('Unsupported accessor component');
  const stride = view.byteStride ?? size * components;
  const start = (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
  return Array.from({length: accessor.count}, (_, i) => Array.from({length: components}, (_, component) => binary[method](start + i * stride + component * size)));
}
const parents = new Map();
doc.nodes.forEach((node, index) => node.children?.forEach(child => parents.set(child, index)));
function transform(point, node) {
  if (node.matrix) {
    const m = node.matrix, [x,y,z] = point;
    return [m[0]*x+m[4]*y+m[8]*z+m[12],m[1]*x+m[5]*y+m[9]*z+m[13],m[2]*x+m[6]*y+m[10]*z+m[14]];
  }
  const s=node.scale??[1,1,1], t=node.translation??[0,0,0], q=node.rotation??[0,0,0,1];
  const [x,y,z]=point.map((value,i)=>value*s[i]), [qx,qy,qz,qw]=q;
  const tx=2*(qy*z-qz*y), ty=2*(qz*x-qx*z), tz=2*(qx*y-qy*x);
  return [x+qw*tx+qy*tz-qz*ty+t[0],y+qw*ty+qz*tx-qx*tz+t[1],z+qw*tz+qx*ty-qy*tx+t[2]];
}
function worldPoint(point, index) {
  for (let cursor=index; cursor!==undefined; cursor=parents.get(cursor)) point=transform(point,doc.nodes[cursor]);
  return point;
}
const matches=[];
for (const [nodeIndex,node] of doc.nodes.entries()) {
  if (node.mesh === undefined) continue;
  for (const primitive of doc.meshes[node.mesh].primitives) {
    const material=doc.materials[primitive.material]?.name??'';
    if (!/^cloth_/.test(material)) continue;
    const positions=readAccessor(primitive.attributes.POSITION,3).map(point=>worldPoint(point,nodeIndex));
    const indices=readAccessor(primitive.indices,1).flat();
    const selected=[];
    for(let i=0;i<indices.length;i+=3){
      const points=[positions[indices[i]],positions[indices[i+1]],positions[indices[i+2]]];
      const center=[0,1,2].map(axis=>points.reduce((sum,p)=>sum+p[axis],0)/3);
      if(Math.hypot(center[0],center[2])<5 && center[1]>4 && center[1]<7) selected.push(points);
    }
    if(selected.length){
      const all=selected.flat();
      matches.push({node:node.name,material,triangles:selected.length,min:[0,1,2].map(axis=>Math.min(...all.map(p=>p[axis]))),max:[0,1,2].map(axis=>Math.max(...all.map(p=>p[axis])))});
    }
  }
}
const result={source:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),coordinateSpace:'glTF city source before runtime placement; fountain center is source X/Z=0',matches};
fs.writeFileSync('planning/evidence/fountain-art-review-20261001-cloth-overlap.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
