/** Atlas windows preserve the supplied artwork's aspect ratio and measured neutral pivot. */
export function controlSpriteGeometry(part, displayWidth, atlasWidth = 1536, atlasHeight = 1024) {
	const [x, y, width, height] = part.rect_xywh;
	const scale = displayWidth / width;
	return {
		width: displayWidth, height: height * scale,
		backgroundSize: `${atlasWidth * scale}px ${atlasHeight * scale}px`,
		backgroundPosition: `${-x * scale}px ${-y * scale}px`,
		pivot: { x: part.pivot_xy_in_rect[0] * scale, y: part.pivot_xy_in_rect[1] * scale },
	};
}
