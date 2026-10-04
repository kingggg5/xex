import{Vector3}from'@babylonjs/core/Maths/math.vector.js';
import{PBRMaterial}from'@babylonjs/core/Materials/PBR/pbrMaterial.js';
import{Texture}from'@babylonjs/core/Materials/Textures/texture.js';
export function createOwnedWaterFloorMaterial(name,scene,owned){const material=new PBRMaterial(name,scene);owned.push(material);return material;}
export function adoptWaterBankGround(scene,bank,borrowed){
 const land=scene.getMaterialByName('env-shared-world-grass');
 if(!(land instanceof PBRMaterial)||!(land.albedoTexture instanceof Texture))throw new Error('Rev3 bank requires the existing shared ground albedo');
 bank.albedoTexture=land.albedoTexture;borrowed.add(land.albedoTexture);bank.albedoColor=land.albedoColor.clone();bank.roughness=land.roughness;
 bank.bumpTexture.coordinatesIndex=1;bank.bumpTexture.level=.35;return land;
}
/** Preserve bank-normal UVs while the albedo follows the same metric world map as land. */
export function projectWaterBankUV(mesh){
 const positions=mesh.getVerticesData('position'),uv=mesh.getVerticesData('uv');
 if(!positions||!uv)throw new Error('Rev3 bank requires its original position/UV data');
 mesh.makeGeometryUnique();mesh.computeWorldMatrix(true);const world=mesh.getWorldMatrix(),worldUV=[];
 for(let k=0;k<positions.length;k+=3){const point=Vector3.TransformCoordinates(Vector3.FromArray(positions,k),world);worldUV.push(point.x/6,point.z/6);}
 mesh.setVerticesData('uv2',Array.from(uv),false,2);mesh.setVerticesData('uv',worldUV,false,2);
}
/** The terrain texture belongs to the world, even when a review bank borrows it. */
export function releaseWaterFloorAssets(support,materials,textures,borrowed){
 for(const material of materials)for(const slot of ['albedoTexture','bumpTexture','metallicTexture','ambientTexture','opacityTexture','emissiveTexture','reflectionTexture'])if(borrowed.has(material[slot]))material[slot]=null;
 if(support?.textures)support.textures=support.textures.filter(texture=>!borrowed.has(texture));
 support?.dispose();
 for(const material of materials)material.dispose(false,false);
 for(const texture of textures)if(!borrowed.has(texture))texture.dispose();
 borrowed.clear();
}
