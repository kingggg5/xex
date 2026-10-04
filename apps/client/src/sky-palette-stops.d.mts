export interface SkyPaletteStop { readonly offset: number; readonly color: readonly number[] }
export function skyPaletteStops(zenith: readonly number[], horizon: readonly number[]): SkyPaletteStop[];
