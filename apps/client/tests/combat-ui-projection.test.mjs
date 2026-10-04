import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {TransformNode} from '@babylonjs/core/Meshes/transformNode';
export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';
export {Ray} from '@babylonjs/core/Culling/ray';
export {projectCombatActors} from './src/combat-ui-projection';`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
function fixture(run,{width=1920,height=1080,pixelRatio=1,renderScale=1}={}){
	const rect={left:41,top:29,width,height},engine=new api.NullEngine({renderWidth:Math.round(width*pixelRatio*renderScale),renderHeight:Math.round(height*pixelRatio*renderScale),textureSize:256});
	engine.getRenderingCanvas=()=>({width:Math.round(width*pixelRatio),height:Math.round(height*pixelRatio),clientWidth:width,clientHeight:height,getBoundingClientRect:()=>rect});
	engine.getHardwareScalingLevel=()=>1/(pixelRatio*renderScale);
	const scene=new api.Scene(engine),camera=new api.ArcRotateCamera('player-camera',-Math.PI/2,1.18,13,new api.Vector3(0,1.65,2),scene);camera.fov=1.02;scene.activeCamera=camera;
	const localRoot=new api.TransformNode('authority-player',scene),root=new api.TransformNode('authority-monster',scene),visual=new api.TransformNode('cosmetic-monster',scene);
	root.position.set(0,0,5);visual.parent=root;
	const body=api.MeshBuilder.CreateBox('rendered-monster',{width:1,height:2,depth:1},scene);body.parent=visual;body.position.y=1;body.metadata={monsterId:101};root.metadata={monsterId:101,kind:3};
	const monster={id:101,kind:3,x:0,z:5,hp:321,max_hp:500,active:true,flags:6,state:2,state_ticks:10,ability:5},catalog=new Map([[3,{name:'Thistle Boar',level:8,rank:'elite',element:'earth',splash_windup_ms:900}]]),lastDamaged=new Map([[101,100]]);
	const world={scene,engine,camera,localRoot,collisionBoxes:[],slimes:new Map([[101,{root,body}]])};
	const refresh=()=>{body.computeWorldMatrix(true);scene.updateTransformMatrix(true);};
	const project=()=>{refresh();return api.projectCombatActors(world,[monster],catalog,lastDamaged,500);};
	const anchor=()=>{refresh();const b=body.getBoundingInfo().boundingBox;return new api.Vector3((b.minimumWorld.x+b.maximumWorld.x)/2,b.maximumWorld.y+.3,(b.minimumWorld.z+b.maximumWorld.z)/2);};
	try{return run({world,root,body,visual,camera,rect,monster,catalog,project,anchor,refresh});}finally{scene.dispose();engine.dispose();}
}
const almost=(actual,expected,epsilon=.0001)=>assert.ok(Math.abs(actual-expected)<epsilon,`${actual} != ${expected}`);
const boxAt=(at,half=.5)=>({minX:at.x-half,maxX:at.x+half,minY:at.y-half,maxY:at.y+half,minZ:at.z-half,maxZ:at.z+half});
test('actual head plus 0.30 m projects into CSS coordinates with container offset and exact snapshot values',()=>fixture(({body,camera,rect,project})=>{
	const [value]=project();
	// Independent perspective oracle: view-space ratios, not Vector3.Project.
	const view=api.Vector3.TransformCoordinates(new api.Vector3(0,2.3,5),camera.getViewMatrix()),denominator=2*Math.tan(camera.fov/2)*view.z;
	almost(value.screenX,rect.left+rect.width/2+view.x*rect.height/denominator);
	almost(value.screenY,rect.top+rect.height/2-view.y*rect.height/denominator);
	assert.equal(value.onScreen,true);assert.equal(value.hp,321);assert.equal(value.maxHp,500);assert.equal(value.targetingMe,true);assert.equal(value.rank,'elite');
	assert.deepEqual(value.cast,{label:'Splash Hop',endsAtMs:1000,durationMs:900});
	body.scaling.y=1.7;const [taller]=project();assert.ok(taller.screenY<value.screenY,'plate follows changed rendered head rather than snapshot floor');
}));
test('anchors behind the actual player camera are excluded from on-screen plates',()=>fixture(({root,monster,camera,project,refresh})=>{
	refresh();const backward=camera.globalPosition.subtract(camera.target).normalize();root.position.copyFrom(camera.globalPosition.add(backward.scale(5)));monster.x=root.position.x;monster.z=root.position.z;
	assert.equal(project()[0].onScreen,false);
}));
test('CSS positions are independent of backing pixel ratio and proportional hardware render scale',()=>{
	const values=[];for(const [pixelRatio,renderScale] of [[1,1],[2,1],[2,.5],[3,.5]])fixture(({root,monster,project})=>{root.position.x=3;monster.x=3;values.push(project()[0]);},{width:896,height:414,pixelRatio,renderScale});
	for(const value of values){almost(value.screenX,values[0].screenX,.02);almost(value.screenY,values[0].screenY,.02);assert.equal(value.onScreen,values[0].onScreen);}
});
test('a collision proxy between camera and head occludes; a proxy behind the target does not',()=>fixture(({world,camera,project,anchor})=>{
	const head=anchor(),direction=head.subtract(camera.globalPosition).normalize();
	world.collisionBoxes=[boxAt(camera.globalPosition.add(head.subtract(camera.globalPosition).scale(.5)))];assert.equal(project()[0].occluded,true);
	world.collisionBoxes=[boxAt(head.add(direction.scale(5)))];assert.equal(project()[0].occluded,false,'the occlusion segment ends at the visible actor head');
}));
test('installed Ray box helper ignores segment length: explicit repro for the projection caller',()=>{
	const ray=new api.Ray(new api.Vector3(0,0,0),new api.Vector3(0,0,1),5);
	assert.equal(ray.intersectsBoxMinMax(new api.Vector3(-1,-1,20),new api.Vector3(1,1,22)),true,'Babylon box helper is intentionally an infinite ray broad-phase');
});
test('segment occlusion includes a box containing the camera or overlapping the head, but rejects one behind the camera',()=>fixture(({world,camera,project,anchor})=>{
	const head=anchor(),direction=head.subtract(camera.globalPosition).normalize();
	world.collisionBoxes=[boxAt(camera.globalPosition)];assert.equal(project()[0].occluded,true,'starting inside opaque collision proxy is occluded');
	world.collisionBoxes=[boxAt(head,1)];assert.equal(project()[0].occluded,true,'part of this box lies before the endpoint');
	world.collisionBoxes=[boxAt(camera.globalPosition.subtract(direction.scale(5)))];assert.equal(project()[0].occluded,false,'negative-distance hit behind the camera does not count');
}));
