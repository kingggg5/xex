import { NullEngine } from '../apps/client/node_modules/@babylonjs/core/Engines/nullEngine';
import { Scene } from '../apps/client/node_modules/@babylonjs/core/scene';
import { MeshBuilder } from '../apps/client/node_modules/@babylonjs/core/Meshes/meshBuilder';
import { VertexBuffer } from '../apps/client/node_modules/@babylonjs/core/Buffers/buffer';
import { clipLegacyGroundToCity } from '../apps/client/src/city-ground-ownership';

const engine=new NullEngine(),scene=new Scene(engine);
const plane=MeshBuilder.CreateGround('env-world-base',{width:10,height:10,subdivisions:2},scene);
const colours=Array.from({length:plane.getTotalVertices()*4},(_,i)=>i%4===3?1:.5);plane.setVerticesData(VertexBuffer.ColorKind,colours,false,4);
const stream=MeshBuilder.CreateGround('env-stream',{width:2,height:2},scene);
const bridge=MeshBuilder.CreateBox('env-bridge-rail-1',{size:1},scene);
const unrelated=MeshBuilder.CreateGround('authored-city',{width:2,height:2},scene);
clipLegacyGroundToCity(scene,{minX:-2,maxX:2,minZ:-2,maxZ:2});
const positions=plane.getVerticesData(VertexBuffer.PositionKind)!,indices=plane.getIndices()!;
let area=0;
for(let i=0;i<indices.length;i+=3){const a=indices[i]*3,b=indices[i+1]*3,c=indices[i+2]*3;
 area+=Math.abs((positions[b]-positions[a])*(positions[c+2]-positions[a+2])-(positions[b+2]-positions[a+2])*(positions[c]-positions[a]))*.5;
 const x=(positions[a]+positions[b]+positions[c])/3,z=(positions[a+2]+positions[b+2]+positions[c+2])/3;
 if(x>-2+1e-5&&x<2-1e-5&&z>-2+1e-5&&z<2-1e-5)throw new Error('Legacy floor still covers authored city');
}
if(Math.abs(area-84)>.0001)throw new Error(`Clipped area ${area}, expected84`);
if(stream.isEnabled()||bridge.isEnabled()||!unrelated.isEnabled())throw new Error('Representation ownership changed an unrelated mesh');
for(const kind of [VertexBuffer.PositionKind,VertexBuffer.NormalKind,VertexBuffer.UVKind,VertexBuffer.ColorKind])if(!plane.getVerticesData(kind)?.every(Number.isFinite))throw new Error(`Lost finite${kind}`);
console.log(JSON.stringify({status:'PASS',remainingArea:area,removedCityArea:16,preservedAttributes:['position','normal','uv','color'],supersededStreamDisabled:true,authoredMeshUnchanged:true,scope:'NullEngine geometry ownership, not native GPU validation'}));
scene.dispose();engine.dispose();
