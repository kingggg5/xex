export interface AtlasPart { rect_xywh: number[]; pivot_xy_in_rect: number[] }
export interface SpriteGeometry { width: number; height: number; backgroundSize: string; backgroundPosition: string; pivot: { x: number; y: number } }
export function controlSpriteGeometry(part: AtlasPart, displayWidth: number, atlasWidth?: number, atlasHeight?: number): SpriteGeometry;
