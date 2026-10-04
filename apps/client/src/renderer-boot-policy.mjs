export const WEBGPU_FEATURES=Object.freeze(['texture-compression-bc','texture-compression-astc','texture-compression-etc2','float32-filterable','float32-blendable','rg11b10ufloat-renderable','texture-formats-tier1','dual-source-blending','timestamp-query']);
/** Phones retain WebGL2 until matched physical-device runs justify changing the default. */
export function rendererBootPolicy(mobile,forced=null){
	const powerPreference=mobile?'default':'high-performance';
	return {preferWebGpu:forced!=='webgl2'&&(!mobile||forced==='webgpu'),antialias:!mobile,powerPreference,
		doNotHandleContextLost:true,
		webGpuOptions:{antialias:!mobile,adaptToDeviceRatio:true,powerPreference,doNotHandleContextLost:true,setMaximumLimits:true,deviceDescriptor:{requiredFeatures:[...WEBGPU_FEATURES]}}};
}
