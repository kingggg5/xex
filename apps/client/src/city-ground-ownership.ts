import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { SubMesh } from '@babylonjs/core/Meshes/subMesh';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer';
import { Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { Scene } from '@babylonjs/core/scene';

export interface CityGroundBounds { minX: number; maxX: number; minZ: number; maxZ: number; }
const LEGACY_NAMES = ['env-world-base','env-meadow','env-meadow-trail','env-stream','env-bank--1','env-bank-1'];

/** Remove legacy flat art only where the authored city owns ground/water.
 * Rectangle subtraction clips boundary triangles; no coarse centroid holes,
 * texture changes, new floor, or invisible collision surfaces are introduced.
 */
export function clipLegacyGroundToCity(scene: Scene, bounds: CityGroundBounds): void {
	// The old meadow crossing is superseded by the authored city bank entries.
	for (const mesh of scene.meshes) if (/^env-bridge(?:-|$)/.test(mesh.name)) mesh.setEnabled(false);
	for (const name of LEGACY_NAMES) {
		const mesh=scene.getMeshByName(name);if (!(mesh instanceof Mesh)) continue;
		const p=mesh.getVerticesData(VertexBuffer.PositionKind),indices=mesh.getIndices();if(!p||!indices)continue;
		const kinds=mesh.getVerticesDataKinds().filter(kind=>mesh.getVerticesData(kind));
		const sizes=kinds.map(kind=>mesh.getVertexBuffer(kind)!.getSize()),data=kinds.map(kind=>mesh.getVerticesData(kind)!);
		const rows:number[][]=Array.from({length:p.length/3},(_,vertex)=>data.flatMap((values,index)=>Array.from(values.slice(vertex*sizes[index],(vertex+1)*sizes[index]))));
		mesh.computeWorldMatrix(true);const matrix=mesh.getWorldMatrix(),positionOffset=sizes.slice(0,kinds.indexOf(VertexBuffer.PositionKind)).reduce((a,b)=>a+b,0);
		const point=(row:number[])=>Vector3.TransformCoordinates(new Vector3(row[positionOffset],row[positionOffset+1],row[positionOffset+2]),matrix);
		const planes=[{axis:'x',limit:bounds.minX,sign:1},{axis:'x',limit:bounds.maxX,sign:-1},{axis:'z',limit:bounds.minZ,sign:1},{axis:'z',limit:bounds.maxZ,sign:-1}] as const;
		const output:number[][]=[],faces:number[]=[];
		for(let index=0;index<indices.length;index+=3){
			let remaining=[rows[indices[index]],rows[indices[index+1]],rows[indices[index+2]]];
			for(const plane of planes){
				if(!remaining.length)break;
				const inside:number[][]=[],outside:number[][]=[];
				for(let i=0;i<remaining.length;i++){
					const a=remaining[i],b=remaining[(i+1)%remaining.length],da=(point(a)[plane.axis]-plane.limit)*plane.sign,db=(point(b)[plane.axis]-plane.limit)*plane.sign;
					if(da>=0)inside.push(a);else outside.push(a);
					if((da>=0)!==(db>=0)){const t=da/(da-db),cut=a.map((value,j)=>value+(b[j]-value)*t);inside.push(cut);outside.push(cut);}
				}
				if(outside.length>=3){const base=output.length;output.push(...outside);for(let i=1;i<outside.length-1;i++)faces.push(base,base+i,base+i+1);}
				remaining=inside;
			}
		}
		if (!faces.length) { mesh.setEnabled(false); continue; }
		let offset=0;
		for(let index=0;index<kinds.length;index++){
			const stride=sizes[index],values=output.flatMap(row=>row.slice(offset,offset+stride));mesh.setVerticesData(kinds[index],values,false,stride);offset+=stride;
		}
		mesh.setIndices(faces);mesh.releaseSubMeshes();new SubMesh(0,0,output.length,0,faces.length,mesh);
		mesh.refreshBoundingInfo();
	}
}
