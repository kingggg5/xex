import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { Color3 } from '@babylonjs/core/Maths/math.color.js';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import { packDressingVertexBuffers } from './dressing-vertex-packing.mjs';

export const STARTER_ROCK_SOURCE=Object.freeze({
  id:'sm_boulder_01', diameter:1.1, triangles:Object.freeze([754,376,150]),
  sha256:Object.freeze([
    'e972db450bb7678569ed1f2492c3c4c7872c1c9bd18cfee66bfb0f98b88db5d2',
    '23998a5e80fdcb69e79e6ff314176e3287b4096c4b04349b0962a32bcc2fc9b3',
    '0db72a84b02fc1af2727fac2acc4963ecc06b3de3351ab271d468fae94225858'
  ]),
  atlas:Object.freeze({albedo:'sm_stone_albedo-384298f87985',normal:'sm_stone_normal-5aac6efc0e22',orm:'sm_stone_orm-ffc61f77267c'}),
  sourcePixelsPerMetre:409.6
});

/** Read-only decoding semantics: classic9.27.1 hides shader gamma when hardware already decodes sRGB. */
export function starterRockTextureColorSpace(texture,channel) {
  if(!texture||!['albedo','normal','orm'].includes(channel))throw new TypeError('Atlas colour-space channel required');
  const shaderGamma=texture.gammaSpace===true;
  const hardwareSRGB=texture.getInternalTexture()?._useSRGBBuffer===true;
  return {shaderGamma,hardwareSRGB,valid:channel==='albedo'?shaderGamma!==hardwareSRGB:!shaderGamma&&!hardwareSRGB};
}
function checkTextures(textures,scene) {
  for(const key of ['albedo','normal','orm']){
    const texture=textures[key];
    if(!texture||texture.getScene()!==scene||texture.isCube||
      !String(texture.name+' '+texture.url).includes(STARTER_ROCK_SOURCE.atlas[key]))
      throw new TypeError('Pinned sm_stone '+key+' atlas required');
    if(!starterRockTextureColorSpace(texture,key).valid)throw new TypeError('Incorrect '+key+' colour space');
  }
}
export function validateStarterRockMaterial(material,scene) {
  if(!(material instanceof PBRMaterial)||material.getScene()!==scene||!scene.materials.includes(material))
    throw new TypeError('Live same-scene PBR atlas material required');
  checkTextures({albedo:material.albedoTexture,normal:material.bumpTexture,orm:material.metallicTexture},scene);
  if(material.alpha!==1||(material.transparencyMode!==null&&material.transparencyMode!==PBRMaterial.MATERIAL_OPAQUE)||
    !material.backFaceCulling||material.albedoTexture.hasAlpha||
    material.useRoughnessFromMetallicTextureAlpha||!material.useRoughnessFromMetallicTextureGreen||
    !material.useAmbientOcclusionFromMetallicTextureRed||!material.useMetallnessFromMetallicTextureBlue)
    throw new TypeError('Opaque stone RGB/ORM contract required');
  return material;
}
/** Optional caller-owned material; borrows existing textures, never creates or changes them. */
export function createStarterRockMaterial(scene,textures) {
  checkTextures(textures,scene);
  const material=new PBRMaterial('starter-rocks-sm-stone-atlas',scene);
  material.albedoTexture=textures.albedo;material.bumpTexture=textures.normal;material.metallicTexture=textures.orm;
  material.albedoColor=Color3.White();material.metallic=1;material.roughness=1;
  material.transparencyMode=PBRMaterial.MATERIAL_OPAQUE;material.backFaceCulling=true;
  material.useRoughnessFromMetallicTextureAlpha=false;material.useRoughnessFromMetallicTextureGreen=true;
  material.useAmbientOcclusionFromMetallicTextureRed=true;material.useMetallnessFromMetallicTextureBlue=true;
  material.invertNormalMapX=!scene.useRightHandedSystem;material.invertNormalMapY=scene.useRightHandedSystem;
  material.metadata={atlas:'sm_stone',starterRocksCandidate:true,glow:false};
  return material;
}

/** Copy only three geometries once. Never author into the borrowed input geometry. */
export function normalizeStarterRockGeometry(scene,templates,sourceHashes) {
  if(templates.length!==3||sourceHashes?.length!==3||
    sourceHashes.some((hash,lod)=>hash!==STARTER_ROCK_SOURCE.sha256[lod]))
    throw new TypeError('Three pinned sm_boulder_01 runtime LOD identities required');
  for(let lod=0;lod<3;lod++){
    const input=templates[lod];
    if(!(input instanceof Mesh)||input.isDisposed()||input.getScene()!==scene||!input.geometry||
      input.skeleton||input.morphTargetManager||input.getTotalIndices()/3!==STARTER_ROCK_SOURCE.triangles[lod]||
      input.subMeshes.length!==1)throw new TypeError('Invalid boulder LOD '+lod);
    for(const [kind,size] of [['position',3],['normal',3],['uv',2],['color',3]]){
      const data=input.getVerticesData(kind);
      if(input.getVertexBuffer(kind)?.getSize()!==size||!data||data.length!==input.getTotalVertices()*size||
        data.some(value=>!Number.isFinite(value)))throw new TypeError('Invalid source '+kind+' at LOD '+lod);
    }
    const matrix=input.computeWorldMatrix(true);
    if(Math.abs(matrix.determinant())<1e-9||matrix.m.some(value=>!Number.isFinite(value)))
      throw new TypeError('Invalid source transform');
  }
  const meshes=[];
  try{
    for(let lod=0;lod<3;lod++){
      const input=templates[lod],mesh=new Mesh('starter-rocks-candidate-lod'+lod,scene);
      meshes.push(mesh);mesh.setEnabled(false);mesh.isVisible=false;mesh.isPickable=false;mesh.checkCollisions=false;
      input.geometry.copy(mesh.name+'-geometry').applyToMesh(mesh);
      const world=input.computeWorldMatrix(true),normalMatrix=world.clone().invert().transpose();
      const normals=input.getVerticesData('normal').slice(),normal=Vector3.Zero();
      mesh.bakeTransformIntoVertices(world);
      for(let index=0;index<normals.length;index+=3){
        Vector3.TransformNormalFromFloatsToRef(normals[index],normals[index+1],normals[index+2],normalMatrix,normal);
        if(normal.lengthSquared()<1e-12)throw new TypeError('Zero source normal');
        normal.normalize().toArray(normals,index);
      }
      mesh.setVerticesData('normal',normals,false,3);
      for(const kind of mesh.getVerticesDataKinds())
        if(!['position','normal','uv','color'].includes(kind))mesh.removeVerticesData(kind);
    }
    const first=meshes[0].getVerticesData('position'),min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
    for(let index=0;index<first.length;index++) {const axis=index%3;min[axis]=Math.min(min[axis],first[index]);max[axis]=Math.max(max[axis],first[index]);}
    const centre=min.map((value,axis)=>(value+max[axis])/2);
    let radius=0;
    for(const mesh of meshes){const positions=mesh.getVerticesData('position');
      for(let index=0;index<positions.length;index+=3)
        radius=Math.max(radius,Math.hypot(positions[index]-centre[0],positions[index+1]-centre[1],positions[index+2]-centre[2]));
    }
    if(!(radius>0&&Number.isFinite(radius)))throw new TypeError('Empty boulder extent');
    const scale=STARTER_ROCK_SOURCE.diameter*.5/radius;
    for(const mesh of meshes){
      const positions=mesh.getVerticesData('position'),uv=mesh.getVerticesData('uv');
      for(let index=0;index<positions.length;index++)positions[index]=(positions[index]-centre[index%3])*scale;
      // The repeating atlas stays in metres after the common uniform geometry resize.
      for(let index=0;index<uv.length;index++)uv[index]*=scale;
      mesh.setVerticesData('position',positions,false,3);mesh.setVerticesData('uv',uv,false,2);
      mesh.useVertexColors=true;mesh.hasVertexAlpha=false;
      mesh.refreshBoundingInfo();packDressingVertexBuffers(mesh);
    }
    return {meshes,centre,scale,normalizedRadius:STARTER_ROCK_SOURCE.diameter*.5,
      geometryAttributeLocations:4,instanceMatrixLocations:4,maximumAttributeLocations:8,
      basePixelsPerMetre:STARTER_ROCK_SOURCE.sourcePixelsPerMetre};
  }catch(error){for(const mesh of meshes)mesh.dispose(false,false);throw error;}
}
