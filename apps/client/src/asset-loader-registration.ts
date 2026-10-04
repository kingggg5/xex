import {registerBuiltInLoaders} from '@babylonjs/loaders/dynamic';
let registered=false;
/** One registration per module graph; loader bodies/extensions are imported only on demand. */
export function ensureAssetLoaders():void {
	if(registered)return;
	registerBuiltInLoaders();registered=true;
}
