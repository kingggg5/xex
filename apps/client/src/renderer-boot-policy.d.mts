import type {WebGPUEngineOptions} from '@babylonjs/core/Engines/webgpuEngine';
export const WEBGPU_FEATURES:readonly string[];
export function rendererBootPolicy(mobile:boolean,forced?:string|null):{preferWebGpu:boolean;antialias:boolean;doNotHandleContextLost:true;powerPreference:'default'|'high-performance';webGpuOptions:WebGPUEngineOptions};
