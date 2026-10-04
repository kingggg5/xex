/** CPU geometry release is destructive. Membership and an owner certificate are both required. */
export function geometryReleaseBlocker(mesh,approved){
	if(!approved)return 'not-audited';
	if(mesh?.metadata?.cpuCacheRelease!=='render-only-static')return 'missing-owner-certificate';
	if(mesh.isDisposed?.())return 'disposed';
	if(!mesh.geometry?.isReady?.())return 'not-prepared';
	if(mesh.isPickable)return 'picking';
	if(mesh.checkCollisions || mesh.physicsBody || mesh.physicsImpostor)return 'collision-or-physics';
	if(mesh.skeleton || mesh.morphTargetManager)return 'skin-or-morph';
	if(mesh.animations?.length)return 'animated';
	if(mesh.instances?.some(instance=>instance.isPickable || instance.checkCollisions || instance.physicsBody || instance.physicsImpostor || instance.metadata?.cpuCacheRelease!=='render-only-static'))return 'unaudited-instance';
	if(mesh.hasThinInstances)return 'thin-instances-retained';
	if(mesh.metadata?.monsterId!==undefined || mesh.metadata?.actor || mesh.metadata?.interactive || mesh.metadata?.dynamicFx || mesh.metadata?.retainCpuSource)return 'dynamic-or-interactive';
	const buffers=mesh.geometry.getVertexBuffers?.();
	if(!buffers)return 'missing-buffers';
	if(Object.values(buffers).some(buffer=>buffer.isUpdatable?.()))return 'updatable-buffer';
	return null;
}

export function textureReleaseBlocker(texture){
	if(texture?.getClassName?.()!=='Texture' || texture.isRenderTarget)return 'not-file-texture';
	if(texture.metadata?.retainCpuSource || texture.metadata?.uiAtlas || texture.metadata?.dynamicFx)return 'retained-source';
	if(!texture.isReady?.())return 'not-ready';
	const source=texture._buffer;
	if(!(source instanceof ArrayBuffer) && !ArrayBuffer.isView(source))return 'not-binary-source';
	return null;
}

/** Upper bound of referenced backing stores, NOT measured RAM freed or garbage-collected bytes. */
export function referencedBytes(sources){
	const seen=new Set();let bytes=0;
	for(const source of sources){
		const backing=ArrayBuffer.isView(source)?source.buffer:source;
		if(!backing || seen.has(backing))continue;seen.add(backing);
		if(backing instanceof ArrayBuffer)bytes+=backing.byteLength;
		else if(Array.isArray(backing))bytes+=backing.length*8;
	}
	return bytes;
}
