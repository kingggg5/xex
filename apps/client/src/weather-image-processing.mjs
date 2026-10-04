/** Resolve the final grade before writing the shared engine configuration.
 * Alternating legacy and graded exposure dirties every scene material twice. */
export function applyWeatherImageProcessing(config, daylight, grade) {
 const exposure=grade?.exposure ?? 1+(1-daylight)*.22;
 if(config.exposure!==exposure)config.exposure=exposure;
 if(grade && config.contrast!==grade.contrast)config.contrast=grade.contrast;
}
