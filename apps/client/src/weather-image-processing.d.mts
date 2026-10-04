import type { ImageProcessingConfiguration } from '@babylonjs/core/Materials/imageProcessingConfiguration';
export function applyWeatherImageProcessing(config: Pick<ImageProcessingConfiguration,'exposure'|'contrast'>,
 daylight: number, grade: {exposure: number; contrast: number} | null): void;
